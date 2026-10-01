"""Phase 7: immutable overlay, residual routes, dependencies, lockouts, unknowns; no base mutation."""

import os
from uuid import uuid4

import psycopg

from tests.api.conftest import as_user
from tests.api.support import membership, source_add, sync

REMOVE_LEGACY = [{"op": "remove_relationship", "relationship": "mem-erick-grp-finance-legacy"}]


def simulate(client, twin, operations=None, change=None, who="investigator", status=201):
    headers = as_user(client, twin["people"], who)
    body = {"operations": operations} if operations else {"change_request_id": change}
    response = client.post(twin["base"] + "/simulations", json=body, headers=headers)
    assert response.status_code == status, response.text
    return response.json()["data"] if status == 201 else None


def identity(result, external_id):
    return next(
        i for i in result["affected_identities"] if i["identity"]["external_id"] == external_id
    )


def counts(env):
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        return [
            conn.execute(
                f"SELECT count(*) FROM {t} WHERE organization_id=(SELECT organization_id "
                "FROM environments WHERE id=%s)",
                (env,),
            ).fetchone()[0]
            for t in ("observations", "relationship_revisions", "sandbox_objects")
        ]


def test_removal_simulation_reports_loss_dependencies_findings_and_never_mutates(client, twin):
    before_counts = counts(twin["env"])
    sim = simulate(client, twin, REMOVE_LEGACY)
    result = sim["result"]
    assert result["mutated_base"] is False and sim["digest"] and sim["expires_at"]
    assert [i["identity"]["external_id"] for i in result["affected_identities"]] == ["idn-erick"]
    lost = {entry["entitlement"] for entry in identity(result, "idn-erick")["lost"]}
    assert "Payroll · SIMULATED · Manage payroll configuration" in lost
    assert result["possible_lockouts"] == []
    assert any(d["depends_on"]["external_id"] == "app-erp" for d in result["dependencies"])
    resolved = {f["rule"] for f in result["findings"]["resolved"]}
    assert "PRIOR_ROLE_RETAINED" in resolved
    assert "not a probability" in result["findings"]["statement"]
    assert any("not observed" in u for u in result["unknowns"])
    assert counts(twin["env"]) == before_counts
    as_user(client, twin["people"], "investigator")
    groups = {
        r["other"]["external_id"]
        for r in client.get(twin["base"] + "/nodes/idn-erick").json()["data"]["relationships"]
    }
    assert "grp-finance-legacy" in groups


def test_alternate_path_variant_reports_residual_access(client, twin):
    source_add(
        twin["org"],
        twin["env"],
        membership(
            "mem-erick-payroll-alt", "idn-erick", "grp-payroll-approvers", ticket="TKT-2301"
        ),
    )
    sync(client, twin)
    result = simulate(client, twin, REMOVE_LEGACY)["result"]
    erick = identity(result, "idn-erick")
    residual = next(
        r
        for r in erick["retained_with_residual_routes"]
        if r["entitlement"] == "Payroll · SIMULATED · Manage payroll configuration"
    )
    assert residual["removed_routes"] == 1
    assert residual["residual_paths"][0]["hops"][0]["to"]["external_id"] == "grp-payroll-approvers"
    assert "PRIOR_ROLE_RETAINED" in {f["rule"] for f in result["findings"]["resolved"]}


def test_lockout_detected_when_no_one_retains_access(client, twin):
    result = simulate(
        client,
        twin,
        [
            {"op": "remove_relationship", "relationship": "gr-grp-erp-operators-role-erp-admin"},
            {
                "op": "remove_relationship",
                "relationship": "gr-grp-payroll-approvers-role-payroll-config",
            },
        ],
    )["result"]
    assert {i["identity"]["external_id"] for i in result["affected_identities"]} >= {
        "idn-tom",
        "idn-erick",
        "idn-ana",
        "idn-svc-erp-sync",
    }
    assert [lock["resource"]["external_id"] for lock in result["possible_lockouts"]] == [
        "res-payroll"
    ]


def test_addition_simulation_reports_gained_privilege(client, twin):
    result = simulate(
        client,
        twin,
        [
            {
                "op": "add_relationship",
                "type": "USER_MEMBER_OF_GROUP",
                "src": "idn-erick",
                "dst": "grp-directory-admins",
            }
        ],
    )["result"]
    gained = identity(result, "idn-erick")["gained"]
    assert any(g["privileged"] and "Directory Admin Portal" in g["entitlement"] for g in gained)
    simulate(
        client,
        twin,
        [
            {
                "op": "add_relationship",
                "type": "GROUP_HAS_ROLE",
                "src": "idn-erick",
                "dst": "grp-directory-admins",
            }
        ],
        status=409,
    )


def test_change_request_simulation_binds_digest_and_versions(client, twin):
    headers = as_user(client, twin["people"], "investigator")
    proposal = client.post(
        twin["base"] + "/change-requests",
        headers=headers,
        json=dict(
            kind="remove_relationship",
            relationship="mem-erick-grp-finance-legacy",
            justification="Retained from Finance role",
            idempotency_key=str(uuid4()),
        ),
    )
    assert proposal.status_code == 201, proposal.text
    change = proposal.json()["data"]
    assert change["status"] == "DRAFT" and change["target"]["src"]["external_id"] == "idn-erick"
    sim = simulate(client, twin, change=change["id"])
    detail = client.get(twin["base"] + f"/change-requests/{change['id']}").json()["data"]
    assert detail["change"]["status"] == "SIMULATED"
    assert detail["change"]["digest"] == sim["digest"] and detail["simulation"]["id"] == sim["id"]
    assert list(sim["source_versions"]) == [change["target"]["relationship_id"]]
    assert [h["action"] for h in detail["history"]] == ["change.proposed", "change.simulated"]
    again = simulate(client, twin, change=change["id"])
    assert again["digest"] != sim["digest"]  # new expiry/version binding


def test_simulation_authorization(client, twin):
    headers = as_user(client, twin["people"], "viewer")
    assert (
        client.post(
            twin["base"] + "/simulations", json={"operations": REMOVE_LEGACY}, headers=headers
        ).status_code
        == 403
    )
    headers = as_user(client, twin["people"], "reviewer")
    assert (
        client.post(
            twin["base"] + "/change-requests",
            headers=headers,
            json=dict(
                kind="remove_relationship",
                relationship="mem-erick-grp-finance-legacy",
                justification="Retained from Finance role",
                idempotency_key=str(uuid4()),
            ),
        ).status_code
        == 403
    )
    headers = as_user(client, twin["people"], "investigator")
    assert client.post(twin["base"] + "/simulations", json={}, headers=headers).status_code == 422
    assert (
        client.post(
            twin["base"] + "/simulations",
            headers=headers,
            json={"operations": [{"op": "remove_relationship", "relationship": "does-not-exist"}]},
        ).status_code
        == 409
    )
