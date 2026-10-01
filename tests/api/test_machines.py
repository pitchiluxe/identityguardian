"""Phase 9: ownerless/aged/expiring credential evidence, dependency-aware proposals, no secrets."""

import os

import psycopg
import pytest

from apps.api.app.db import Database
from tests.api.conftest import as_user
from tests.api.support import run_change, source_add, source_update, sync


@pytest.fixture
def worker():
    return Database(os.environ["WORKER_DATABASE_URL"])


def rules(client, twin, who="reviewer"):
    as_user(client, twin["people"], who)
    return client.get(twin["base"] + "/findings").json()["data"]


def test_machine_inventory_and_findings(client, twin):
    as_user(client, twin["people"], "viewer")
    machines = {
        m["identity"]["external_id"]: m
        for m in client.get(twin["base"] + "/machines").json()["data"]
    }
    assert set(machines) == {"idn-svc-backup", "idn-svc-erp-sync", "idn-svc-ci", "idn-k8s-payments"}
    sync_sa = machines["idn-svc-erp-sync"]
    assert sync_sa["owners"] == [] and "ERP" in [d["name"] for d in sync_sa["dependents"]]
    assert "Payroll · SIMULATED" in sync_sa["privileged"]
    assert sync_sa["findings"] == []  # viewer lacks findings:read; inventory still visible
    assert [o["external_id"] for o in machines["idn-svc-backup"]["owners"]] == ["idn-maria"]
    found = rules(client, twin)
    ownerless = [f for f in found if f["rule"] == "OWNERLESS_MACHINE"]
    assert [f["identity"]["external_id"] for f in ownerless] == ["idn-svc-erp-sync"]
    assert ownerless[0]["severity"] == "high"
    expiring = [f for f in found if f["rule"] == "CREDENTIAL_EXPIRING"]
    assert [f["credential"]["credential"] for f in expiring] == ["cert-erp-sync"]
    assert "ERP" in expiring[0]["dependents"]
    aged = {f["credential"]["credential"] for f in found if f["rule"] == "CREDENTIAL_AGED"}
    assert aged == {"cert-erp-sync", "cred-backup-secret"}


def test_owner_assignment_never_grants_access_and_resolves_finding(client, twin, worker):
    change, sim = run_change(
        client,
        twin,
        worker,
        dict(
            kind="add_relationship",
            type="USER_OWNS_SERVICE_ACCOUNT",
            src="idn-maria",
            dst="idn-svc-erp-sync",
            justification="Assign accountable owner for ERP sync",
        ),
    )
    assert sim["result"]["affected_identities"] == []  # ownership is context, not access
    assert change["change"]["status"] == "SUCCEEDED"
    assert not [f for f in rules(client, twin) if f["rule"] == "OWNERLESS_MACHINE"]


def test_credential_rotation_is_dependency_aware_and_metadata_only(client, twin, worker):
    change, sim = run_change(
        client,
        twin,
        worker,
        dict(
            kind="rotate_credential",
            credential="cert-erp-sync",
            justification="Rotate before 2026-10-20 expiry",
        ),
    )
    impact = sim["result"]["operations"][0]["impact"]
    assert "ERP" in impact["must_update"] and "never sees secret values" in impact["guidance"]
    assert change["change"]["status"] == "SUCCEEDED", change
    remaining = {
        (f["rule"], f.get("credential", {}).get("credential")) for f in rules(client, twin)
    }
    assert ("CREDENTIAL_EXPIRING", "cert-erp-sync") not in remaining
    assert ("CREDENTIAL_AGED", "cert-erp-sync") not in remaining


def test_rotation_goes_stale_if_source_rotated_after_simulation(client, twin, worker):
    change, sim = run_change(
        client,
        twin,
        worker,
        dict(
            kind="rotate_credential",
            credential="cred-backup-secret",
            justification="Annual rotation of backup secret",
        ),
        finish=False,
    )

    def rotated_elsewhere(body):
        latest = dict(body["revisions"][-1])
        latest["valid_from"] = "2026-09-30T01:00:00+00:00"
        latest["attributes"] = dict(latest["attributes"], rotated_at="2026-09-30T01:00:00+00:00")
        body["revisions"] = body["revisions"] + [latest]
        return body, False

    source_update(twin["env"], "cred-backup-secret", rotated_elsewhere)
    sync(client, twin)
    headers = as_user(client, twin["people"], "operator")
    client.post(
        twin["base"] + f"/change-requests/{change['change']['id']}/execute",
        json={"digest": sim["digest"]},
        headers=headers,
    )
    from apps.worker.main import process_one

    process_one(worker, twin["org"])
    as_user(client, twin["people"], "investigator")
    status = client.get(twin["base"] + f"/change-requests/{change['change']['id']}").json()["data"][
        "change"
    ]["status"]
    assert status == "STALE"


def test_secret_material_is_never_stored_or_returned(client, twin):
    canary = "CANARY-7f3c9e-never-store"
    source_add(
        twin["org"],
        twin["env"],
        dict(
            type="node",
            id="cred-canary",
            kind="credential",
            subtype="client_secret",
            name="cred-canary",
            revisions=[
                dict(
                    valid_from="2026-09-01T00:00:00+00:00",
                    status="active",
                    attributes=dict(
                        created_at="2026-09-01T00:00:00+00:00",
                        client_secret_value=canary,
                        nested=dict(private_key=canary),
                        expires_at="2027-09-01T00:00:00+00:00",
                    ),
                )
            ],
        ),
    )
    sync(client, twin)
    as_user(client, twin["people"], "auditor")
    body = client.get(twin["base"] + "/nodes/cred-canary").text
    assert canary not in body and "client_secret_value" not in body
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        stored = conn.execute(
            "SELECT payload::text FROM observations WHERE environment_id=%s AND external_id='cred-canary'",
            (twin["env"],),
        ).fetchone()[0]
        assert canary not in stored and "_redacted_fields" in stored
        assert (
            conn.execute(
                "SELECT count(*) FROM node_revisions WHERE attributes::text LIKE %s",
                (f"%{canary}%",),
            ).fetchone()[0]
            == 0
        )
