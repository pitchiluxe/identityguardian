"""Phase 2: environments, synthetic sandbox seeding, ingestion and twin exploration."""

import base64
import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require_session
from ..domain import graph
from ..domain.ingest import run_sync, seed_sandbox
from ..scope import envelope, scoped

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])
ENV = "/environments/{env}"


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant: Literal["standard", "alternate_path"] = "standard"
    confirm_synthetic: Literal[True]


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["incremental", "full"] = "incremental"


def times(effective_at, known_at):
    try:
        return graph.utc(effective_at), graph.utc(known_at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def snapshot_for(scope, effective_at=None, known_at=None):
    t, k = times(effective_at, known_at)
    return graph.load(scope.conn, scope.env_id, t, k)


def resolve(snapshot, node_id: str):
    node = snapshot.nodes.get(node_id) or snapshot.by_external(node_id)
    if not node:
        raise HTTPException(404, "Node not found in this environment at the requested time")
    return node


@router.get("/environments")
def environments(org: UUID, request: Request):
    with scoped(request, org, None, "overview:read") as scope:
        rows = scope.conn.execute(
            "SELECT e.id, e.name, e.kind, "
            "(SELECT max(finished_at) FROM sync_runs s WHERE s.environment_id=e.id "
            " AND s.status IN ('SUCCEEDED','PARTIAL')) AS last_sync "
            "FROM environments e WHERE e.lab_learner IS NULL OR e.lab_learner=%s OR %s "
            "ORDER BY e.lab_learner NULLS FIRST, e.kind, e.name",
            (scope.user_id, "lab:manage" in scope.caps),
        ).fetchall()
        return envelope(scope, rows)


@router.post(ENV + "/sandbox/seed")
def seed(org: UUID, env: UUID, body: SeedRequest, request: Request):
    with scoped(request, org, env, "sandbox:seed") as scope:
        try:
            changed = seed_sandbox(scope.conn, scope.environment, body.variant == "alternate_path")
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from None
        scope.audit(
            "sandbox.seeded",
            env,
            f"Loaded SYNTHETIC Contoso fixture ({body.variant})",
            after={"changed_objects": changed, "variant": body.variant},
        )
        return envelope(
            scope, {"changed_objects": changed, "variant": body.variant, "label": "SYNTHETIC"}
        )


@router.post(ENV + "/connectors/sandbox/sync")
def sync(org: UUID, env: UUID, body: SyncRequest, request: Request):
    with scoped(request, org, env, "connector:sync") as scope:
        scope.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("sync:" + str(env),))
        run = run_sync(scope.conn, scope.environment, scope.user_id, full=body.mode == "full")
        scope.audit(
            "connector.synced",
            run["id"],
            f"Sandbox {body.mode} sync",
            after={
                k: run[k]
                for k in (
                    "status",
                    "coverage",
                    "observed",
                    "unchanged",
                    "created",
                    "updated",
                    "tombstoned",
                    "rejected",
                )
            },
        )
        return envelope(scope, run)


@router.get(ENV + "/sync-runs")
def sync_runs(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "identity:read") as scope:
        rows = scope.conn.execute(
            "SELECT s.*, c.name AS connector FROM sync_runs s JOIN connectors c ON c.id=s.connector_id "
            "WHERE s.environment_id=%s ORDER BY s.started_at DESC LIMIT 20",
            (env,),
        ).fetchall()
        return envelope(scope, rows)


@router.get(ENV + "/summary")
def summary(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "identity:read") as scope:
        snap = snapshot_for(scope)
        counts: dict = {}
        for node in snap.nodes.values():
            key = node.kind if node.kind != "identity" else f"identity:{node.subtype}"
            counts[key] = counts.get(key, 0) + 1
        identities = [n for n in snap.nodes.values() if n.kind == "identity"]
        return envelope(
            scope,
            {
                "counts": counts,
                "identities": len(identities),
                "relationships": len(snap.edges),
                "terminated_identities": sum(1 for n in identities if n.status == "terminated"),
            },
            snapshot=snap,
        )


def encode_cursor(name, node_id):
    return base64.urlsafe_b64encode(json.dumps([name, str(node_id)]).encode()).decode()


