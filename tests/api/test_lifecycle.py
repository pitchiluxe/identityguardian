"""Phase 11: approved joiner baseline, mover retain/review/remove, leaver dependencies, partial failure."""

import os

import pytest

from apps.api.app.db import Database
from apps.worker.main import process_one
from tests.api.conftest import as_user
from tests.api.support import source_add, sync


@pytest.fixture
def worker():
    db = Database(os.environ["WORKER_DATABASE_URL"])
    yield db
    db.close()


def post(client, twin, who, path, body, status=None):
    headers = as_user(client, twin["people"], who)
    response = client.post(twin["base"] + path, json=body, headers=headers)
    if status:
        assert response.status_code == status, response.text
    return response


def baseline(client, twin, department, groups):
    created = post(
        client,
        twin,
        "admin",
        "/lifecycle/baselines",
        dict(department=department, groups=groups, justification=f"{department} standard access"),
        201,
    ).json()["data"]
    post(
        client,
        twin,
        "approver",
        f"/lifecycle/baselines/{created['id']}/decision",
        {"decision": "APPROVE"},
        200,
    )
    return created


def event_id(client, twin, who, kind):
    as_user(client, twin["people"], "investigator")
    events = client.get(twin["base"] + "/lifecycle/events").json()["data"]
    return next(
        e["id"]
        for e in events
        if e["identity"] and e["identity"]["external_id"] == who and e["kind"] == kind
    )


def plan(client, twin, who, kind):
    as_user(client, twin["people"], "investigator")
    return client.get(
        twin["base"] + f"/lifecycle/events/{event_id(client, twin, who, kind)}/plan"
    ).json()["data"]


def decisions(result):
    return {a["label"]: a["decision"] for a in result["actions"]}


def test_baseline_requires_independent_mfa_approval_and_supersedes(client, twin):
    created = post(
        client,
        twin,
        "admin",
        "/lifecycle/baselines",
        dict(
            department="Finance",
            groups=["grp-finance-analysts", "grp-all-staff"],
            justification="Finance joiner standard",
        ),
        201,
    ).json()["data"]
    url = f"/lifecycle/baselines/{created['id']}/decision"
    assert post(client, twin, "admin", url, {"decision": "APPROVE"}).status_code == 403
    assert (
        post(
            client,
            twin,
            "admin",
            "/lifecycle/baselines",
            dict(department="Finance", groups=["grp-unknown"], justification="bad group"),
        ).status_code
        == 422
    )
    post(client, twin, "approver", url, {"decision": "APPROVE"}, 200)
    assert post(client, twin, "approver", url, {"decision": "APPROVE"}).status_code == 409
    baseline(client, twin, "Finance", ["grp-finance-analysts"])
    as_user(client, twin["people"], "investigator")
    rows = client.get(twin["base"] + "/lifecycle/baselines").json()["data"]
    assert sorted((r["version"], r["status"]) for r in rows) == [(1, "SUPERSEDED"), (2, "APPROVED")]


def test_joiner_uses_only_approved_baseline(client, twin):
    assert plan(client, twin, "idn-nina", "join")["status"] == "NO_APPROVED_BASELINE"
    baseline(client, twin, "Engineering", ["grp-engineering", "grp-all-staff"])
    grace = decisions(plan(client, twin, "idn-grace", "join"))
    assert grace["Retain Engineering"] == "RETAIN"
    assert grace["Review Global Administrator"] == "REVIEW"


def test_mover_classifies_retain_review_remove(client, twin):
    baseline(client, twin, "IT", ["grp-it-support", "grp-helpdesk-l2", "grp-all-staff"])
    result = plan(client, twin, "idn-erick", "move")
    found = decisions(result)
    assert found["Remove Finance-Legacy"] == "REMOVE"
    assert found["Retain HelpDesk-L2"] == "RETAIN" and found["Retain IT-Support"] == "RETAIN"
    assert found["Retain All-Staff"] == "RETAIN"
    remove = next(a for a in result["actions"] if a["label"] == "Remove Finance-Legacy")
    assert "TKT-1042" in remove["rationale"] and remove["evidence_ids"]
    assert result["basis"] == "RULE-BASED"


def test_leaver_plan_covers_accounts_ownership_exposure_and_sessions(client, twin):
    source_add(
        twin["org"],
        twin["env"],
        dict(
            type="relationship",
            id="own-ben-ci",
            rel="USER_OWNS_SERVICE_ACCOUNT",
            src="idn-ben",
            dst="idn-svc-ci",
            valid_from="2024-01-01T00:00:00+00:00",
            valid_to=None,
            attributes={"origin": "direct_assignment"},
        ),
    )
    sync(client, twin)
    result = plan(client, twin, "idn-ben", "leave")
    labels = {a["label"]: a for a in result["actions"]}
    assert labels["Disable account ben@contoso.example"]["proposal"]["kind"] == "disable_account"
    assert labels["Remove Sales-Team"]["decision"] == "REMOVE"
    transfer = labels["Transfer ownership of github-actions-deploy"]
    assert transfer["proposal"]["src"] == "idn-olivia"
    assert "Credential-reset exposure" in labels
    assert labels["Sessions and tokens"]["rationale"].startswith("UNKNOWN")


def test_leaver_workflow_reports_partial_failure(client, twin, worker):
    result = plan(client, twin, "idn-ben", "leave")
    picks = [
        i
        for i, a in enumerate(result["actions"])
        if a["label"] in {"Disable account ben@contoso.example", "Remove Sales-Team"}
    ]
    event = event_id(client, twin, "idn-ben", "leave")
    info = next(i for i, a in enumerate(result["actions"]) if a["kind"] == "unknown")
    assert (
        post(
            client,
            twin,
            "investigator",
            f"/lifecycle/events/{event}/workflow",
            dict(actions=[info], justification="Leaver clean-up"),
        ).status_code
        == 422
    )
    flow = post(
        client,
        twin,
        "investigator",
        f"/lifecycle/events/{event}/workflow",
        dict(actions=picks, justification="Leaver clean-up for Ben"),
        201,
    ).json()["data"]
    assert (
        post(
            client,
            twin,
            "investigator",
            f"/lifecycle/events/{event}/workflow",
            dict(actions=picks, justification="Leaver clean-up for Ben"),
        ).status_code
        == 409
    )
    headers = as_user(client, twin["people"], "admin")
    client.put(
        twin["base"] + "/sandbox/faults",
        headers=headers,
        json=dict(operation="remove_relationship", mode="fail_before_write"),
    )
    for change_id in flow["change_request_ids"]:
        as_user(client, twin["people"], "investigator")
        change = client.get(twin["base"] + f"/change-requests/{change_id}").json()["data"]["change"]
        assert change["status"] == "IN_REVIEW" and change["origin"] == "lifecycle"
        post(
            client,
            twin,
            "approver",
            f"/change-requests/{change_id}/decision",
            dict(
                digest=change["digest"],
                decision="APPROVE",
                justification="Leaver clean-up approved",
            ),
            200,
        )
        post(
            client,
            twin,
            "operator",
            f"/change-requests/{change_id}/execute",
            {"digest": change["digest"]},
            202,
        )
        process_one(worker, twin["org"])
    as_user(client, twin["people"], "investigator")
    status = client.get(twin["base"] + f"/lifecycle/workflows/{flow['id']}").json()["data"]
    assert sorted(c["status"] for c in status["changes"]) == ["FAILED", "SUCCEEDED"]
    assert status["status"] == "PARTIAL"
    accounts = client.get(twin["base"] + "/nodes/acct-ben").json()["data"]["node"]
    assert accounts["attributes"]["enabled"] is False
