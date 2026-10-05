# Verification strategy

Tools: pytest (unit, API and integration against a real local PostgreSQL with the runtime role), Playwright (browser flows against real Keycloak), ruff, pip-audit and npm audit. Vitest is planned once UI logic warrants it. Synthetic fixtures only.

```
.venv/Scripts/python -m pytest                      # API/integration tests need migrated DB from .env
.venv/Scripts/python -m pytest -m "not integration"
npx playwright test                                 # needs built web, API on :8000, Keycloak, bootstrap
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pip_audit -r requirements.lock && npm audit --omit=dev
```

## Phase 1 results (2026-09-30, Windows 11, local PostgreSQL 17, Keycloak 26.7.3)

| Check | Result |
|---|---|
| pytest (unit, OIDC, API authorization, regressions, database RLS, worker) | 35 passed |
| Playwright (signed-out shell, mobile layout, real OIDC login/logout, viewer denial via UI and API) | 4 passed |
| `npm run build` (tsc + Vite) | succeeded |
| ruff check / format | clean |
| pip-audit / npm audit (production deps) | no known vulnerabilities |

Phase 1 review-focus cases exercised: pooled tenant context, cross-tenant forged IDs, revoked membership, self-promotion and non-independent approval, stale digest/version, attacker-supplied role fields, audit rollback on failed transaction, interrupted/replayed login state, forged-cookie rate-limit reset and approval revocation while waiting for the execution lock. Two regressions were reproduced red before their fixes, then green.

Not yet covered: approve/execute through the browser with real MFA (realm issues password-only sessions), DST/clock tests, independent penetration testing. Phase 19 synthetic benchmarks and their limitations are in docs/plans/phase-19-performance.md. Planned layers below apply to later phases.

| Layer | Required cases |
|---|---|
| Unit/graph | Cycles, alternative grants, conditions/denies, temporal boundaries, bounded traversal |
| Database | Composite FKs, runtime-role RLS, pooled context reset, temporal overlap and outbox atomicity |
| API/RBAC | Every endpoint × role, forged IDs/fields, other tenants, revoked membership, self-promotion |
| Approval | Self-approval, payload changes, stale versions, expiry, replay and concurrent execution |
| Simulation | No base writes, alternate routes, unknown dependencies, possible lockouts |
| History | Late evidence, effective/knowledge distinction, tombstones, DST and coverage gaps |
| JIT | Expiry, restart, source outage, overdue alerts and reconciliation |
| AI | No evidence, fake citations, source injection, unsupported intent, tenant leak, offline provider, invented numbers |
| Audit | App update/delete denied, durable intent, redaction, correlation and failed-action events |
| Connector | Replay, partial sync, rate limit, timeout after source write and readback |
| E2E | Login, scope, evidence, simulation, independent approval, sandbox execution, history/export |
| Lab | Learner isolation, no production access, negative grading cases and non-completing hints |
| Security/ops | CSRF, fixation, XSS, SSRF, formula injection, scans and restore drill |

Each phase adds meaningful tests, runs relevant regression/security suites and documents actual results before its commit. Compilation alone is insufficient. Phase 19 records benchmark hardware/data and p50/p95/p99; Phase 18 includes independent penetration validation, not just scanning.
