"""Phases 7–8: what-if simulations and the change-request workflow."""

import secrets
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
from ..security import capabilities, digest, require_recent_mfa
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_relationship", "add_relationship", "rotate_credential"]
    relationship: str | None = Field(None, max_length=120)
    credential: str | None = Field(None, max_length=120)
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
    kind: Literal["remove_relationship", "add_relationship", "rotate_credential"]
    relationship: str | None = Field(None, max_length=120)
    credential: str | None = Field(None, max_length=120)
    type: Literal["USER_MEMBER_OF_GROUP", "USER_HAS_ROLE", "USER_OWNS_SERVICE_ACCOUNT"] | None = (
        None
    )
    src: str | None = Field(None, max_length=120)
    dst: str | None = Field(None, max_length=120)
    justification: str = Field(min_length=8, max_length=2000)
    idempotency_key: UUID


def operations_for(change):
    target = change["target"]
    if change["kind"] == "remove_relationship":
        return [dict(op="remove_relationship", relationship=target["relationship_id"])]
    if change["kind"] == "rotate_credential":
        return [dict(op="rotate_credential", credential=target["credential"]["external_id"])]
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
        elif body.kind == "rotate_credential":
            credential = snap.by_external(body.credential or "")
            if not credential or credential.kind != "credential":
                raise HTTPException(422, "Choose a credential")
            holder = next(
                (snap.nodes[e.src] for e in snap.inc[credential.id] if e.type == "HAS_CREDENTIAL"),
                None,
            )
            target = dict(
                type="CREDENTIAL_ROTATION",
                credential=node_json(credential),
                src=node_json(holder) if holder else node_json(credential),
                dst=node_json(credential),
            )
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


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(min_length=16, max_length=64)
    decision: Literal["APPROVE", "REJECT"]
    justification: str = Field(min_length=8, max_length=2000)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(min_length=16, max_length=64)


class JitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(max_length=120)
    group: str = Field(max_length=120)
    duration_minutes: int = Field(ge=15, le=480)
    justification: str = Field(min_length=8, max_length=2000)
    idempotency_key: UUID


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["remove_relationship", "add_relationship"]
    mode: Literal["fail_before_write", "timeout_after_write"]
    remaining: int = Field(1, ge=0, le=5)


def require_mfa(scope):
    try:
        require_recent_mfa(scope.user["amr"], scope.user["auth_time"])
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from None


def capability_for(change, action):
    jit = change["kind"] == "jit_grant"
    return {
        "approve": "jit:approve" if jit else "change:approve",
        "execute": "jit:execute" if jit else "change:execute",
    }[action]


def simulation_current(scope, change):
    """The bound simulation if unexpired and its target versions are current; False if stale."""
    sim = scope.conn.execute(
        "SELECT * FROM simulations WHERE id=%s", (change["simulation_id"],)
    ).fetchone()
    if not sim or sim["expires_at"] <= datetime.now(timezone.utc):
        return None
    return sim if changes.versions_current(scope.conn, sim["source_versions"]) else False


@router.post(ENV + "/change-requests/{change_id}/submit")
def submit(org: UUID, env: UUID, change_id: UUID, body: Transition, request: Request):
    with scoped(request, org, env, "change:propose") as scope:
        change = load_change(scope, change_id, lock=True)
        if change["status"] != "SIMULATED":
            raise HTTPException(409, "Only simulated requests can be submitted for approval")
        if not simulation_current(scope, change):
            raise HTTPException(409, "Simulation expired or target changed; re-simulate first")
        moved = changes.transition(scope.conn, change, "IN_REVIEW", body.expected_version)
        scope.audit(
            "change.submitted",
            change_id,
            change["justification"],
            before=dict(status=change["status"]),
            after=dict(status="IN_REVIEW", digest=change["digest"]),
        )
        return envelope(scope, moved)


