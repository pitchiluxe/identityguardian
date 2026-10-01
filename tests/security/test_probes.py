"""Phase 18 self-assessment probes (internal; NOT an independent penetration test)."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from tests.api.conftest import as_user
from tests.api.support import source_update, sync


def test_security_headers_everywhere(client, twin):
    as_user(client, twin["people"], "viewer")
    for url in ["/api/v1/health", twin["base"] + "/identities", "/"]:
        headers = client.get(url).headers
        csp = headers["content-security-policy"]
        assert (
            "script-src 'self'" in csp
            and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
        )
        assert "frame-ancestors 'none'" in csp
        assert (
            headers["x-frame-options"] == "DENY" and headers["x-content-type-options"] == "nosniff"
        )
        assert (
            headers["cache-control"] == "no-store" and headers["referrer-policy"] == "same-origin"
        )
        assert "strict-transport-security" not in headers  # loopback development only


def test_hsts_when_secure_cookies():
    settings = Settings(
        app_origin="https://iam.example.com",
        oidc_issuer_url="https://idp.example.com/realms/x",
        development=False,
        secure_cookies=True,
    )
    with TestClient(create_app(settings), base_url="https://iam.example.com") as secure:
        assert (
            "max-age=31536000" in secure.get("/api/v1/health").headers["strict-transport-security"]
        )


def test_csrf_and_origin_are_enforced_before_validation(client, twin):
    as_user(client, twin["people"], "admin")
    url = twin["base"] + "/reports"
    good = {"Origin": "http://localhost:8000", "X-CSRF-Token": twin["people"]["admin"]["csrf"]}
    assert (
        client.post(
            url, json={"report_type": "jml"}, headers={**good, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json={"report_type": "jml"}, headers={"Origin": "http://localhost:8000"}
        ).status_code
        == 403
    )
    assert (
        client.post(url, json={"bogus": 1}, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.post(url, json={"report_type": "jml"}, headers=good).status_code == 201


def test_validation_errors_never_echo_input(client, twin):
    headers = as_user(client, twin["people"], "admin")
    secret = "super-secret-webhook-value-123"
    response = client.post(
        twin["base"] + "/connectors",
        headers=headers,
        json=dict(
            kind="mock_entra",
            name="x",
            endpoint="mock://entra/x",
            webhook_secret=secret,
            unexpected=secret,
        ),
    )
    assert response.status_code == 422 and secret not in response.text
    assert all(set(e) == {"loc", "msg", "type"} for e in response.json()["detail"])


def test_oversized_bodies_rejected(client, twin):
    headers = as_user(client, twin["people"], "admin")
    big = "x" * 1_100_000
    response = client.post(twin["base"] + "/reports", headers=headers, content=big)
    assert response.status_code == 413


def test_stored_markup_is_returned_as_data_not_html(client, twin):
    def inject(body):
        body["attributes"]["justification"] = (
            "<img src=x onerror=alert(1)><script>alert(2)</script>"
        )
        return body, False

    source_update(twin["env"], "mem-erick-grp-finance-legacy", inject)
    sync(client, twin)
    as_user(client, twin["people"], "viewer")
    response = client.get(twin["base"] + "/nodes/idn-erick")
    assert response.headers["content-type"].startswith("application/json")
    legacy = next(
        r
        for r in response.json()["data"]["relationships"]
        if r["other"]["external_id"] == "grp-finance-legacy"
    )
    # Stored verbatim as JSON data; the React UI renders text nodes, never HTML.
    assert legacy["attributes"]["justification"].startswith("<img src=x")


def test_errors_are_generic_and_correlated(client, twin):
    class FailingDatabase:  # only this client's app sees the failure
        @contextmanager
        def transaction(self, organization_id=None):
            raise psycopg.errors.InsufficientPrivilege("permission denied for table twin_nodes")
            yield

        def close(self):
            pass

    as_user(client, twin["people"], "viewer")
    client.app.state.db = FailingDatabase()
    response = client.get(twin["base"] + "/summary")
    assert (
        response.status_code == 503
        and "twin_nodes" not in response.text
        and "permission" not in response.text
    )
    assert response.headers["x-correlation-id"]


def test_no_open_redirect_and_unsupported_methods(client):
    login = client.get(
        "/api/v1/auth/login", params={"next": "https://evil.example"}, follow_redirects=False
    )
    assert login.status_code in {302, 307} and login.headers["location"].startswith(
        "http://localhost:58080/"
    )
    assert "evil.example" not in login.headers["location"]
    assert client.request("TRACE", "/api/v1/health").status_code == 405
    assert client.delete("/api/v1/health").status_code == 405


def test_session_fixation_and_logout(client, twin):
    as_user(client, twin["people"], "viewer")
    stolen = twin["people"]["viewer"]["token"]
    headers = {"Origin": "http://localhost:8000", "X-CSRF-Token": twin["people"]["viewer"]["csrf"]}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    client.cookies.set("ig_session", stolen)
    assert client.get("/api/v1/session").status_code == 401  # revoked server-side, not just cleared
    client.cookies.set("ig_session", str(uuid4()))
    assert client.get("/api/v1/session").status_code == 401
