"""Phase 15: isolated attempts, 16 lab rubrics, progressive hints, deterministic scores and reports."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.api.conftest import as_user

LATER = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
J = {"justification": "Ticket INC-100 approved by manager"}

SOLUTIONS = {
    "onboarding": [
        dict(
            type="set_identity",
            identity="idn-nina",
            attributes={"department": "Finance", "manager": "idn-ana"},
        ),
        dict(type="add_membership", identity="idn-nina", group="grp-finance-analysts", **J),
    ],
    "password-reset": [
        dict(type="reset_password", identity="idn-sofia", verification="manager_callback", **J)
    ],
    "account-lockout": [
        dict(type="answer", question="cause", value="password_spray"),
        dict(type="reset_password", identity="idn-tom", verification="id_document"),
        dict(type="unlock_account", identity="idn-tom"),
    ],
    "group-management": [
        dict(type="add_membership", identity="idn-sofia", group="grp-finance-analysts", **J)
    ],
    "rbac": [
        dict(
            type="create_role",
            role="role-lab-ledger-reader",
            name="Ledger Reader (lab)",
            permissions=["perm-ledger-read"],
        ),
        dict(type="assign_role", identity="idn-nina", role="role-lab-ledger-reader", **J),
    ],
    "mfa-registration": [dict(type="register_mfa", identity="idn-dave", method="webauthn")],
    "conditional-access": [
        dict(
            type="add_condition",
            relationship="gr-grp-sales-team-role-crm-user",
            condition="mfa_required",
        )
    ],
    "sso-configuration": [
        dict(
            type="configure_sso",
            application="app-crm",
            issuer="https://idp.contoso.example/realms/contoso",
            audience="crm",
            mappings={"email": "email", "department": "department"},
        )
    ],
    "access-review": [
        dict(type="answer", question="decision", value="REMOVE"),
        dict(type="answer", question="justification", value="TKT-1042 predates the move to IT"),
        dict(type="answer", question="proposal", value="mem-erick-grp-finance-legacy"),
    ],
    "privileged-access": [
        dict(
            type="add_membership",
            identity="idn-chen",
            group="grp-directory-admins",
            expires_at=LATER,
            approver="idn-priya",
            justification="Change window CHG-42",
        )
    ],
    "service-account": [
        dict(type="set_owner", machine="idn-svc-erp-sync", owner="idn-ana"),
        dict(type="rotate_credential", credential="cert-erp-sync"),
    ],
    "termination": [
        dict(type="disable_account", identity="idn-ben"),
        dict(type="remove_membership", identity="idn-ben", group="grp-sales-team", **J),
        dict(type="remove_membership", identity="idn-ben", group="grp-all-staff", **J),
        dict(type="answer", question="sessions", value="revoke_at_idp"),
    ],
    "role-transfer": [
        dict(type="add_membership", identity="idn-tom", group="grp-sales-team", **J),
        dict(type="remove_membership", identity="idn-tom", group="grp-erp-operators", **J),
        dict(type="remove_membership", identity="idn-tom", group="grp-finance-analysts", **J),
    ],
    "privilege-creep": [
        dict(type="answer", question="grant", value="grp-finance-legacy"),
        dict(type="answer", question="via", value="grp-erp-operators"),
        dict(type="answer", question="ticket", value="TKT-1042"),
    ],
    "incident-investigation": [
        dict(type="answer", question="access_on_2026_05_01", value="yes"),
        dict(
            type="answer",
            question="payroll_use_after_move",
            value="no_observed_use_during_coverage",
        ),
        dict(type="answer", question="coverage_window", value="2026-06-01/2026-09-30"),
    ],
    "attack-path": [
        dict(type="answer", question="reset_target", value="idn-sofia"),
        dict(type="answer", question="destination", value="res-customer-data"),
        dict(type="answer", question="condition", value="target_mfa_registered"),
        dict(type="answer", question="control", value="require_mfa_reverification"),
    ],
}
NEGATIVE = {
    "onboarding": [
        dict(type="add_membership", identity="idn-nina", group="grp-payroll-approvers", **J)
    ],
    "password-reset": [dict(type="reset_password", identity="idn-fatima", verification="none")],
    "account-lockout": [dict(type="unlock_account", identity="idn-tom")],
    "group-management": [
        dict(type="add_membership", identity="idn-sofia", group="grp-finance-analysts", **J),
        dict(type="remove_membership", identity="idn-olivia", group="grp-sales-team", **J),
    ],
    "rbac": [
        dict(
            type="create_role",
            role="role-lab-too-much",
            name="Too much",
            permissions=["perm-ledger-read", "perm-tenant-admin"],
        ),
        dict(type="assign_role", identity="idn-nina", role="role-lab-too-much"),
    ],
    "mfa-registration": [dict(type="register_mfa", identity="idn-dave", method="sms")],
    "conditional-access": [
        dict(type="add_condition", relationship="ur-sofia-crm-cond", condition="mfa_required")
    ],
    "sso-configuration": [
        dict(
            type="configure_sso",
            application="app-crm",
            issuer="https://idp.contoso.example/realms/contoso",
            audience="*",
            mappings={"email": "email"},
        )
    ],
    "access-review": [
        dict(type="remove_membership", identity="idn-erick", group="grp-helpdesk-l2", **J)
    ],
    "privileged-access": [
        dict(type="add_membership", identity="idn-chen", group="grp-directory-admins", **J)
    ],
    "service-account": [
        dict(type="remove_membership", identity="idn-svc-erp-sync", group="grp-erp-operators", **J)
    ],
    "termination": [
        dict(type="disable_account", identity="idn-ben"),
        dict(type="disable_account", identity="idn-olivia"),
    ],
    "role-transfer": [
        dict(type="remove_membership", identity="idn-tom", group="grp-all-staff", **J)
    ],
    "privilege-creep": [dict(type="answer", question="grant", value="grp-helpdesk-l2")],
    "incident-investigation": [
        dict(type="answer", question="payroll_use_after_move", value="never_used")
    ],
    "attack-path": [dict(type="answer", question="control", value="exploit the reset")],
}


def post(client, tenant, who, path, body=None, status=None):
    org, _, people = tenant
    headers = as_user(client, people, who)
    response = client.post(
        f"/api/v1/organizations/{org}{path}", json=body if body is not None else {}, headers=headers
    )
    if status:
        assert response.status_code == status, response.text
    return response


def run(client, tenant, lab, actions, who="learner"):
    attempt = post(client, tenant, who, f"/labs/{lab}/attempts", status=201).json()["data"]
    for action in actions:
        post(
            client, tenant, who, f"/labs/attempts/{attempt['id']}/actions", {"action": action}, 200
        )
    return attempt, post(
        client, tenant, who, f"/labs/attempts/{attempt['id']}/submit", status=200
    ).json()["data"]


@pytest.mark.parametrize("lab", sorted(SOLUTIONS))
def test_worked_solution_passes(client, tenant, lab):
    _, report = run(client, tenant, lab, SOLUTIONS[lab])
    assert report["score"]["passed"] is True, report
    assert report["score"]["total"] >= 70 and report["graded_by"] == "DETERMINISTIC validator"


@pytest.mark.parametrize("lab", sorted(NEGATIVE))
def test_negative_case_does_not_pass(client, tenant, lab):
    _, report = run(client, tenant, lab, NEGATIVE[lab])
    assert report["score"]["passed"] is False, report


def test_catalog_has_sixteen_labs(client, tenant):
    org, _, people = tenant
    as_user(client, people, "learner")
    labs = client.get(f"/api/v1/organizations/{org}/labs").json()["data"]["labs"]
    assert len(labs) == 16 and {lab["id"] for lab in labs} == set(SOLUTIONS)
    as_user(client, people, "viewer")
    assert client.get(f"/api/v1/organizations/{org}/labs").status_code == 403


def test_attempts_are_isolated_per_learner(client, twin):
    tenant = (twin["org"], twin["other"], twin["people"])
    org, people = twin["org"], twin["people"]
    attempt = post(client, tenant, "learner", "/labs/group-management/attempts", status=201).json()[
        "data"
    ]
    env_base = f"/api/v1/organizations/{org}/environments/{attempt['environment_id']}"
    as_user(client, people, "learner")
    assert client.get(env_base + "/identities").status_code == 200  # own lab environment
    assert client.get(twin["base"] + "/identities").status_code == 403  # main environment
    as_user(client, people, "learner2")
    assert client.get(env_base + "/identities").status_code == 404
    assert (
        client.get(f"/api/v1/organizations/{org}/labs/attempts/{attempt['id']}").status_code == 404
    )
    assert (
        post(
            client,
            tenant,
            "learner2",
            f"/labs/attempts/{attempt['id']}/actions",
            {"action": SOLUTIONS["group-management"][0]},
        ).status_code
        == 404
    )
    as_user(client, people, "admin")  # lab:manage may observe
    assert (
        client.get(f"/api/v1/organizations/{org}/labs/attempts/{attempt['id']}").status_code == 200
    )
    post(
        client,
        tenant,
        "learner",
        f"/labs/attempts/{attempt['id']}/actions",
        {"action": SOLUTIONS["group-management"][0]},
        200,
    )
    as_user(client, people, "investigator")
    main = {
        r["other"]["external_id"]
        for r in client.get(twin["base"] + "/nodes/idn-sofia").json()["data"]["relationships"]
    }
    assert "grp-finance-analysts" not in main  # lab change never reached the main environment
    as_user(client, people, "learner")
    envs = client.get(f"/api/v1/organizations/{org}/environments").json()["data"]
    as_user(client, people, "learner2")
    envs2 = client.get(f"/api/v1/organizations/{org}/environments").json()["data"]
    assert attempt["environment_id"] in {e["id"] for e in envs} and attempt[
        "environment_id"
    ] not in {e["id"] for e in envs2}


def test_reset_hints_solution_and_report(client, tenant):
    org, _, people = tenant
    attempt = post(client, tenant, "learner", "/labs/onboarding/attempts", status=201).json()[
        "data"
    ]
    base = f"/labs/attempts/{attempt['id']}"
    post(client, tenant, "learner", base + "/actions", {"action": NEGATIVE["onboarding"][0]}, 200)
    post(client, tenant, "learner", base + "/reset", status=200)
    as_user(client, people, "learner")
    assert (
        client.get(f"/api/v1/organizations/{org}{base}/hint", params={"level": 2}).status_code
        == 409
    )
    hint = client.get(f"/api/v1/organizations/{org}{base}/hint", params={"level": 1}).json()["data"]
    assert hint["kind"] == "concept" and hint["source"] == "DETERMINISTIC"
    assert client.get(f"/api/v1/organizations/{org}{base}/solution").status_code == 409
    for action in SOLUTIONS["onboarding"]:
        post(client, tenant, "learner", base + "/actions", {"action": action}, 200)
    report = post(client, tenant, "learner", base + "/submit", status=200).json()["data"]
    assert (
        report["score"]["passed"] is True and report["resets"] == 1
    )  # reset cleared the unsafe grant
    assert report["hints_used"][0]["level"] == 1 and report["changes"] == SOLUTIONS["onboarding"]
    as_user(client, people, "learner")
    assert client.get(f"/api/v1/organizations/{org}{base}/solution").status_code == 200
    assert (
        client.get(f"/api/v1/organizations/{org}{base}/report").json()["data"]["score"]["total"]
        == report["score"]["total"]
    )
    assert (
        post(
            client, tenant, "learner", base + "/actions", {"action": SOLUTIONS["onboarding"][1]}
        ).status_code
        == 409
    )
    bad = post(client, tenant, "learner", "/labs/onboarding/attempts", status=201).json()["data"]
    rejected = post(
        client,
        tenant,
        "learner",
        f"/labs/attempts/{bad['id']}/actions",
        {"action": {"type": "drop_database"}},
    )
    assert rejected.status_code == 422


def test_instructor_explains_but_cannot_score(client, tenant):
    class Fake:
        name, model = "fake", "instructor"

        def complete(self, messages, schema):
            return {
                "insufficient_evidence": False,
                "claims": [
                    {
                        "text": "Check the department setting first.",
                        "type": "recommendation",
                        "citations": ["R1"],
                    },
                    {"text": "You scored 100.", "type": "fact", "citations": ["R1"]},
                ],
            }, 3

    attempt = post(client, tenant, "learner", "/labs/onboarding/attempts", status=201).json()[
        "data"
    ]
    client.app.state.llm = Fake()
    out = post(
        client, tenant, "learner", f"/labs/attempts/{attempt['id']}/explain", status=200
    ).json()["data"]
    assert (
        out["claims"][0]["citations"] == ["R1"] and len(out["rejected"]) == 1
    )  # invented score rejected
    client.app.state.llm = None
    out = post(
        client, tenant, "learner", f"/labs/attempts/{attempt['id']}/explain", status=200
    ).json()["data"]
    assert out["source"] == "DETERMINISTIC" and "unavailable" in out["note"]
