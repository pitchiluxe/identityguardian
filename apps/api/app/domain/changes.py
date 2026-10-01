"""Canonical IAM change proposals (SECURITY.md state machine).

Proposals describe an exact operation against the sandbox source. Creating one never changes
access. Later phases simulate, independently approve (digest-bound) and execute them.
"""

from uuid import uuid4

from fastapi import HTTPException

from ..jsonutil import jsonb as Jsonb
from .graph import Snapshot, node_json

REMOVABLE = {
    "USER_MEMBER_OF_GROUP",
    "USER_HAS_ROLE",
    "GROUP_HAS_ROLE",
    "GROUP_INHERITS_GROUP",
    "SERVICE_ACCOUNT_ACCESS_APPLICATION",
    "AI_AGENT_USES_TOOL",
    "AI_AGENT_ACCESS_DATA",
    "ROLE_HAS_PERMISSION",
    "CAN_RESET_CREDENTIAL",
    "CAN_ASSUME_ROLE",
}
GRANTABLE = {"USER_MEMBER_OF_GROUP", "USER_HAS_ROLE"}

TRANSITIONS = {
    "DRAFT": {"SIMULATED", "CANCELLED"},
    "SIMULATED": {"SIMULATED", "IN_REVIEW", "CANCELLED", "STALE"},
    "IN_REVIEW": {"APPROVED", "REJECTED", "EXPIRED", "STALE", "CANCELLED", "SIMULATED"},
    "APPROVED": {"QUEUED", "EXPIRED", "STALE", "CANCELLED"},
    "QUEUED": {"EXECUTING", "STALE", "EXPIRED", "FAILED"},
    "EXECUTING": {"SUCCEEDED", "FAILED", "PARTIAL", "RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"SUCCEEDED", "FAILED", "PARTIAL"},
    "STALE": {"SIMULATED", "CANCELLED"},
}


def relationship_target(snap: Snapshot, conn, relationship_id):
    row = conn.execute(
        "SELECT r.*, (SELECT rr.observation_id FROM relationship_revisions rr WHERE "
        "rr.relationship_id=r.id AND rr.recorded_to IS NULL ORDER BY rr.valid_from DESC LIMIT 1) "
        "AS observation_id FROM relationships r WHERE r.id=%s",
        (relationship_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Relationship not found")
    current = next((e for e in snap.edges if e.relationship_id == str(row["id"])), None)
    if not current:
        raise HTTPException(409, "Relationship is not currently effective")
    if row["type"] not in REMOVABLE:
        raise HTTPException(422, "Only grant or exposure relationships can be proposed for removal")
    return dict(
        relationship_id=str(row["id"]),
        external_id=row["external_id"],
        type=row["type"],
        source=row["source"],
        src=node_json(snap.nodes[str(row["from_node"])]),
        dst=node_json(snap.nodes[str(row["to_node"])]),
        attributes=current.attributes,
        valid_from=current.valid_from.isoformat(),
        evidence_id=str(row["observation_id"]),
    )


def create(
    conn,
    scope,
    kind,
    target,
    justification,
    origin,
    origin_ref=None,
    parameters=None,
    idempotency_key=None,
):
    key = idempotency_key or uuid4()
    existing = conn.execute(
        "SELECT * FROM change_requests WHERE requester_id=%s AND idempotency_key=%s",
        (scope.user_id, key),
    ).fetchone()
    if existing:
        if existing["target"] != target or existing["kind"] != kind:
            raise HTTPException(409, "Idempotency key already used for another proposal")
        return existing
    row = conn.execute(
        "INSERT INTO change_requests(id,organization_id,environment_id,kind,target,parameters,"
        "justification,origin,origin_ref,requester_id,idempotency_key) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            uuid4(),
            scope.org,
            scope.env_id,
            kind,
            Jsonb(target),
            Jsonb(parameters or {}),
            justification,
            origin,
            origin_ref,
            scope.user_id,
            key,
        ),
    ).fetchone()
    scope.audit(
        "change.proposed",
        row["id"],
        justification,
        after=dict(kind=kind, target=target, origin=origin, status="DRAFT"),
    )
    return row


def transition(conn, change, new_status, expected_version=None):
    if new_status not in TRANSITIONS.get(change["status"], set()):
        raise HTTPException(409, f"Cannot move a {change['status']} request to {new_status}")
    if expected_version is not None and change["version"] != expected_version:
        raise HTTPException(409, "Request changed; refresh and review again")
    return (
        conn.execute(
            "UPDATE change_requests SET status=%s, version=version+1, updated_at=now() "
            "WHERE id=%s AND version=%s RETURNING *",
            (new_status, change["id"], change["version"]),
        ).fetchone()
        or _conflict()
    )


def _conflict():
    raise HTTPException(409, "Request changed concurrently; refresh and review again")


def versions_current(conn, source_versions) -> bool:
    """True when every bound source version is still the current one.

    Keys are relationship IDs (bound to their current revision ID) or ``credential:<node id>``
    (bound to the credential's current ``rotated_at``).
    """
    for key, bound in (source_versions or {}).items():
        if key.startswith("node:"):
            _, node_id, attribute = key.split(":", 2)
            row = conn.execute(
                "SELECT attributes->>%s AS value FROM node_revisions WHERE node_id=%s "
                "AND recorded_to IS NULL ORDER BY valid_from DESC LIMIT 1",
                (attribute, node_id),
            ).fetchone()
            if not row or str(row["value"]) != bound:
                return False
            continue
        if key.startswith("credential:"):
            row = conn.execute(
                "SELECT attributes->>'rotated_at' AS rotated FROM node_revisions WHERE node_id=%s "
                "AND recorded_to IS NULL ORDER BY valid_from DESC LIMIT 1",
                (key.split(":", 1)[1],),
            ).fetchone()
            if not row or str(row["rotated"]) != bound:
                return False
            continue
        row = conn.execute(
            "SELECT id FROM relationship_revisions WHERE relationship_id=%s AND recorded_to IS NULL "
            "AND (valid_to IS NULL OR valid_to>now()) ORDER BY valid_from DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row or str(row["id"]) != bound:
            return False
    return True
