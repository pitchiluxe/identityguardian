import os
import secrets
import time
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from apps.api.app.security import digest

load_dotenv()


@pytest.fixture
def tenant():
    org, other = str(uuid4()), str(uuid4())
    people = {}
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        for oid in (org, other):
            conn.execute("INSERT INTO organizations VALUES (%s,'Test organization')", (oid,))
        for name, roles in [
            ("admin", ["org_admin", "operator"]),
            ("approver", ["approver"]),
            ("viewer", ["viewer"]),
        ]:
            uid, token = str(uuid4()), secrets.token_urlsafe(32)
            csrf = digest("csrf:" + token)
            conn.execute("INSERT INTO users VALUES (%s,'test',%s,%s)", (uid, uid, name))
            conn.execute(
                "INSERT INTO memberships(organization_id,user_id,roles) VALUES(%s,%s,%s)",
                (org, uid, roles),
            )
            conn.execute(
                "INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,auth_time,amr) "
                "VALUES(%s,%s,%s,now()+interval '1 hour',%s,ARRAY['mfa'])",
                (digest(token), uid, digest(csrf), time.time()),
            )
            people[name] = dict(id=uid, token=token, csrf=csrf)
    return org, other, people


@pytest.fixture
def client():
    with TestClient(create_app(Settings()), base_url="http://localhost:8000") as value:
        yield value
