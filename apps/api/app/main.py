import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import logs
from .ai.provider import OllamaProvider
from .auth import (
    authenticate,
    begin_login,
    begin_registration,
    complete_login,
    membership,
    require_session,
)
from .config import Settings
from .db import Database
from .limits import within_quota
from .logs import JsonFormatter  # noqa: F401  (re-exported for the worker and tests)
from .routes import ROUTERS
from .security import ROLE_CAPABILITIES, capabilities, digest, require_recent_mfa

MAX_BODY_BYTES = 1_000_000


class RoleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: UUID
    roles: list[str] = Field(min_length=1, max_length=8)
    justification: str = Field(min_length=8, max_length=1000)
    expected_version: int = Field(ge=1)
    idempotency_key: UUID


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(min_length=1, max_length=64)


def audit(
    conn, org, actor, action, target, reason, correlation, before=None, after=None, approval=None
):
    conn.execute(
        "INSERT INTO audit_events(id,organization_id,actor_id,action,target,before_state,after_state,"
        "justification,approval_id,result,correlation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'succeeded',%s)",
        (
            uuid4(),
            org,
            actor,
            action,
            str(target),
            Jsonb(before or {}),
            Jsonb(after or {}),
            reason,
            approval,
            correlation,
        ),
    )


def mfa(session):
    try:
        require_recent_mfa(session["amr"], session["auth_time"])
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from None


PROBES = {"/api/v1/health", "/api/v1/ready"}
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def expected_migrations():
    return len(list(MIGRATIONS.glob("*.sql")))


