"""Phase 6: evidence-backed access reviews. REMOVE creates a proposal; it never revokes."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import membership, require_session
from ..domain import changes
from ..domain.findings import all_findings
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from ..security import capabilities
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])
RULES = {
    "PRIOR_ROLE_RETAINED",
    "TERMINATED_WITH_ACCESS",
    "DORMANT_PRIVILEGED",
    "UNUSED_PRIVILEGED_ENTITLEMENT",
}


class CampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=200)
    rules: list[str] = Field(min_length=1, max_length=4)
    reviewer_id: UUID
    due_days: int = Field(14, ge=1, le=90)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["KEEP", "REMOVE", "ESCALATE"]
    justification: str = Field(min_length=8, max_length=2000)
    expected_version: int = Field(ge=1)


def uncertainty(finding):
    notes = []
    for u in finding.get("usage", []):
        if u["state"] in {"UNKNOWN", "NOT_OBSERVED_PARTIAL"}:
            notes.append(f"{u['target']}: {u['text']}")
        elif u["state"] == "NOT_OBSERVED":
            notes.append(
                f"{u['target']}: absence of observed use is bounded by coverage, not proof of non-use"
            )
    for reach in finding.get("reaches", []):
        if reach["decision"] in {"CONDITIONAL", "UNKNOWN"}:
            notes.append(f"{reach['target']}: access is {reach['decision']} (conditions apply)")
    grant = finding.get("grant") or {}
    if (grant.get("attributes") or {}).get("origin") == "unknown":
        notes.append("Grant provenance is unknown at the source")
    if finding.get("peers", {}).get("sample_size", 99) < 3:
        notes.append(f"Peer comparison uses a small sample ({finding['peers']['sample_size']})")
    return notes


def recommend(finding):
    """REMOVE only when nothing shows observed use and every privileged target has complete
    coverage without observed use. Anything less certain stays REVIEW."""
    if finding["rule"] == "TERMINATED_WITH_ACCESS":
        return "REMOVE"
    usage = {u["target"]: u["state"] for u in finding.get("usage", [])}
    privileged = [r["target"] for r in finding.get("reaches", []) if r["privileged"]]
    if not privileged or "OBSERVED" in usage.values():
        return "REVIEW"
    if all(usage.get(target) == "NOT_OBSERVED" for target in privileged):
        return "REMOVE"
    return "REVIEW"


@router.get("/reviewers")
def reviewers(org: UUID, request: Request):
    with scoped(request, org, None, "review:manage") as scope:
        rows = scope.conn.execute(
            "SELECT m.user_id, u.display_name, m.roles FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE m.active ORDER BY u.display_name"
        ).fetchall()
        return envelope(scope, [r for r in rows if "review:decide" in capabilities(r["roles"])])


@router.post(ENV + "/reviews", status_code=201)
def create_campaign(org: UUID, env: UUID, body: CampaignRequest, request: Request):
    if set(body.rules) - RULES:
        raise HTTPException(422, "Unknown finding rule")
    with scoped(request, org, env, "review:manage") as scope:
        try:
            reviewer = membership(scope.conn, body.reviewer_id, "review:decide")
        except HTTPException:
            raise HTTPException(
                422, "Reviewer must be an active member with review authority"
            ) from None
        if reviewer["user_id"] == scope.user_id:
            raise HTTPException(403, "Campaign owners cannot assign reviews to themselves")
        snap = snapshot_for(scope)
        findings = [
            f for f in all_findings(snap, scope.conn, scope.env_id) if f["rule"] in body.rules
        ]
        campaign = scope.conn.execute(
            "INSERT INTO review_campaigns(id,organization_id,environment_id,name,rules,created_by,"
            "due_at,snapshot) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                env,
                body.name,
                sorted(set(body.rules)),
                scope.user_id,
                datetime.now(timezone.utc) + timedelta(days=body.due_days),
                Jsonb(snap.describe()),
            ),
        ).fetchone()
        items: dict = {}
        for finding in findings:
            first_hops = {}
            if finding.get("grant"):
                first_hops[finding["grant"]["relationship_id"]] = finding["grant"]
            for reach in finding["reaches"]:
                for path in reach["paths"]:
                    edge = path["hops"][0]["edge"]
                    first_hops.setdefault(edge["relationship_id"], edge)
            for rel_id, edge in first_hops.items():
                item = items.setdefault(
                    rel_id,
                    dict(
                        identity=finding["identity"]["id"],
                        edge=edge,
                        findings=[],
                        recommendation="REVIEW",
                        uncertainty=[],
                    ),
                )
                item["findings"].append(finding)
                if recommend(finding) == "REMOVE":
                    item["recommendation"] = "REMOVE"
                item["uncertainty"] += [
                    u for u in uncertainty(finding) if u not in item["uncertainty"]
                ]
        for rel_id, item in items.items():
            evidence = dict(
                grant=item["edge"],
                findings=[
                    {
                        k: f[k]
                        for k in (
                            "key",
                            "rule",
                            "severity",
                            "title",
                            "summary",
                            "usage",
                            "reaches",
                            "evidence_ids",
                            "rules_version",
                        )
                        if k in f
                    }
                    | ({"peers": f["peers"]} if "peers" in f else {})
                    | ({"event": f["event"]} if "event" in f else {})
                    for f in item["findings"]
                ],
            )
            scope.conn.execute(
                "INSERT INTO review_items(id,organization_id,campaign_id,identity_node,relationship_id,"
                "finding_keys,evidence,recommendation,recommendation_basis,uncertainty,reviewer_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    org,
                    campaign["id"],
                    item["identity"],
                    rel_id,
                    [f["key"] for f in item["findings"]],
                    Jsonb(evidence),
                    item["recommendation"],
                    "RULE-BASED ("
                    + ", ".join(sorted({f["rules_version"] for f in item["findings"]}))
                    + ")",
                    Jsonb(item["uncertainty"]),
                    body.reviewer_id,
                ),
            )
        scope.audit(
            "review.campaign_created",
            campaign["id"],
            body.name,
            after=dict(
                rules=body.rules,
                items=len(items),
                reviewer=str(body.reviewer_id),
                snapshot=snap.describe(),
            ),
        )
        return envelope(scope, dict(campaign, item_count=len(items)), snapshot=snap)


@router.get(ENV + "/reviews")
def campaigns(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "findings:read") as scope:
        rows = scope.conn.execute(
            "SELECT c.*, count(i.id) AS items, count(i.id) FILTER (WHERE i.status='DECIDED') AS decided, "
            "count(i.id) FILTER (WHERE i.reviewer_id=%s AND i.status='PENDING') AS assigned_to_me "
            "FROM review_campaigns c LEFT JOIN review_items i ON i.campaign_id=c.id "
            "WHERE c.environment_id=%s GROUP BY c.id ORDER BY c.created_at DESC LIMIT 50",
            (scope.user_id, env),
        ).fetchall()
        return envelope(scope, rows)


@router.get(ENV + "/reviews/{campaign_id}")
def campaign_items(
    org: UUID, env: UUID, campaign_id: UUID, request: Request, mine: bool = Query(False)
):
    with scoped(request, org, env, "findings:read") as scope:
        campaign = scope.conn.execute(
            "SELECT * FROM review_campaigns WHERE id=%s AND environment_id=%s", (campaign_id, env)
        ).fetchone()
        if not campaign:
            raise HTTPException(404, "Review campaign not found")
        rows = scope.conn.execute(
            "SELECT i.*, u.display_name AS reviewer_name, d.display_name AS decided_by_name, "
            "cr.status AS change_status FROM review_items i JOIN users u ON u.id=i.reviewer_id "
            "LEFT JOIN users d ON d.id=i.decided_by LEFT JOIN change_requests cr ON cr.id=i.change_request_id "
            "WHERE i.campaign_id=%s AND (NOT %s OR i.reviewer_id=%s) ORDER BY i.status, i.recommendation DESC",
            (campaign_id, mine, scope.user_id),
        ).fetchall()
        return envelope(scope, dict(campaign=campaign, items=rows))


@router.post(ENV + "/reviews/{campaign_id}/items/{item_id}/decision")
def decide(
    org: UUID, env: UUID, campaign_id: UUID, item_id: UUID, body: DecisionRequest, request: Request
):
    with scoped(request, org, env, "review:decide") as scope:
        item = scope.conn.execute(
            "SELECT i.*, c.status AS campaign_status FROM review_items i JOIN review_campaigns c "
            "ON c.id=i.campaign_id WHERE i.id=%s AND i.campaign_id=%s AND c.environment_id=%s FOR UPDATE",
            (item_id, campaign_id, env),
        ).fetchone()
        if not item:
            raise HTTPException(404, "Review item not found")
        if item["reviewer_id"] != scope.user_id:
            raise HTTPException(403, "This item is assigned to another reviewer")
        if item["status"] != "PENDING" or item["campaign_status"] != "OPEN":
            raise HTTPException(409, "Item already decided or campaign closed")
        if item["version"] != body.expected_version:
            raise HTTPException(409, "Item changed; refresh and review again")
        change = None
        if body.decision == "REMOVE":
            snap = snapshot_for(scope)
            target = changes.relationship_target(snap, scope.conn, item["relationship_id"])
            change = changes.create(
                scope.conn,
                scope,
                "remove_relationship",
                target,
                body.justification,
                "review",
                str(item["id"]),
            )
        updated = scope.conn.execute(
            "UPDATE review_items SET status='DECIDED', decision=%s, decision_justification=%s, "
            "decided_by=%s, decided_at=now(), change_request_id=%s, version=version+1 "
            "WHERE id=%s RETURNING *",
            (
                body.decision,
                body.justification,
                scope.user_id,
                change["id"] if change else None,
                item_id,
            ),
        ).fetchone()
        scope.audit(
            "review.decided",
            item_id,
            body.justification,
            before=dict(status="PENDING", recommendation=item["recommendation"]),
            after=dict(
                decision=body.decision, change_request=str(change["id"]) if change else None
            ),
        )
        return envelope(scope, dict(item=updated, change_request=change))


@router.get(ENV + "/change-requests")
def change_requests(
    org: UUID, env: UUID, request: Request, status: str | None = Query(None, pattern="^[A-Z_]+$")
):
    with scoped(request, org, env, "findings:read") as scope:
        rows = scope.conn.execute(
            "SELECT cr.*, u.display_name AS requester_name FROM change_requests cr JOIN users u "
            "ON u.id=cr.requester_id WHERE cr.environment_id=%s AND (%s::text IS NULL OR cr.status=%s) "
            "ORDER BY cr.created_at DESC LIMIT 100",
            (env, status, status),
        ).fetchall()
        return envelope(scope, rows)
