"""Phase 14: schema/operator validation, tests, scope simulation, independent approval, activation."""

import copy
from uuid import uuid4

from tests.api.conftest import as_user

CONTRACTOR_GA = {
    "schema_version": "1",
    "name": "No permanent Global Administrator for contractors",
    "purpose": "Contractors may only hold Global Administrator with an expiry.",
    "scope": {"identity_subtypes": ["contractor"]},
    "conditions": {
        "all": [
            {"field": "target.name", "op": "eq", "value": "Global Administrator"},
            {"field": "grant.expires_at", "op": "missing"},
        ]
    },
    "action": "flag",
    "exceptions": [],
    "tests": [
        {
            "name": "permanent contractor",
            "expect": "violation",
            "input": {"identity.subtype": "contractor", "target.name": "Global Administrator"},
        },
        {
            "name": "time-bound contractor",
            "expect": "no_violation",
            "input": {
                "identity.subtype": "contractor",
                "target.name": "Global Administrator",
                "grant.expires_at": "2026-12-01T00:00:00+00:00",
            },
        },
        {
            "name": "employee",
            "expect": "no_violation",
            "input": {"identity.subtype": "employee", "target.name": "Global Administrator"},
        },
    ],
}


def post(client, twin, who, path, body=None, status=None):
    headers = as_user(client, twin["people"], who)
    response = client.post(
        twin["base"] + path, json=body if body is not None else {}, headers=headers
    )
    if status:
        assert response.status_code == status, response.text
    return response


def activate(client, twin, definition, policy_id=None):
    body = {"definition": definition, **({"policy_id": policy_id} if policy_id else {})}
    version = post(client, twin, "admin", "/policies", body, 201).json()["data"]
    tested = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/test", status=200
    ).json()["data"]
    assert tested["status"] == "TESTED", tested["test_results"]
    simulated = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/simulate", status=200
    ).json()["data"]
    post(
        client,
        twin,
        "approver",
        f"/policies/versions/{version['id']}/decision",
        {"digest": simulated["approval_digest"], "decision": "APPROVE"},
        200,
    )
    post(client, twin, "admin", f"/policies/versions/{version['id']}/activate", status=200)
    return version, simulated


def test_definitions_are_validated_and_never_code(client, twin):
    bad = []
    for mutate in [
        lambda d: d["conditions"]["all"].append(
            {"field": "target.name", "op": "regex", "value": ".*"}
        ),
        lambda d: d["conditions"]["all"].append({"field": "os.system", "op": "eq", "value": "x"}),
        lambda d: d.update(script="import os"),
        lambda d: d.update(tests=d["tests"][:1]),
        lambda d: d["conditions"]["all"].append(
            {"field": "grant.expires_at", "op": "before", "value": "2026-01-01T00:00:00"}
        ),
        lambda d: d.update(action="revoke"),
    ]:
        definition = copy.deepcopy(CONTRACTOR_GA)
        mutate(definition)
        bad.append(post(client, twin, "admin", "/policies", {"definition": definition}).status_code)
    assert bad == [422] * 6
    assert (
        post(client, twin, "viewer", "/policies", {"definition": CONTRACTOR_GA}).status_code == 403
    )


def test_full_lifecycle_flags_without_revoking(client, twin):
    version = post(client, twin, "admin", "/policies", {"definition": CONTRACTOR_GA}, 201).json()[
        "data"
    ]
    assert (
        post(client, twin, "admin", f"/policies/versions/{version['id']}/simulate").status_code
        == 409
    )
    post(client, twin, "admin", f"/policies/versions/{version['id']}/test", status=200)
    simulated = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/simulate", status=200
    ).json()["data"]
    matches = [
        (v["identity"]["external_id"], v["target"]["name"])
        for v in simulated["simulation"]["violations"]
    ]
    assert matches == [("idn-grace", "Global Administrator")]
    assert "never revokes" in simulated["simulation"]["statement"]
    decision = f"/policies/versions/{version['id']}/decision"
    assert (
        post(
            client, twin, "approver", decision, {"digest": "0" * 64, "decision": "APPROVE"}
        ).status_code
        == 409
    )
    assert (
        post(
            client,
            twin,
            "admin",
            decision,
            {"digest": simulated["approval_digest"], "decision": "APPROVE"},
        ).status_code
        == 403
    )
    post(
        client,
        twin,
        "approver",
        decision,
        {"digest": simulated["approval_digest"], "decision": "APPROVE"},
        200,
    )
    post(client, twin, "admin", f"/policies/versions/{version['id']}/activate", status=200)
    as_user(client, twin["people"], "reviewer")
    found = [
        f
        for f in client.get(twin["base"] + "/findings").json()["data"]
        if f["rule"] == "POLICY_VIOLATION"
    ]
    assert [f["identity"]["external_id"] for f in found] == ["idn-grace"]
    profile = client.get(twin["base"] + "/nodes/idn-grace").json()["data"]
    assert any(r["other"]["name"] == "Global Administrator" for r in profile["relationships"])


