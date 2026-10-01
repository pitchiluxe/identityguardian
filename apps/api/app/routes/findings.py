"""Phase 4: rule-based findings (privilege creep, dormant, leaver, unused) and identity timeline."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import require_session
from ..domain.access import effective_access
from ..domain.agents import AGENT_RULES, activity, agent_profile
from ..domain.exposure import attack_paths
from ..domain.findings import RULES_VERSION, all_findings, is_privileged, machine_context, timeline
from ..domain.graph import node_json
from ..scope import envelope, scoped
from .twin import ENV, resolve, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])


@router.get(ENV + "/findings")
def findings(
    org: UUID,
    env: UUID,
    request: Request,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
    rule: str | None = Query(None, pattern="^[A-Z_]+$"),
    identity: str | None = Query(None, max_length=80),
):
    with scoped(request, org, env, "findings:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        items = all_findings(snap, scope.conn, scope.env_id)
        if rule:
            items = [f for f in items if f["rule"] == rule]
        if identity:
            node = resolve(snap, identity)
            items = [f for f in items if f["identity"]["id"] == node.id]
        counts: dict = {}
        for f in items:
            counts[f["rule"]] = counts.get(f["rule"], 0) + 1
        return envelope(
            scope,
            items,
            snapshot=snap,
            rules_version=RULES_VERSION,
            counts=counts,
            evidence_ids=[e for f in items for e in f["evidence_ids"]],
        )


@router.get(ENV + "/identities/{node_id}/timeline")
def identity_timeline(
    org: UUID, env: UUID, node_id: str, request: Request, known_at: datetime | None = None
):
    with scoped(request, org, env, "history:read") as scope:
        snap = snapshot_for(scope, None, known_at)
        node = resolve(snap, node_id)
        if node.kind != "identity":
            raise HTTPException(422, "Timelines are available for identities")
        return envelope(scope, timeline(snap, scope.conn, node.id), snapshot=snap)


@router.get(ENV + "/attack-paths")
def exposure_paths(
    org: UUID,
    env: UUID,
    request: Request,
    source: str | None = Query(None, max_length=80),
    destination: str | None = Query(None, max_length=80),
    max_steps: int = Query(2, ge=1, le=3),
    max_paths: int = Query(100, ge=1, le=300),
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
):
    with scoped(request, org, env, "findings:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        start = resolve(snap, source).id if source else None
        target = resolve(snap, destination).id if destination else None
        result = attack_paths(snap, scope.conn, start, target, max_steps, max_paths)
        return envelope(
            scope,
            result,
            snapshot=snap,
            completeness="complete" if result["complete"] else "partial",
            evidence_ids=[e for p in result["paths"] for e in p["evidence_ids"]],
        )


@router.get(ENV + "/machines")
def machines(
    org: UUID,
    env: UUID,
    request: Request,
    subtype: str = Query("machine", pattern="^(machine|agent)$"),
):
    with scoped(request, org, env, "identity:read") as scope:
        snap = snapshot_for(scope)
        findings_by_identity: dict = {}
        if "findings:read" in scope.caps:
            for f in all_findings(snap, scope.conn, scope.env_id):
                findings_by_identity.setdefault(f["identity"]["id"], []).append(
                    dict(key=f["key"], rule=f["rule"], severity=f["severity"], title=f["title"])
                )
        rows = []
        for node in sorted(snap.nodes.values(), key=lambda n: n.name):
            if node.kind != "identity" or node.subtype != subtype:
                continue
            _, owners, credentials, dependents, direct = machine_context(snap, node.id)
            access = effective_access(snap, node.id, scope.conn)
            last = scope.conn.execute(
                "SELECT max(occurred_at) AS last FROM usage_events WHERE identity_node=%s",
                (node.id,),
            ).fetchone()["last"]
            rows.append(
                dict(
                    identity=node_json(node),
                    owners=[node_json(o) for o in owners],
                    credentials=[
                        dict(node_json(c), relationship_evidence=e.observation_id)
                        for c, e in credentials
                    ],
                    dependents=[node_json(d) for d in dependents],
                    direct_access=[node_json(d) for d in direct],
                    entitlements=len(access["entries"]),
                    privileged=[
                        (e["resource"] or e["permission"])["name"]
                        for e in access["entries"]
                        if is_privileged(e)
                    ],
                    tools=[
                        node_json(snap.nodes[e.dst])
                        for e in snap.out[node.id]
                        if e.type == "AI_AGENT_USES_TOOL"
                    ],
                    last_observed_use=last,
                    findings=findings_by_identity.get(node.id, []),
                )
            )
        return envelope(scope, rows, snapshot=snap)


@router.get(ENV + "/agents")
def agents(
    org: UUID,
    env: UUID,
    request: Request,
    tool: str | None = Query(None, max_length=80),
    data_classification: str | None = Query(None, max_length=80),
    effective_at: datetime | None = None,
):
    with scoped(request, org, env, "identity:read") as scope:
        snap = snapshot_for(scope, effective_at)
        rows = []
        for node in sorted(snap.nodes.values(), key=lambda n: n.name):
            if node.kind != "identity" or node.subtype != "agent":
                continue
            profile = agent_profile(snap, scope.conn, node.id)
            profile.pop("_access")
            if tool and tool not in profile["effective"]["tools"]:
                continue
            if data_classification and data_classification not in profile["effective"]["data"]:
                continue
            rows.append(profile)
        return envelope(scope, rows, snapshot=snap, rules_version=AGENT_RULES)


@router.get(ENV + "/agents/{node_id}/activity")
def agent_activity(
    org: UUID,
    env: UUID,
    node_id: str,
    request: Request,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
):
    with scoped(request, org, env, "history:read") as scope:
        snap = snapshot_for(scope)
        node = resolve(snap, node_id)
        if node.subtype != "agent":
            raise HTTPException(422, "Activity queries are for registered agents")
        try:
            return envelope(scope, activity(scope.conn, node.id, start, end))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
