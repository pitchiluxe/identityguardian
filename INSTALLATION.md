# Installation

Status: Phase 1 local foundation. Loopback development only; no production packaging, TLS or backups. All data is synthetic (Contoso, LAB environment).

Verified on Windows 11 with Node.js/npm, a project `.venv` (Python 3.12, deps from `requirements.lock`), PostgreSQL 17 binaries and portable Keycloak 26.7.3 / Java 21. Docker is optional: `infra/compose.yaml` provides PostgreSQL and Keycloak on the same loopback ports.

## First-time setup

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock
npm ci
.venv/Scripts/python scripts/local_setup.py        # unique secrets -> ignored .env, realm + synthetic users -> .local/
.venv/Scripts/python scripts/native_postgres.py    # project-local cluster on 127.0.0.1:55432 (set POSTGRES_BIN if not PostgreSQL 17 default path)
.venv/Scripts/python scripts/install_local_idp.py  # checksum-verified Java + Keycloak into .local/runtime
powershell -File scripts/start_idp.ps1             # Keycloak on localhost:58080 (leave running)
.venv/Scripts/python scripts/manage.py migrate     # creates runtime/worker roles, applies migrations
.venv/Scripts/python scripts/manage.py bootstrap   # one-time synthetic organization and memberships
.venv/Scripts/python scripts/provision_local_users.py --mfa alex --mfa jordan --mfa jamie --mfa quinn
npm run build
```

`local_setup.py` refuses to overwrite an existing `.env`. `bootstrap` refuses to run twice. No default password ships; synthetic login credentials are generated into `.local/bootstrap.json` (ignored by Git). Synthetic users: alex (org_admin, operator), jordan and jamie (approvers), quinn (operator), riley (reviewer), casey (investigator), morgan (auditor), sam (viewer), lee (learner).

`provision_local_users.py` is idempotent: it adds any missing synthetic users to the loopback Keycloak realm and memberships, configures the realm's `amr` claim (password → `pwd`, one-time code → `otp`), and enrols TOTP for the named users. TOTP seeds are stored only in `.local/bootstrap.json`; add the seed to an authenticator app or let the browser tests compute codes.

## Run

```
powershell -File scripts/dev_api.ps1     # (re)starts API on 127.0.0.1:8000 and the worker
```

Or individually:

```
.venv/Scripts/python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000
.venv/Scripts/python -m apps.worker.main --organization 10000000-0000-4000-8000-000000000001
```

Open http://localhost:8000 and sign in through Keycloak. The API serves the built shell from `apps/web/dist`. The worker executes approved changes against the sandbox connector only, expires JIT grants and reconciles uncertain outcomes; without `--organization` it serves every organization with pending work.

## Limitations

- HTTP and non-Secure cookies are accepted only for loopback with `DEVELOPMENT=true`; any other origin fails configuration validation.
- Approval and execution require `pwd`+`otp` (or `mfa`) within 5 minutes. Users without enrolled TOTP can view and propose but cannot approve or execute.
- All execution targets the sandbox connector. No production adapter exists; PRODUCTION environments refuse execution.
- No identity ingestion, graph, AI or connectors (Phase 2+).
