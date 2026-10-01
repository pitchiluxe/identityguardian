"""Phase 12: Time Machine — bitemporal reconstruction and checksummed snapshots."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict

from ..domain.graph import load
from ..domain.history import checksum, coverage, reconstruct
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from .twin import ENV, times

router = APIRouter(prefix="/api/v1/organizations/{org}")


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_at: AwareDatetime
    known_at: AwareDatetime | None = None


@router.get(ENV + "/history/identities/{node_id}")
def identity_history(
    org: UUID,
    env: UUID,
    node_id: str,
    request: Request,
    effective_at: datetime,
    known_at: datetime | None = None,
):
    with scoped(request, org, env, "history:read") as scope:
        t, k = times(effective_at, known_at)
        if k > datetime.now(timezone.utc):
            raise HTTPException(422, "Knowledge time cannot be in the future")
        try:
            result = reconstruct(scope.conn, scope.env_id, node_id, t, k)
        except KeyError:
            raise HTTPException(404, "No evidence of this identity in this environment") from None
        return envelope(scope, result)


@router.post(ENV + "/history/snapshots", status_code=201)
def create_snapshot(org: UUID, env: UUID, body: SnapshotRequest, request: Request):
    with scoped(request, org, env, "history:read") as scope:
        t, k = times(body.effective_at, body.known_at)
        if k > datetime.now(timezone.utc):
            raise HTTPException(422, "Knowledge time cannot be in the future")
        snap = load(scope.conn, scope.env_id, t, k)
        row = scope.conn.execute(
            "INSERT INTO historical_snapshots(id,organization_id,environment_id,effective_at,known_at,"
            "graph_version,node_count,edge_count,checksum,coverage,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                env,
                t,
                k,
                snap.version,
                len(snap.nodes),
                len(snap.edges),
                checksum(snap),
                Jsonb(coverage(scope.conn, scope.env_id, t, k)),
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "history.snapshot_created",
            row["id"],
            "Checksummed historical snapshot",
            after=dict(
                effective_at=t.isoformat(), known_at=k.isoformat(), checksum=row["checksum"]
            ),
        )
        return envelope(scope, row)


@router.get(ENV + "/history/snapshots")
def snapshots(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "history:read") as scope:
        return envelope(
            scope,
            scope.conn.execute(
                "SELECT id, effective_at, known_at, graph_version, node_count, edge_count, checksum, created_at "
                "FROM historical_snapshots WHERE environment_id=%s ORDER BY created_at DESC LIMIT 50",
                (env,),
            ).fetchall(),
        )


@router.get(ENV + "/history/snapshots/{snapshot_id}/verify")
def verify_snapshot(org: UUID, env: UUID, snapshot_id: UUID, request: Request):
    with scoped(request, org, env, "history:read") as scope:
        row = scope.conn.execute(
            "SELECT * FROM historical_snapshots WHERE id=%s AND environment_id=%s",
            (snapshot_id, env),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Snapshot not found")
        replay = load(scope.conn, scope.env_id, row["effective_at"], row["known_at"])
        recomputed = checksum(replay)
        return envelope(
            scope,
            dict(
                snapshot_id=str(snapshot_id),
                stored=row["checksum"],
                recomputed=recomputed,
                result="MATCH" if recomputed == row["checksum"] else "MISMATCH",
                statement="Replay from immutable evidence reproduces the snapshot."
                if recomputed == row["checksum"]
                else "Replay differs: evidence or history was altered after the snapshot.",
            ),
        )
