# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Governance (read first)

Read AGENTS.md, PHASE_0_REVIEW.md and the current phase plan (`docs/plans/phase-1-execution.md`). PROMPT.md is the original brief; user instructions take precedence. Follow the human approval boundary: work only inside the approved phase, never start a later phase without user approval, never push/publish without authorization.

- Planned is not implemented. Do not describe planned integrations, AI, graph features or controls as working. Every control either works (with tests) or is labeled DEMO/PLANNED.
- Never fabricate IAM findings, AI outputs, screenshots or test results. Synthetic data must be labeled.
- AI has no execution authority. No production connections or real IAM changes.
- `docs/agents/*.md` are role descriptions, not authorization to spawn agents.
- New trust boundaries require THREAT_MODEL.md updates; new controls require negative authorization tests.

## Status

Phase 0 (design docs) approved; Phase 1 "foundation" is in progress per `docs/plans/phase-1-execution.md`. Top-level docs (README.md, INSTALLATION.md, TESTING.md) still describe the Phase 0 state and lag the code. Phase 1 scope only: OIDC login, PostgreSQL tenant isolation, independent role-change approval, audit/outbox, accessible shell. No graph, AI or connector functionality.

## Commands

Windows, native execution (no Docker required). Python lives in project `.venv`; use `.venv/Scripts/python`. The npm wrapper on this machine is broken — call the installed npm CLI directly.

Local setup (generates ignored `.env` and `.local/`; refuses to overwrite an existing `.env`):
```
.venv/Scripts/python scripts/local_setup.py          # secrets, Keycloak realm, synthetic users -> .local/bootstrap.json
.venv/Scripts/python scripts/native_postgres.py      # project-local PostgreSQL cluster on 127.0.0.1:55432 (POSTGRES_BIN overrides path)
.venv/Scripts/python scripts/install_local_idp.py    # checksum-verified portable Java + Keycloak into .local/runtime
powershell scripts/start_idp.ps1                     # Keycloak on localhost:58080 with realm import
.venv/Scripts/python scripts/manage.py migrate       # creates guardian_app/guardian_worker roles, applies migrations/*.sql
.venv/Scripts/python scripts/manage.py bootstrap     # one-time synthetic Contoso org; refuses if already bootstrapped
```
`infra/compose.yaml` is the Docker alternative for PostgreSQL + Keycloak (same ports).

Run:
```
npm run build                                                    # tsc --noEmit + vite build -> apps/web/dist
.venv/Scripts/python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000   # API also serves apps/web/dist
.venv/Scripts/python -m apps.worker.main --organization <uuid> [--once]
npm run dev                                                      # Vite dev server, proxies /api to :8000
```

Test / lint:
```
.venv/Scripts/python -m pytest                                   # all Python tests (API + integration need migrated DB via .env)
.venv/Scripts/python -m pytest tests/unit                        # no DB needed
.venv/Scripts/python -m pytest tests/api/test_foundation.py::test_viewer_cannot_forge_role_or_skip_csrf
.venv/Scripts/python -m pytest -m "not integration"
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pip_audit -r requirements.lock
npm test                                                         # Playwright E2E; needs built web, API on :8000, Keycloak, bootstrap
npx playwright test tests/e2e/login.spec.ts -g "viewer"
```
Python deps are pinned in `requirements.lock`; JS deps pinned exactly in `package.json`. Record actual test output; compilation alone is not verification.

## Architecture

FastAPI modular monolith + React/Vite shell + PostgreSQL with RLS + local Keycloak (OIDC). Full design in ARCHITECTURE.md / SECURITY.md / DATABASE.md; key cross-file mechanics:

- **Tenant isolation is two layers.** `Database.transaction(org)` (`apps/api/app/db.py`) opens a fresh connection and sets transaction-local `app.org`; RLS policies in `migrations/001_foundation.sql` (FORCE RLS) filter scoped tables by it. RLS does not authorize tenant choice — the API must check membership first (`auth.membership`). Unscoped queries as runtime role return nothing. Org discovery goes through the narrow `SECURITY DEFINER` function `user_organizations(uid)`.
- **Three DB roles.** `guardian_migrator` (owner; used only by `scripts/manage.py` and test fixtures), `guardian_app` (API runtime, NOBYPASSRLS, column-level grants, INSERT-only on `audit_events`), `guardian_worker`. Never let runtime code use the migration URL. Schema changes = new numbered file in `migrations/` plus matching grants.
- **Auth.** `apps/api/app/auth.py`: server-stored OIDC state/nonce/PKCE (`login_attempts`), opaque session cookie stored hashed (`sessions`), CSRF hash, idle/absolute expiry, membership rechecked per request. Only the validated subject is trusted — never role claims from tokens. Roles come from `memberships.roles`; `security.ROLE_CAPABILITIES` maps roles → capabilities.
- **Role change workflow.** propose (`members:propose`) → approve (`members:approve`, recent MFA, approver ≠ requester ≠ target, enforced also by DB CHECK) → execute (`members:execute`). Each step binds a `digest` of the canonical request plus `expected_version`; stale versions/digests are rejected. Domain change, audit event and outbox row commit in one transaction.
- **Worker** (`apps/worker/main.py`): leases outbox rows with `FOR UPDATE SKIP LOCKED`, writes idempotent `event_receipts`, marks processed. No external side effects.
- **API boundary middleware** (`main.py`): DB-backed rate limits (`limits.py`), strict security headers/CSP, correlation IDs, psycopg errors → 503. OpenAPI/docs disabled.
- **Config** (`config.py`): HTTP only allowed for loopback with `DEVELOPMENT=true`; non-development requires secure cookies.
- **Web** (`apps/web/src/main.tsx`): single-file shell; unimplemented sections render as explicitly "Planned".
- **Tests**: `tests/api/conftest.py` seeds two orgs and sessions directly via the migration URL and uses `TestClient(create_app(Settings()))`. E2E reads synthetic credentials from `.local/bootstrap.json`.

## Secrets

`.env`, `.local/` (generated passwords, realm, Postgres data, Keycloak runtime) are git-ignored. Scripts never print secrets; keep it that way. Do not read or echo `.local/bootstrap.json` credentials into chat or commits.
