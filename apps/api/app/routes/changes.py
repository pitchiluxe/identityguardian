"""Phases 7–8: what-if simulations and the change-request workflow."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..domain import changes
from ..domain.graph import node_json
from ..domain.simulate import APPROVAL_TTL, POLICY_VERSION, simulate
from ..domain.types import validate
from ..jsonutil import dumps
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from ..security import digest
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_relationship", "add_relationship"]
    relationship: str | None = Field(None, max_length=120)
    type: str | None = Field(None, max_length=60)
    src: str | None = Field(None, max_length=120)
    dst: str | None = Field(None, max_length=120)
    expires_at: datetime | None = None


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[Operation] | None = Field(None, max_length=10)
    change_request_id: UUID | None = None
    expected_version: int | None = Field(None, ge=1)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["remove_relationship", "add_relationship"]
    relationship: str | None = Field(None, max_length=120)
    type: Literal["USER_MEMBER_OF_GROUP", "USER_HAS_ROLE"] | None = None
    src: str | None = Field(None, max_length=120)
    dst: str | None = Field(None, max_length=120)
    justification: str = Field(min_length=8, max_length=2000)
    idempotency_key: UUID


def operations_for(change):
    target = change["target"]
    if change["kind"] == "remove_relationship":
        return [dict(op="remove_relationship", relationship=target["relationship_id"])]
    params = change["parameters"]
    return [
        dict(
            op="add_relationship",
            type=target["type"],
            src=target["src"]["external_id"],
            dst=target["dst"]["external_id"],
            expires_at=params.get("expires_at"),
        )
    ]


def binding(org, env, change, operations, source_versions, graph_version, expires_at):
    return digest(
        dumps(
            dict(
                org=str(org),
                env=str(env),
                change_request=str(change["id"]) if change else None,
                kind=change["kind"] if change else "what_if",
                target=change["target"] if change else None,
                parameters=change["parameters"] if change else {},
                operations=operations,
                source_versions=source_versions,
                graph_version=graph_version,
                policy_version=POLICY_VERSION,
                expires_at=expires_at.isoformat(),
            )
        )
    )


def load_change(scope, change_id, lock=False):
    row = scope.conn.execute(
        "SELECT * FROM change_requests WHERE id=%s AND environment_id=%s"
        + (" FOR UPDATE" if lock else ""),
        (change_id, scope.env_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Change request not found")
    return row


@router.post(ENV + "/simulations", status_code=201)
def create_simulation(org: UUID, env: UUID, body: SimulationRequest, request: Request):
    if bool(body.operations) == bool(body.change_request_id):
        raise HTTPException(422, "Provide either operations or a change_request_id")
    with scoped(request, org, env, "change:simulate") as scope:
        change = None
        if body.change_request_id:
            change = load_change(scope, body.change_request_id, lock=True)
            if body.expected_version is not None and change["version"] != body.expected_version:
                raise HTTPException(409, "Request changed; refresh and review again")
            if change["status"] not in {"DRAFT", "SIMULATED", "STALE", "IN_REVIEW"}:
                raise HTTPException(409, f"A {change['status']} request cannot be re-simulated")
            ops = operations_for(change)
        else:
            ops = [o.model_dump(exclude_none=True, mode="json") for o in body.operations]
        snap = snapshot_for(scope)
        try:
            result, source_versions = simulate(scope.conn, snap, scope.env_id, ops)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        expires_at = datetime.now(timezone.utc) + APPROVAL_TTL
        bound = binding(org, env, change, ops, source_versions, snap.version, expires_at)
        sim = scope.conn.execute(
            "INSERT INTO simulations(id,organization_id,environment_id,change_request_id,operations,"
            "base_graph_version,source_versions,policy_version,parameters,result,digest,created_by,"
            "expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                env,
                change["id"] if change else None,
                Jsonb(ops),
                snap.version,
                Jsonb(source_versions),
                POLICY_VERSION,
                Jsonb({}),
                Jsonb(result),
                bound,
                scope.user_id,
                expires_at,
            ),
        ).fetchone()
        if change:
            moved = changes.transition(scope.conn, change, "SIMULATED")
            scope.conn.execute(
                "UPDATE change_requests SET simulation_id=%s, digest=%s WHERE id=%s",
                (sim["id"], bound, change["id"]),
            )
            scope.audit(
                "change.simulated",
                change["id"],
                change["justification"],
                before=dict(status=change["status"]),
                after=dict(status=moved["status"], simulation=str(sim["id"]), digest=bound),
            )
        return envelope(scope, sim, snapshot=snap)


@router.get(ENV + "/simulations/{simulation_id}")
def get_simulation(org: UUID, env: UUID, simulation_id: UUID, request: Request):
    with scoped(request, org, env, "access:read") as scope:
        row = scope.conn.execute(
            "SELECT * FROM simulations WHERE id=%s AND environment_id=%s", (simulation_id, env)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Simulation not found")
        return envelope(scope, row)


@router.post(ENV + "/change-requests", status_code=201)
def propose(org: UUID, env: UUID, body: ProposalRequest, request: Request):
    with scoped(request, org, env, "change:propose") as scope:
        snap = snapshot_for(scope)
        if body.kind == "remove_relationship":
            if not body.relationship:
                raise HTTPException(422, "relationship is required")
            row = scope.conn.execute(
                "SELECT id FROM relationships WHERE environment_id=%s AND (id::text=%s OR external_id=%s)",
                (env, body.relationship, body.relationship),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Relationship not found")
            target = changes.relationship_target(snap, scope.conn, row["id"])
        else:
            src, dst = snap.by_external(body.src or ""), snap.by_external(body.dst or "")
            if not src or not dst or not body.type:
                raise HTTPException(422, "type, src and dst are required")
            try:
                validate(body.type, src.kind, dst.kind)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            target = dict(type=body.type, src=node_json(src), dst=node_json(dst))
        row = changes.create(
            scope.conn,
            scope,
            body.kind,
            target,
            body.justification,
            "manual",
            idempotency_key=body.idempotency_key,
        )
        return envelope(scope, row)


@router.get(ENV + "/change-requests/{change_id}")
def get_change(org: UUID, env: UUID, change_id: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        change = load_change(scope, change_id)
        sim = None
        if change["simulation_id"]:
            sim = scope.conn.execute(
                "SELECT * FROM simulations WHERE id=%s", (change["simulation_id"],)
            ).fetchone()
        history = scope.conn.execute(
            "SELECT action, actor_id, created_at, before_state, after_state, justification, result "
            "FROM audit_events WHERE target=%s ORDER BY created_at",
            (str(change_id),),
        ).fetchall()
        return envelope(scope, dict(change=change, simulation=sim, history=history))
