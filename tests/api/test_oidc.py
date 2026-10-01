import base64
import hashlib
import json
import os
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import psycopg
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.api.app.config import Settings
from apps.api.app.security import digest
from tests.api.test_foundation import login


def test_signed_callback_rotates_session_ignores_role_claims_and_rejects_replay(
    client, tenant, monkeypatch
):
    _, _, people = tenant
    login(client, people, "viewer")
    settings = Settings()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE users SET issuer=%s WHERE id=%s",
            (settings.oidc_issuer_url, people["viewer"]["id"]),
        )
    redirect = client.get("/api/v1/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(redirect.headers["location"]).query)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public["kid"] = "test-signing-key"
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": settings.oidc_issuer_url,
            "aud": settings.oidc_client_id,
            "sub": people["viewer"]["id"],
            "nonce": params["nonce"][0],
            "exp": now + 300,
            "iat": now,
            "auth_time": now,
            "amr": ["pwd"],
            "roles": ["org_admin"],
        },
        key,
        algorithm="RS256",
        headers={"kid": "test-signing-key"},
    )
    real_client = httpx.Client

    def remote(request):
        if request.url.path.endswith("/token"):
            form = parse_qs(request.content.decode())
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            assert challenge == params["code_challenge"][0]
            assert form["redirect_uri"] == [settings.app_origin + "/api/v1/auth/callback"]
            return httpx.Response(200, json={"id_token": token})
        assert request.url.path.endswith("/certs")
        return httpx.Response(200, json={"keys": [public]})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(remote), **kwargs),
    )
    callback = f"/api/v1/auth/callback?code=one-use&state={params['state'][0]}"
    assert client.get(callback, follow_redirects=False).status_code == 303
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        assert (
            conn.execute(
                "SELECT 1 FROM sessions WHERE token_hash=%s", (digest(people["viewer"]["token"]),)
            ).fetchone()
            is None
        )
    session = client.get("/api/v1/session").json()
    assert session["user"]["id"] == people["viewer"]["id"]
    org = tenant[0]
    assert client.get(f"/api/v1/organizations/{org}/members").status_code == 403
    assert client.get(callback, follow_redirects=False).status_code == 400


def test_interrupted_exchange_consumes_state(client, monkeypatch):
    redirect = client.get("/api/v1/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(redirect.headers["location"]).query)
    real_client = httpx.Client

    def remote(request):
        raise httpx.ConnectError("test provider outage", request=request)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(remote), **kwargs),
    )
    callback = f"/api/v1/auth/callback?code=interrupted&state={params['state'][0]}"
    assert client.get(callback, follow_redirects=False).status_code == 400
    assert client.get(callback, follow_redirects=False).status_code == 400
    assert client.get("/api/v1/session").status_code == 401
