"""Phase 23: registering a read-only Entra ID connector and syncing it through the worker."""

import base64
import os
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.connectors import entra
from apps.api.app.db import Database
from apps.api.app.main import create_app
from apps.worker.main import process_one
from tests.api.conftest import as_user
from tests.api.test_production_profile import PROD
from tests.unit.test_entra_connector import CLIENT, SECRET, TENANT, FakeMicrosoft

BODY = dict(
    kind="entra", name="Entra demo tenant", tenant_id=TENANT, client_id=CLIENT, client_secret=SECRET
)


@pytest.fixture(autouse=True)
def master_key(client):
    client.app.state.settings.secret_master_key = base64.b64encode(os.urandom(32)).decode()


def sandbox_env(org):
    env = uuid4()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "INSERT INTO environments(id,organization_id,name,kind) VALUES (%s,%s,'Entra demo','SANDBOX')",
            (env, org),
        )
    return env


def create(client, twin, env, who="admin", body=BODY):
    headers = as_user(client, twin["people"], who)
    return client.post(
        f"/api/v1/organizations/{twin['org']}/environments/{env}/connectors",
        headers=headers,
        json=body,
    )


def test_registration_seals_secret_and_never_returns_it(client, twin):
    env = sandbox_env(twin["org"])
    response = create(client, twin, env)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["kind"] == "entra" and data["has_secret"] is True and SECRET not in response.text
    assert data["config"] == {"tenant_id": TENANT, "client_id": CLIENT}
    as_user(client, twin["people"], "admin")
    listing = client.get(f"/api/v1/organizations/{twin['org']}/environments/{env}/connectors").text
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        audit = conn.execute(
            "SELECT string_agg(after_state::text, ' ') FROM audit_events WHERE organization_id=%s",
            (twin["org"],),
        ).fetchone()[0]
        stored = conn.execute(
            "SELECT secret_envelope::text FROM connectors WHERE id=%s", (data["id"],)
        ).fetchone()[0]
    assert SECRET not in listing and SECRET not in (audit or "") and SECRET not in stored


def test_registration_rules(client, twin):
    env = sandbox_env(twin["org"])
    assert create(client, twin, twin["env"]).status_code == 409  # LAB: training only
    assert create(client, twin, env, who="viewer").status_code == 403
    assert create(client, twin, env, body=dict(BODY, tenant_id="evil.example")).status_code == 422
    assert create(client, twin, env, body=dict(BODY, client_secret="")).status_code == 422


def test_entra_allowed_in_production_mode_while_mocks_are_not(shared_db, twin):
    env = sandbox_env(twin["org"])
    settings = Settings(**PROD, secret_master_key=base64.b64encode(os.urandom(32)).decode())
    with TestClient(create_app(settings, db=shared_db), base_url="https://iam.example.com") as prod:
        headers = as_user(prod, twin["people"], "admin")
        headers["Origin"] = "https://iam.example.com"
        url = f"/api/v1/organizations/{twin['org']}/environments/{env}/connectors"
        assert prod.post(url, headers=headers, json=BODY).status_code == 201
        mock = dict(
            kind="mock_entra",
            name="Mock directory",
            endpoint="mock://mock_entra/x",
            authoritative=True,
        )
        assert prod.post(url, headers=headers, json=mock).status_code == 422


def test_worker_sync_ingests_the_tenant_with_the_decrypted_secret(client, twin, monkeypatch):
    env = sandbox_env(twin["org"])
    connector = create(client, twin, env).json()["data"]
    got = []
    real = entra.EntraConnector

    def factory(config, client_secret, http=None):
        got.append(client_secret)
        return real(
            config, client_secret, http=httpx.Client(transport=httpx.MockTransport(FakeMicrosoft()))
        )

    monkeypatch.setattr(entra, "EntraConnector", factory)
    monkeypatch.setenv("SECRET_MASTER_KEY", client.app.state.settings.secret_master_key)
    headers = as_user(client, twin["people"], "operator")
    base = f"/api/v1/organizations/{twin['org']}/environments/{env}"
    assert (
        client.post(
            base + f"/connectors/{connector['id']}/sync", headers=headers, json={"mode": "full"}
        ).status_code
        == 202
    )
    worker = Database(os.environ["WORKER_DATABASE_URL"])
    try:
        process_one(worker, twin["org"])
    finally:
        worker.close()
    assert got == [SECRET]
    as_user(client, twin["people"], "viewer")
    names = {i["name"] for i in client.get(base + "/identities").json()["data"]}
    assert {"Ada Admin", "Gus Guest"} <= names