def create_app(settings=None, db=None):
    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_db:  # a shared database belongs to its creator
            app.state.db.close()

    app = FastAPI(
        lifespan=lifespan,
        title="IdentityGuardian AI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings or Settings()
    logs.configure(app.state.settings.log_format)
    owns_db = db is None
    # Two warm connections: opening a PostgreSQL backend on Windows can exceed the connect timeout
    # under load, which would turn the first request after an idle minute into a 503.
    app.state.db = db or Database(app.state.settings.database_url, min_size=2)
    app.state.llm, app.state.llm_error = None, None
    if app.state.settings.ai_enabled:
        try:
            app.state.llm = OllamaProvider(
                app.state.settings.ollama_base_url,
                app.state.settings.ollama_model,
                app.state.settings.ollama_timeout_seconds,
                app.state.settings.ai_allowed_hosts,
            )
        except ValueError as exc:  # misconfiguration is reported, never silently bypassed
            app.state.llm_error = str(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Field locations and messages only: never echo submitted values (they may be secrets).
        errors = [
            dict(loc=list(e.get("loc", [])), msg=e.get("msg"), type=e.get("type"))
            for e in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.middleware("http")
    async def boundary(request, call_next):
        request.state.correlation = uuid4()
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": "Request body too large"},
                status_code=413,
                headers={"X-Correlation-ID": str(request.state.correlation)},
            )
        try:
            if request.url.path.startswith("/api/") and request.url.path not in PROBES:
                if not await run_in_threadpool(within_quota, request):
                    response = JSONResponse(
                        {"detail": "Request limit reached; retry shortly"},
                        429,
                        headers={"Retry-After": "60"},
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
        except psycopg.Error:
            # Logged server-side with the correlation ID; the client receives no SQL details.
            logging.getLogger("identityguardian").exception(
                "Database error (correlation %s)",
                request.state.correlation,
                extra={"correlation_id": request.state.correlation},
            )
            response = JSONResponse(
                {"detail": "Database unavailable; contact the local administrator"}, 503
            )
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                "X-Correlation-ID": str(request.state.correlation),
            }
        )
        if app.state.settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def deployment():
        # Display-only context for the shell; every restriction is enforced server-side.
        return {"mode": "development" if app.state.settings.development else "production"}

    @app.get("/api/v1/health")
    def health():
        # Liveness: the process answers. Never touches the database.
        return {"status": "ok"}

    @app.get("/api/v1/ready")
    def ready():
        # Readiness: database reachable and every migration shipped with this build applied.
        # Status and a fixed reason only; no versions, counts or connection details.
        try:
            with app.state.db.transaction() as conn:
                applied = conn.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()
        except psycopg.Error:
            logging.getLogger("identityguardian").warning("Readiness: database unavailable")
            return JSONResponse({"status": "not_ready", "reason": "database unavailable"}, 503)
        if applied["n"] < expected_migrations():
            return JSONResponse({"status": "not_ready", "reason": "migrations pending"}, 503)
        return {"status": "ready"}

    app.get("/api/v1/auth/login")(begin_login)
    app.get("/api/v1/auth/callback")(complete_login)
    app.get("/api/v1/auth/register")(begin_registration)

    @app.get("/api/v1/session")
    def session(request: Request):
        user = authenticate(request)
        with app.state.db.transaction() as conn:
            organizations = conn.execute(
                "SELECT * FROM user_organizations(%s)", (user["user_id"],)
            ).fetchall()
        return {
            "user": {"id": user["user_id"], "name": user["display_name"]},
            "organizations": organizations,
            "csrf_token": digest("csrf:" + request.cookies["ig_session"]),
            "deployment": deployment(),
            "amr": user["amr"],
            "auth_time": user["auth_time"],
        }

    @app.post("/api/v1/auth/logout", dependencies=[Depends(require_session)])
    def logout(request: Request):
        user = authenticate(request)
        with app.state.db.transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=%s", (user["token_hash"],))
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie("ig_session", path="/")
        return response

    @app.get("/api/v1/organizations/{org}/overview")
    def overview(org: UUID, request: Request):
        user = authenticate(request)
        with app.state.db.transaction(org) as conn:
            member = membership(conn, user["user_id"], "overview:read")
            organization = conn.execute("SELECT * FROM organizations").fetchone()
            environments = conn.execute("SELECT * FROM environments ORDER BY name").fetchall()
            count = conn.execute(
                "SELECT count(*) AS value FROM memberships WHERE active"
            ).fetchone()["value"]
        return {
            "organization": organization,
            "environments": environments,
            "member_count": count,
            "roles": member["roles"],
            "capabilities": sorted(capabilities(member["roles"])),
            "deployment": deployment(),
        }

    @app.get("/api/v1/organizations/{org}/members")
    def members(org: UUID, request: Request):
        user = authenticate(request)
        with app.state.db.transaction(org) as conn:
            membership(conn, user["user_id"], "members:read")
            return conn.execute(
                "SELECT m.user_id,m.roles,m.active,m.version,u.display_name FROM memberships m "
                "JOIN users u ON u.id=m.user_id ORDER BY u.display_name LIMIT 100"
            ).fetchall()

    @app.get("/api/v1/organizations/{org}/audit")
    def audit_log(org: UUID, request: Request):
        user = authenticate(request)
        with app.state.db.transaction(org) as conn:
            membership(conn, user["user_id"], "audit:read")
            return conn.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC,id LIMIT 100"
            ).fetchall()

    @app.get("/api/v1/organizations/{org}/role-requests")
    def requests(org: UUID, request: Request):
        user = authenticate(request)
        with app.state.db.transaction(org) as conn:
            membership(conn, user["user_id"], "members:read")
            return conn.execute(
                "SELECT * FROM role_requests ORDER BY created_at DESC LIMIT 100"
            ).fetchall()

    @app.post(
        "/api/v1/organizations/{org}/role-requests",
        status_code=201,
        dependencies=[Depends(require_session)],
    )
    def propose(org: UUID, body: RoleProposal, request: Request):
        user = authenticate(request)
        if set(body.roles) - ROLE_CAPABILITIES.keys():
            raise HTTPException(422, "Unknown platform role")
        with app.state.db.transaction(org) as conn:
            membership(conn, user["user_id"], "members:propose")
            if body.target_id == user["user_id"]:
                raise HTTPException(403, "You cannot propose changes to your own roles")
            previous = conn.execute(
                "SELECT * FROM memberships WHERE user_id=%s AND active FOR UPDATE",
                (body.target_id,),
            ).fetchone()
            if not previous:
                raise HTTPException(404, "Member not found")
            canonical = json.dumps(
                {
                    "org": str(org),
                    "target": str(body.target_id),
                    "roles": sorted(set(body.roles)),
                    "version": body.expected_version,
                    "justification": body.justification,
                },
                sort_keys=True,
            )
            fingerprint = digest(canonical)
            existing = conn.execute(
                "SELECT * FROM role_requests WHERE requester_id=%s AND idempotency_key=%s",
                (user["user_id"], body.idempotency_key),
            ).fetchone()
            if existing:
                if existing["digest"] != fingerprint:
                    raise HTTPException(409, "Idempotency key already used for another proposal")
                return existing
            if previous["version"] != body.expected_version:
                raise HTTPException(409, "Member changed; refresh and review again")
            row = conn.execute(
                "INSERT INTO role_requests(id,organization_id,target_id,requester_id,roles,previous_roles,"
                "expected_version,justification,digest,expires_at,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    uuid4(),
                    org,
                    body.target_id,
                    user["user_id"],
                    sorted(set(body.roles)),
                    previous["roles"],
                    body.expected_version,
                    body.justification,
                    fingerprint,
                    datetime.now(timezone.utc) + timedelta(minutes=30),
                    body.idempotency_key,
                ),
            ).fetchone()
            audit(
                conn,
                org,
                user["user_id"],
                "membership.proposed",
                row["id"],
                body.justification,
                request.state.correlation,
                {"roles": previous["roles"]},
                {"roles": row["roles"]},
            )
            return row

    def transition(org, identifier, body, request, execute=False):
        with app.state.db.transaction(org) as conn:
            # All role transitions serialize before reading authorization or locking targets.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(org),))
            user = authenticate(request, fresh=True)  # re-validate after waiting for the lock
            membership(conn, user["user_id"], "members:execute" if execute else "members:approve")
            mfa(user)
            row = conn.execute(
                "SELECT * FROM role_requests WHERE id=%s FOR UPDATE", (identifier,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Request not found")
            if row["status"] != ("APPROVED" if execute else "IN_REVIEW") or row[
                "expires_at"
            ] <= datetime.now(timezone.utc):
                raise HTTPException(409, "Request expired or not in the required state")
            if not secrets.compare_digest(row["digest"], body.digest):
                raise HTTPException(409, "Proposal digest changed")
            target = conn.execute(
                "SELECT * FROM memberships WHERE user_id=%s AND active FOR UPDATE",
                (row["target_id"],),
            ).fetchone()
            if not target or target["version"] != row["expected_version"]:
                raise HTTPException(409, "Target changed; submit a new proposal")
            if not execute:
                if user["user_id"] in {row["requester_id"], row["target_id"]}:
                    raise HTTPException(403, "Approval must be independent of requester and target")
                conn.execute(
                    "UPDATE role_requests SET status='APPROVED',approver_id=%s,approved_at=now() WHERE id=%s",
                    (user["user_id"], identifier),
                )
                audit(
                    conn,
                    org,
                    user["user_id"],
                    "membership.approved",
                    identifier,
                    row["justification"],
                    request.state.correlation,
                    approval=identifier,
                )
            else:
                membership(conn, row["approver_id"], "members:approve")
                membership(conn, row["requester_id"], "members:propose")
                if "org_admin" in target["roles"] and "org_admin" not in row["roles"]:
                    admins = conn.execute(
                        "SELECT count(*) AS n FROM memberships WHERE active AND 'org_admin'=ANY(roles)"
                    ).fetchone()["n"]
                    if admins <= 1:
                        raise HTTPException(
                            409, "Cannot remove the final organization administrator"
                        )
                conn.execute(
                    "UPDATE memberships SET roles=%s,version=version+1 WHERE user_id=%s",
                    (row["roles"], row["target_id"]),
                )
                conn.execute(
                    "UPDATE role_requests SET status='EXECUTED' WHERE id=%s", (identifier,)
                )
                audit(
                    conn,
                    org,
                    user["user_id"],
                    "membership.changed",
                    row["target_id"],
                    row["justification"],
                    request.state.correlation,
                    {"roles": target["roles"]},
                    {"roles": row["roles"]},
                    identifier,
                )
                conn.execute(
                    "INSERT INTO outbox(id,organization_id,event_type,payload) VALUES(%s,%s,'role_change_recorded',%s)",
                    (uuid4(), org, Jsonb({"request_id": str(identifier)})),
                )
            return {"status": "EXECUTED" if execute else "APPROVED"}

    @app.post(
        "/api/v1/organizations/{org}/role-requests/{identifier}/approve",
        dependencies=[Depends(require_session)],
    )
    def approve(org: UUID, identifier: UUID, body: Decision, request: Request):
        return transition(org, identifier, body, request)

    @app.post(
        "/api/v1/organizations/{org}/role-requests/{identifier}/execute",
        dependencies=[Depends(require_session)],
    )
    def execute(org: UUID, identifier: UUID, body: Decision, request: Request):
        return transition(org, identifier, body, request, True)

    for router in ROUTERS:
        app.include_router(router)

    web = Path(__file__).resolve().parents[2] / "web" / "dist"
    if web.exists():

        @app.get("/invite/{token}", include_in_schema=False)
        def invite_page(token: str):
            # Deep link into the single-page shell; static HTML only, no invite lookup here.
            return FileResponse(web / "index.html")

        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()
