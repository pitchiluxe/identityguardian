"""Phase 11: joiner baselines, mover/leaver plans and lifecycle workflows."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require_session
from ..domain import changes
from ..domain.graph import node_json
from ..domain.lifecycle import plan_for, workflow_status
from ..domain.types import validate
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from .changes import ProposalRequest, require_mfa, simulate_and_submit
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])


class BaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str = Field(min_length=2, max_length=80)
    groups: list[str] = Field(min_length=1, max_length=20)
    justification: str = Field(min_length=8, max_length=1000)


class BaselineDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[int] = Field(min_length=1, max_length=30)
    justification: str = Field(min_length=8, max_length=1000)


@router.get(ENV + "/lifecycle/baselines")
def baselines(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        rows = scope.conn.execute(
            "SELECT b.*, p.display_name AS proposed_by_name, a.display_name AS approved_by_name "
            "FROM jml_baselines b JOIN users p ON p.id=b.proposed_by LEFT JOIN users a ON a.id=b.approved_by "
            "WHERE b.environment_id=%s ORDER BY b.department, b.version DESC",
            (env,),
        ).fetchall()
        return envelope(scope, rows)


@router.post(ENV + "/lifecycle/baselines", status_code=201)
def propose_baseline(org: UUID, env: UUID, body: BaselineRequest, request: Request):
    with scoped(request, org, env, "policy:propose") as scope:
        snap = snapshot_for(scope)
        for group in body.groups:
            node = snap.by_external(group)
            if not node or node.kind != "group":
                raise HTTPException(422, f"Unknown group {group}")
        version = scope.conn.execute(
            "SELECT coalesce(max(version),0)+1 AS v FROM jml_baselines WHERE environment_id=%s "
            "AND department=%s",
            (env, body.department),
        ).fetchone()["v"]
        row = scope.conn.execute(
            "INSERT INTO jml_baselines(id,organization_id,environment_id,department,groups,version,"
            "justification,proposed_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                env,
                body.department,
                sorted(set(body.groups)),
                version,
                body.justification,
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "baseline.proposed",
            row["id"],
            body.justification,
            after=dict(department=body.department, groups=row["groups"], version=version),
        )
        return envelope(scope, row)


@router.post(ENV + "/lifecycle/baselines/{baseline_id}/decision")
def decide_baseline(
    org: UUID, env: UUID, baseline_id: UUID, body: BaselineDecision, request: Request
):
    with scoped(request, org, env, "policy:approve") as scope:
        require_mfa(scope)
        row = scope.conn.execute(
            "SELECT * FROM jml_baselines WHERE id=%s AND environment_id=%s FOR UPDATE",
            (baseline_id, env),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Baseline not found")
        if row["status"] != "PROPOSED":
            raise HTTPException(409, "Baseline already decided")
        if row["proposed_by"] == scope.user_id:
            raise HTTPException(403, "Baselines require an independent approver")
        if body.decision == "APPROVE":
            scope.conn.execute(
                "UPDATE jml_baselines SET status='SUPERSEDED' WHERE environment_id=%s AND department=%s "
                "AND status='APPROVED'",
                (env, row["department"]),
            )
        status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        updated = scope.conn.execute(
            "UPDATE jml_baselines SET status=%s, approved_by=%s, approved_at=%s WHERE id=%s RETURNING *",
            (status, scope.user_id, datetime.now(timezone.utc), baseline_id),
        ).fetchone()
        scope.audit(
            f"baseline.{status.lower()}",
            baseline_id,
            f"{row['department']} baseline v{row['version']}",
            after=dict(status=status, groups=row["groups"]),
        )
        return envelope(scope, updated)


@router.get(ENV + "/lifecycle/events")
def events(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        snap = snapshot_for(scope)
        rows = scope.conn.execute(
            "SELECT e.*, w.id AS workflow_id FROM employment_events e LEFT JOIN lifecycle_workflows w "
            "ON w.event_id=e.id WHERE e.environment_id=%s ORDER BY e.effective_at DESC",
            (env,),
        ).fetchall()
        out = []
        for row in rows:
            node = snap.nodes.get(str(row["identity_node"]))
            out.append(
                dict(
                    id=row["id"],
                    kind=row["kind"],
                    effective_at=row["effective_at"],
                    details=row["details"],
                    workflow_id=row["workflow_id"],
                    identity=node_json(node) if node else None,
                )
            )
        return envelope(scope, out, snapshot=snap)


def load_event(scope, event_id):
    event = scope.conn.execute(
        "SELECT * FROM employment_events WHERE id=%s AND environment_id=%s",
        (event_id, scope.env_id),
    ).fetchone()
    if not event:
        raise HTTPException(404, "Lifecycle event not found")
    return event


@router.get(ENV + "/lifecycle/events/{event_id}/plan")
def plan(org: UUID, env: UUID, event_id: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        snap = snapshot_for(scope)
        return envelope(
            scope,
            plan_for(snap, scope.conn, scope.env_id, load_event(scope, event_id)),
            snapshot=snap,
        )


@router.post(ENV + "/lifecycle/events/{event_id}/workflow", status_code=201)
def start_workflow(org: UUID, env: UUID, event_id: UUID, body: WorkflowRequest, request: Request):
    with scoped(request, org, env, "change:propose") as scope:
        event = load_event(scope, event_id)
        if scope.conn.execute(
            "SELECT 1 FROM lifecycle_workflows WHERE event_id=%s", (event_id,)
        ).fetchone():
            raise HTTPException(409, "A workflow already exists for this event")
        snap = snapshot_for(scope)
        current = plan_for(snap, scope.conn, scope.env_id, event)
        created = []
        for index in sorted(set(body.actions)):
            if index >= len(current["actions"]) or not current["actions"][index]["proposal"]:
                raise HTTPException(422, f"Action {index} has no executable proposal")
            proposal = ProposalRequest(
                **current["actions"][index]["proposal"],
                justification=f"{body.justification} — {current['actions'][index]['label']}",
                idempotency_key=uuid4(),
            )
            target = proposal_target(snap, scope, proposal)
            change = changes.create(
                scope.conn,
                scope,
                proposal.kind,
                target,
                proposal.justification,
                "lifecycle",
                origin_ref=str(event_id),
            )
            change, _, _ = simulate_and_submit(scope, change, snap)
            created.append(change["id"])
        workflow = scope.conn.execute(
            "INSERT INTO lifecycle_workflows(id,organization_id,environment_id,kind,identity_node,event_id,"
            "plan,change_request_ids,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                env,
                event["kind"],
                event["identity_node"],
                event_id,
                Jsonb(current),
                created,
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "lifecycle.workflow_started",
            workflow["id"],
            body.justification,
            after=dict(kind=event["kind"], change_requests=[str(c) for c in created]),
        )
        return envelope(scope, workflow)


def proposal_target(snap, scope, proposal):
    """Build the canonical change target exactly as the manual proposal endpoint does."""
    if proposal.kind == "remove_relationship":
        return changes.relationship_target(snap, scope.conn, proposal.relationship)
    if proposal.kind == "disable_account":
        account = snap.by_external(proposal.account)
        holder = next(
            (snap.nodes[e.src] for e in snap.inc[account.id] if e.type == "HAS_ACCOUNT"), None
        )
        return dict(
            type="ACCOUNT_DISABLE",
            account=node_json(account),
            src=node_json(holder),
            dst=node_json(account),
        )
    if proposal.kind == "rotate_credential":
        credential = snap.by_external(proposal.credential)
        holder = next(
            (snap.nodes[e.src] for e in snap.inc[credential.id] if e.type == "HAS_CREDENTIAL"), None
        )
        return dict(
            type="CREDENTIAL_ROTATION",
            credential=node_json(credential),
            src=node_json(holder),
            dst=node_json(credential),
        )
    src, dst = snap.by_external(proposal.src or ""), snap.by_external(proposal.dst or "")
    if not src or not dst:
        raise HTTPException(422, "Proposal endpoints are not effective")
    validate(proposal.type, src.kind, dst.kind)
    return dict(type=proposal.type, src=node_json(src), dst=node_json(dst))


@router.get(ENV + "/lifecycle/workflows/{workflow_id}")
def workflow(org: UUID, env: UUID, workflow_id: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        row = scope.conn.execute(
            "SELECT * FROM lifecycle_workflows WHERE id=%s AND environment_id=%s",
            (workflow_id, env),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Workflow not found")
        items = scope.conn.execute(
            "SELECT id, kind, status, target, justification FROM change_requests WHERE id = ANY(%s) "
            "ORDER BY created_at",
            (row["change_request_ids"],),
        ).fetchall()
        return envelope(
            scope,
            dict(workflow=row, changes=items, status=workflow_status([i["status"] for i in items])),
        )
