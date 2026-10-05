"""Phase 16: connector registry, sync jobs, fault injection and signed webhooks."""

import hashlib
import hmac
import logging
import time
from typing import Annotated, Literal
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require_session
from ..connectors import entra
from ..connectors.base import validate_endpoint
from ..connectors.providers import PROVIDERS, build
from ..jsonutil import jsonb as Jsonb
from ..scope import development_only, envelope, scoped
from ..secrets_envelope import open_envelope, seal
from .twin import ENV

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])
# Provider webhooks carry no session; authenticity is the HMAC signature.
webhooks = APIRouter(prefix="/api/v1/organizations/{org}")
WEBHOOK_TOLERANCE = 300


GUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class EntraRequest(BaseModel):
    """Read-only Microsoft Entra ID tenant (Phase 23). The client secret is sealed, never stored
    in plaintext or returned."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["entra"]
    name: str = Field(min_length=3, max_length=100)
    tenant_id: str = Field(pattern=GUID)
    client_id: str = Field(pattern=GUID)
    client_secret: str = Field(min_length=8, max_length=500)
    authoritative: bool = True


class ConnectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mock_entra", "mock_okta"]
    name: str = Field(min_length=3, max_length=100)
    endpoint: str = Field(max_length=300)
    authoritative: bool = False
    webhook_secret: str | None = Field(None, min_length=16, max_length=200)


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["full", "incremental", "resume"] = "full"


class FaultConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fail_on_page: int | None = Field(None, ge=1, le=20)
    rate_limit_on_page: int | None = Field(None, ge=1, le=20)
    rate_limit_times: int = Field(1, ge=1, le=10)
    omit: list[str] = Field(default_factory=list, max_length=50)


def public(row):
    """Never expose secret material: only whether a secret reference exists."""
    data = {k: v for k, v in row.items() if k not in {"secret_envelope"}}
    data["has_secret"] = row.get("secret_envelope") is not None
    return data


def queue(scope, connector_id, mode):
    scope.conn.execute(
        "INSERT INTO outbox(id,organization_id,event_type,payload) VALUES(%s,%s,'connector_sync_requested',%s)",
        (
            uuid4(),
            scope.org,
            Jsonb(dict(connector_id=str(connector_id), mode=mode, actor=str(scope.user_id))),
        ),
    )


def connector_for(scope, connector_id):
    row = scope.conn.execute(
        "SELECT * FROM connectors WHERE id=%s AND environment_id=%s", (connector_id, scope.env_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Connector not found")
    return row


@router.get(ENV + "/connectors")
def connectors(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "identity:read") as scope:
        rows = scope.conn.execute(
            "SELECT c.*, (SELECT row_to_json(s) FROM (SELECT status, coverage, pages, retries, finished_at, "
            "cursor_token FROM sync_runs WHERE connector_id=c.id ORDER BY started_at DESC LIMIT 1) s) AS last_run "
            "FROM connectors c WHERE c.environment_id=%s ORDER BY c.created_at",
            (env,),
        ).fetchall()
        return envelope(scope, [public(r) for r in rows])


@router.post(ENV + "/connectors", status_code=201)
def create(
    org: UUID,
    env: UUID,
    body: Annotated[ConnectorRequest | EntraRequest, Body(discriminator="kind")],
    request: Request,
):
    settings = request.app.state.settings
    if body.kind == "entra":
        return create_entra(org, env, body, request)
    with scoped(request, org, env, "connector:manage") as scope:
        if not settings.development:
            raise HTTPException(422, "Connector kind not available in production")
        if scope.environment["kind"] not in {"LAB", "SANDBOX"}:
            raise HTTPException(
                409,
                "Mock providers are limited to LAB/SANDBOX; real connectors need separate approval",
            )
        try:
            validate_endpoint(body.endpoint, settings.connector_allowlist)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        connector_id = uuid4()
        sealed = None
        if body.webhook_secret:
            try:
                sealed = seal(
                    body.webhook_secret, settings.secret_master_key, f"connector:{connector_id}"
                )
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
        impl = build(dict(kind=body.kind, config={}))
        row = scope.conn.execute(
            "INSERT INTO connectors(id,organization_id,environment_id,kind,name,capabilities,authoritative,config,"
            "secret_ref,secret_envelope,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                connector_id,
                org,
                env,
                body.kind,
                body.name,
                Jsonb(impl.capabilities().as_dict()),
                body.authoritative,
                Jsonb(dict(endpoint=body.endpoint)),
                f"envelope:connector:{connector_id}" if sealed else None,
                Jsonb(sealed) if sealed else None,
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "connector.created",
            connector_id,
            body.name,
            after=dict(
                kind=body.kind,
                endpoint=body.endpoint,
                authoritative=body.authoritative,
                has_secret=bool(sealed),
            ),
        )
        return envelope(scope, public(row))


def create_entra(org: UUID, env: UUID, body: EntraRequest, request: Request):
    settings = request.app.state.settings
    with scoped(request, org, env, "connector:manage") as scope:
        if scope.environment["kind"] not in {"SANDBOX", "PRODUCTION"}:
            raise HTTPException(
                409, "Entra ID connectors belong in a SANDBOX or PRODUCTION environment"
            )
        if scope.conn.execute(
            "SELECT 1 FROM connectors WHERE environment_id=%s AND kind='entra'", (env,)
        ).fetchone():
            raise HTTPException(
                409, "This environment already has an Entra ID tenant; use a separate environment"
            )
        connector_id = uuid4()
        try:
            sealed = seal(
                body.client_secret, settings.secret_master_key, f"connector:{connector_id}"
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        config = dict(tenant_id=body.tenant_id.lower(), client_id=body.client_id.lower())
        capabilities = entra.EntraConnector(config, "placeholder-not-used").capabilities()
        row = scope.conn.execute(
            "INSERT INTO connectors(id,organization_id,environment_id,kind,name,capabilities,authoritative,config,"
            "secret_ref,secret_envelope,created_by) VALUES(%s,%s,%s,'entra',%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                connector_id,
                org,
                env,
                body.name,
                Jsonb(capabilities.as_dict()),
                body.authoritative,
                Jsonb(config),
                f"envelope:connector:{connector_id}",
                Jsonb(sealed),
                scope.user_id,
            ),
        ).fetchone()
        scope.audit(
            "connector.created",
            connector_id,
            body.name,
            after=dict(
                kind="entra",
                tenant_id=config["tenant_id"],
                authoritative=body.authoritative,
                has_secret=True,
            ),
        )
        return envelope(scope, public(row))


@router.put(ENV + "/connectors/{connector_id}/faults", dependencies=[Depends(development_only)])
def faults(org: UUID, env: UUID, connector_id: UUID, body: FaultConfig, request: Request):
    with scoped(request, org, env, "connector:manage") as scope:
        if scope.environment["kind"] not in {"LAB", "SANDBOX"}:
            raise HTTPException(
                409, "Fault injection exists only for mock connectors in LAB/SANDBOX"
            )
        row = connector_for(scope, connector_id)
        config = dict(
            row["config"], **{k: v for k, v in body.model_dump().items() if v is not None}
        )
        for key in ("fail_on_page", "rate_limit_on_page"):
            if getattr(body, key) is None:
                config.pop(key, None)
        scope.conn.execute(
            "UPDATE connectors SET config=%s WHERE id=%s", (Jsonb(config), connector_id)
        )
        scope.audit(
            "connector.faults_configured",
            connector_id,
            "Mock provider fault injection",
            after=config,
        )
        return envelope(scope, dict(config=config))


@router.post(ENV + "/connectors/{connector_id}/sync", status_code=202)
def sync(org: UUID, env: UUID, connector_id: UUID, body: SyncRequest, request: Request):
    with scoped(request, org, env, "connector:sync") as scope:
        row = connector_for(scope, connector_id)
        if not request.app.state.settings.development and row["kind"] in PROVIDERS:
            # Mock providers replay SYNTHETIC payloads; leftovers from development stay inert.
            raise HTTPException(422, "Connector kind not available in production")
        if row["kind"] == "sandbox":
            raise HTTPException(409, "Use the sandbox sync endpoint for the sandbox connector")
        queue(scope, connector_id, body.mode)
        scope.audit("connector.sync_queued", connector_id, f"{body.mode} sync queued")
        return envelope(
            scope,
            dict(
                queued=True,
                mode=body.mode,
                status_url=f"/api/v1/organizations/{org}/environments/{env}/sync-runs",
            ),
        )


@webhooks.post(ENV + "/connectors/{connector_id}/webhook", status_code=202)
async def webhook(org: UUID, env: UUID, connector_id: UUID, request: Request):
    """Signed change notification from a provider. No session: authenticity is the HMAC."""
    raw = await request.body()
    signature = request.headers.get("X-Signature", "")
    stamp = request.headers.get("X-Timestamp", "")
    delivery = request.headers.get("X-Delivery-Id", "")
    if not (signature.startswith("sha256=") and stamp.isdigit() and 8 <= len(delivery) <= 100):
        raise HTTPException(401, "Missing or malformed signature headers")
    if abs(time.time() - int(stamp)) > WEBHOOK_TOLERANCE:
        raise HTTPException(401, "Stale webhook timestamp")
    settings = request.app.state.settings
    with request.app.state.db.transaction(org) as conn:
        row = conn.execute(
            "SELECT * FROM connectors WHERE id=%s AND environment_id=%s", (connector_id, env)
        ).fetchone()
        if not row or not row["secret_envelope"]:
            raise HTTPException(401, "Webhook verification failed")
        if (not settings.development and row["kind"] in PROVIDERS) or row["kind"] == "entra":
            # Entra connectors have no webhooks; their envelope holds the Graph client secret.
            raise HTTPException(401, "Webhook verification failed")
        try:
            secret = open_envelope(
                row["secret_envelope"],
                settings.secret_master_key,
                f"connector:{connector_id}",
                settings.secret_master_key_previous,
            )
        except (ValueError, InvalidTag):
            # Key withdrawn or misconfigured: fail closed, tell the operator, not the sender.
            logging.getLogger("identityguardian").error(
                "Connector %s secret cannot be opened with the configured master keys",
                connector_id,
            )
            raise HTTPException(503, "Webhook verification unavailable") from None
        expected = hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest("sha256=" + expected, signature):
            raise HTTPException(401, "Webhook verification failed")
        if conn.execute(
            "SELECT 1 FROM webhook_deliveries WHERE connector_id=%s AND delivery_id=%s",
            (connector_id, delivery),
        ).fetchone():
            raise HTTPException(409, "Duplicate webhook delivery")
        conn.execute(
            "INSERT INTO webhook_deliveries(organization_id,connector_id,delivery_id) VALUES(%s,%s,%s)",
            (org, connector_id, delivery),
        )
        conn.execute(
            "INSERT INTO outbox(id,organization_id,event_type,payload) "
            "VALUES(%s,%s,'connector_sync_requested',%s)",
            (
                uuid4(),
                org,
                Jsonb(dict(connector_id=str(connector_id), mode="incremental", actor=None)),
            ),
        )
        return dict(accepted=True, mode="incremental")
