"""Phase 18: tamper-evident audit chain and signed checkpoints."""

import base64
import os
from uuid import uuid4

import psycopg

from tests.api.conftest import as_user


def test_chain_verifies_detects_edits_and_checkpoints_catch_rewrites(client, tenant):
    org, _, people = tenant
    client.app.state.settings.audit_signing_key = base64.b64encode(os.urandom(32)).decode()
    headers = as_user(client, people, "admin")
    for i in range(3):  # generate audited events
        client.post(
            f"/api/v1/organizations/{org}/role-requests",
            headers=headers,
            json=dict(
                target_id=people["viewer"]["id"],
                roles=["auditor"],
                justification=f"Audit chain test {i}",
                expected_version=1,
                idempotency_key=str(uuid4()),
            ),
        )
    verify = client.get(f"/api/v1/organizations/{org}/audit/verify").json()["data"]
    assert verify["result"] == "VERIFIED" and verify["chain"]["events"] == 3
    checkpoint = client.post(
        f"/api/v1/organizations/{org}/audit/checkpoints", headers=headers
    ).json()["data"]
    assert checkpoint["sequence"] == 3 and checkpoint["signature"]
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:  # simulated insider edit
        conn.execute(
            "UPDATE audit_events SET justification='edited later' WHERE organization_id=%s AND sequence=2",
            (org,),
        )
    broken = client.get(f"/api/v1/organizations/{org}/audit/verify").json()["data"]
    assert broken["result"] == "FAILED" and broken["chain"]["first_broken_sequence"] == 2
    with psycopg.connect(
        os.environ["MIGRATION_DATABASE_URL"]
    ) as conn:  # attacker recomputes the whole chain
        conn.execute("SET LOCAL session_replication_role = replica")  # this session only
        prev = "genesis"
        for seq in (1, 2, 3):
            prev = conn.execute(
                "UPDATE audit_events a SET prev_hash=%s, hash=encode(sha256(convert_to(%s || '|' || "
                "audit_canonical(a), 'UTF8')), 'hex') WHERE organization_id=%s AND sequence=%s RETURNING hash",
                (prev, prev, org, seq),
            ).fetchone()[0]
    rewritten = client.get(f"/api/v1/organizations/{org}/audit/verify").json()["data"]
    assert rewritten["chain"]["result"] == "INTACT"  # internally consistent again …
    assert (
        rewritten["checkpoints"][0]["chain_matches"] is False
    )  # … but the signed checkpoint disagrees
    assert rewritten["result"] == "FAILED"


def test_runtime_role_cannot_alter_audit(tenant):
    org = tenant[0]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("SELECT set_config('app.org', %s, true)", (org,))
        for statement in [
            "UPDATE audit_events SET justification='x'",
            "DELETE FROM audit_events",
            "UPDATE audit_checkpoints SET hash='x'",
        ]:
            try:
                with conn.transaction():
                    conn.execute(statement)
                raise AssertionError(f"runtime role was allowed: {statement}")
            except psycopg.errors.InsufficientPrivilege:
                pass


def test_checkpoint_requires_signing_key_and_audit_authority(client, tenant):
    org, _, people = tenant
    client.app.state.settings.audit_signing_key = ""
    headers = as_user(client, people, "admin")
    assert (
        client.post(f"/api/v1/organizations/{org}/audit/checkpoints", headers=headers).status_code
        == 409
    )
    as_user(client, people, "viewer")
    assert client.get(f"/api/v1/organizations/{org}/audit/verify").status_code == 403
