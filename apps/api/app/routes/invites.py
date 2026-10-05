"""Phase 21: invites. Access comes only from an invite; privileged invites need an approver."""

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import require_session
from ..scope import envelope, scoped
from ..security import digest, require_recent_mfa

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])
PRIVILEGED = {"org_admin", "approver", "operator"}
Role = Literal[
    "viewer", "investigator", "reviewer", "approver", "operator", "org_admin", "auditor", "learner"
]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Every readable column except token_hash, which never leaves the database.
COLUMNS = sql.SQL(", ").join(
    sql.Identifier(c)
    for c in (
        "id",
        "email_normalized",
        "roles",
        "inviter_id",
        "approver_id",
        "approved_at",
        "digest",
        "justification",
        "status",
        "expires_at",
        "redeemed_by",
        "redeemed_at",
        "created_at",
    )
)


class InviteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    role: Role
    justification: str = Field(min_length=8, max_length=1000)

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        value = value.strip().lower()
        if not EMAIL.match(value):
            raise ValueError("Enter a valid email address")
        return value


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(min_length=64, max_length=64)
    decision: Literal["APPROVE"]


def invite_digest(org, email, role, expires_at):
    return digest(f"invite|{org}|{email}|{role}|{expires_at}")


def outbox(conn, org, invite_id):
    conn.execute(
        "INSERT INTO outbox(id,organization_id,event_type,payload) VALUES(%s,%s,'invite_recorded',%s)",
        (uuid4(), org, Jsonb({"invite_id": str(invite_id)})),
    )


@router.post("/invites", status_code=201)
def create(org: UUID, body: InviteBody, request: Request):
    with scoped(request, org, None, "members:propose") as scope:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=72)
        status = "PENDING_APPROVAL" if body.role in PRIVILEGED else "ACTIVE"
        identifier = uuid4()
        row = scope.conn.execute(
            sql.SQL(
                "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,"
                "inviter_id,digest,justification,status,expires_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {}"
            ).format(COLUMNS),
            (
                identifier,
                org,
                body.email,
                [body.role],
                digest(token),
                scope.user_id,
                invite_digest(org, body.email, body.role, expires.isoformat()),
                body.justification,
                status,
                expires,
            ),
        ).fetchone()
        scope.audit(
            "invite.created",
            identifier,
            body.justification,
            after=dict(email=body.email, roles=[body.role], status=status),
        )
        outbox(scope.conn, org, identifier)
        return envelope(scope, dict(invite=row, link=f"/invite/{token}"))


@router.get("/invites")
def listing(org: UUID, request: Request):
    with scoped(request, org, None, "members:read") as scope:
        rows = scope.conn.execute(
            sql.SQL("SELECT {} FROM invites ORDER BY created_at DESC LIMIT 100").format(COLUMNS)
        ).fetchall()
        return envelope(scope, rows)


def locked(scope, identifier):
    row = scope.conn.execute(
        sql.SQL("SELECT {} FROM invites WHERE id=%s FOR UPDATE").format(COLUMNS), (identifier,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Invite not found")
    return row


@router.post("/invites/{identifier}/decision")
def decide(org: UUID, identifier: UUID, body: Decision, request: Request):
    with scoped(request, org, None, "members:approve") as scope:
        try:
            require_recent_mfa(scope.user["amr"], scope.user["auth_time"])
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from None
        row = locked(scope, identifier)
        if row["inviter_id"] == scope.user_id:
            raise HTTPException(403, "Approval must be independent of the inviter")
        if row["status"] != "PENDING_APPROVAL" or row["expires_at"] <= datetime.now(timezone.utc):
            raise HTTPException(409, "Invite expired or not awaiting approval")
        if not secrets.compare_digest(row["digest"], body.digest):
            raise HTTPException(409, "Invite changed; review it again")
        updated = scope.conn.execute(
            sql.SQL(
                "UPDATE invites SET status='ACTIVE', approver_id=%s, approved_at=now() "
                "WHERE id=%s RETURNING {}"
            ).format(COLUMNS),
            (scope.user_id, identifier),
        ).fetchone()
        scope.audit(
            "invite.approved",
            identifier,
            row["justification"],
            approval=identifier,
            before=dict(status=row["status"]),
            after=dict(status="ACTIVE"),
        )
        outbox(scope.conn, org, identifier)
        return envelope(scope, updated)


@router.post("/invites/{identifier}/revoke")
def revoke(org: UUID, identifier: UUID, request: Request):
    with scoped(request, org, None, "members:propose") as scope:
        row = locked(scope, identifier)
        if row["status"] not in ("ACTIVE", "PENDING_APPROVAL"):
            raise HTTPException(409, "Invite already used or revoked")
        updated = scope.conn.execute(
            sql.SQL("UPDATE invites SET status='REVOKED' WHERE id=%s RETURNING {}").format(COLUMNS),
            (identifier,),
        ).fetchone()
        scope.audit(
            "invite.revoked",
            identifier,
            "Invite revoked by administrator",
            before=dict(status=row["status"]),
            after=dict(status="REVOKED"),
        )
        outbox(scope.conn, org, identifier)
        return envelope(scope, updated)