@router.post(ENV + "/change-requests/{change_id}/decision")
def decide_change(org: UUID, env: UUID, change_id: UUID, body: ApprovalRequest, request: Request):
    with scoped(request, org, env, "overview:read") as scope:
        change = load_change(scope, change_id, lock=True)
        if capability_for(change, "approve") not in capabilities(scope.member["roles"]):
            raise HTTPException(403, "Your role does not allow this action")
        require_mfa(scope)
        if change["requester_id"] == scope.user_id:
            raise HTTPException(403, "Approval must be independent of the requester")
        if change["status"] != "IN_REVIEW":
            raise HTTPException(409, "Request is not awaiting approval")
        if not secrets.compare_digest(change["digest"] or "", body.digest):
            raise HTTPException(409, "Proposal digest changed; review the current simulation")
        sim = simulation_current(scope, change)
        if sim is False or sim is None:
            status = "STALE" if sim is False else "EXPIRED"
            reason = (
                "Target changed since simulation"
                if sim is False
                else "Simulation expired before approval"
            )
            changes.transition(scope.conn, change, status)
            scope.audit(f"change.{status.lower()}", change_id, reason, result="refused")
            # Commit the state change, then report the refusal.
            scope.conn.commit()
            raise HTTPException(409, f"{reason}; request marked {status}")
        approval = scope.conn.execute(
            "INSERT INTO approvals(id,organization_id,change_request_id,approver_id,decision,digest,"
            "justification,auth_time,amr,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                change_id,
                scope.user_id,
                body.decision,
                body.digest,
                body.justification,
                scope.user["auth_time"],
                scope.user["amr"],
                datetime.now(timezone.utc) + APPROVAL_TTL,
            ),
        ).fetchone()
        status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        moved = changes.transition(scope.conn, change, status)
        scope.audit(
            f"change.{status.lower()}",
            change_id,
            body.justification,
            before=dict(status="IN_REVIEW"),
            after=dict(status=status, digest=body.digest),
            approval=approval["id"],
        )
        return envelope(scope, dict(change=moved, approval=approval))


@router.post(ENV + "/change-requests/{change_id}/execute", status_code=202)
def execute(org: UUID, env: UUID, change_id: UUID, body: ExecuteRequest, request: Request):
    with scoped(request, org, env, "overview:read") as scope:
        if scope.environment["kind"] == "PRODUCTION":
            raise HTTPException(
                409, "Execution is limited to sandbox connectors; no production adapter is approved"
            )
        change = load_change(scope, change_id, lock=True)
        if capability_for(change, "execute") not in capabilities(scope.member["roles"]):
            raise HTTPException(403, "Your role does not allow this action")
        require_mfa(scope)
        if change["status"] != "APPROVED":
            raise HTTPException(409, "Only approved requests can be executed")
        approval = scope.conn.execute(
            "SELECT * FROM approvals WHERE change_request_id=%s AND decision='APPROVE' "
            "ORDER BY created_at DESC LIMIT 1",
            (change_id,),
        ).fetchone()
        if approval["approver_id"] == scope.user_id:
            raise HTTPException(403, "The approver cannot also execute the change")
        if (
            not secrets.compare_digest(approval["digest"], body.digest)
            or approval["digest"] != change["digest"]
        ):
            raise HTTPException(409, "Digest does not match the approved proposal")
        if approval["expires_at"] <= datetime.now(timezone.utc):
            changes.transition(scope.conn, change, "EXPIRED")
            scope.audit(
                "change.expired", change_id, "Approval expired before execution", result="refused"
            )
            scope.conn.commit()
            raise HTTPException(409, "Approval expired; request marked EXPIRED")
        moved = changes.transition(scope.conn, change, "QUEUED")
        execution = scope.conn.execute(
            "INSERT INTO executions(id,organization_id,change_request_id,approval_id,executor_id,"
            "digest,status) VALUES(%s,%s,%s,%s,%s,%s,'QUEUED') RETURNING *",
            (uuid4(), org, change_id, approval["id"], scope.user_id, body.digest),
        ).fetchone()
        scope.conn.execute(
            "INSERT INTO outbox(id,organization_id,event_type,payload) "
            "VALUES(%s,%s,'change_execution_requested',%s)",
            (
                uuid4(),
                org,
                Jsonb(dict(change_request_id=str(change_id), execution_id=str(execution["id"]))),
            ),
        )
        scope.audit(
            "change.queued",
            change_id,
            change["justification"],
            after=dict(status="QUEUED"),
            approval=approval["id"],
        )
        return envelope(
            scope,
            dict(
                change=moved,
                execution=execution,
                status_url=f"/api/v1/organizations/{org}/environments/{env}/change-requests/{change_id}",
            ),
        )


@router.post(ENV + "/change-requests/{change_id}/cancel")
def cancel(org: UUID, env: UUID, change_id: UUID, body: Transition, request: Request):
    with scoped(request, org, env, "change:propose") as scope:
        change = load_change(scope, change_id, lock=True)
        if change["requester_id"] != scope.user_id:
            raise HTTPException(403, "Only the requester can cancel this request")
        moved = changes.transition(scope.conn, change, "CANCELLED", body.expected_version)
        scope.audit(
            "change.cancelled", change_id, "Cancelled by requester", after=dict(status="CANCELLED")
        )
        return envelope(scope, moved)


