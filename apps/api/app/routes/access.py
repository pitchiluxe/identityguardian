"""Phase 3: effective access and lineage."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..domain.access import Bounds, effective_access, principals_for
from ..scope import envelope, scoped
from .twin import ENV, resolve, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


def bounds(depth, paths):
    return Bounds(depth=depth, paths=paths)


def evidence(paths):
    return [eid for p in paths for eid in p["evidence_ids"]]


@router.get(ENV + "/identities/{node_id}/access")
def identity_access(
    org: UUID,
    env: UUID,
    node_id: str,
    request: Request,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
    depth: int = Query(8, ge=1, le=12),
    max_paths: int = Query(100, ge=1, le=500),
):
    with scoped(request, org, env, "access:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        node = resolve(snap, node_id)
        if node.kind != "identity":
            raise HTTPException(422, "Effective access is calculated for identities")
        result = effective_access(snap, node.id, scope.conn, bounds(depth, max_paths))
        return envelope(
            scope,
            result,
            snapshot=snap,
            completeness="complete" if result["complete"] else "partial",
            evidence_ids=[e for entry in result["entries"] for e in evidence(entry["paths"])],
        )


@router.get(ENV + "/resources/{node_id}/principals")
def resource_principals(
    org: UUID,
    env: UUID,
    node_id: str,
    request: Request,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
    depth: int = Query(8, ge=1, le=12),
    max_paths: int = Query(100, ge=1, le=500),
):
    with scoped(request, org, env, "access:read") as scope:
        snap = snapshot_for(scope, effective_at, known_at)
        node = resolve(snap, node_id)
        if node.kind not in {"resource", "application", "tool", "permission"}:
            raise HTTPException(422, "Choose a resource, application, tool or permission")
        result = principals_for(snap, node.id, bounds(depth, max_paths))
        return envelope(
            scope,
            result,
            snapshot=snap,
            completeness="complete" if result["complete"] else "partial",
            evidence_ids=[e for p in result["principals"] for e in evidence(p["paths"])],
        )
