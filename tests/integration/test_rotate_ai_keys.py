"""Phase 24 review fix: master-key rotation re-wraps users' AI provider keys too."""

import base64
import os

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from apps.api.app.config import Settings
from apps.api.app.secrets_envelope import key_id, open_envelope, seal
from scripts.manage import rotate_ai_keys
from tests.integration.test_ai_settings_db import session_for

load_dotenv()
pytestmark = pytest.mark.integration


def test_ai_keys_are_rewrapped_and_counted():
    old, new = (base64.b64encode(os.urandom(32)).decode() for _ in range(2))
    user, token = session_for()
    context = f"ai-key:{user}:anthropic"
    secret = "sk-ant-ROTATE-0123456789abcdefghij"  # secret-scan: allow - synthetic canary
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "SELECT ai_key_put(%s,'anthropic',%s,'ghij')",
            (token, Jsonb(seal(secret, old, context))),
        )
    operator = Settings(secret_master_key=new, secret_master_key_previous=[old])
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        assert rotate_ai_keys(conn, operator, user) == dict(rewrapped=1, current=0, unavailable=0)
        assert rotate_ai_keys(conn, operator, user)["current"] == 1
        assert rotate_ai_keys(conn, Settings(secret_master_key=old), user)["unavailable"] == 1
        envelope = conn.execute(
            "SELECT envelope FROM user_ai_keys WHERE user_id=%s", (user,)
        ).fetchone()[0]
    assert envelope["kid"] == key_id(new) and open_envelope(envelope, new, context) == secret
