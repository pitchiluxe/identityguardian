import hashlib
import secrets
import time

import jwt

ROLE_CAPABILITIES = {
    "viewer": {"overview:read"},
    "investigator": {"overview:read"},
    "reviewer": {"overview:read"},
    "approver": {"overview:read", "members:read", "members:approve"},
    "operator": {"overview:read", "members:read", "members:execute"},
    "org_admin": {"overview:read", "members:read", "members:propose", "audit:read"},
    "auditor": {"overview:read", "audit:read"},
    "learner": {"overview:read"},
}


def capabilities(roles):
    return set().union(*(ROLE_CAPABILITIES.get(role, set()) for role in roles))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def require_recent_mfa(amr, auth_time):
    age = time.time() - auth_time
    methods = set(amr)
    verified = "mfa" in methods or {"pwd", "otp"}.issubset(methods)
    if not verified or not 0 <= age <= 300:
        raise ValueError("Recent verified MFA is required; sign in with MFA again.")


def validate_claims(token, key, issuer, audience, nonce):
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
    )
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise ValueError("Missing subject")
    if not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce):
        raise ValueError("Invalid nonce")
    if isinstance(claims["aud"], list) and len(claims["aud"]) > 1:
        if claims.get("azp") != audience:
            raise ValueError("Invalid authorized party")
    return claims
