"""Phase 21: invites table, grants and redeem_invite (runtime role)."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.security import digest

load_dotenv()
pytestmark = pytest.mark.integration
MIGRATOR, RUNTIME = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]


def seed(status="ACTIVE", roles=("viewer",), email="new.person@example.org", hours=72):
    org, inviter, token = uuid4(), uuid4(), secrets.token_urlsafe(32)
    with psycopg.connect(MIGRATOR) as conn:
        conn.execute("INSERT INTO organizations VALUES (%s,'Invite test')", (org,))
        conn.execute("INSERT INTO users VALUES (%s,'test',%s,'Inviter')", (inviter, str(inviter)))
        conn.execute(
            "INSERT INTO memberships(organization_id,user_id,roles) VALUES (%s,%s,%s)",
            (org, inviter, ["org_admin"]),
        )
        conn.execute(
            "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,"
            "digest,status,expires_at) VALUES (%s,%s,%s,%s,%s,%s,'d',%s,%s)",
            (
                uuid4(),
                org,
                email,
                list(roles),
                digest(token),
                inviter,
                status,
                datetime.now(timezone.utc) + timedelta(hours=hours),
            ),
        )
    return org, digest(token)


def redeem(token_hash, subject=None, email="New.Person@Example.org "):
    with psycopg.connect(RUNTIME) as conn:
        return conn.execute(
            "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'New Person',%s)",
            (token_hash, subject or str(uuid4()), email),
        ).fetchone()


def test_redeem_creates_user_membership_and_is_single_use():
    org, token_hash = seed()
    user_id, organization_id, reason = redeem(token_hash)
    assert reason is None and organization_id == org
    with psycopg.connect(MIGRATOR) as conn:
        roles = conn.execute(
            "SELECT roles FROM memberships WHERE user_id=%s AND organization_id=%s", (user_id, org)
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM invites WHERE token_hash=%s", (token_hash,)
        ).fetchone()[0]
        audited = conn.execute(
            "SELECT count(*) FROM audit_events WHERE organization_id=%s AND action='invite.redeemed'",
            (org,),
        ).fetchone()[0]
    assert roles == ["viewer"] and status == "REDEEMED" and audited == 1
    assert redeem(token_hash)[2] == "invalid"  # replay


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        (dict(hours=-1), "expired"),
        (dict(status="REVOKED"), "invalid"),
        (dict(status="PENDING_APPROVAL", roles=("org_admin",)), "not_approved"),
        (dict(email="someone.else@example.org"), "email_mismatch"),
    ],
)
def test_refusals(kwargs, reason):
    _, token_hash = seed(**kwargs)
    assert redeem(token_hash) == (None, None, reason)


def test_unknown_token_is_invalid():
    assert redeem(digest("not-a-token")) == (None, None, "invalid")


def test_existing_member_is_refused_and_roles_unchanged():
    org, token_hash = seed(roles=("auditor",))
    _, first = seed()
    subject = str(uuid4())
    redeem(first, subject)  # subject becomes a member of another org: allowed
    with psycopg.connect(MIGRATOR) as conn:
        uid = conn.execute("SELECT id FROM users WHERE subject=%s", (subject,)).fetchone()[0]
        conn.execute(
            "INSERT INTO memberships(organization_id,user_id,roles) VALUES (%s,%s,%s)",
            (org, uid, ["viewer"]),
        )
    assert redeem(token_hash, subject)[2] == "already_member"
    with psycopg.connect(MIGRATOR) as conn:
        assert conn.execute(
            "SELECT roles FROM memberships WHERE organization_id=%s AND user_id=%s", (org, uid)
        ).fetchone()[0] == ["viewer"]


def test_concurrent_redeem_yields_one_membership():
    org, token_hash = seed()
    with psycopg.connect(RUNTIME) as a, psycopg.connect(RUNTIME) as b:
        a.execute("BEGIN")
        first = a.execute(
            "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'A',%s)",
            (token_hash, str(uuid4()), "new.person@example.org"),
        ).fetchone()
        b.execute("SET lock_timeout='200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            b.execute(
                "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'B',%s)",
                (token_hash, str(uuid4()), "new.person@example.org"),
            )
        a.execute("COMMIT")
    assert first[2] is None
    assert redeem(token_hash)[2] == "invalid"


def test_runtime_role_cannot_bypass_function():
    org, token_hash = seed()
    with psycopg.connect(RUNTIME) as conn:
        conn.execute("SELECT set_config('app.org', %s, false)", (str(org),))
        for statement in [
            "UPDATE invites SET roles=ARRAY['org_admin']",
            "UPDATE invites SET email_normalized='x@y'",
            "DELETE FROM invites",
            "INSERT INTO users VALUES (gen_random_uuid(),'i','s','n')",
        ]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(statement)


def test_self_approval_blocked_by_check():
    org, token_hash = seed(status="PENDING_APPROVAL", roles=("approver",))
    with psycopg.connect(MIGRATOR) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE invites SET approver_id=inviter_id, status='ACTIVE' WHERE token_hash=%s",
            (token_hash,),
        )


def test_invite_usable_only_for_active_unexpired():
    _, active = seed()
    _, pending = seed(status="PENDING_APPROVAL", roles=("operator",))
    _, expired = seed(hours=-1)
    with psycopg.connect(RUNTIME) as conn:
        usable = [
            conn.execute("SELECT invite_usable(%s)", (h,)).fetchone()[0]
            for h in (active, pending, expired, digest("unknown"))
        ]
    assert usable == [True, False, False, False]
