"""Mock identity provider for callback tests: signs claims and serves /token and /certs."""

import base64
import hashlib
import json
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


def fake_idp(monkeypatch, settings, params, claims):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public["kid"] = "test-signing-key"
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-signing-key"})
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
