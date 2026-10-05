# Invite-based Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An invited person registers their own Keycloak credentials (password and TOTP) and signs in with exactly the role an org admin invited them with. Privileged invites need an independent approver.

**Architecture:**
- New RLS-scoped `invites` table plus a narrow `SECURITY DEFINER` function, `redeem_invite`, which is the only runtime path that creates users and memberships from an invite.
- New router `routes/invites.py` for create, list, decide and revoke. A public `GET /api/v1/auth/register` stores the invite hash in the server-side login attempt and redirects to Keycloak's `/registrations`. The existing callback redeems the invite when the attempt carries one.
- Web: an Invites panel under Administration, plus an `/invite/<token>` landing view.

**Tech Stack:** FastAPI, psycopg 3, PostgreSQL 17 RLS, Keycloak 26 (local), React 19 + Vite, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-invite-registration-design.md`

## Global Constraints

- Exactly one role per invite, from `viewer, investigator, reviewer, approver, operator, org_admin, auditor, learner`.
- Privileged roles are exactly `org_admin, approver, operator`. They start `PENDING_APPROVAL`; every other role starts `ACTIVE`.
- Invites expire 72 hours after creation. The token is 32 random bytes (`secrets.token_urlsafe(32)`). Only `digest(token)` (SHA-256 hex) is stored.
- The link `/invite/<token>` is returned only in the create response, never by list or any other route.
- Approver ≠ inviter, enforced by the API (403) and a DB CHECK. Approval needs `members:approve` and recent MFA (`require_recent_mfa`), and the digest must match.
- Refusal reasons are exactly `invalid`, `expired`, `not_approved`, `email_mismatch`, `already_member`.
- Keycloak password policy is `length(12) and notUsername`. `CONFIGURE_TOTP` is a default required action for new users.
- Email sending stays PLANNED. Never claim email verification locally.
- Runtime code never uses the migration URL. Schema changes go in `migrations/023_invites.sql` with matching grants.
- Every new public or protected route is declared in `tests/security/test_authorization_matrix.py`.

## Review Focus

1. Mixed-case or space-padded email in the invite or the token claim must still match. Normalize with `strip().lower()` on both sides (pinned in Task 1).
2. An invitee who opens the link while already signed in as a different existing user is redeemed as that signed-in subject only after a fresh IdP login, never via the old session (pinned in Task 3: register always forces a new OIDC round trip).
3. Two browsers redeeming the same token concurrently: exactly one membership (pinned in Task 1 via the `FOR UPDATE` row lock test).
4. An invite approved after it expired cannot become usable (pinned in Task 2: decision on an expired invite returns 409).
5. A token with surrounding whitespace or URL-encoding from copy/paste still resolves. The landing page trims the token, and an invalid token gets the generic page (pinned in Task 3).

---

### Task 1: Schema, grants and `redeem_invite`

**Files:**
- Create: `migrations/023_invites.sql`
- Test: `tests/integration/test_invites_db.py`

**Interfaces:**
- Produces: table `invites`; column `login_attempts.invite_hash`; SQL function `redeem_invite(p_hash text, p_issuer text, p_subject text, p_name text, p_email text) RETURNS TABLE(user_id uuid, organization_id uuid, reason text)`. `reason` is NULL on success.

- [ ] **Step 1: Write the failing test**

```python
"""Phase 21: invites table, grants and redeem_invite (runtime role)."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from apps.api.app.security import digest

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
    first, _ = seed()
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest -n 0 tests/integration/test_invites_db.py -q`
Expected: FAIL, `relation "invites" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- Phase 21: invite-based registration. Credentials stay at the IdP; access comes only from an
-- invite. redeem_invite is the only runtime path that creates users/memberships from an invite.
CREATE TABLE invites (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 email_normalized text NOT NULL CHECK (email_normalized = lower(btrim(email_normalized)) AND email_normalized LIKE '%_@_%'),
 roles text[] NOT NULL CHECK (cardinality(roles) = 1 AND roles <@ ARRAY['viewer','investigator','reviewer','approver','operator','org_admin','auditor','learner']),
 token_hash text NOT NULL UNIQUE, inviter_id uuid NOT NULL REFERENCES users,
 approver_id uuid REFERENCES users, approved_at timestamptz, digest text NOT NULL,
 justification text NOT NULL DEFAULT '',
 status text NOT NULL CHECK (status IN ('PENDING_APPROVAL','ACTIVE','REDEEMED','REVOKED')),
 expires_at timestamptz NOT NULL, redeemed_by uuid REFERENCES users, redeemed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (approver_id IS NULL OR approver_id <> inviter_id)
);
CREATE INDEX invites_scope ON invites(organization_id, created_at DESC);
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant ON invites USING (organization_id = nullif(current_setting('app.org', true), '')::uuid)
 WITH CHECK (organization_id = nullif(current_setting('app.org', true), '')::uuid);
GRANT SELECT, INSERT ON invites TO guardian_app;
GRANT UPDATE (status, approver_id, approved_at) ON invites TO guardian_app;

ALTER TABLE login_attempts ADD COLUMN invite_hash text;

ALTER TABLE outbox DROP CONSTRAINT IF EXISTS outbox_event_type_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_event_type_check
 CHECK (event_type IN ('role_change_recorded','change_execution_requested','connector_sync_requested','invite_recorded'));

CREATE FUNCTION redeem_invite(p_hash text, p_issuer text, p_subject text, p_name text, p_email text)
RETURNS TABLE(user_id uuid, organization_id uuid, reason text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE inv invites%ROWTYPE; uid uuid;
BEGIN
 SELECT * INTO inv FROM invites i WHERE i.token_hash = p_hash FOR UPDATE;
 IF NOT FOUND OR inv.status IN ('REDEEMED','REVOKED') THEN RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'invalid'; RETURN; END IF;
 IF inv.expires_at <= now() THEN RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'expired'; RETURN; END IF;
 IF inv.status <> 'ACTIVE' THEN RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'not_approved'; RETURN; END IF;
 IF lower(btrim(coalesce(p_email, ''))) <> inv.email_normalized THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'email_mismatch'; RETURN; END IF;
 SELECT u.id INTO uid FROM users u WHERE u.issuer = p_issuer AND u.subject = p_subject;
 IF uid IS NULL THEN
  uid := gen_random_uuid();
  INSERT INTO users VALUES (uid, p_issuer, p_subject, left(coalesce(nullif(btrim(p_name), ''), inv.email_normalized), 200));
 ELSIF EXISTS (SELECT 1 FROM memberships m WHERE m.organization_id = inv.organization_id AND m.user_id = uid) THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'already_member'; RETURN;
 END IF;
 INSERT INTO memberships(organization_id, user_id, roles) VALUES (inv.organization_id, uid, inv.roles);
 UPDATE invites SET status = 'REDEEMED', redeemed_by = uid, redeemed_at = now() WHERE id = inv.id;
 INSERT INTO audit_events(id, organization_id, actor_id, action, target, after_state, justification, approval_id, result, correlation_id)
 VALUES (gen_random_uuid(), inv.organization_id, uid, 'invite.redeemed', inv.id::text,
         jsonb_build_object('roles', inv.roles), 'Invitee registered and accepted the invite', inv.id, 'succeeded', gen_random_uuid());
 RETURN QUERY SELECT uid, inv.organization_id, NULL::text;
END $$;
REVOKE ALL ON FUNCTION redeem_invite(text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION redeem_invite(text, text, text, text, text) TO guardian_app;
```

Before writing it, check the real outbox constraint name with `SELECT conname FROM pg_constraint WHERE conrelid='outbox'::regclass AND contype='c'` (migration 016 recreated it) and the existing tenant policy expression in `001_foundation.sql`, then copy both exactly.

- [ ] **Step 4: Apply and run tests**

Run: `.venv/Scripts/python scripts/manage.py migrate && .venv/Scripts/python -m pytest -n 0 tests/integration/test_invites_db.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add migrations/023_invites.sql tests/integration/test_invites_db.py
git commit -m "feat(invites): schema, grants and redeem_invite"
```

### Task 2: Invite management API

**Files:**
- Create: `apps/api/app/routes/invites.py`
- Modify: `apps/api/app/routes/__init__.py` (register `invites.router`)
- Test: `tests/api/test_invites.py`

**Interfaces:**
- Consumes: `scoped()` and `Scope.audit()` from `scope.py`; `digest`, `require_recent_mfa`, `capabilities` from `security.py`; `authenticate`, `membership` from `auth.py`.
- Produces: `PRIVILEGED = {"org_admin", "approver", "operator"}`; `invite_digest(org, email, role, expires_at_iso) -> str`; routes `POST/GET /api/v1/organizations/{org}/invites`, `POST .../invites/{id}/decision`, `POST .../invites/{id}/revoke`. The create response is `{"data": {"invite": {...}, "link": "/invite/<token>"}}`.

- [ ] **Step 1: Write the failing tests**

```python
"""Phase 21: invite management API."""

from uuid import uuid4

from tests.api.conftest import as_user


def create(client, org, people, role="viewer", user="admin", status=201, email="pat@example.org"):
    headers = as_user(client, people, user)
    response = client.post(
        f"/api/v1/organizations/{org}/invites",
        headers=headers,
        json=dict(email=email, role=role, justification="New analyst joining the team"),
    )
    assert response.status_code == status, response.text
    return response.json()["data"] if status == 201 else response


def test_create_returns_link_once_and_list_never_does(client, tenant):
    org, _, people = tenant
    made = create(client, org, people)
    assert made["link"].startswith("/invite/") and len(made["link"]) > 40
    assert made["invite"]["status"] == "ACTIVE" and made["invite"]["roles"] == ["viewer"]
    as_user(client, people, "admin")
    listing = client.get(f"/api/v1/organizations/{org}/invites").text
    assert made["link"].split("/")[-1] not in listing and "token" not in listing


def test_privileged_invite_needs_independent_mfa_approval(client, tenant):
    org, _, people = tenant
    made = create(client, org, people, role="org_admin")["invite"]
    assert made["status"] == "PENDING_APPROVAL"
    url = f"/api/v1/organizations/{org}/invites/{made['id']}/decision"
    body = dict(digest=made["digest"], decision="APPROVE")
    assert client.post(url, headers=as_user(client, people, "admin"), json=body).status_code == 403
    stale = dict(digest="0" * 64, decision="APPROVE")
    assert (
        client.post(url, headers=as_user(client, people, "approver"), json=stale).status_code == 409
    )
    ok = client.post(url, headers=as_user(client, people, "approver"), json=body)
    assert ok.status_code == 200 and ok.json()["data"]["status"] == "ACTIVE"
    again = client.post(url, headers=as_user(client, people, "approver2"), json=body)
    assert again.status_code == 409


def test_only_admins_create_and_cross_tenant_is_hidden(client, tenant):
    org, other, people = tenant
    for user in ["viewer", "investigator", "approver", "auditor"]:
        create(client, org, people, user=user, status=403)
    made = create(client, org, people)["invite"]
    headers = as_user(client, people, "admin")
    assert client.post(
        f"/api/v1/organizations/{other}/invites/{made['id']}/revoke", headers=headers
    ).status_code in (403, 404)
    assert (
        client.post(
            f"/api/v1/organizations/{org}/invites/{uuid4()}/revoke", headers=headers
        ).status_code
        == 404
    )


def test_revoke_and_validation(client, tenant):
    org, _, people = tenant
    made = create(client, org, people)["invite"]
    headers = as_user(client, people, "admin")
    url = f"/api/v1/organizations/{org}/invites/{made['id']}/revoke"
    assert client.post(url, headers=headers).json()["data"]["status"] == "REVOKED"
    assert client.post(url, headers=headers).status_code == 409
    create(client, org, people, role="superuser", status=422)
    create(client, org, people, email="not-an-email", status=422)


def test_decision_on_expired_invite_is_refused(client, tenant):
    import os

    import psycopg

    org, _, people = tenant
    made = create(client, org, people, role="operator")["invite"]
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE invites SET expires_at=now()-interval '1 minute' WHERE id=%s", (made["id"],)
        )
    response = client.post(
        f"/api/v1/organizations/{org}/invites/{made['id']}/decision",
        headers=as_user(client, people, "approver"),
        json=dict(digest=made["digest"], decision="APPROVE"),
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -n 0 tests/api/test_invites.py -q`
Expected: FAIL with 404 on `/invites`.

- [ ] **Step 3: Implement `routes/invites.py`**

```python
"""Phase 21: invites. Access comes only from an invite; privileged invites need an approver."""

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
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
COLUMNS = (
    "id, email_normalized, roles, inviter_id, approver_id, approved_at, digest, justification, "
    "status, expires_at, redeemed_by, redeemed_at, created_at"
)  # never token_hash


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
            f"INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,"
            f"digest,justification,status,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            f"RETURNING {COLUMNS}",
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
            f"SELECT {COLUMNS} FROM invites ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        return envelope(scope, rows)


def locked(scope, identifier):
    row = scope.conn.execute(
        f"SELECT {COLUMNS} FROM invites WHERE id=%s FOR UPDATE", (identifier,)
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
            f"UPDATE invites SET status='ACTIVE', approver_id=%s, approved_at=now() WHERE id=%s "
            f"RETURNING {COLUMNS}",
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
            f"UPDATE invites SET status='REVOKED' WHERE id=%s RETURNING {COLUMNS}", (identifier,)
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
```

Check that `scope.user` exposes `amr` and `auth_time` (the dict from `authenticate`). It does in `main.py`'s `mfa(user)`. Ruff format afterwards: the multi-value tuples above are compressed for the plan.

- [ ] **Step 4: Register router and run tests**

In `routes/__init__.py`, add `invites` to the import list and `invites.router` to `ROUTERS`.
Run: `.venv/Scripts/python -m pytest -n 0 tests/api/test_invites.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routes/invites.py apps/api/app/routes/__init__.py tests/api/test_invites.py
git commit -m "feat(invites): create, list, approve and revoke API"
```

### Task 3: Registration start and callback redemption

**Files:**
- Modify: `apps/api/app/auth.py` (`begin_login` gains an optional invite; new `begin_registration`; `complete_login` redeems)
- Modify: `apps/api/app/main.py` (route `GET /api/v1/auth/register`)
- Test: `tests/api/test_invite_login.py`

**Interfaces:**
- Consumes: `redeem_invite` (Task 1); `/invites` create (Task 2) for fixtures.
- Produces: `GET /api/v1/auth/register?invite=<token>` → 302 to `{issuer}/protocol/openid-connect/registrations?...`, or 303 to `/invite/invalid` when the token is unusable. The callback creates a session for a redeemed invitee, or returns 403 with the fixed messages from the spec.

- [ ] **Step 1: Write the failing tests**

Reuse the mock-IdP pattern from `tests/api/test_oidc.py`. Put a helper `fake_idp(monkeypatch, settings, params, claims)` in the test file. It signs `claims` with a fresh RSA key and patches `httpx.Client` with a `MockTransport` serving `/token` and `/certs`. Copy the body of `test_signed_callback_rotates_session_ignores_role_claims_and_rejects_replay` lines 28–67 into the helper, parameterized by `claims`.

```python
"""Phase 21: registration through an invite, redeemed at the OIDC callback."""

import os
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg

from apps.api.app.config import Settings
from tests.api.test_invites import create
from tests.api.test_oidc_support import fake_idp  # helper extracted from test_oidc.py


def start(client, token):
    client.cookies.clear()
    response = client.get(f"/api/v1/auth/register?invite={token}", follow_redirects=False)
    return response, parse_qs(urlparse(response.headers.get("location", "")).query)


def claims(settings, params, subject, email="pat@example.org", **extra):
    now = int(time.time())
    return dict(
        iss=settings.oidc_issuer_url,
        aud=settings.oidc_client_id,
        sub=subject,
        nonce=params["nonce"][0],
        exp=now + 300,
        iat=now,
        auth_time=now,
        amr=["pwd", "otp"],
        email=email,
        name="Pat Example",
        **extra,
    )


def test_invitee_registers_and_gets_exactly_the_invited_role(client, tenant, monkeypatch):
    org, _, people = tenant
    link = create(client, org, people, role="investigator")["link"]
    response, params = start(client, link.split("/")[-1])
    assert (
        response.status_code == 302
        and "/protocol/openid-connect/registrations" in response.headers["location"]
    )
    assert params["scope"] == ["openid profile email"]
    settings, subject = Settings(), str(uuid4())
    fake_idp(monkeypatch, settings, params, claims(settings, params, subject, roles=["org_admin"]))
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 303
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        roles = conn.execute(
            "SELECT m.roles FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE u.subject=%s AND m.organization_id=%s",
            (subject, org),
        ).fetchone()[0]
    assert roles == ["investigator"]  # token role claims ignored
    assert client.get("/api/v1/session").status_code == 200


def test_invalid_tokens_get_generic_page_without_idp_state(client):
    for token in ["nope", " ", "%20" + "a" * 43]:
        response, _ = start(client, token)
        assert response.status_code == 303 and response.headers["location"] == "/invite/invalid"
        assert "ig_login" not in response.headers.get("set-cookie", "")


def test_email_mismatch_is_refused_with_fixed_message(client, tenant, monkeypatch):
    org, _, people = tenant
    link = create(client, org, people)["link"]
    _, params = start(client, link.split("/")[-1])
    settings = Settings()
    fake_idp(
        monkeypatch,
        settings,
        params,
        claims(settings, params, str(uuid4()), email="other@example.org"),
    )
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 403
    assert done.json()["detail"] == "Sign in with the email address the invite was sent to"


def test_unknown_subject_without_invite_still_refused(client, monkeypatch):
    client.cookies.clear()
    redirect = client.get("/api/v1/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(redirect.headers["location"]).query)
    settings = Settings()
    fake_idp(monkeypatch, settings, params, claims(settings, params, str(uuid4())))
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 403
    assert done.json()["detail"] == "This identity has not been provisioned for the platform"
```

Also extract `fake_idp` from `test_oidc.py` into `tests/api/test_oidc_support.py`, keeping `test_oidc.py` passing by importing it there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -n 0 tests/api/test_invite_login.py -q`
Expected: FAIL, 404 for `/api/v1/auth/register`.

- [ ] **Step 3: Implement in `auth.py`**

Refactor `begin_login(request)` into `_begin(request, endpoint="auth", invite_hash=None)`, keeping all current behavior and storing `invite_hash` in the `login_attempts` insert (add the column to the INSERT list). `begin_login` calls `_begin(request)`. Add:

```python
REFUSALS = {
    "invalid": "This invite is no longer valid — ask your administrator for a new one",
    "expired": "This invite is no longer valid — ask your administrator for a new one",
    "not_approved": "This invite is no longer valid — ask your administrator for a new one",
    "email_mismatch": "Sign in with the email address the invite was sent to",
    "already_member": "You are already a member of this organization",
}


def begin_registration(request: Request, invite: str = ""):
    token = invite.strip()
    usable = False
    if 20 <= len(token) <= 128:
        with request.app.state.db.transaction() as conn:
            usable = conn.execute("SELECT invite_usable(%s) AS ok", (digest(token),)).fetchone()[
                "ok"
            ]
    if not usable:
        return RedirectResponse(
            "/invite/invalid", status_code=303
        )  # same response for every failure
    return _begin(request, endpoint="registrations", invite_hash=digest(token))
```

`invite_usable(p_hash text) RETURNS boolean` is a second narrow `SECURITY DEFINER` function: true only for an `ACTIVE`, unexpired invite. Add it to `023_invites.sql` in Task 1 with the same REVOKE/GRANT pattern, and add `assert` coverage for it in `test_invites_db.py`. Change `scope` in `params` to `"openid profile email"` for both flows. When `endpoint == "registrations"`, use the URL path `/protocol/openid-connect/registrations`.

In `complete_login`, replace the `if not user: raise HTTPException(403, ...)` block with:

```python
if attempt.get("invite_hash"):
    redeemed = conn.execute(
        "SELECT * FROM redeem_invite(%s,%s,%s,%s,%s)",
        (
            attempt["invite_hash"],
            claims["iss"],
            claims["sub"],
            str(claims.get("name") or claims.get("preferred_username") or ""),
            str(claims.get("email") or ""),
        ),
    ).fetchone()
    if redeemed["reason"]:
        logging.getLogger("identityguardian").info("Invite refused: %s", redeemed["reason"])
        raise HTTPException(403, REFUSALS[redeemed["reason"]])
    user = {"id": redeemed["user_id"]}
elif not user:
    raise HTTPException(403, "This identity has not been provisioned for the platform")
```

Note: the 403 raised inside `db.transaction()` rolls back nothing that the function committed, because the function runs in the same transaction and refusals write nothing. Only the success path writes.

- [ ] **Step 4: Wire the route and run tests**

In `main.py`, next to the login routes: `app.get("/api/v1/auth/register")(begin_registration)`. Add `/api/v1/auth/register` to `PUBLIC` in `tests/security/test_authorization_matrix.py`.
Run: `.venv/Scripts/python -m pytest -n 0 tests/api/test_invite_login.py tests/api/test_oidc.py tests/security -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/auth.py apps/api/app/main.py migrations/023_invites.sql tests/api/test_invite_login.py tests/api/test_oidc_support.py tests/api/test_oidc.py tests/integration/test_invites_db.py tests/security/test_authorization_matrix.py
git commit -m "feat(invites): registration start and callback redemption"
```

### Task 4: Local Keycloak registration settings

**Files:**
- Modify: `scripts/local_setup.py` (new realms: `registrationAllowed=True`, `passwordPolicy`, `requiredActions` default)
- Modify: `scripts/provision_local_users.py` (add `configure_registration(client, headers)`, called where `configure_amr` is)

- [ ] **Step 1: Implement `configure_registration`**

```python
def configure_registration(client, headers):
    """Self-registration for invitees: own password (policy) and mandatory TOTP enrolment.
    Access is still granted only by an invite in the platform."""
    admin = f"{KEYCLOAK}/admin/realms/{REALM}"
    realm = client.get(admin, headers=headers).json()
    realm.update(registrationAllowed=True, passwordPolicy="length(12) and notUsername")
    client.put(admin, headers=headers, json=realm).raise_for_status()
    action = client.get(
        f"{admin}/authentication/required-actions/CONFIGURE_TOTP", headers=headers
    ).json()
    action.update(enabled=True, defaultAction=True)
    client.put(
        f"{admin}/authentication/required-actions/CONFIGURE_TOTP", headers=headers, json=action
    ).raise_for_status()
```

In `local_setup.py`, set `registrationAllowed=True` and add `passwordPolicy="length(12) and notUsername"` to the realm dict. Existing users keep `requiredActions=[]`.

- [ ] **Step 2: Apply to the running realm and verify**

Run: `.venv/Scripts/python scripts/provision_local_users.py` (Keycloak on :58080).
Verify: `GET http://localhost:58080/realms/identityguardian/protocol/openid-connect/registrations?client_id=identityguardian&response_type=code&scope=openid&redirect_uri=http://localhost:8000/api/v1/auth/callback` returns 200 with a registration form (`id="kc-register-form"`).

- [ ] **Step 3: Commit**

```bash
git add scripts/local_setup.py scripts/provision_local_users.py
git commit -m "feat(invites): local Keycloak self-registration with mandatory TOTP"
```

### Task 5: Web — Invites panel and invite landing page

**Files:**
- Create: `apps/web/src/pages/Invites.tsx`
- Modify: `apps/web/src/pages/index.tsx` (render `<Invites>` inside Administration when `members:read`)
- Modify: `apps/web/src/App.tsx` (`InviteLanding` when `location.pathname` starts with `/invite/`)
- Modify: `apps/api/app/main.py` (serve `index.html` for `/invite/{token}` so deep links work)

- [ ] **Step 1: Implement `Invites.tsx`**

```tsx
import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { api } from '../api';
import type { Session } from '../api';

type Invite = { id: string; email_normalized: string; roles: string[]; status: string; digest: string; inviter_id: string; expires_at: string; justification: string };
const roles = ['viewer', 'investigator', 'reviewer', 'auditor', 'learner', 'operator', 'approver', 'org_admin'];
const privileged = new Set(['operator', 'approver', 'org_admin']);

export function Invites({ org, session, can }: { org: string; session: Session; can: (c: string) => boolean }) {
  const [items, setItems] = useState<Invite[]>([]); const [email, setEmail] = useState(''); const [role, setRole] = useState('viewer');
  const [reason, setReason] = useState(''); const [link, setLink] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const base = `/organizations/${org}/invites`;
  const refresh = () => api<{ data: Invite[] }>(base).then(r => setItems(r.data)).catch(e => setError(e.message));
  useEffect(() => { refresh(); }, [org]);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(''); try { await fn(); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const submit = (e: React.FormEvent) => { e.preventDefault(); act(async () => {
    const r = await api<{ data: { link: string } }>(base, 'POST', { email, role, justification: reason }, session.csrf_token);
    setLink(window.location.origin + r.data.link); setEmail(''); setReason(''); }); };
  const status = (i: Invite) => (['ACTIVE', 'PENDING_APPROVAL'].includes(i.status) && new Date(i.expires_at) < new Date()) ? 'EXPIRED' : i.status;
  return <section className="panel"><div className="section-heading"><h2>Invites</h2><span>Invitees register their own password and one-time code</span></div><div className="pad">
    {can('members:propose') && <form className="proposal" onSubmit={submit}><div className="form-grid">
      <label>Email<input className="text-input" type="email" required value={email} onChange={e => setEmail(e.target.value)}/></label>
      <label>Role<select value={role} onChange={e => setRole(e.target.value)}>{roles.map(r => <option key={r}>{r}</option>)}</select></label></div>
      {privileged.has(role) && <p className="muted">Privileged role: an independent approver must approve before the link works.</p>}
      <label>Justification<textarea required minLength={8} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>
      <button className="primary" disabled={busy}>Create invite</button></form>}
    {link && <div className="notice" role="status"><Check size={16}/><span>Copy this link now — it is shown only once and expires in 72 hours. Email delivery is planned, not implemented.</span>
      <code className="block">{link}</code><button className="secondary" onClick={() => navigator.clipboard?.writeText(link)}><Copy size={15}/> Copy link</button></div>}
    {error && <p className="error" role="alert">{error}</p>}
    {items.length === 0 ? <p className="empty-text">No invites yet.</p> : <div className="table-scroll"><table><thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Expires</th><th/></tr></thead><tbody>
      {items.map(i => <tr key={i.id}><td>{i.email_normalized}</td><td>{i.roles.join(', ')}</td><td><span className="pill">{status(i)}</span></td><td>{new Date(i.expires_at).toLocaleString()}</td><td className="button-row">
        {status(i) === 'PENDING_APPROVAL' && can('members:approve') && i.inviter_id !== session.user.id && <button className="secondary" disabled={busy} onClick={() => act(() => api(`${base}/${i.id}/decision`, 'POST', { digest: i.digest, decision: 'APPROVE' }, session.csrf_token))}>Approve</button>}
        {['ACTIVE', 'PENDING_APPROVAL'].includes(status(i)) && can('members:propose') && <button className="secondary" disabled={busy} onClick={() => act(() => api(`${base}/${i.id}/revoke`, 'POST', undefined, session.csrf_token))}>Revoke</button>}
      </td></tr>)}</tbody></table></div>}
  </div></section>;
}
```

- [ ] **Step 2: Landing page in `App.tsx`**

Before the `/session` effect, check `const inviteToken = window.location.pathname.match(/^\/invite\/([^/]+)$/)?.[1];`. If `inviteToken` is set and there's no session, render:

```tsx
function InviteLanding({ token }: { token: string }) {
  const invalid = token === 'invalid';
  return <div className="entry"><header><Brand/><span className="pill">{BUILD_LABEL}</span></header><main className="entry-grid"><section className="entry-copy">
    <h1>{invalid ? 'This invite cannot be used' : "You've been invited"}</h1>
    <p className="entry-description">{invalid ? 'It may have expired, been used or been revoked. Ask your administrator for a new invite.' : 'Create your own account with a password and an authenticator app. Your access is set by the invite.'}</p>
    {!invalid && <><a className="primary login" href={`/api/v1/auth/register?invite=${encodeURIComponent(token.trim())}`}>Create account <ArrowUpRight size={18}/></a>
      <a className="secondary" href="/api/v1/auth/login">I already have an account</a></>}
  </section></main></div>;
}
```

"I already have an account" for an existing user of another organization is out of scope for this iteration. That user signs in and asks the admin. Mention this in the landing copy only if a reviewer asks; the spec lists cross-org redemption via the register flow, which still works because Keycloak shows a login link on the registration page.

In `main.py`, before mounting static files, add `@app.get("/invite/{token}")` returning `FileResponse(web / "index.html")` when `web` exists. It is exempt from auth and serves only static HTML.

- [ ] **Step 3: Build and type-check**

Run: `node "C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js" run build`
Expected: `✓ built`.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Invites.tsx apps/web/src/pages/index.tsx apps/web/src/App.tsx apps/api/app/main.py
git commit -m "feat(invites): invites panel and invite landing page"
```

### Task 6: End-to-end, threat model and docs

**Files:**
- Create: `tests/e2e/invite.spec.ts`
- Modify: `THREAT_MODEL.md`, `docs/plans/phase-21-invites.md` (new ledger), `CLAUDE.md` (status line)

- [ ] **Step 1: E2E test**

```ts
import { test, expect } from '@playwright/test';
import { signIn, open, totp } from './helpers';

test('invitee registers own credentials and lands with the invited role', async ({ page, browser }) => {
  await signIn(page, 'alex');
  await open(page, 'Administration');
  const email = `e2e.${Date.now()}@example.org`;
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Role').selectOption('viewer');
  await page.getByLabel('Justification').fill('SYNTHETIC end-to-end invitee');
  await page.getByRole('button', { name: 'Create invite' }).click();
  const link = await page.locator('.notice code').innerText();
  const invitee = await (await browser.newContext()).newPage();
  await invitee.goto(link);
  await invitee.getByRole('link', { name: 'Create account' }).click();
  const username = `e2e${Date.now()}`;
  await invitee.locator('#username').fill(username);
  await invitee.locator('#email').fill(email);
  await invitee.locator('#firstName').fill('Synthetic');
  await invitee.locator('#lastName').fill('Invitee');
  await invitee.locator('#password').fill('Synthetic-Pass-2026!');
  await invitee.locator('#password-confirm').fill('Synthetic-Pass-2026!');
  await invitee.getByRole('button', { name: /register/i }).click();
  await invitee.getByRole('link', { name: /unable to scan/i }).click();
  const seed = (await invitee.locator('#kc-totp-secret-key').innerText()).replace(/\s/g, '');
  // The displayed key is base32 of the secret's UTF-8 bytes; decode to the raw secret for totp().
  const raw = Buffer.from(base32Decode(seed)).toString('utf8');
  await invitee.locator('#totp').fill(totp(raw));
  await invitee.getByRole('button', { name: /submit/i }).click();
  await expect(invitee.getByRole('heading', { name: 'Your identity workspace' })).toBeVisible({ timeout: 20000 });
});

function base32Decode(s: string) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = ''; const out: number[] = [];
  for (const c of s.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0');
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Uint8Array.from(out);
}
```

The Keycloak TOTP setup page's element ids (`#kc-totp-secret-key`, `#totp`) must be checked against the running Keycloak 26.7 theme. Run with `--headed` once and adjust selectors to what is actually rendered.

Run: `npx playwright test tests/e2e/invite.spec.ts` (API on :8000 with fresh build, Keycloak, bootstrap)
Expected: 1 passed.

- [ ] **Step 2: Threat model and ledger**

Add a THREAT_MODEL.md row "Invite registration (Phase 21)" containing the spec's Security table and the residual risk "possession of the link is the factor until email verification exists". Create `docs/plans/phase-21-invites.md` with a short bounded plan pointing to the spec and this plan, and a verification ledger recording actual command output.

- [ ] **Step 3: Full verification**

Run: `.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check . && .venv/Scripts/python -m pytest -q && npx playwright test`
Expected: all pass. Record the real counts in the ledger, including any flake with its cause.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/invite.spec.ts THREAT_MODEL.md docs/plans/phase-21-invites.md CLAUDE.md
git commit -m "test(invites): end-to-end registration; threat model and ledger"
```
