"""Phase 2: deterministic sandbox ingestion, replay safety, bitemporal history, tenant isolation."""

import os
import time
from datetime import datetime, timezone

import psycopg

from tests.api.conftest import as_user
from tests.api.support import MIGRATION, source_update


def test_deterministic_import_and_replay_is_idempotent(client, twin):
    base, headers = twin["base"], twin["headers"]
    runs = client.get(base + "/sync-runs").json()["data"]
    first = runs[0]
    assert first["status"] == "SUCCEEDED" and first["rejected"] == 0
    assert first["coverage"] == "complete_authoritative"
    assert first["created"] == 434 and first["observed"] == 434
    again = client.post(base + "/connectors/sandbox/sync", json={"mode": "full"}, headers=headers)
    body = again.json()["data"]
    assert body["observed"] == 434 and body["unchanged"] == 434 and body["created"] == 0
    assert body["tombstoned"] == 0
    incremental = client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).json()
    assert incremental["data"]["observed"] == 0
    summary = client.get(base + "/summary").json()["data"]
    assert summary["counts"]["identity:employee"] == 12
    assert summary["counts"]["identity:machine"] == 4
    assert summary["counts"]["identity:agent"] == 2
    assert summary["terminated_identities"] == 1


def test_seed_and_sync_require_capabilities_and_lab_environment(client, twin):
    base = twin["base"]
    headers = as_user(client, twin["people"], "viewer")
    assert (
        client.post(
            base + "/sandbox/seed", json={"confirm_synthetic": True}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).status_code == 403
    )
    assert client.get(base + "/identities").status_code == 200
    headers = as_user(client, twin["people"], "admin")
    assert client.post(base + "/sandbox/seed", json={}, headers=headers).status_code == 422
    with psycopg.connect(MIGRATION) as conn:
        conn.execute("UPDATE environments SET kind='PRODUCTION' WHERE id=%s", (twin["env"],))
    response = client.post(
        base + "/sandbox/seed", json={"confirm_synthetic": True}, headers=headers
    )
    assert response.status_code == 409


def test_tenant_and_environment_isolation(client, twin):
    as_user(client, twin["people"], "viewer")
    org, other, env, other_env = twin["org"], twin["other"], twin["env"], twin["other_env"]
    assert (
        client.get(f"/api/v1/organizations/{org}/environments/{other_env}/identities").status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/organizations/{other}/environments/{env}/identities").status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/organizations/{other}/environments/{other_env}/identities").status_code
        == 404
    )
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("SELECT set_config('app.org', %s, true)", (twin["other"],))
        assert (
            conn.execute(
                "SELECT count(*) FROM twin_nodes WHERE environment_id=%s", (env,)
            ).fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0


def test_profile_shows_provenance_and_attribute_history(client, twin):
    as_user(client, twin["people"], "viewer")
    profile = client.get(twin["base"] + "/nodes/idn-erick").json()
    node = profile["data"]["node"]
    assert node["attributes"]["department"] == "IT" and node["attributes"]["synthetic"] is True
    legacy = next(
        r
        for r in profile["data"]["relationships"]
        if r["other"]["external_id"] == "grp-finance-legacy"
    )
    assert legacy["attributes"]["ticket"] == "TKT-1042"
    assert legacy["attributes"]["origin"] == "legacy_entitlement"
    assert legacy["evidence_id"] in profile["evidence_ids"]
    assert [h["attributes"]["department"] for h in profile["data"]["history"]] == ["Finance", "IT"]
    past = client.get(
        twin["base"] + "/nodes/idn-erick", params={"effective_at": "2026-05-01T00:00:00Z"}
    ).json()["data"]
    assert past["node"]["attributes"]["department"] == "Finance"
    assert any(r["other"]["external_id"] == "grp-finance-analysts" for r in past["relationships"])
    assert (
        client.get(
            twin["base"] + "/nodes/idn-erick", params={"effective_at": "2026-05-01T00:00:00"}
        ).status_code
        == 422
    )


def test_explorer_is_bounded_and_preserves_cycles(client, twin):
    as_user(client, twin["people"], "viewer")
    hood = client.get(
        twin["base"] + "/graph/neighbors", params={"node": "idn-erick", "depth": 1}
    ).json()
    names = {n["external_id"] for n in hood["data"]["nodes"]}
    assert {"grp-finance-legacy", "grp-helpdesk-l2", "acct-erick"} <= names
    small = client.get(
        twin["base"] + "/graph/neighbors",
        params={"node": "grp-all-staff", "depth": 2, "max_nodes": 10},
    ).json()
    assert small["data"]["complete"] is False and small["completeness"] == "partial"
    cycle = client.get(
        twin["base"] + "/graph/neighbors", params={"node": "grp-eng-sre", "depth": 2}
    ).json()
    types = [e for e in cycle["data"]["edges"] if e["type"] == "GROUP_INHERITS_GROUP"]
    assert len(types) == 2
    assert (
        client.get(twin["base"] + "/graph/neighbors", params={"node": "missing"}).status_code == 404
    )


def test_source_removal_is_bitemporal(client, twin):
    base, headers = twin["base"], twin["headers"]
    before_sync = datetime.now(timezone.utc).isoformat()
    time.sleep(0.05)

    def remove(body):
        body["valid_to"] = "2026-09-29T12:00:00+00:00"
        return body, True

    source_update(twin["env"], "mem-erick-grp-finance-legacy", remove)
    run = client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).json()["data"]
    assert run["tombstoned"] == 1 and run["observed"] == 1
    as_user(client, twin["people"], "viewer")
    now_groups = {
        r["other"]["external_id"]
        for r in client.get(base + "/nodes/idn-erick").json()["data"]["relationships"]
    }
    assert "grp-finance-legacy" not in now_groups
    past = client.get(
        base + "/nodes/idn-erick", params={"effective_at": "2026-09-01T00:00:00Z"}
    ).json()
    assert any(
        r["other"]["external_id"] == "grp-finance-legacy" and r["valid_to"]
        for r in past["data"]["relationships"]
    )
    known_before = client.get(base + "/nodes/idn-erick", params={"known_at": before_sync}).json()[
        "data"
    ]
    legacy = next(
        r
        for r in known_before["relationships"]
        if r["other"]["external_id"] == "grp-finance-legacy"
    )
    assert legacy["valid_to"] is None


