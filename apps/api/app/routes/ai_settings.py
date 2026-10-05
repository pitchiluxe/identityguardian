"""Phase 24: AI provider settings, per-user API keys and the organization hosted-AI policy."""

from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from ..ai.provider import ProviderUnavailable
from ..ai.registry import HOSTED, key_context, org_policy, provider_for, user_choice
from ..auth import authenticate, require_session
from ..scope import envelope, scoped
from ..secrets_envelope import seal

router = APIRouter(dependencies=[Depends(require_session)])
ORG = "/api/v1/organizations/{org}/ai"
Provider = Literal["ollama", "anthropic", "openai"]
Hosted = Literal["anthropic", "openai"]
TEST_PROMPT = [
    {
        "role": "system",
        "content": "Reply with the JSON object requested. This is a connection test.",
    },
    {"role": "user", "content": 'Return {"ok": true}.'},
]
TEST_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider
    ollama_model: str | None = Field(None, max_length=100)
    anthropic_model: str | None = Field(None, max_length=100)
    openai_model: str | None = Field(None, max_length=100)


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_hosted_ai: bool


class KeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=20, max_length=300, pattern=r"^\S+$")


def token(request):
    return request.cookies.get("ig_session", "")


def ollama_status(settings, model):
    try:
        with httpx.Client(timeout=3, follow_redirects=False) as client:
            tags = client.get(settings.ollama_base_url.rstrip("/") + "/api/tags").json()
        names = sorted(m["name"] for m in tags.get("models", []))
        return dict(reachable=True, model=model, available_models=names, installed=model in names)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return dict(reachable=False, model=model, available_models=[], installed=False)


@router.get(ORG + "/settings")
def read_settings(org: UUID, request: Request):
    settings = request.app.state.settings
    with scoped(request, org, None, "overview:read") as scope:
        choice = user_choice(scope.conn, scope.user_id)
        keys = {p: {"saved": False} for p in HOSTED}
        for row in scope.conn.execute("SELECT * FROM ai_key_meta(%s)", (token(request),)):
            keys[row["provider"]] = {"saved": True, "last4": row["last4"]}
        model = (choice and choice["ollama_model"]) or settings.ollama_model
        return envelope(
            scope,
            dict(
                allow_hosted_ai=org_policy(scope.conn),
                can_configure="ai:configure" in scope.caps,
                provider=choice["provider"] if choice else "ollama",
                ollama_model=model,
                anthropic_model=(choice and choice["anthropic_model"]) or "claude-opus-5-5",
                openai_model=(choice and choice["openai_model"]) or "",
                hosted_acknowledged=bool(choice and choice["hosted_ack_at"]),
                keys=keys,
                ollama=ollama_status(settings, model),
            ),
        )


@router.put(ORG + "/settings")
def write_settings(org: UUID, body: SettingsBody, request: Request):
    with scoped(request, org, None, "overview:read") as scope:
        if body.provider in HOSTED:
            if not org_policy(scope.conn):
                raise HTTPException(409, "Hosted AI providers are disabled for this organization")
            saved = scope.conn.execute(
                "SELECT ai_key_get(%s,%s) AS e", (token(request), body.provider)
            ).fetchone()["e"]
            if not saved:
                raise HTTPException(409, "Save an API key for this provider first")
            if body.provider == "openai" and not (body.openai_model or "").strip():
                raise HTTPException(409, "Enter the OpenAI model ID to use")
        scope.conn.execute(
            "INSERT INTO user_ai_settings(organization_id,user_id,provider,ollama_model,"
            "anthropic_model,openai_model) VALUES(%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (organization_id,user_id) DO UPDATE SET provider=excluded.provider,"
            "ollama_model=excluded.ollama_model,anthropic_model=excluded.anthropic_model,"
            "openai_model=excluded.openai_model,updated_at=now()",
            (
                org,
                scope.user_id,
                body.provider,
                body.ollama_model,
                body.anthropic_model,
                (body.openai_model or "").strip() or None,
            ),
        )
        scope.audit(
            "ai.provider_selected",
            scope.user_id,
            "User AI provider choice",
            after=dict(provider=body.provider),
        )
        return envelope(scope, dict(provider=body.provider))


