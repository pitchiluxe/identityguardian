"""Phase 12: effective vs known-at reconstruction, late evidence, coverage gaps, post-removal history."""

import os
import time
from datetime import datetime, timezone

import psycopg

from tests.api.conftest import as_user
from tests.api.support import membership, source_add, source_update, sync


def history(client, twin, who, **params):
    as_user(client, twin["people"], "auditor")
    response = client.get(twin["base"] + f"/history/identities/{who}", params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def names(view):
    return {e["entitlement"] for e in view["entitlements"]}


PAYROLL = "Payroll · SIMULATED · Manage payroll configuration"


def test_late_evidence_is_distinguished_from_what_was_known(client, twin):
    before = datetime.now(timezone.utc).isoformat()
    time.sleep(0.05)
    source_add(
        twin["org"],
        twin["env"],
        membership(
            "mem-erick-dir-late",
            "idn-erick",
            "grp-directory-admins",
            since="2026-05-01T00:00:00+00:00",
            ticket="TKT-LATE",
        ),
    )
    sync(client, twin)
    result = history(
        client, twin, "idn-erick", effective_at="2026-06-15T00:00:00Z", known_at=before
    )
    portal = "Directory Admin Portal · Administer identity tenant"
    assert portal not in names(result["as_known_then"]) and portal in names(result["as_known_now"])
    late = next(d for d in result["differences"] if d["entitlement"] == portal)
    assert (
        late["kind"] == "LEARNED_LATER"
        and late["late_edges"][0]["attributes"]["ticket"] == "TKT-LATE"
    )
    assert result["timezone"] == "UTC" and result["known_at"] != result["effective_at"]


def test_post_removal_history_and_correction(client, twin):
    def remove(body):
        body["valid_to"] = "2026-09-29T12:00:00+00:00"
        return body, True

    source_update(twin["env"], "mem-erick-grp-finance-legacy", remove)
    sync(client, twin)
    past = history(client, twin, "idn-erick", effective_at="2026-07-01T00:00:00Z")
    assert PAYROLL in names(past["as_known_now"])  # still effective then
    today = history(client, twin, "idn-erick", effective_at=datetime.now(timezone.utc).isoformat())
    assert PAYROLL not in names(today["as_known_now"])


def test_missing_history_is_unknown_and_coverage_explained(client, twin):
    result = history(client, twin, "idn-nina", effective_at="2026-01-01T00:00:00Z")
    assert result["as_known_now"]["status"] == "UNKNOWN"  # Nina joined 2026-09-28
    early = history(client, twin, "idn-erick", effective_at="2010-01-01T00:00:00Z")
    assert any("precedes the earliest source evidence" in n for n in early["coverage"]["notes"])
    before_any = history(
        client,
        twin,
        "idn-erick",
        effective_at="2026-07-01T00:00:00Z",
        known_at="2000-01-01T00:00:00Z",
    )
    assert before_any["as_known_then"]["status"] == "UNKNOWN"
    assert any("Nothing had been ingested" in n for n in before_any["coverage"]["notes"])


def test_offsets_and_dst_are_normalised(client, twin):
    # 2026-03-08 02:30 does not exist in New York; aware instants are unambiguous.
    a = history(client, twin, "idn-erick", effective_at="2026-03-08T07:30:00Z")
    b = history(client, twin, "idn-erick", effective_at="2026-03-08T03:30:00-04:00")
    assert a["effective_at"] == b["effective_at"] and names(a["as_known_now"]) == names(
        b["as_known_now"]
    )
    as_user(client, twin["people"], "auditor")
    naive = client.get(
        twin["base"] + "/history/identities/idn-erick",
        params={"effective_at": "2026-03-08T02:30:00"},
    )
    assert naive.status_code == 422
    future = client.get(
        twin["base"] + "/history/identities/idn-erick",
        params={"effective_at": "2026-03-08T07:30:00Z", "known_at": "2099-01-01T00:00:00Z"},
    )
    assert future.status_code == 422
    as_user(client, twin["people"], "viewer")
    assert (
        client.get(
            twin["base"] + "/history/identities/idn-erick",
            params={"effective_at": "2026-03-08T07:30:00Z"},
        ).status_code
        == 403
    )


def test_snapshot_checksum_replays_and_detects_tampering(client, twin):
    headers = as_user(client, twin["people"], "auditor")
    created = client.post(
        twin["base"] + "/history/snapshots",
        headers=headers,
        json={"effective_at": "2026-07-01T00:00:00Z"},
    )
    assert created.status_code == 201, created.text
    snap = created.json()["data"]
    assert snap["edge_count"] > 0 and snap["coverage"]["syncs_before_known_at"]
    verify = client.get(twin["base"] + f"/history/snapshots/{snap['id']}/verify").json()["data"]
    assert verify["result"] == "MATCH"
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:  # simulated DBA tampering
        conn.execute(
            'UPDATE relationship_revisions SET attributes=attributes || \'{"ticket":"FORGED"}\' '
            "WHERE relationship_id=(SELECT id FROM relationships WHERE environment_id=%s "
            "AND external_id='mem-erick-grp-finance-legacy')",
            (twin["env"],),
        )
        conn.execute(
            "UPDATE relationship_revisions SET id=gen_random_uuid() WHERE relationship_id=(SELECT id "
            "FROM relationships WHERE environment_id=%s AND external_id='mem-tom-grp-erp-operators')",
            (twin["env"],),
        )
    verify = client.get(twin["base"] + f"/history/snapshots/{snap['id']}/verify").json()["data"]
    assert verify["result"] == "MISMATCH"