def test_failing_tests_block_simulation(client, twin):
    definition = copy.deepcopy(CONTRACTOR_GA)
    definition["tests"][1]["expect"] = "violation"
    version = post(client, twin, "admin", "/policies", {"definition": definition}, 201).json()[
        "data"
    ]
    tested = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/test", status=200
    ).json()["data"]
    assert tested["status"] == "TEST_FAILED"
    assert [r["passed"] for r in tested["test_results"]] == [True, False, True]
    assert (
        post(client, twin, "admin", f"/policies/versions/{version['id']}/simulate").status_code
        == 409
    )


def test_exceptions_expire(client, twin):
    definition = copy.deepcopy(CONTRACTOR_GA)
    definition["exceptions"] = [
        {
            "identity": "idn-grace",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "justification": "Tenant migration window",
        }
    ]
    version = post(client, twin, "admin", "/policies", {"definition": definition}, 201).json()[
        "data"
    ]
    post(client, twin, "admin", f"/policies/versions/{version['id']}/test", status=200)
    sim = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/simulate", status=200
    ).json()["data"]
    assert (
        sim["simulation"]["violations"] == []
        and sim["simulation"]["excepted"][0]["identity"] == "idn-grace"
    )
    definition["exceptions"][0]["expires_at"] = "2026-01-01T00:00:00+00:00"
    version = post(client, twin, "admin", "/policies", {"definition": definition}, 201).json()[
        "data"
    ]
    post(client, twin, "admin", f"/policies/versions/{version['id']}/test", status=200)
    sim = post(
        client, twin, "admin", f"/policies/versions/{version['id']}/simulate", status=200
    ).json()["data"]
    assert len(sim["simulation"]["violations"]) == 1


def test_reject_proposed_blocks_new_grants_and_policy_change_invalidates_approval(client, twin):
    pending = post(
        client,
        twin,
        "investigator",
        "/change-requests",
        dict(
            kind="remove_relationship",
            relationship="mem-erick-grp-finance-legacy",
            justification="Retained from Finance",
            idempotency_key=str(uuid4()),
        ),
        201,
    ).json()["data"]
    post(client, twin, "investigator", "/simulations", {"change_request_id": pending["id"]}, 201)
    as_user(client, twin["people"], "investigator")
    current = client.get(twin["base"] + f"/change-requests/{pending['id']}").json()["data"][
        "change"
    ]
    post(
        client,
        twin,
        "investigator",
        f"/change-requests/{pending['id']}/submit",
        {"expected_version": current["version"]},
        200,
    )

    rule = copy.deepcopy(CONTRACTOR_GA)
    rule.update(
        name="Directory admins must be time-bound",
        action="reject_proposed",
        scope={},
        purpose="New Directory-Admins memberships need an expiry.",
        conditions={
            "all": [
                {"field": "target.external_id", "op": "eq", "value": "grp-directory-admins"},
                {"field": "grant.expires_at", "op": "missing"},
            ]
        },
        tests=[
            {
                "name": "permanent",
                "expect": "violation",
                "input": {"target.external_id": "grp-directory-admins"},
            },
            {
                "name": "other group",
                "expect": "no_violation",
                "input": {"target.external_id": "grp-it-support"},
            },
        ],
    )
    activate(client, twin, rule)
    blocked = post(
        client,
        twin,
        "investigator",
        "/change-requests",
        dict(
            kind="add_relationship",
            type="USER_MEMBER_OF_GROUP",
            src="idn-erick",
            dst="grp-directory-admins",
            justification="Needs directory admin",
            idempotency_key=str(uuid4()),
        ),
        201,
    ).json()["data"]
    sim = post(
        client, twin, "investigator", "/simulations", {"change_request_id": blocked["id"]}, 201
    ).json()["data"]
    assert sim["result"]["policy_violations"][0]["policy"] == "Directory admins must be time-bound"
    as_user(client, twin["people"], "investigator")
    version = client.get(twin["base"] + f"/change-requests/{blocked['id']}").json()["data"][
        "change"
    ]["version"]
    refused = post(
        client,
        twin,
        "investigator",
        f"/change-requests/{blocked['id']}/submit",
        {"expected_version": version},
    )
    assert refused.status_code == 409 and "Blocked by active policy" in refused.text

    approval = post(
        client,
        twin,
        "approver",
        f"/change-requests/{pending['id']}/decision",
        dict(digest=current["digest"], decision="APPROVE", justification="Approve removal"),
    )
    assert approval.status_code == 409
    as_user(client, twin["people"], "investigator")
    assert (
        client.get(twin["base"] + f"/change-requests/{pending['id']}").json()["data"]["change"][
            "status"
        ]
        == "STALE"
    )


def test_reversion_is_a_new_reviewed_version(client, twin):
    first, _ = activate(client, twin, CONTRACTOR_GA)
    revised = copy.deepcopy(CONTRACTOR_GA)
    revised["purpose"] = "Revert to the reviewed contractor rule (version 2)."
    second, _ = activate(client, twin, revised, policy_id=first["policy_id"])
    as_user(client, twin["people"], "auditor")
    rows = {
        r["version"]: r["status"]
        for r in client.get(twin["base"] + "/policies").json()["data"]
        if r["policy_id"] == first["policy_id"]
    }
    assert rows == {1: "SUPERSEDED", 2: "ACTIVE"}