@router.post(ENV + "/jit-requests", status_code=201)
def request_jit(org: UUID, env: UUID, body: JitRequest, request: Request):
    with scoped(request, org, env, "jit:request") as scope:
        snap = snapshot_for(scope)
        src, dst = snap.by_external(body.identity), snap.by_external(body.group)
        if not src or not dst or src.kind != "identity" or dst.kind != "group":
            raise HTTPException(422, "Choose an identity and a group")
        if any(e.type == "USER_MEMBER_OF_GROUP" and e.dst == dst.id for e in snap.out[src.id]):
            raise HTTPException(409, "The identity already holds this membership")
        target = dict(type="USER_MEMBER_OF_GROUP", src=node_json(src), dst=node_json(dst))
        change = changes.create(
            scope.conn,
            scope,
            "jit_grant",
            target,
            body.justification,
            "jit",
            parameters=dict(duration_minutes=body.duration_minutes),
            idempotency_key=body.idempotency_key,
        )
        if change["status"] != "DRAFT":
            return envelope(scope, change)
        ops = operations_for(change)
        result, source_versions = simulate(scope.conn, snap, scope.env_id, ops)
        expires_at = datetime.now(timezone.utc) + APPROVAL_TTL
        bound = binding(org, env, change, ops, source_versions, snap.version, expires_at)
        sim = scope.conn.execute(
            "INSERT INTO simulations(id,organization_id,environment_id,change_request_id,operations,"
            "base_graph_version,source_versions,policy_version,parameters,result,digest,created_by,"
            "expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                uuid4(),
                org,
                env,
                change["id"],
                Jsonb(ops),
                snap.version,
                Jsonb(source_versions),
                POLICY_VERSION,
                Jsonb(change["parameters"]),
                Jsonb(result),
                bound,
                scope.user_id,
                expires_at,
            ),
        ).fetchone()
        change = changes.transition(scope.conn, change, "SIMULATED")
        scope.conn.execute(
            "UPDATE change_requests SET simulation_id=%s, digest=%s WHERE id=%s",
            (sim["id"], bound, change["id"]),
        )
        change = changes.transition(scope.conn, change, "IN_REVIEW")
        scope.audit(
            "jit.requested",
            change["id"],
            body.justification,
            after=dict(status="IN_REVIEW", duration_minutes=body.duration_minutes, digest=bound),
        )
        return envelope(scope, dict(change, digest=bound, simulation_id=sim["id"]))


@router.get(ENV + "/jit-grants")
def jit_grants(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        rows = scope.conn.execute(
            "SELECT g.*, c.target, c.justification, c.requester_id, "
            "(g.status <> 'EXPIRED' AND g.expires_at <= now() - interval '5 minutes') AS overdue "
            "FROM jit_grants g JOIN change_requests c ON c.id=g.change_request_id "
            "WHERE g.environment_id=%s ORDER BY g.granted_at DESC LIMIT 100",
            (env,),
        ).fetchall()
        pending = scope.conn.execute(
            "SELECT * FROM change_requests WHERE environment_id=%s AND kind='jit_grant' "
            "AND status IN ('IN_REVIEW','APPROVED','QUEUED','EXECUTING') ORDER BY created_at DESC",
            (env,),
        ).fetchall()
        return envelope(
            scope, dict(grants=rows, requests=pending, overdue=[r for r in rows if r["overdue"]])
        )


@router.put(ENV + "/sandbox/faults")
def set_fault(org: UUID, env: UUID, body: FaultRequest, request: Request):
    with scoped(request, org, env, "sandbox:seed") as scope:
        if scope.environment["kind"] not in {"LAB", "SANDBOX"}:
            raise HTTPException(409, "Fault injection exists only for sandbox connectors")
        scope.conn.execute(
            "INSERT INTO sandbox_faults(organization_id,environment_id,operation,mode,remaining) "
            "VALUES(%s,%s,%s,%s,%s) ON CONFLICT (organization_id,environment_id,operation) "
            "DO UPDATE SET mode=excluded.mode, remaining=excluded.remaining",
            (org, env, body.operation, body.mode, body.remaining),
        )
        scope.audit(
            "sandbox.fault_configured",
            env,
            "Sandbox connector fault injection for testing",
            after=body.model_dump(),
        )
        return envelope(scope, body.model_dump())
