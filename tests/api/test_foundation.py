import os
from uuid import uuid4

import psycopg
from dotenv import load_dotenv

load_dotenv()


def login(client, people, name):
    user = people[name]
    client.cookies.set("ig_session", user["token"])
    return {"Origin": "http://localhost:8000", "X-CSRF-Token": user["csrf"]}


def test_anonymous_and_cross_tenant_denied(client, tenant):
    org, other, people = tenant
    assert client.get(f"/api/v1/organizations/{org}/overview").status_code == 401
    login(client, people, "viewer")
    assert client.get(f"/api/v1/organizations/{other}/overview").status_code == 404
    assert client.get(f"/api/v1/organizations/{org}/members").status_code == 403
    assert client.get(f"/api/v1/organizations/{org}/audit").status_code == 403


def test_viewer_cannot_forge_role_or_skip_csrf(client, tenant):
    org, _, people = tenant
    headers = login(client, people, "viewer")
    payload = dict(
        target_id=people["viewer"]["id"],
        roles=["org_admin"],
        justification="promote me",
        expected_version=1,
        idempotency_key=str(uuid4()),
    )
    url = f"/api/v1/organizations/{org}/role-requests"
    assert client.post(url, json=payload, headers=headers).status_code == 403
    login(client, people, "admin")
    assert client.post(url, json=payload).status_code == 403


def test_independent_approval_execution_audit_and_replay(client, tenant):
    org, _, people = tenant
    base = f"/api/v1/organizations/{org}"
    headers = login(client, people, "admin")
    payload = dict(
        target_id=people["viewer"]["id"],
        roles=["auditor"],
        justification="Assigned evidence review",
        expected_version=1,
        idempotency_key=str(uuid4()),
    )
    proposed = client.post(base + "/role-requests", json=payload, headers=headers)
    assert proposed.status_code == 201, proposed.text
    request = proposed.json()
    decision = {"digest": request["digest"]}
    assert (
        client.post(
            base + f"/role-requests/{request['id']}/approve", json=decision, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + f"/role-requests/{request['id']}/execute", json=decision, headers=headers
        ).status_code
        == 409
    )
    headers = login(client, people, "approver")
    assert (
        client.post(
            base + f"/role-requests/{request['id']}/approve",
            json={"digest": "forged"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + f"/role-requests/{request['id']}/approve", json=decision, headers=headers
        ).status_code
        == 200
    )
    headers = login(client, people, "admin")
    response = client.post(
        base + f"/role-requests/{request['id']}/execute", json=decision, headers=headers
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            base + f"/role-requests/{request['id']}/execute", json=decision, headers=headers
        ).status_code
        == 409
    )
    audit = client.get(base + "/audit").json()
    assert any(e["action"] == "membership.changed" and e["approval_id"] for e in audit)
    login(client, people, "viewer")
    assert client.get(base + "/audit").status_code == 200


def test_revoked_membership_is_not_cached(client, tenant):
    org, _, people = tenant
    login(client, people, "viewer")
    assert client.get(f"/api/v1/organizations/{org}/overview").status_code == 200
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE memberships SET active=false WHERE organization_id=%s AND user_id=%s",
            (org, people["viewer"]["id"]),
        )
    assert client.get(f"/api/v1/organizations/{org}/overview").status_code == 404


def test_invalid_callback_and_headers(client):
    assert client.get("/api/v1/auth/callback?code=bad&state=bad").status_code == 400
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"


def test_caller_cannot_set_approval_fields(client, tenant):
    org, _, people = tenant
    headers = login(client, people, "admin")
    result = client.post(
        f"/api/v1/organizations/{org}/role-requests",
        headers=headers,
        json={
            "target_id": people["viewer"]["id"],
            "roles": ["org_admin"],
            "justification": "Review scope",
            "expected_version": 1,
            "idempotency_key": str(uuid4()),
            "status": "APPROVED",
        },
    )
    assert result.status_code == 422


def test_approval_requires_mfa_and_cannot_be_self_approved(client, tenant):
    org, _, people = tenant
    base = f"/api/v1/organizations/{org}/role-requests"
    headers = login(client, people, "admin")
    proposal = client.post(
        base,
        headers=headers,
        json={
            "target_id": people["viewer"]["id"],
            "roles": ["auditor"],
            "justification": "Evidence review",
            "expected_version": 1,
            "idempotency_key": str(uuid4()),
        },
    ).json()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE memberships SET roles=ARRAY['org_admin','operator','approver'] "
            "WHERE organization_id=%s AND user_id=%s",
            (org, people["admin"]["id"]),
        )
        conn.execute(
            "UPDATE sessions SET amr=ARRAY['pwd'] WHERE user_id=%s", (people["approver"]["id"],)
        )
    assert (
        client.post(
            base + f"/{proposal['id']}/approve",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 403
    )
    headers = login(client, people, "approver")
    assert (
        client.post(
            base + f"/{proposal['id']}/approve",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 403
    )


def test_expired_session_and_foreign_origin_denied(client, tenant):
    org, _, people = tenant
    headers = login(client, people, "admin")
    headers["Origin"] = "https://attacker.test"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 403
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE sessions SET expires_at=now()-interval '1 second' WHERE user_id=%s",
            (people["admin"]["id"],),
        )
    assert client.get(f"/api/v1/organizations/{org}/overview").status_code == 401


def test_stale_target_and_revoked_approver_prevent_execution(client, tenant):
    org, _, people = tenant
    base = f"/api/v1/organizations/{org}/role-requests"
    headers = login(client, people, "admin")
    proposal = client.post(
        base,
        headers=headers,
        json={
            "target_id": people["viewer"]["id"],
            "roles": ["auditor"],
            "justification": "Evidence review",
            "expected_version": 1,
            "idempotency_key": str(uuid4()),
        },
    ).json()
    headers = login(client, people, "approver")
    assert (
        client.post(
            base + f"/{proposal['id']}/approve",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 200
    )
    headers = login(client, people, "admin")
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE memberships SET active=false WHERE organization_id=%s AND user_id=%s",
            (org, people["approver"]["id"]),
        )
    assert (
        client.post(
            base + f"/{proposal['id']}/execute",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 404
    )
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE memberships SET active=true WHERE organization_id=%s AND user_id=%s",
            (org, people["approver"]["id"]),
        )
        conn.execute(
            "UPDATE memberships SET version=2 WHERE organization_id=%s AND user_id=%s",
            (org, people["viewer"]["id"]),
        )
    assert (
        client.post(
            base + f"/{proposal['id']}/execute",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 409
    )


def test_audit_failure_rolls_back_proposal(client, tenant):
    org, _, people = tenant
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "CREATE FUNCTION test_reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'test audit failure'; END $$"
        )
        conn.execute(
            "CREATE TRIGGER test_audit_failure BEFORE INSERT ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION test_reject_audit()"
        )
    try:
        headers = login(client, people, "admin")
        response = client.post(
            f"/api/v1/organizations/{org}/role-requests",
            headers=headers,
            json={
                "target_id": people["viewer"]["id"],
                "roles": ["auditor"],
                "justification": "Evidence review",
                "expected_version": 1,
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code == 503
        with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM role_requests WHERE organization_id=%s", (org,)
                ).fetchone()[0]
                == 0
            )
    finally:
        with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
            conn.execute("DROP TRIGGER test_audit_failure ON audit_events")
            conn.execute("DROP FUNCTION test_reject_audit()")
