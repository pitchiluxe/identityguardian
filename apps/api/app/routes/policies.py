"""Phase 14: policy-as-code lifecycle — validate, test, simulate, approve by digest, activate."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require_session
from ..domain.policy import (
    PolicyError,
    definition_digest,
    run_tests,
    scan,
    validate_definition,
)
from ..jsonutil import dumps
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from ..security import digest
from .changes import require_mfa
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: dict[str, Any]
    policy_id: UUID | None = None  # new version of an existing policy (including reversion)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(min_length=16, max_length=64)
    decision: Literal["APPROVE", "REJECT"]


def load_version(scope, version_id, lock=False):
    base = (
        "SELECT v.*, p.environment_id FROM policy_versions v JOIN policies p ON p.id=v.policy_id "
        "WHERE v.id=%s AND p.environment_id=%s"
    )
    locked = (
        "SELECT v.*, p.environment_id FROM policy_versions v JOIN policies p ON p.id=v.policy_id "
        "WHERE v.id=%s AND p.environment_id=%s FOR UPDATE OF v"
    )
    row = scope.conn.execute(locked if lock else base, (version_id, scope.env_id)).fetchone()
    if not row:
        raise HTTPException(404, "Policy version not found")
    return row


def set_status(scope, row, status, **fields):
    sets = ", ".join(f"{k}=%s" for k in fields)
    return scope.conn.execute(
        f"UPDATE policy_versions SET status=%s{', ' + sets if sets else ''} WHERE id=%s RETURNING *",  # noqa: S608
        (
            status,
            *[Jsonb(v) if isinstance(v, (dict, list)) else v for v in fields.values()],
            row["id"],
        ),
    ).fetchone()


@router.get(ENV + "/policies")
def policies(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        return envelope(
            scope,
            scope.conn.execute(
                "SELECT v.id, v.policy_id, v.version, v.status, v.definition, v.test_results, v.simulation, "
                "v.approval_digest, v.proposed_by, pu.display_name AS proposed_by_name, au.display_name AS approved_by_name, "
                "v.activated_at, v.created_at FROM policy_versions v JOIN policies p ON p.id=v.policy_id "
                "JOIN users pu ON pu.id=v.proposed_by LEFT JOIN users au ON au.id=v.approved_by "
                "WHERE p.environment_id=%s ORDER BY p.created_at DESC, v.version DESC",
                (env,),
            ).fetchall(),
        )


@router.post(ENV + "/policies", status_code=201)
def propose(org: UUID, env: UUID, body: PolicyRequest, request: Request):
    with scoped(request, org, env, "policy:propose") as scope:
        try:
            definition = validate_definition(body.definition)
        except (PolicyError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"Invalid policy: {exc}") from None
        if body.policy_id:
            policy = scope.conn.execute(
                "SELECT * FROM policies WHERE id=%s AND environment_id=%s", (body.policy_id, env)
            ).fetchone()
            if not policy:
                raise HTTPException(404, "Policy not found")
        else:
            policy = scope.conn.execute(
                "INSERT INTO policies(id,organization_id,environment_id,name,created_by) VALUES(%s,%s,%s,%s,%s) "
                "RETURNING *",
                (uuid4(), org, env, definition["name"], scope.user_id),
            ).fetchone()
        version = scope.conn.execute(
            "SELECT coalesce(max(version),0)+1 AS v FROM policy_versions WHERE policy_id=%s",
            (policy["id"],),
        ).fetchone()["v"]
        row = scope.conn.execute(
            "INSERT INTO policy_versions(id,organization_id,policy_id,version,definition,definition_digest,"
            "proposed_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                policy["id"],
                version,
                Jsonb(definition),
                definition_digest(definition),
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "policy.proposed",
            row["id"],
            definition["purpose"],
            after=dict(name=definition["name"], version=version, action=definition["action"]),
        )
        return envelope(scope, row)


@router.post(ENV + "/policies/versions/{version_id}/test")
def test_policy(org: UUID, env: UUID, version_id: UUID, request: Request):
    with scoped(request, org, env, "policy:propose") as scope:
        row = load_version(scope, version_id, lock=True)
        if row["status"] not in {"DRAFT", "TEST_FAILED", "TESTED"}:
            raise HTTPException(409, "Only draft policies can be tested")
        results = run_tests(row["definition"])
        status = "TESTED" if all(r["passed"] for r in results) else "TEST_FAILED"
        updated = set_status(scope, row, status, test_results=results)
        scope.audit(
            "policy.tested",
            version_id,
            f"{sum(r['passed'] for r in results)}/{len(results)} tests passed",
            after=dict(status=status),
        )
        return envelope(scope, updated)


@router.post(ENV + "/policies/versions/{version_id}/simulate")
def simulate_policy(org: UUID, env: UUID, version_id: UUID, request: Request):
    with scoped(request, org, env, "policy:propose") as scope:
        row = load_version(scope, version_id, lock=True)
        if row["status"] not in {"TESTED", "SIMULATED"}:
            raise HTTPException(409, "Policies must pass their tests before simulation")
        snap = snapshot_for(scope)
        result = scan(row["definition"], snap)
        bound = digest(
            dumps(
                dict(
                    policy=str(row["id"]),
                    definition=row["definition_digest"],
                    tests=row["test_results"],
                    violations=[v["grant"]["id"] for v in result["violations"]],
                    graph=snap.version,
                )
            )
        )
        updated = set_status(
            scope,
            row,
            "SIMULATED",
            simulation=result,
            approval_digest=bound,
            graph_version=snap.version,
        )
        scope.audit(
            "policy.simulated",
            version_id,
            f"{len(result['violations'])} existing grant(s) match",
            after=dict(digest=bound),
        )
        return envelope(scope, updated, snapshot=snap)


@router.post(ENV + "/policies/versions/{version_id}/decision")
def decide_policy(org: UUID, env: UUID, version_id: UUID, body: PolicyDecision, request: Request):
    with scoped(request, org, env, "policy:approve") as scope:
        require_mfa(scope)
        row = load_version(scope, version_id, lock=True)
        if row["status"] != "SIMULATED":
            raise HTTPException(409, "Only simulated policies can be decided")
        if row["proposed_by"] == scope.user_id:
            raise HTTPException(403, "Policies require an independent approver")
        if row["approval_digest"] != body.digest:
            raise HTTPException(409, "Digest does not match the simulated policy")
        if row["graph_version"] != snapshot_for(scope).version:
            raise HTTPException(
                409, "The twin changed since simulation; re-simulate before approval"
            )
        status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        updated = set_status(
            scope, row, status, approved_by=scope.user_id, approved_at=datetime.now(timezone.utc)
        )
        scope.audit(
            f"policy.{status.lower()}",
            version_id,
            row["definition"]["name"],
            after=dict(status=status, digest=body.digest),
        )
        return envelope(scope, updated)


@router.post(ENV + "/policies/versions/{version_id}/activate")
def activate(org: UUID, env: UUID, version_id: UUID, request: Request):
    with scoped(request, org, env, "policy:propose") as scope:
        row = load_version(scope, version_id, lock=True)
        if row["status"] != "APPROVED":
            raise HTTPException(409, "Only approved policies can be activated")
        scope.conn.execute(
            "UPDATE policy_versions SET status='SUPERSEDED' WHERE policy_id=%s AND status='ACTIVE'",
            (row["policy_id"],),
        )
        updated = set_status(
            scope,
            row,
            "ACTIVE",
            activated_by=scope.user_id,
            activated_at=datetime.now(timezone.utc),
        )
        scope.audit(
            "policy.activated",
            version_id,
            row["definition"]["name"],
            after=dict(version=row["version"], digest=row["approval_digest"]),
        )
        return envelope(scope, updated)
