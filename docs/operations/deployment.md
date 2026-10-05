# Deployment runbook

Status: **packaging for local acceptance**. This project has not been deployed anywhere. Before any production use, the owner must sign off the gates in [production-acceptance.md](production-acceptance.md).

## Topology

`infra/compose.production.yaml` defines the stack. One image (`infra/docker/Dockerfile`) runs the API, the worker and operator commands as non-root uid 10001. All application containers run with a read-only root filesystem, a tmpfs `/tmp`, all capabilities dropped and `no-new-privileges`.

| Service | Networks | Role |
|---|---|---|
| `proxy` (Caddy) | edge, fixed IP 172.30.0.10 | TLS, 1 MB body cap including chunked bodies (U2), HSTS, blocks `/api/v1/ready` from outside, JSON access log |
| `api` | edge + backend | FastAPI and the web shell. Trusts `X-Forwarded-*` only from the proxy IP, so rate limits key on the real client |
| `worker` | backend (internal, no egress) | Outbox, sandbox execution, JIT expiry, reconciliation. Heartbeat healthcheck |
| `migrate` | backend | One-shot `manage.py migrate`. API and worker start only after it succeeds |
| `postgres` | backend (internal) | No published port |

## Prerequisites

- An external OIDC provider over HTTPS. Register a public client with PKCE whose redirect URI is `https://<domain>/api/v1/auth/callback`, and require MFA (`otp`) for approvers and operators. The local Keycloak is development-only (U4).
- A DNS name for `IG_DOMAIN`. With `localhost`, Caddy uses its internal CA, which is only suitable for local acceptance.
- Docker Engine 24+ with Compose v2.

## First start

```
python -m scripts.package_secrets            # random secrets -> .local/secrets/ (refuses to overwrite)
set IG_DOMAIN=iam.example.org
set OIDC_ISSUER_URL=https://idp.example.org/realms/identityguardian
docker compose -f infra/compose.production.yaml up -d --build
docker compose -f infra/compose.production.yaml ps     # all healthy; migrate exited 0
```

Create the real organization and its first administrator once:

```
docker compose -f infra/compose.production.yaml run --rm migrate   python scripts/manage.py init-organization --name "Your Organization" --admin-email admin@your-domain
```

The command creates the organization, a **Production** environment and a single-use, 72-hour org_admin invite. It prints `/invite/<token>`: prefix it with `APP_ORIGIN` and send it only to that administrator, who registers their own password and one-time code. It refuses to run if an organization already exists (use `--allow-additional` deliberately). The synthetic `bootstrap` command is refused outside development.

## Configuration

Secrets come from files under `/run/secrets` (`IG_SECRETS_DIR`), never from the image. Non-secret settings are environment variables: `APP_ORIGIN`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `DEVELOPMENT=false`, `SECURE_COOKIES=true`, `LOG_FORMAT=json` and `AI_ENABLED`. Settings refuse to start if HTTP is used outside loopback development or if Secure cookies are disabled in deployed mode.

AI is off by default because no model server is packaged. To enable it, run Ollama on a host reachable from the `api` service and set `OLLAMA_BASE_URL` and `AI_ALLOWED_HOSTS`.

## Upgrade

1. Take a backup and confirm the drill passes (see [backup-recovery.md](backup-recovery.md)).
2. Run `docker compose ... build`, then `up -d`. `migrate` applies new numbered migrations before the API restarts.
3. `GET /api/v1/ready` from inside the network returns `ready` only when every shipped migration is applied.

Migrations are forward-only. To roll back, restore the pre-upgrade backup and the previous image.
