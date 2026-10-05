"""Phase 21: registration through an invite, redeemed at the OIDC callback."""

import os
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg

from apps.api.app.config import Settings
from tests.api.oidc_support import fake_idp
from tests.api.test_invites import create


def start(client, token):
    client.cookies.clear()
    response = client.get(f"/api/v1/auth/register?invite={token}", follow_redirects=False)
    return response, parse_qs(urlparse(response.headers.get("location", "")).query)


def claims(settings, params, subject, email="pat@example.org", **extra):
    now = int(time.time())
    return dict(
        iss=settings.oidc_issuer_url,
        aud=settings.oidc_client_id,
        sub=subject,
        nonce=params["nonce"][0],
        exp=now + 300,
        iat=now,
        auth_time=now,
        amr=["pwd", "otp"],
        email=email,
        name="Pat Example",
        **extra,
    )


def test_invitee_registers_and_gets_exactly_the_invited_role(client, tenant, monkeypatch):
    org, _, people = tenant
    link = create(client, org, people, role="investigator")["link"]
    response, params = start(client, link.split("/")[-1])
    assert (
        response.status_code == 307
        and "/protocol/openid-connect/registrations" in response.headers["location"]
    )
    assert params["scope"] == ["openid profile email"]
    settings, subject = Settings(), str(uuid4())
    fake_idp(monkeypatch, settings, params, claims(settings, params, subject, roles=["org_admin"]))
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 303
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        roles = conn.execute(
            "SELECT m.roles FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE u.subject=%s AND m.organization_id=%s",
            (subject, org),
        ).fetchone()[0]
    assert roles == ["investigator"]  # token role claims ignored
    assert client.get("/api/v1/session").status_code == 200


def test_invalid_tokens_get_generic_page_without_idp_state(client):
    for token in ["nope", " ", "%20" + "a" * 43]:
        response, _ = start(client, token)
        assert response.status_code == 303 and response.headers["location"] == "/invite/invalid"
        assert "ig_login" not in response.headers.get("set-cookie", "")


def test_email_mismatch_is_refused_with_fixed_message(client, tenant, monkeypatch):
    org, _, people = tenant
    link = create(client, org, people)["link"]
    _, params = start(client, link.split("/")[-1])
    settings = Settings()
    fake_idp(
        monkeypatch,
        settings,
        params,
        claims(settings, params, str(uuid4()), email="other@example.org"),
    )
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 403
    assert done.json()["detail"] == "Sign in with the email address the invite was sent to"


def test_unknown_subject_without_invite_still_refused(client, monkeypatch):
    client.cookies.clear()
    redirect = client.get("/api/v1/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(redirect.headers["location"]).query)
    settings = Settings()
    fake_idp(monkeypatch, settings, params, claims(settings, params, str(uuid4())))
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 403
    assert done.json()["detail"] == "This identity has not been provisioned for the platform"


def test_invite_deep_link_serves_shell_without_invite_details(client, tenant):
    org, _, people = tenant
    token = create(client, org, people)["link"].split("/")[-1]
    client.cookies.clear()
    for path in (f"/invite/{token}", "/invite/invalid"):
        response = client.get(path)
        assert response.status_code == 200 and "<div id=" in response.text
        assert "pat@example.org" not in response.text and str(org) not in response.text
        assert response.headers["content-security-policy"].startswith("default-src 'self'")


def test_refused_redemption_is_audited_in_the_tenant(client, tenant, monkeypatch):
    org, _, people = tenant
    made = create(client, org, people)
    _, params = start(client, made["link"].split("/")[-1])
    settings, subject = Settings(), str(uuid4())
    fake_idp(
        monkeypatch, settings, params, claims(settings, params, subject, email="other@example.org")
    )
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 403 and "ig_session" not in done.headers.get("set-cookie", "")
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT target, after_state, result FROM audit_events WHERE organization_id=%s "
            "AND action='invite.redemption_refused'",
            (org,),
        ).fetchone()
    assert row is not None and row[0] == made["invite"]["id"]
    assert row[1]["reason"] == "email_mismatch" and row[1]["subject"] == subject
    assert row[2] == "refused"


def test_existing_account_signs_in_and_redeems(client, tenant, monkeypatch):
    org, _, people = tenant
    settings, subject = Settings(), str(uuid4())
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "INSERT INTO users VALUES (gen_random_uuid(),%s,%s,'Existing Person')",
            (settings.oidc_issuer_url, subject),
        )
    token = create(client, org, people, role="auditor")["link"].split("/")[-1]
    client.cookies.clear()
    response = client.get(
        f"/api/v1/auth/register?invite={token}&mode=login", follow_redirects=False
    )
    assert "/protocol/openid-connect/auth?" in response.headers["location"]
    params = parse_qs(urlparse(response.headers["location"]).query)
    fake_idp(monkeypatch, settings, params, claims(settings, params, subject))
    done = client.get(
        f"/api/v1/auth/callback?code=c&state={params['state'][0]}", follow_redirects=False
    )
    assert done.status_code == 303
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        roles = conn.execute(
            "SELECT m.roles FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE u.subject=%s AND m.organization_id=%s",
            (subject, org),
        ).fetchone()[0]
    assert roles == ["auditor"]
