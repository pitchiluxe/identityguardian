"""Phase 21: invite management API."""

from uuid import uuid4

from tests.api.conftest import as_user


def create(client, org, people, role="viewer", user="admin", status=201, email="pat@example.org"):
    headers = as_user(client, people, user)
    response = client.post(
        f"/api/v1/organizations/{org}/invites",
        headers=headers,
        json=dict(email=email, role=role, justification="New analyst joining the team"),
    )
    assert response.status_code == status, response.text
    return response.json()["data"] if status == 201 else response


def test_create_returns_link_once_and_list_never_does(client, tenant):
    org, _, people = tenant
    made = create(client, org, people)
    assert made["link"].startswith("/invite/") and len(made["link"]) > 40
    assert made["invite"]["status"] == "ACTIVE" and made["invite"]["roles"] == ["viewer"]
    as_user(client, people, "admin")
    listing = client.get(f"/api/v1/organizations/{org}/invites").text
    assert made["link"].split("/")[-1] not in listing and "token" not in listing


def test_privileged_invite_needs_independent_mfa_approval(client, tenant):
    org, _, people = tenant
    made = create(client, org, people, role="org_admin")["invite"]
    assert made["status"] == "PENDING_APPROVAL"
    url = f"/api/v1/organizations/{org}/invites/{made['id']}/decision"
    body = dict(digest=made["digest"], decision="APPROVE")
    assert client.post(url, headers=as_user(client, people, "admin"), json=body).status_code == 403
    stale = dict(digest="0" * 64, decision="APPROVE")
    assert (
        client.post(url, headers=as_user(client, people, "approver"), json=stale).status_code == 409
    )
    ok = client.post(url, headers=as_user(client, people, "approver"), json=body)
    assert ok.status_code == 200 and ok.json()["data"]["status"] == "ACTIVE"
    again = client.post(url, headers=as_user(client, people, "approver2"), json=body)
    assert again.status_code == 409


def test_only_admins_create_and_cross_tenant_is_hidden(client, tenant):
    org, other, people = tenant
    for user in ["viewer", "investigator", "approver", "auditor"]:
        create(client, org, people, user=user, status=403)
    made = create(client, org, people)["invite"]
    headers = as_user(client, people, "admin")
    assert client.post(
        f"/api/v1/organizations/{other}/invites/{made['id']}/revoke", headers=headers
    ).status_code in (403, 404)
    assert (
        client.post(
            f"/api/v1/organizations/{org}/invites/{uuid4()}/revoke", headers=headers
        ).status_code
        == 404
    )


def test_revoke_and_validation(client, tenant):
    org, _, people = tenant
    made = create(client, org, people)["invite"]
    headers = as_user(client, people, "admin")
    url = f"/api/v1/organizations/{org}/invites/{made['id']}/revoke"
    assert client.post(url, headers=headers).json()["data"]["status"] == "REVOKED"
    assert client.post(url, headers=headers).status_code == 409
    create(client, org, people, role="superuser", status=422)
    create(client, org, people, email="not-an-email", status=422)


def test_decision_on_expired_invite_is_refused(client, tenant):
    import os

    import psycopg

    org, _, people = tenant
    made = create(client, org, people, role="operator")["invite"]
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE invites SET expires_at=now()-interval '1 minute' WHERE id=%s", (made["id"],)
        )
    response = client.post(
        f"/api/v1/organizations/{org}/invites/{made['id']}/decision",
        headers=as_user(client, people, "approver"),
        json=dict(digest=made["digest"], decision="APPROVE"),
    )
    assert response.status_code == 409
