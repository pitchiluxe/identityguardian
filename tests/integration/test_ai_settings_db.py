"""Phase 24: AI settings tables and session-bound key functions (runtime role)."""

import os
import secrets
import time
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.security import digest

load_dotenv()
pytestmark = pytest.mark.integration
MIGRATOR, RUNTIME = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]


def session_for():
    uid, token = uuid4(), secrets.token_urlsafe(32)
    with psycopg.connect(MIGRATOR) as conn:
        conn.execute("INSERT INTO users VALUES (%s,'test',%s,'K')", (uid, str(uid)))
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,auth_time,amr) "
            "VALUES(%s,%s,'c',now()+interval '1 hour',%s,ARRAY['pwd'])",
            (digest(token), uid, time.time()),
        )
    return uid, token


def test_keys_are_bound_to_the_live_session():
    _, alice = session_for()
    _, bob = session_for()
    with psycopg.connect(RUNTIME) as conn:
        conn.execute("SELECT ai_key_put(%s,'anthropic','{\"ct\":\"x\"}','a1b2')", (alice,))
        assert conn.execute("SELECT ai_key_get(%s,'anthropic')", (alice,)).fetchone()[0] == {
            "ct": "x"
        }
        assert conn.execute("SELECT ai_key_get(%s,'anthropic')", (bob,)).fetchone()[0] is None
        assert conn.execute("SELECT * FROM ai_key_meta(%s)", (alice,)).fetchall() == [
            ("anthropic", "a1b2")
        ]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "SELECT ai_key_get(%s,'anthropic')", (digest(alice),)
            )  # hash is not a token
        assert conn.execute("SELECT ai_key_delete(%s,'anthropic')", (alice,)).fetchone()[0] is True


def test_runtime_role_cannot_touch_key_table():
    with psycopg.connect(RUNTIME) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM user_ai_keys")


def test_settings_defaults_and_provider_check():
    org = uuid4()
    with psycopg.connect(MIGRATOR) as conn:
        conn.execute("INSERT INTO organizations VALUES (%s,'AI test')", (org,))
        conn.execute("INSERT INTO organization_ai_settings(organization_id) VALUES (%s)", (org,))
        assert (
            conn.execute(
                "SELECT allow_hosted_ai FROM organization_ai_settings WHERE organization_id=%s",
                (org,),
            ).fetchone()[0]
            is False
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO user_ai_settings(organization_id,user_id,provider) "
                "VALUES (%s,%s,'gemini')",
                (org, uuid4()),
            )
