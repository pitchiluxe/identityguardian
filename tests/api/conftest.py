import os
import secrets
import time
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.db import Database
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
            ("investigator", ["investigator"]),
            ("reviewer", ["reviewer"]),
            ("auditor", ["auditor"]),
            ("operator", ["operator"]),
            ("approver2", ["approver"]),
            ("learner", ["learner"]),
            ("learner2", ["learner"]),
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


@pytest.fixture(scope="session")
def shared_db():
    # One pool per xdist worker. A fresh pool per test opened hundreds of backends, and PostgreSQL
    # backend startup on Windows under parallel load exceeded the connect timeout (Phase 19).
    db = Database(Settings().database_url)
    yield db
    db.close()


@pytest.fixture
def client(shared_db):
    settings = Settings(read_limit_per_minute=5000, write_limit_per_minute=1000)
    with TestClient(create_app(settings, db=shared_db), base_url="http://localhost:8000") as value:
        yield value


@pytest.fixture
def twin(client, tenant):
    """A LAB environment in the tenant organization loaded with the SYNTHETIC fixture."""
    org, other, people = tenant
    env, other_env = str(uuid4()), str(uuid4())
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute("INSERT INTO environments VALUES (%s,%s,'Test lab','LAB')", (env, org))
        conn.execute(
            "INSERT INTO environments VALUES (%s,%s,'Other lab','LAB')", (other_env, other)
        )
    base = f"/api/v1/organizations/{org}/environments/{env}"
    headers = as_user(client, people, "admin")
    seeded = client.post(base + "/sandbox/seed", json={"confirm_synthetic": True}, headers=headers)
    assert seeded.status_code == 200, seeded.text
    synced = client.post(base + "/connectors/sandbox/sync", json={"mode": "full"}, headers=headers)
    assert synced.status_code == 200, synced.text
    return dict(
        org=org,
        other=other,
        env=env,
        other_env=other_env,
        people=people,
        base=base,
        headers=headers,
    )


def as_user(client, people, name):
    user = people[name]
    client.cookies.set("ig_session", user["token"])
    return {"Origin": "http://localhost:8000", "X-CSRF-Token": user["csrf"]}
