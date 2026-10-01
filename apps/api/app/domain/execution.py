"""Controlled execution (SECURITY.md "Approval and execution"). Runs in the worker.

Order of operations, each step its own transaction:
  1. Recheck every binding (status, approval, approver membership, expiry, digest, source
     versions) and record durable intent (EXECUTING + audit) before dispatch.
  2. Dispatch the exact approved operation to the sandbox connector.
  3. Read back the source, ingest it, and only then report SUCCEEDED.
A lost response leaves RECONCILIATION_REQUIRED, never invented success. JIT expiry removal is
authorized by the original bounded approval and never extends access.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..jsonutil import jsonb as Jsonb
from ..security import capabilities
from . import connector
from .changes import transition, versions_current
from .ingest import run_sync
from .policy import active_policy_version

OVERDUE_GRACE = timedelta(minutes=5)


def audit(
    conn,
    org,
    actor,
    action,
    target,
    justification,
    after=None,
    approval=None,
    result="succeeded",
    correlation=None,
):
    conn.execute(
        "INSERT INTO audit_events(id,organization_id,actor_id,action,target,after_state,"
        "justification,approval_id,result,correlation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            org,
            actor,
            action,
            str(target),
            Jsonb(after or {}),
            justification,
            approval,
            result,
            correlation or uuid4(),
        ),
    )


def source_object(change):
    if change["kind"] == "remove_relationship":
        return change["target"]["external_id"]
    if change["kind"] == "rotate_credential":
        return change["target"]["credential"]["external_id"]
    if change["kind"] == "disable_account":
        return change["target"]["account"]["external_id"]
    return f"jit-{change['id']}" if change["kind"] == "jit_grant" else f"add-{change['id']}"


def _set(conn, change, execution, status, **fields):
    current = conn.execute(
        "SELECT * FROM change_requests WHERE id=%s FOR UPDATE", (change["id"],)
    ).fetchone()
    transition(conn, current, status)
    sets = ", ".join(f"{k}=%s" for k in fields)
    conn.execute(
        f"UPDATE executions SET status=%s, updated_at=now(){', ' + sets if sets else ''} WHERE id=%s",  # noqa: S608
        (
            status,
            *[Jsonb(v) if isinstance(v, dict) else v for v in fields.values()],
            execution["id"],
        ),
    )


def recheck(conn, change, execution):
    """Return (ok, terminal_status, reason)."""
    approval = conn.execute(
        "SELECT * FROM approvals WHERE id=%s", (execution["approval_id"],)
    ).fetchone()
    needed = "jit:approve" if change["kind"] == "jit_grant" else "change:approve"
    member = conn.execute(
        "SELECT roles FROM memberships WHERE user_id=%s AND active", (approval["approver_id"],)
    ).fetchone()
    if not member or needed not in capabilities(member["roles"]):
        return False, "STALE", "Approver no longer holds approval authority"
    if approval["expires_at"] <= datetime.now(timezone.utc):
        return False, "EXPIRED", "Approval expired before execution"
    if not (change["digest"] == approval["digest"] == execution["digest"]):
        return False, "STALE", "Proposal digest changed after approval"
    sim = conn.execute(
        "SELECT source_versions, policy_version FROM simulations WHERE id=%s",
        (change["simulation_id"],),
    ).fetchone()
    if sim["policy_version"] != active_policy_version(conn, change["environment_id"]):
        return False, "STALE", "Active policies changed since simulation"
    if not versions_current(conn, sim["source_versions"]):
        return False, "STALE", "Target changed at the source since simulation"
    return True, None, None


def execute_change(db, org, change_id):
    """Execute one QUEUED change. Returns the final execution status."""
    with db.transaction(org) as conn:
        change = conn.execute(
            "SELECT * FROM change_requests WHERE id=%s FOR UPDATE", (change_id,)
        ).fetchone()
        execution = conn.execute(
            "SELECT * FROM executions WHERE change_request_id=%s FOR UPDATE", (change_id,)
        ).fetchone()
        if not change or not execution:
            return None
        if execution["status"] == "EXECUTING":
            # A previous attempt died after recording intent: the outcome is unknown.
            _set(
                conn,
                change,
                execution,
                "RECONCILIATION_REQUIRED",
                error="Worker restarted during execution; source outcome unknown",
            )
            audit(
                conn,
                org,
                None,
                "change.reconciliation_required",
                change_id,
                "Execution interrupted; reconciliation required",
                result="unknown",
            )
            return "RECONCILIATION_REQUIRED"
        if change["status"] != "QUEUED" or execution["status"] != "QUEUED":
            return execution["status"]
        ok, status, reason = recheck(conn, change, execution)
        if not ok:
            _set(conn, change, execution, status, error=reason)
            audit(
                conn,
                org,
                execution["executor_id"],
                "change.execution_refused",
                change_id,
                reason,
                after=dict(status=status),
                approval=execution["approval_id"],
                result="refused",
            )
            return status
        _set(conn, change, execution, "EXECUTING", attempts=execution["attempts"] + 1)
        audit(
            conn,
            org,
            execution["executor_id"],
            "change.executing",
            change_id,
            change["justification"],
            after=dict(status="EXECUTING", digest=change["digest"]),
            approval=execution["approval_id"],
            result="intent",
        )
        environment = conn.execute(
            "SELECT * FROM environments WHERE id=%s", (change["environment_id"],)
        ).fetchone()
    with db.transaction(org) as conn:
        operation = "add_relationship" if change["kind"] == "jit_grant" else change["kind"]
        fault = connector.consume_fault(conn, environment["id"], operation)
    object_id = source_object(change)
    try:
        with db.transaction(org) as conn:
            if change["kind"] == "remove_relationship":
                result = connector.remove_relationship(
                    conn, environment["id"], object_id, fault=fault
                )
            elif change["kind"] == "rotate_credential":
                result = connector.rotate_credential(
                    conn, environment["id"], object_id, fault=fault
                )
            elif change["kind"] == "disable_account":
                result = connector.disable_account(conn, environment["id"], object_id, fault=fault)
            else:
                target, params = change["target"], change["parameters"]
                expires = None
                attributes = dict(
                    origin="temporary_privilege"
                    if change["kind"] == "jit_grant"
                    else "direct_assignment",
                    ticket=f"CR-{str(change_id)[:8]}",
                    approver=str(execution["approval_id"]),
                    justification=change["justification"],
                )
                now = datetime.now(timezone.utc)
                if change["kind"] == "jit_grant":
                    expires = now + timedelta(minutes=int(params["duration_minutes"]))
                    attributes["expires_at"] = expires.isoformat()
                result = connector.add_relationship(
                    conn,
                    org,
                    environment["id"],
                    object_id,
                    target["type"],
                    target["src"]["external_id"],
                    target["dst"]["external_id"],
                    attributes,
                    effective_at=now,
                    fault=fault,
                )
                if expires:
                    conn.execute(
                        "INSERT INTO jit_grants(id,organization_id,environment_id,change_request_id,"
                        "source_object_id,granted_at,expires_at,status) VALUES(%s,%s,%s,%s,%s,%s,%s,'ACTIVE') "
                        "ON CONFLICT (organization_id, change_request_id) DO NOTHING",
                        (uuid4(), org, environment["id"], change_id, object_id, now, expires),
                    )
    except connector.ConnectorError as exc:
        with db.transaction(org) as conn:
            _set(conn, change, execution, "FAILED", error=str(exc))
            audit(
                conn,
                org,
                execution["executor_id"],
                "change.failed",
                change_id,
                str(exc),
                approval=execution["approval_id"],
                result="failed",
            )
        return "FAILED"
    if result.get("lost_response"):
        with db.transaction(org) as conn:
            _set(
                conn,
                change,
                execution,
                "RECONCILIATION_REQUIRED",
                connector_result=result,
                error="No confirmation from the source; outcome must be reconciled by read-back",
            )
            audit(
                conn,
                org,
                execution["executor_id"],
                "change.reconciliation_required",
                change_id,
                "Connector response lost after dispatch",
                approval=execution["approval_id"],
                result="unknown",
            )
        return "RECONCILIATION_REQUIRED"
    return confirm(db, org, change, execution, object_id, result)


def confirm(db, org, change, execution, object_id, result=None):
    with db.transaction(org) as conn:
        if change["kind"] == "rotate_credential":
            dispatched = (result or {}).get("effective_at")
            since = datetime.fromisoformat(dispatched) if dispatched else execution["created_at"]
            readback = connector.credential_rotated_since(
                conn, change["environment_id"], object_id, since - timedelta(seconds=1)
            )
        elif change["kind"] == "disable_account":
            readback = connector.account_disabled(conn, change["environment_id"], object_id)
        else:
            readback = connector.read_back(conn, change["environment_id"], object_id)
        expected_present = change["kind"] != "remove_relationship"
        if readback is None or readback["present"] != expected_present:
            _set(
                conn,
                change,
                execution,
                "FAILED",
                readback=readback or {},
                error="Read-back does not show the approved change",
            )
            audit(
                conn,
                org,
                execution["executor_id"],
                "change.failed",
                change["id"],
                "Read-back mismatch",
                approval=execution["approval_id"],
                result="failed",
            )
            return "FAILED"
        environment = conn.execute(
            "SELECT * FROM environments WHERE id=%s", (change["environment_id"],)
        ).fetchone()
        run = run_sync(conn, environment, None)
        _set(
            conn,
            change,
            execution,
            "SUCCEEDED",
            readback=readback,
            connector_result=dict(result or {}, sync_run=str(run["id"]), sync_status=run["status"]),
        )
        audit(
            conn,
            org,
            execution["executor_id"],
            "change.succeeded",
            change["id"],
            change["justification"],
            after=dict(status="SUCCEEDED", readback=readback, sync_run=str(run["id"])),
            approval=execution["approval_id"],
        )
    return "SUCCEEDED"


def reconcile(db, org):
    """Resolve RECONCILIATION_REQUIRED executions by reading back the source."""
    resolved = []
    with db.transaction(org) as conn:
        rows = conn.execute(
            "SELECT e.*, c.kind, c.target, c.environment_id, c.justification, c.id AS cid "
            "FROM executions e JOIN change_requests c ON c.id=e.change_request_id "
            "WHERE e.status='RECONCILIATION_REQUIRED'"
        ).fetchall()
    for row in rows:
        change = dict(
            id=row["cid"],
            kind=row["kind"],
            target=row["target"],
            environment_id=row["environment_id"],
            justification=row["justification"],
        )
        resolved.append(
            (
                row["cid"],
                confirm(db, org, change, row, source_object(change), row["connector_result"]),
            )
        )
    return resolved


def expire_jit(db, org, now=None):
    """Revoke expired JIT grants at the source. Disconnected sources stay REVOKE_PENDING."""
    now = now or datetime.now(timezone.utc)
    outcomes = []
    with db.transaction(org) as conn:
        due = conn.execute(
            "SELECT * FROM jit_grants WHERE status IN ('ACTIVE','REVOKE_PENDING') AND expires_at<=%s",
            (now,),
        ).fetchall()
    for grant in due:
        with db.transaction(org) as conn:
            fault = connector.consume_fault(conn, grant["environment_id"], "remove_relationship")
        try:
            with db.transaction(org) as conn:
                connector.remove_relationship(
                    conn,
                    grant["environment_id"],
                    grant["source_object_id"],
                    effective_at=grant["expires_at"],
                    fault=fault,
                )
                if fault == "timeout_after_write":
                    raise connector.ConnectorError("No confirmation from source after revocation")
        except connector.ConnectorError as exc:
            with db.transaction(org) as conn:
                conn.execute(
                    "UPDATE jit_grants SET status='REVOKE_PENDING', attempts=attempts+1, "
                    "last_error=%s WHERE id=%s",
                    (str(exc), grant["id"]),
                )
                audit(
                    conn,
                    org,
                    None,
                    "jit.revocation_pending",
                    grant["change_request_id"],
                    str(exc),
                    result="failed",
                )
            outcomes.append((grant["id"], "REVOKE_PENDING"))
            continue
        with db.transaction(org) as conn:
            readback = connector.read_back(conn, grant["environment_id"], grant["source_object_id"])
            if readback and not readback["present"]:
                environment = conn.execute(
                    "SELECT * FROM environments WHERE id=%s", (grant["environment_id"],)
                ).fetchone()
                run_sync(conn, environment, None)
                conn.execute(
                    "UPDATE jit_grants SET status='EXPIRED', revoked_at=now(), "
                    "attempts=attempts+1, last_error=NULL WHERE id=%s",
                    (grant["id"],),
                )
                audit(
                    conn,
                    org,
                    None,
                    "jit.expired",
                    grant["change_request_id"],
                    "Expiry revocation authorized by the original bounded approval",
                    after=dict(expires_at=grant["expires_at"].isoformat(), readback=readback),
                )
                outcomes.append((grant["id"], "EXPIRED"))
    return outcomes


def overdue(conn, now=None):
    now = now or datetime.now(timezone.utc)
    return conn.execute(
        "SELECT * FROM jit_grants WHERE status IN ('ACTIVE','REVOKE_PENDING') AND expires_at<=%s",
        (now - OVERDUE_GRACE,),
    ).fetchall()