def test_invalid_records_are_rejected_without_partial_writes(client, twin):
    base, headers = twin["base"], twin["headers"]

    def bad_type(body):
        body["rel"] = "GROUP_HAS_ROLE"  # identity -> group is not a GROUP_HAS_ROLE
        return body, False

    source_update(twin["env"], "mem-tom-grp-erp-operators", bad_type)
    run = client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).json()["data"]
    assert run["status"] == "PARTIAL" and run["rejected"] == 1
    assert "cannot" in run["errors"][0]["reason"]
    groups = {
        r["other"]["external_id"]
        for r in client.get(base + "/nodes/idn-tom").json()["data"]["relationships"]
    }
    assert "grp-erp-operators" in groups


def test_partial_sync_never_implies_absence(client, twin):
    base, headers = twin["base"], twin["headers"]
    source_update(twin["env"], "mem-tom-grp-erp-operators", delete_row=True)
    run = client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).json()["data"]
    assert run["coverage"] == "partial" and run["tombstoned"] == 0
    groups = {
        r["other"]["external_id"]
        for r in client.get(base + "/nodes/idn-tom").json()["data"]["relationships"]
    }
    assert "grp-erp-operators" in groups
    run = client.post(
        base + "/connectors/sandbox/sync", json={"mode": "full"}, headers=headers
    ).json()["data"]
    assert run["coverage"] == "complete_authoritative" and run["tombstoned"] == 1
    past = client.get(
        base + "/nodes/idn-tom", params={"effective_at": "2026-09-01T00:00:00Z"}
    ).json()
    edge = next(
        r for r in past["data"]["relationships"] if r["other"]["external_id"] == "grp-erp-operators"
    )
    assert edge["end_inferred"] is True


def test_identity_pagination(client, twin):
    as_user(client, twin["people"], "viewer")
    first = client.get(twin["base"] + "/identities", params={"limit": 10}).json()
    assert len(first["data"]) == 10 and first["next_cursor"]
    second = client.get(
        twin["base"] + "/identities", params={"limit": 10, "cursor": first["next_cursor"]}
    ).json()
    assert not {r["id"] for r in first["data"]} & {r["id"] for r in second["data"]}
    assert client.get(twin["base"] + "/identities", params={"cursor": "bad"}).status_code == 422
    machines = client.get(twin["base"] + "/identities", params={"subtype": "machine"}).json()[
        "data"
    ]
    assert len(machines) == 4


def test_source_object_returning_to_earlier_state_is_reingested(client, twin):
    """Regression: a removed grant restored at the source must reappear in the twin."""
    base, headers = twin["base"], twin["headers"]

    def remove(body):
        body["valid_to"] = "2026-09-29T12:00:00+00:00"
        return body, True

    def restore(body):
        body["valid_to"] = None
        return body, False

    source_update(twin["env"], "mem-erick-grp-finance-legacy", remove)
    client.post(base + "/connectors/sandbox/sync", json={}, headers=headers)
    source_update(twin["env"], "mem-erick-grp-finance-legacy", restore)
    run = client.post(base + "/connectors/sandbox/sync", json={}, headers=headers).json()["data"]
    assert run["observed"] == 1 and run["unchanged"] == 0
    groups = {
        r["other"]["external_id"]
        for r in client.get(base + "/nodes/idn-erick").json()["data"]["relationships"]
    }
    assert "grp-finance-legacy" in groups
