"""Phase 22: one-time real organization bootstrap with a bootstrap org_admin invite."""

import os
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.security import digest
from scripts.manage import init_organization

load_dotenv()
pytestmark = pytest.mark.integration
MIGRATOR, RUNTIME = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]


def test_init_creates_org_env_and_bootstrap_invite_once():
    name = f"Init Test {uuid4().hex[:6]}"
    with psycopg.connect(MIGRATOR) as conn:
        made = init_organization(
            conn,
            name,
            "First.Admin@Example.org ",
            "first.approver@example.org",
            allow_additional=True,
        )
        with pytest.raises(SystemExit):
            init_organization(
                conn, name, "x@example.org", "y@example.org"
            )  # orgs exist; no --allow-additional
        org = made["organization_id"]
        assert conn.execute(
            "SELECT kind FROM environments WHERE organization_id=%s", (org,)
        ).fetchall() == [("PRODUCTION",)]
        token = made["invite_path"].rsplit("/", 1)[1]
        row = conn.execute(
            "SELECT status, roles, bootstrap, email_normalized FROM invites WHERE token_hash=%s",
            (digest(token),),
        ).fetchone()
    assert row == ("ACTIVE", ["org_admin"], True, "first.admin@example.org")
    with psycopg.connect(RUNTIME) as conn:
        result = conn.execute(
            "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'First Admin','first.admin@example.org')",
            (digest(token), str(uuid4())),
        ).fetchone()
    assert result[3] is None


def test_runtime_role_cannot_create_bootstrap_invites():
    with psycopg.connect(RUNTIME) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,digest,status,expires_at,bootstrap) "
            "VALUES (gen_random_uuid(),gen_random_uuid(),'a@b.c',ARRAY['org_admin'],'h',gen_random_uuid(),'d','ACTIVE',now(),true)"
        )


def test_synthetic_bootstrap_refuses_outside_development():
    import subprocess
    import sys

    env = dict(
        os.environ,
        DEVELOPMENT="false",
        SECURE_COOKIES="true",
        APP_ORIGIN="https://iam.example.com",
        OIDC_ISSUER_URL="https://idp.example.com/realms/identityguardian",
    )
    result = subprocess.run(
        [sys.executable, "scripts/manage.py", "bootstrap"], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "disabled outside development" in result.stderr


def test_init_issues_independent_approver_invite():
    name = f"Init Approver {uuid4().hex[:6]}"
    with psycopg.connect(MIGRATOR) as conn:
        with pytest.raises(SystemExit):
            init_organization(conn, name, "a@example.org", "A@Example.org", allow_additional=True)
        made = init_organization(
            conn, name, "admin@example.org", "approver@example.org", allow_additional=True
        )
    token = made["approver_invite_path"].rsplit("/", 1)[1]
    with psycopg.connect(RUNTIME) as conn:
        result = conn.execute(
            "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'Approver','approver@example.org')",
            (digest(token), str(uuid4())),
        ).fetchone()
    assert result[3] is None
    with psycopg.connect(MIGRATOR) as conn:
        roles = conn.execute(
            "SELECT roles FROM memberships WHERE user_id=%s", (result[0],)
        ).fetchone()[0]
    assert roles == ["approver"]
