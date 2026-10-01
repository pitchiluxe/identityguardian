"""Phase 8: separate approval, digest/version binding, sandbox execution, expiry/restart/reconciliation."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from apps.api.app.db import Database
from apps.worker.main import process_one, tick
from tests.api.conftest import as_user
from tests.api.support import source_update, sync

MIGRATION = os.environ.get("MIGRATION_DATABASE_URL")


@pytest.fixture
def worker():
    return Database(os.environ["WORKER_DATABASE_URL"])


def db(sql, *params):
    with psycopg.connect(MIGRATION) as conn:
        return (
            conn.execute(sql, params).fetchall()
            if sql.lstrip().upper().startswith("SELECT")
            else conn.execute(sql, params)
        )


def post(client, twin, who, path, body, status=None):
    headers = as_user(client, twin["people"], who)
    response = client.post(twin["base"] + path, json=body, headers=headers)
    if status:
        assert response.status_code == status, response.text
    return response


def change(client, twin, change_id):
    as_user(client, twin["people"], "investigator")
    return client.get(twin["base"] + f"/change-requests/{change_id}").json()["data"]["change"]


def in_review(client, twin, relationship="mem-erick-grp-finance-legacy"):
    created = post(
        client,
        twin,
        "investigator",
        "/change-requests",
        dict(
            kind="remove_relationship",
            relationship=relationship,
            justification="Retained after the move to IT",
            idempotency_key=str(uuid4()),
        ),
        201,
    ).json()["data"]
    post(client, twin, "investigator", "/simulations", {"change_request_id": created["id"]}, 201)
    current = change(client, twin, created["id"])
    post(
        client,
        twin,
        "investigator",
        f"/change-requests/{created['id']}/submit",
        {"expected_version": current["version"]},
        200,
    )
    return change(client, twin, created["id"])


def approved(client, twin, **kw):
    current = in_review(client, twin, **kw)
    post(
        client,
        twin,
        "approver",
        f"/change-requests/{current['id']}/decision",
        dict(
            digest=current["digest"], decision="APPROVE", justification="Evidence reviewed; remove"
        ),
        200,
    )
    return change(client, twin, current["id"])


def groups(client, twin, who="idn-erick", **params):
    as_user(client, twin["people"], "investigator")
    data = client.get(twin["base"] + f"/nodes/{who}", params=params).json()["data"]
    return {r["other"]["external_id"] for r in data["relationships"]}


def test_independent_approval_sandbox_execution_and_history(client, twin, worker):
    current = approved(client, twin)
    assert current["status"] == "APPROVED"
    queued = post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        202,
    ).json()["data"]
    assert queued["change"]["status"] == "QUEUED" and queued["status_url"].endswith(current["id"])
    assert "grp-finance-legacy" in groups(client, twin)  # pending is not success
    assert process_one(worker, twin["org"]) is True
    done = change(client, twin, current["id"])
    assert done["status"] == "SUCCEEDED"
    source = db(
        "SELECT deleted, body->>'valid_to' FROM sandbox_objects WHERE environment_id=%s "
        "AND object_id='mem-erick-grp-finance-legacy'",
        twin["env"],
    )[0]
    assert source[0] is True and source[1]
    assert "grp-finance-legacy" not in groups(client, twin)
    assert "grp-finance-legacy" in groups(client, twin, effective_at="2026-05-01T00:00:00Z")
    as_user(client, twin["people"], "reviewer")
    prior = client.get(twin["base"] + "/findings", params={"rule": "PRIOR_ROLE_RETAINED"}).json()
    assert prior["data"] == []
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        409,
    )
    assert process_one(worker, twin["org"]) is False
    history = [
        h["action"]
        for h in client.get(twin["base"] + f"/change-requests/{current['id']}").json()["data"][
            "history"
        ]
    ]
    assert history[:4] == [
        "change.proposed",
        "change.simulated",
        "change.submitted",
        "change.approved",
    ]
    assert history[-3:] == ["change.queued", "change.executing", "change.succeeded"]


def test_self_approval_tampering_mfa_and_separation_of_duties(client, twin):
    current = in_review(client, twin)
    db(
        "UPDATE memberships SET roles=ARRAY['investigator','approver','operator'] WHERE user_id=%s",
        twin["people"]["investigator"]["id"],
    )
    url = f"/change-requests/{current['id']}/decision"
    body = dict(
        digest=current["digest"], decision="APPROVE", justification="Approving my own request"
    )
    assert post(client, twin, "investigator", url, body).status_code == 403
    assert post(client, twin, "viewer", url, body).status_code == 403
    tampered = dict(body, digest="0" * 64)
    assert post(client, twin, "approver", url, tampered).status_code == 409
    db("UPDATE sessions SET amr=ARRAY['pwd'] WHERE user_id=%s", twin["people"]["approver"]["id"])
    assert post(client, twin, "approver", url, body).status_code == 403
    assert post(client, twin, "approver2", url, body).status_code == 200
    db(
        "UPDATE memberships SET roles=ARRAY['approver','operator'] WHERE user_id=%s",
        twin["people"]["approver2"]["id"],
    )
    execute = f"/change-requests/{current['id']}/execute"
    assert (
        post(client, twin, "approver2", execute, {"digest": current["digest"]}).status_code == 403
    )
    assert post(client, twin, "reviewer", execute, {"digest": current["digest"]}).status_code == 403


def test_stale_target_and_revoked_approver_are_refused_by_worker(client, twin, worker):
    current = approved(client, twin)
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        202,
    )

    def touch(body):
        body["attributes"]["justification"] = "Re-justified at source"
        return body, False

    source_update(twin["env"], "mem-erick-grp-finance-legacy", touch)
    sync(client, twin)
    process_one(worker, twin["org"])
    assert change(client, twin, current["id"])["status"] == "STALE"
    assert "grp-finance-legacy" in groups(client, twin)

    other = approved(client, twin, relationship="mem-tom-grp-erp-operators")
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{other['id']}/execute",
        {"digest": other["digest"]},
        202,
    )
    db("UPDATE memberships SET active=false WHERE user_id=%s", twin["people"]["approver"]["id"])
    process_one(worker, twin["org"])
    assert change(client, twin, other["id"])["status"] == "STALE"


def test_expired_approval_cannot_execute(client, twin):
    current = approved(client, twin)
    db(
        "UPDATE approvals SET expires_at=now()-interval '1 minute' WHERE change_request_id=%s",
        current["id"],
    )
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        409,
    )
    assert change(client, twin, current["id"])["status"] == "EXPIRED"


def test_connector_failure_and_lost_response_reconciliation(client, twin, worker):
    admin = as_user(client, twin["people"], "admin")
    client.put(
        twin["base"] + "/sandbox/faults",
        headers=admin,
        json=dict(operation="remove_relationship", mode="fail_before_write"),
    )
    current = approved(client, twin)
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        202,
    )
    process_one(worker, twin["org"])
    assert change(client, twin, current["id"])["status"] == "FAILED"
    assert "grp-finance-legacy" in groups(client, twin)

    admin = as_user(client, twin["people"], "admin")
    client.put(
        twin["base"] + "/sandbox/faults",
        headers=admin,
        json=dict(operation="remove_relationship", mode="timeout_after_write"),
    )
    retry = approved(client, twin)
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{retry['id']}/execute",
        {"digest": retry["digest"]},
        202,
    )
    process_one(worker, twin["org"])
    assert change(client, twin, retry["id"])["status"] == "RECONCILIATION_REQUIRED"
    tick(worker, twin["org"])  # read-back confirms the write that did happen
    assert change(client, twin, retry["id"])["status"] == "SUCCEEDED"
    assert "grp-finance-legacy" not in groups(client, twin)


def test_worker_restart_during_execution_requires_reconciliation(client, twin, worker):
    current = approved(client, twin)
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        202,
    )
    db("UPDATE executions SET status='EXECUTING' WHERE change_request_id=%s", current["id"])
    db("UPDATE change_requests SET status='EXECUTING' WHERE id=%s", current["id"])
    process_one(worker, twin["org"])
    assert change(client, twin, current["id"])["status"] == "RECONCILIATION_REQUIRED"
    tick(worker, twin["org"])
    # The source was never written, so read-back cannot confirm success.
    assert change(client, twin, current["id"])["status"] == "FAILED"


def test_concurrent_execution_runs_once(client, twin):
    current = approved(client, twin)
    url = twin["base"] + f"/change-requests/{current['id']}/execute"
    headers = as_user(client, twin["people"], "operator")
    cookie = twin["people"]["operator"]["token"]

    def run(_):
        from fastapi.testclient import TestClient

        from apps.api.app.config import Settings
        from apps.api.app.main import create_app

        with TestClient(
            create_app(Settings(read_limit_per_minute=999, write_limit_per_minute=999)),
            base_url="http://localhost:8000",
        ) as c:
            c.cookies.set("ig_session", cookie)
            return c.post(url, json={"digest": current["digest"]}, headers=headers).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(run, range(2)))
    assert codes == [202, 409]


def test_jit_grant_expiry_and_overdue_alert(client, twin, worker):
    requested = post(
        client,
        twin,
        "investigator",
        "/jit-requests",
        dict(
            identity="idn-erick",
            group="grp-backup-operators",
            duration_minutes=60,
            justification="Restore test for incident INC-77",
            idempotency_key=str(uuid4()),
        ),
        201,
    ).json()["data"]
    assert requested["status"] == "IN_REVIEW" and requested["kind"] == "jit_grant"
    post(
        client,
        twin,
        "investigator",
        f"/change-requests/{requested['id']}/decision",
        dict(digest=requested["digest"], decision="APPROVE", justification="Self approval attempt"),
        403,
    )
    post(
        client,
        twin,
        "approver",
        f"/change-requests/{requested['id']}/decision",
        dict(
            digest=requested["digest"], decision="APPROVE", justification="Bounded restore window"
        ),
        200,
    )
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{requested['id']}/execute",
        {"digest": requested["digest"]},
        202,
    )
    process_one(worker, twin["org"])
    assert change(client, twin, requested["id"])["status"] == "SUCCEEDED"
    assert "grp-backup-operators" in groups(client, twin)
    as_user(client, twin["people"], "investigator")
    grants = client.get(twin["base"] + "/jit-grants").json()["data"]["grants"]
    assert grants[0]["status"] == "ACTIVE"
    # Simulate the passage of time: grant window ended 10 minutes ago, source is down once.
    db(
        "UPDATE jit_grants SET granted_at=now()-interval '70 minutes', expires_at=now()-interval '10 minutes' "
        "WHERE change_request_id=%s",
        requested["id"],
    )
    when = db(
        "SELECT granted_at, expires_at FROM jit_grants WHERE change_request_id=%s", requested["id"]
    )[0]

    def shift(body):
        body["valid_from"] = when[0].isoformat()
        body["attributes"]["expires_at"] = when[1].isoformat()
        return body, False

    source_update(twin["env"], f"jit-{requested['id']}", shift)
    sync(client, twin)
    assert "grp-backup-operators" not in groups(client, twin)  # source-native TTL already applies
    admin = as_user(client, twin["people"], "admin")
    client.put(
        twin["base"] + "/sandbox/faults",
        headers=admin,
        json=dict(operation="remove_relationship", mode="fail_before_write"),
    )
    tick(worker, twin["org"])
    as_user(client, twin["people"], "investigator")
    data = client.get(twin["base"] + "/jit-grants").json()["data"]
    assert data["grants"][0]["status"] == "REVOKE_PENDING" and data["overdue"]
    tick(worker, twin["org"])  # "restart": the next tick retries from durable state
    data = client.get(twin["base"] + "/jit-grants").json()["data"]
    assert data["grants"][0]["status"] == "EXPIRED" and not data["overdue"]
    assert "grp-backup-operators" not in groups(client, twin)


def test_production_environment_never_executes(client, twin):
    current = approved(client, twin)
    db("UPDATE environments SET kind='PRODUCTION' WHERE id=%s", twin["env"])
    post(
        client,
        twin,
        "operator",
        f"/change-requests/{current['id']}/execute",
        {"digest": current["digest"]},
        409,
    )
