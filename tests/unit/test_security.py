import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.api.app.security import capabilities, require_recent_mfa, validate_claims


def test_viewer_cannot_gain_admin_capabilities_from_unknown_role():
    assert "members:propose" not in capabilities(["viewer", "Global Administrator"])
    assert "members:propose" in capabilities(["org_admin"])
    assert "members:approve" not in capabilities(["org_admin"])


@pytest.mark.parametrize("amr,age", [([], 0), (["pwd"], 0), (["mfa"], 301), (["mfa"], -60)])
def test_high_risk_requires_recent_verified_mfa(amr, age):
    with pytest.raises(ValueError):
        require_recent_mfa(amr, time.time() - age)


def test_recent_mfa_accepted():
    require_recent_mfa(["pwd", "mfa"], time.time() - 10)


@pytest.mark.parametrize("amr", [["otp"], ["hwk"], ["pwd"]])
def test_single_factor_is_not_mfa(amr):
    with pytest.raises(ValueError):
        require_recent_mfa(amr, time.time() - 10)


def test_password_and_otp_are_independent_factors():
    require_recent_mfa(["pwd", "otp"], time.time() - 10)


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize(
    "field,value",
    [
        ("iss", "https://attacker.test"),
        ("aud", "other-app"),
        ("nonce", "wrong"),
        ("exp", 1),
        ("sub", ""),
    ],
)
def test_invalid_identity_token_rejected(signing_key, field, value):
    now = int(time.time())
    claims = dict(
        iss="https://issuer.test",
        aud="guardian",
        sub="alice",
        nonce="expected",
        exp=now + 300,
        iat=now,
        auth_time=now,
    )
    claims[field] = value
    token = jwt.encode(claims, signing_key, algorithm="RS256")
    with pytest.raises((ValueError, jwt.PyJWTError)):
        validate_claims(
            token, signing_key.public_key(), "https://issuer.test", "guardian", "expected"
        )


def test_signed_valid_token_returns_subject(signing_key):
    now = int(time.time())
    token = jwt.encode(
        dict(
            iss="https://issuer.test",
            aud="guardian",
            sub="alice",
            nonce="expected",
            exp=now + 300,
            iat=now,
            auth_time=now,
        ),
        signing_key,
        algorithm="RS256",
    )
    assert (
        validate_claims(
            token, signing_key.public_key(), "https://issuer.test", "guardian", "expected"
        )["sub"]
        == "alice"
    )