@router.put(ORG + "/policy")
def write_policy(org: UUID, body: PolicyBody, request: Request):
    with scoped(request, org, None, "ai:configure") as scope:
        before = org_policy(scope.conn)
        scope.conn.execute(
            "INSERT INTO organization_ai_settings(organization_id,allow_hosted_ai,updated_by) "
            "VALUES(%s,%s,%s) ON CONFLICT (organization_id) DO UPDATE SET "
            "allow_hosted_ai=excluded.allow_hosted_ai,updated_by=excluded.updated_by,updated_at=now()",
            (org, body.allow_hosted_ai, scope.user_id),
        )
        scope.audit(
            "ai.hosted_policy_changed",
            org,
            "Organization hosted-AI policy",
            before=dict(allow_hosted_ai=before),
            after=dict(allow_hosted_ai=body.allow_hosted_ai),
        )
        return envelope(scope, dict(allow_hosted_ai=body.allow_hosted_ai))


@router.post(ORG + "/acknowledge-hosted")
def acknowledge(org: UUID, request: Request):
    with scoped(request, org, None, "overview:read") as scope:
        scope.conn.execute(
            "INSERT INTO user_ai_settings(organization_id,user_id,hosted_ack_at) VALUES(%s,%s,now()) "
            "ON CONFLICT (organization_id,user_id) DO UPDATE SET hosted_ack_at=now()",
            (org, scope.user_id),
        )
        scope.audit(
            "ai.hosted_acknowledged",
            scope.user_id,
            "User acknowledged that evidence may be sent to a hosted AI provider",
        )
        return envelope(scope, dict(hosted_acknowledged=True))


@router.post(ORG + "/test")
def test_connection(org: UUID, request: Request):
    with scoped(request, org, None, "overview:read") as scope:
        provider, reason = provider_for(request, scope)
        if provider is None:
            return envelope(scope, dict(ok=False, reason=reason))
        try:
            provider.complete(TEST_PROMPT, TEST_SCHEMA)  # fixed prompt; no tenant evidence
        except ProviderUnavailable as exc:
            return envelope(scope, dict(ok=False, reason=str(exc)))
        return envelope(scope, dict(ok=True, provider=provider.name, model=provider.model))


def audit_everywhere(request, user, action, provider):
    """Keys belong to the user, not one organization: record the event in each membership."""
    with request.app.state.db.transaction() as conn:
        orgs = [
            r["id"]
            for r in conn.execute("SELECT * FROM user_organizations(%s)", (user["user_id"],))
        ]
    for org in orgs:
        with request.app.state.db.transaction(org) as conn:
            conn.execute(
                "INSERT INTO audit_events(id,organization_id,actor_id,action,target,after_state,"
                "justification,result,correlation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,'succeeded',%s)",
                (
                    uuid4(),
                    org,
                    user["user_id"],
                    action,
                    provider,
                    Jsonb(dict(provider=provider)),
                    "User API key change (key not recorded)",
                    request.state.correlation,
                ),
            )


@router.put("/api/v1/ai/keys/{provider}")
def save_key(provider: Hosted, body: KeyBody, request: Request):
    settings = request.app.state.settings
    user = authenticate(request)
    try:
        sealed = seal(
            body.api_key, settings.secret_master_key, key_context(user["user_id"], provider)
        )
    except ValueError:
        raise HTTPException(409, "Secret storage is not configured on this server") from None
    with request.app.state.db.transaction() as conn:
        conn.execute(
            "SELECT ai_key_put(%s,%s,%s,%s)",
            (token(request), provider, Jsonb(sealed), body.api_key[-4:]),
        )
    audit_everywhere(request, user, "ai.key_saved", provider)
    return {"data": {"last4": body.api_key[-4:]}}


@router.delete("/api/v1/ai/keys/{provider}")
def delete_key(provider: Hosted, request: Request):
    user = authenticate(request)
    with request.app.state.db.transaction() as conn:
        removed = conn.execute(
            "SELECT ai_key_delete(%s,%s) AS gone", (token(request), provider)
        ).fetchone()["gone"]
    if removed:
        audit_everywhere(request, user, "ai.key_deleted", provider)
    return {"data": {"removed": bool(removed)}}
