"""Phase 16: connector registry, job syncs, cursors/replay/reconciliation, secrets and webhooks."""

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

import psycopg
import pytest

from apps.api.app.db import Database
from apps.worker.main import process_one
from tests.api.conftest import as_user

SECRET = "mock-webhook-signing-secret-0001"  # secret-scan: allow - synthetic test value


@pytest.fixture
def worker():
    db = Database(os.environ["WORKER_DATABASE_URL"])
    yield db
    db.close()


@pytest.fixture(autouse=True)
def master_key(client):
    client.app.state.settings.secret_master_key = base64.b64encode(os.urandom(32)).decode()


def create(client, twin, kind="mock_entra", authoritative=True, **extra):
    headers = as_user(client, twin["people"], "admin")
    response = client.post(
        twin["base"] + "/connectors",
        headers=headers,
        json=dict(
            kind=kind,
            name=f"{kind} {uuid4().hex[:6]}",
            endpoint=f"mock://{kind}/contoso",
            authoritative=authoritative,
            **extra,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def sync(client, twin, worker, connector, mode="full"):
    headers = as_user(client, twin["people"], "operator")
    response = client.post(
        twin["base"] + f"/connectors/{connector['id']}/sync", json={"mode": mode}, headers=headers
    )
    assert response.status_code == 202, response.text
    process_one(worker, twin["org"])
    as_user(client, twin["people"], "viewer")
    runs = client.get(twin["base"] + "/sync-runs").json()["data"]
    return next(r for r in runs if r["connector_id"] == connector["id"])


def faults(client, twin, connector, **config):
    headers = as_user(client, twin["people"], "admin")
    assert (
        client.put(
            twin["base"] + f"/connectors/{connector['id']}/faults", headers=headers, json=config
        ).status_code
        == 200
    )


def test_job_sync_pages_replay_and_secret_never_returned(client, twin, worker):
    connector = create(client, twin, webhook_secret=SECRET)
    assert connector["has_secret"] is True and "secret_envelope" not in connector
    run = sync(client, twin, worker, connector)
    assert (
        run["status"] == "SUCCEEDED"
        and run["pages"] >= 4
        and run["coverage"] == "complete_authoritative"
    )
    assert run["created"] > 200
    as_user(client, twin["people"], "viewer")
    listed = client.get(twin["base"] + "/connectors").json()
    assert SECRET not in json.dumps(listed) and "secret_envelope" not in json.dumps(listed)
    mock_users = client.get(twin["base"] + "/identities", params={"q": "Mock User"}).json()["data"]
    assert len(mock_users) == 50  # page limit; more exist
    replay = sync(client, twin, worker, connector)
    assert (
        replay["created"] == 0
        and replay["unchanged"] == run["observed"]
        and replay["tombstoned"] == 0
    )


def test_failure_mid_sync_keeps_cursor_and_never_deletes(client, twin, worker):
    connector = create(client, twin)
    faults(client, twin, connector, fail_on_page=3)
    partial = sync(client, twin, worker, connector)
    assert (
        partial["status"] == "PARTIAL" and partial["pages"] == 2 and partial["cursor_token"] == "50"
    )
    assert partial["tombstoned"] == 0
    faults(client, twin, connector)
    resumed = sync(client, twin, worker, connector, mode="resume")
    assert resumed["status"] == "SUCCEEDED" and resumed["coverage"] == "partial"
    assert resumed["observed"] < partial["observed"] + resumed["observed"]
    as_user(client, twin["people"], "viewer")
    health = next(
        c
        for c in client.get(twin["base"] + "/connectors").json()["data"]
        if c["id"] == connector["id"]
    )
    assert health["health"] == "HEALTHY"


def test_rate_limits_retry_with_bounds(client, twin, worker):
    connector = create(client, twin, kind="mock_okta")
    faults(client, twin, connector, rate_limit_on_page=1, rate_limit_times=2)
    run = sync(client, twin, worker, connector)
    assert run["status"] == "SUCCEEDED" and run["retries"] == 2
    faults(client, twin, connector, rate_limit_on_page=1, rate_limit_times=9)
    run = sync(client, twin, worker, connector)
    assert run["status"] == "PARTIAL" and run["retries"] == 4


def test_absence_reconciled_only_for_complete_authoritative_reads(client, twin, worker):
    authoritative = create(client, twin)
    sync(client, twin, worker, authoritative)
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        member = conn.execute(
            "SELECT external_id FROM relationships WHERE environment_id=%s AND source='mock_entra' "
            "AND type='USER_MEMBER_OF_GROUP' ORDER BY external_id LIMIT 1",
            (twin["env"],),
        ).fetchone()[0]
    faults(client, twin, authoritative, omit=[member])
    assert sync(client, twin, worker, authoritative, mode="incremental")["tombstoned"] == 0
    assert sync(client, twin, worker, authoritative)["tombstoned"] == 1
    other = create(client, twin, kind="mock_okta", authoritative=False)
    sync(client, twin, worker, other)
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        okta_member = conn.execute(
            "SELECT external_id FROM relationships WHERE environment_id=%s AND source='mock_okta' "
            "AND type='USER_MEMBER_OF_GROUP' ORDER BY external_id LIMIT 1",
            (twin["env"],),
        ).fetchone()[0]
    faults(client, twin, other, omit=[okta_member])
    assert sync(client, twin, worker, other)["tombstoned"] == 0  # not authoritative


def signed(body: bytes, secret=SECRET, stamp=None, delivery=None):
    stamp = str(stamp or int(time.time()))
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return {
        "X-Signature": "sha256=" + sig,
        "X-Timestamp": stamp,
        "X-Delivery-Id": delivery or uuid4().hex,
    }


def test_webhooks_are_verified_and_replay_safe(client, twin):
    connector = create(client, twin, webhook_secret=SECRET)
    url = twin["base"] + f"/connectors/{connector['id']}/webhook"
    body = b'{"changes":["users"]}'
    client.cookies.clear()
    headers = signed(body)
    assert client.post(url, content=body, headers=headers).status_code == 202
    assert client.post(url, content=body, headers=headers).status_code == 409  # same delivery
    assert (
        client.post(
            url,
            content=body,
            headers=signed(body, secret="wrong-secret-value-000"),  # secret-scan: allow - synthetic
        ).status_code
        == 401
    )
    assert (
        client.post(
            url, content=body, headers=signed(body, stamp=int(time.time()) - 3600)
        ).status_code
        == 401
    )
    assert (
        client.post(url, content=b'{"changes":["tampered"]}', headers=signed(body)).status_code
        == 401
    )
    unsigned = create(client, twin)
    client.cookies.clear()
    assert (
        client.post(
            twin["base"] + f"/connectors/{unsigned['id']}/webhook",
            content=body,
            headers=signed(body),
        ).status_code
        == 401
    )


def test_registry_authorization_and_environment_limits(client, twin):
    headers = as_user(client, twin["people"], "viewer")
    assert (
        client.post(
            twin["base"] + "/connectors",
            headers=headers,
            json=dict(kind="mock_entra", name="nope", endpoint="mock://entra/x"),
        ).status_code
        == 403
    )
    headers = as_user(client, twin["people"], "admin")
    assert (
        client.post(
            twin["base"] + "/connectors",
            headers=headers,
            json=dict(kind="mock_entra", name="ssrf", endpoint="https://169.254.169.254/"),
        ).status_code
        == 422
    )
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute("UPDATE environments SET kind='PRODUCTION' WHERE id=%s", (twin["env"],))
    assert (
        client.post(
            twin["base"] + "/connectors",
            headers=headers,
            json=dict(kind="mock_entra", name="prod", endpoint="mock://entra/x"),
        ).status_code
        == 409
    )


def test_admins_create_sandbox_environments_but_never_production(client, twin):
    base = f"/api/v1/organizations/{twin['org']}/environments"
    headers = as_user(client, twin["people"], "admin")
    created = client.post(base, headers=headers, json={"name": "Connector sandbox"})
    assert created.status_code == 201 and created.json()["data"]["kind"] == "SANDBOX"
    assert (
        client.post(base, headers=headers, json={"name": "x", "kind": "PRODUCTION"}).status_code
        == 422
    )
    headers = as_user(client, twin["people"], "viewer")
    assert client.post(base, headers=headers, json={"name": "Nope env"}).status_code == 403
    with psycopg.connect(
        os.environ["DATABASE_URL"]
    ) as conn:  # the runtime role itself is constrained
        conn.execute("SELECT set_config('app.org', %s, true)", (twin["org"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO environments(id,organization_id,name,kind) VALUES(%s,%s,'p','PRODUCTION')",
                (uuid4(), twin["org"]),
            )


def test_master_key_rotation_rewraps_and_withdrawn_key_fails_closed(client, twin):
    from apps.api.app.config import Settings
    from scripts.manage import rotate_master_key

    settings = client.app.state.settings
    old = settings.secret_master_key
    connector = create(client, twin, webhook_secret=SECRET)
    url = twin["base"] + f"/connectors/{connector['id']}/webhook"
    body = b'{"changes":["users"]}'
    client.cookies.clear()

    new = base64.b64encode(os.urandom(32)).decode()
    settings.secret_master_key, settings.secret_master_key_previous = new, []
    assert client.post(url, content=body, headers=signed(body)).status_code == 503  # fails closed

    settings.secret_master_key_previous = [old]
    assert client.post(url, content=body, headers=signed(body)).status_code == 202

    operator = Settings(secret_master_key=new, secret_master_key_previous=[old])
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        assert rotate_master_key(conn, operator, twin["org"]) == dict(
            rewrapped=1, current=0, unavailable=0
        )
        assert rotate_master_key(conn, operator, twin["org"])["current"] == 1  # idempotent
        assert rotate_master_key(conn, Settings(secret_master_key=old), twin["org"]) == dict(
            rewrapped=0,
            current=0,
            unavailable=1,  # reported, never silently skipped
        )
        audited = conn.execute(
            "SELECT count(*) FROM audit_events WHERE organization_id=%s "
            "AND action='connector.secret_rewrapped'",
            (twin["org"],),
        ).fetchone()[0]
    assert audited == 1

    settings.secret_master_key_previous = []  # old key retired after rotation
    assert client.post(url, content=body, headers=signed(body)).status_code == 202


def test_access_removed_then_regranted_is_reopened(client, twin, worker):
    # Regression (Phase 23 review): an authoritative read closed the membership without a new
    # observation, so when the identical membership came back it was skipped as "unchanged".
    connector = create(client, twin)
    sync(client, twin, worker, connector)
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        member = conn.execute(
            "SELECT external_id FROM relationships WHERE environment_id=%s AND source='mock_entra' "
            "AND type='USER_MEMBER_OF_GROUP' ORDER BY external_id LIMIT 1",
            (twin["env"],),
        ).fetchone()[0]
    faults(client, twin, connector, omit=[member])
    assert sync(client, twin, worker, connector)["tombstoned"] == 1
    faults(client, twin, connector, omit=[])
    sync(client, twin, worker, connector)
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        open_revisions = conn.execute(
            "SELECT count(*) FROM relationship_revisions rr JOIN relationships r "
            "ON r.id=rr.relationship_id WHERE r.environment_id=%s AND r.external_id=%s "
            "AND rr.recorded_to IS NULL AND rr.valid_to IS NULL",
            (twin["env"], member),
        ).fetchone()[0]
    assert open_revisions == 1  # the re-granted membership is current again
