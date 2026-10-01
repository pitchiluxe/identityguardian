"""Phase 4: rule-based findings (privilege creep, dormant, leaver, unused) and identity timeline."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..domain.exposure import attack_paths
from ..domain.findings import RULES_VERSION, all_findings, timeline
from ..scope import envelope, scoped
from .twin import ENV, resolve, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


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