@router.get(ENV + "/identities")
def identities(
    org: UUID,
    env: UUID,
    request: Request,
    kind: str = Query("identity", pattern="^[a-z_]+$"),
    subtype: str | None = Query(None, pattern="^[a-z_]+$"),
    q: str | None = Query(None, max_length=80),
    cursor: str | None = Query(None, max_length=400),
    limit: int = Query(50, ge=1, le=100),
):
    with scoped(request, org, env, "identity:read") as scope:
        after = ("", "00000000-0000-0000-0000-000000000000")
        if cursor:
            try:
                after = tuple(json.loads(base64.urlsafe_b64decode(cursor)))
                UUID(after[1])
            except (ValueError, TypeError, IndexError):
                raise HTTPException(422, "Invalid cursor") from None
        rows = scope.conn.execute(
            "SELECT n.id, n.external_id, n.kind, n.subtype, r.name, r.status, r.attributes "
            "FROM twin_nodes n JOIN node_revisions r ON r.node_id=n.id AND r.recorded_to IS NULL "
            "AND r.valid_from<=now() AND (r.valid_to IS NULL OR r.valid_to>now()) "
            "WHERE n.environment_id=%s AND n.kind=%s AND (%s::text IS NULL OR n.subtype=%s) "
            "AND (%s::text IS NULL OR r.name ILIKE '%%' || %s || '%%') "
            "AND (r.name, n.id) > (%s, %s::uuid) ORDER BY r.name, n.id LIMIT %s",
            (env, kind, subtype, subtype, q, q, after[0], after[1], limit + 1),
        ).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        return envelope(
            scope,
            rows,
            next_cursor=encode_cursor(rows[-1]["name"], rows[-1]["id"]) if more else None,
        )


@router.get(ENV + "/nodes/{node_id}")
def profile(
    org: UUID,
    env: UUID,
    node_id: str,
    request: Request,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
):
    with scoped(request, org, env, "identity:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        node = resolve(snap, node_id)
        history = scope.conn.execute(
            "SELECT name, status, attributes, valid_from, valid_to, recorded_from, recorded_to, "
            "observation_id FROM node_revisions WHERE node_id=%s ORDER BY recorded_from, valid_from",
            (node.id,),
        ).fetchall()
        related = []
        for edge in snap.out[node.id] + snap.inc[node.id]:
            other = snap.nodes[edge.dst if edge.src == node.id else edge.src]
            related.append(
                dict(
                    graph.edge_json(edge),
                    direction="out" if edge.src == node.id else "in",
                    other=graph.node_json(other),
                )
            )
        related.sort(key=lambda r: (r["classification"], r["type"], r["other"]["name"]))
        return envelope(
            scope,
            dict(node=graph.node_json(node), relationships=related, history=history),
            snapshot=snap,
            evidence_ids=[r["evidence_id"] for r in related],
        )


@router.get(ENV + "/graph/neighbors")
def neighbors(
    org: UUID,
    env: UUID,
    request: Request,
    node: str = Query(..., max_length=80),
    depth: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(150, ge=10, le=400),
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
):
    with scoped(request, org, env, "graph:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        start = resolve(snap, node)
        result = graph.neighborhood(snap, start.id, depth, max_nodes)
        return envelope(
            scope,
            result,
            snapshot=snap,
            completeness="complete" if result["complete"] else "partial",
        )


@router.get(ENV + "/applications")
def applications(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "identity:read") as scope:
        snap = snapshot_for(scope)
        rows = []
        for node in snap.nodes.values():
            if node.kind not in {"application", "resource"}:
                continue
            grants = [e for e in snap.inc[node.id] if e.classification == "grant"]
            rows.append(
                dict(
                    graph.node_json(node),
                    direct_grants=len(grants),
                    depends_on=[
                        snap.nodes[e.dst].name
                        for e in snap.out[node.id]
                        if e.type == "RESOURCE_DEPENDS_ON"
                    ],
                )
            )
        rows.sort(key=lambda r: (r["kind"], r["name"]))
        return envelope(scope, rows, snapshot=snap)


@router.get(ENV + "/capabilities")
def environment_capabilities(org: UUID, env: UUID, request: Request):
    """Effective capabilities in this environment (learners gain analysis rights only in their lab)."""
    with scoped(request, org, env, "overview:read") as scope:
        return envelope(scope, sorted(scope.caps))


class EnvironmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=80)


@router.post("/environments", status_code=201)
def create_environment(org: UUID, body: EnvironmentRequest, request: Request):
    """SANDBOX environments isolate connector and simulation work. PRODUCTION is never created here."""
    with scoped(request, org, None, "connector:manage") as scope:
        row = scope.conn.execute(
            "INSERT INTO environments(id,organization_id,name,kind) VALUES(%s,%s,%s,'SANDBOX') RETURNING *",
            (uuid4(), org, body.name),
        ).fetchone()
        scope.audit("environment.created", row["id"], body.name, after=dict(kind="SANDBOX"))
        return envelope(scope, row)
