import hashlib
import secrets
import time

import jwt

_READ = {"overview:read", "identity:read", "graph:read"}
_ANALYSIS = _READ | {"access:read", "findings:read", "history:read"}

# Capabilities are the only authority. Observed directory roles never map into this table.
ROLE_CAPABILITIES = {
    "viewer": _READ,
    "investigator": _ANALYSIS
    | {"change:simulate", "change:propose", "investigation:run", "jit:request"},
    "reviewer": _ANALYSIS | {"review:decide"},
    "approver": _ANALYSIS
    | {"members:read", "members:approve", "change:approve", "jit:approve", "policy:approve"},
    "operator": _ANALYSIS
    | {"members:read", "members:execute", "change:execute", "connector:sync", "jit:execute"},
    "org_admin": _ANALYSIS
    | {
        "members:read",
        "members:propose",
        "audit:read",
        "connector:manage",
        "connector:sync",
        "sandbox:seed",
        "review:manage",
        "policy:propose",
        "report:create",
        "report:read",
        "lab:manage",
        "ai:configure",
    },
    "auditor": _ANALYSIS | {"audit:read", "report:read", "report:create"},
    "learner": {"overview:read", "lab:attempt"},
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
