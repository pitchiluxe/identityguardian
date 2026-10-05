import base64
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from .security import capabilities, digest, validate_claims


def authenticate(request: Request, fresh: bool = False):
    """Validate the session (and CSRF for mutations). Cached per request unless `fresh`."""
    cached = getattr(request.state, "session", None)
    if cached is not None and not fresh:
        return cached
    token = request.cookies.get("ig_session", "")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    settings = request.app.state.settings
    with request.app.state.db.transaction() as conn:
        session = conn.execute(
            "SELECT s.*,u.display_name FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE token_hash=%s AND expires_at>now() "
            "AND last_seen>now()-(%s * interval '1 second')",
            (digest(token), settings.session_idle_seconds),
        ).fetchone()
        if not session:
            raise HTTPException(401, "Session expired; sign in again")
        conn.execute("UPDATE sessions SET last_seen=now() WHERE token_hash=%s", (digest(token),))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if request.headers.get("Origin") != settings.app_origin or not secrets.compare_digest(
            digest(csrf), session["csrf_hash"]
        ):
            raise HTTPException(403, "Invalid request origin or CSRF token")
    request.state.session = session
    return session


def require_session(request: Request):
    """Router dependency: authenticate before request bodies are validated."""
    authenticate(request)


def membership(conn, user_id, capability=None):
    row = conn.execute(
        "SELECT * FROM memberships WHERE user_id=%s AND active", (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Organization not found")
    if capability and capability not in capabilities(row["roles"]):
        raise HTTPException(403, "Your role does not allow this action")
    return row


REFUSALS = {
    "invalid": "This invite is no longer valid — ask your administrator for a new one",
    "expired": "This invite is no longer valid — ask your administrator for a new one",
    "not_approved": "This invite is no longer valid — ask your administrator for a new one",
    "email_mismatch": "Sign in with the email address the invite was sent to",
    "already_member": "You are already a member of this organization",
}


def begin_login(request: Request):
    return _begin(request)


def begin_registration(request: Request, invite: str = ""):
    """Start IdP self-registration for an invite. Every unusable token gets the same response."""
    token = invite.strip()
    usable = False
    if 20 <= len(token) <= 128:
        with request.app.state.db.transaction() as conn:
            usable = conn.execute("SELECT invite_usable(%s) AS ok", (digest(token),)).fetchone()[
                "ok"
            ]
    if not usable:
        return RedirectResponse("/invite/invalid", status_code=303)
    return _begin(request, endpoint="registrations", invite_hash=digest(token))


def _begin(request: Request, endpoint="auth", invite_hash=None):
    settings = request.app.state.settings
    browser, state, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    with request.app.state.db.transaction() as conn:
        conn.execute("DELETE FROM login_attempts WHERE expires_at<now()")
        conn.execute(
            "INSERT INTO login_attempts(token_hash,state,nonce,verifier,expires_at,invite_hash) "
            "VALUES(%s,%s,%s,%s,%s,%s)",
            (
                digest(browser),
                state,
                nonce,
                verifier,
                datetime.now(timezone.utc) + timedelta(minutes=5),
                invite_hash,
            ),
        )
    params = dict(
        client_id=settings.oidc_client_id,
        response_type="code",
        scope="openid profile email",
        redirect_uri=settings.app_origin + "/api/v1/auth/callback",
        state=state,
        nonce=nonce,
        code_challenge=challenge,
        code_challenge_method="S256",
        max_age="0",
    )
    response = RedirectResponse(
        f"{settings.oidc_issuer_url}/protocol/openid-connect/{endpoint}?" + urlencode(params)
    )
    response.set_cookie(
        "ig_login",
        browser,
        max_age=300,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/v1/auth",
    )
    return response


def complete_login(request: Request):
    settings, db = request.app.state.settings, request.app.state.db
    browser = request.cookies.get("ig_login", "")
    if not browser:
        raise HTTPException(400, "Login expired or invalid; start again")
    # Consume before network calls: failed and successful callbacks cannot be replayed.
    with db.transaction() as conn:
        attempt = conn.execute(
            "DELETE FROM login_attempts WHERE token_hash=%s AND expires_at>now() RETURNING *",
            (digest(browser),),
        ).fetchone()
    if not attempt or not secrets.compare_digest(
        request.query_params.get("state", ""), attempt["state"]
    ):
        raise HTTPException(400, "Login state is invalid; start again")
    code = request.query_params.get("code", "")
    if not code or len(code) > 4096:
        raise HTTPException(400, "Authorization was not completed")
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            token_response = client.post(
                settings.oidc_issuer_url + "/protocol/openid-connect/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.oidc_client_id,
                    "redirect_uri": settings.app_origin + "/api/v1/auth/callback",
                    "code_verifier": attempt["verifier"],
                },
            )
            token_response.raise_for_status()
            token = token_response.json()["id_token"]
            keys_response = client.get(settings.oidc_issuer_url + "/protocol/openid-connect/certs")
            keys_response.raise_for_status()
            kid = jwt.get_unverified_header(token).get("kid")
            key = next(
                jwt.PyJWK.from_dict(k).key
                for k in keys_response.json()["keys"]
                if k.get("kid") == kid
            )
            claims = validate_claims(
                token, key, settings.oidc_issuer_url, settings.oidc_client_id, attempt["nonce"]
            )
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, StopIteration, TypeError):
        raise HTTPException(400, "Identity provider response could not be verified") from None
    raw = secrets.token_urlsafe(32)
    csrf = digest("csrf:" + raw)
    amr = claims.get("amr", [])
    if not isinstance(amr, list) or not all(isinstance(x, str) for x in amr):
        amr = []
    auth_time = claims.get("auth_time", 0)
    if not isinstance(auth_time, (int, float)) or auth_time > time.time():
        auth_time = 0
    with db.transaction() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE issuer=%s AND subject=%s", (claims["iss"], claims["sub"])
        ).fetchone()
        if attempt.get("invite_hash"):
            # Access comes only from the stored invite; token claims never choose the role.
            redeemed = conn.execute(
                "SELECT * FROM redeem_invite(%s,%s,%s,%s,%s)",
                (
                    attempt["invite_hash"],
                    claims["iss"],
                    claims["sub"],
                    str(claims.get("name") or claims.get("preferred_username") or ""),
                    str(claims.get("email") or ""),
                ),
            ).fetchone()
            if redeemed["reason"]:
                logging.getLogger("identityguardian").info(
                    "Invite redemption refused: %s", redeemed["reason"]
                )
                raise HTTPException(403, REFUSALS[redeemed["reason"]])
            user = {"id": redeemed["user_id"]}
        elif not user:
            raise HTTPException(403, "This identity has not been provisioned for the platform")
        conn.execute(
            "DELETE FROM sessions WHERE token_hash=%s",
            (digest(request.cookies.get("ig_session", "")),),
        )
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,auth_time,amr) VALUES(%s,%s,%s,%s,%s,%s)",
            (
                digest(raw),
                user["id"],
                digest(csrf),
                datetime.now(timezone.utc) + timedelta(seconds=settings.session_absolute_seconds),
                auth_time,
                amr,
            ),
        )
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("ig_login", path="/api/v1/auth")
    response.set_cookie(
        "ig_session",
        raw,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response
