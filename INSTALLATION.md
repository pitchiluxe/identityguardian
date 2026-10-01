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
npm run build
```

`local_setup.py` refuses to overwrite an existing `.env`. `bootstrap` refuses to run twice. No default password ships; synthetic login credentials are generated into `.local/bootstrap.json` (ignored by Git). Synthetic users: alex (org_admin, operator), jordan (approver), sam (viewer).

## Run

```
.venv/Scripts/python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000 and sign in through Keycloak. The API serves the built shell from `apps/web/dist`. Optional worker (records outbox receipts only; no external side effects):

```
.venv/Scripts/python -m apps.worker.main --organization 10000000-0000-4000-8000-000000000001
```

## Limitations

- HTTP and non-Secure cookies are accepted only for loopback with `DEVELOPMENT=true`; any other origin fails configuration validation.
- The synthetic Keycloak realm uses passwords only. The `mfa` assurance needed to approve or execute role changes is not issued by this realm, so those UI actions are refused with an MFA message in real browser sessions; API tests exercise them with seeded MFA sessions. Configuring OTP in the realm is future work.
- The worker processes one organization per process.
- No identity ingestion, graph, AI or connectors (Phase 2+).
