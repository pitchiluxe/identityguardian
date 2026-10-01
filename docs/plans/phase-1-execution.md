# Phase 1 execution plan

Approved direction: PHASE_0_REVIEW.md. Goal: a runnable local foundation with real OIDC, PostgreSQL isolation, independent platform-role approval, audit/outbox and an accessible shell. No later-phase IAM functionality.

Implementation uses native execution and test-first security cases. Preserve all Phase 0 invariants. Dependency versions are captured from actual installation. Local HTTP is limited to loopback development; deployed mode requires HTTPS secure cookies.

## Interfaces and task order

1. Configuration and security primitives: `Settings`, `digest`, `capabilities`, `require_recent_mfa`, `validate_claims`. Consumers: auth/API. Tests: forged issuer/audience/nonce, expired/future authentication and unknown roles. Files: apps/api/app/config.py, security.py; tests/unit/test_security.py.
2. Database: scoped transaction and migration; users/sessions/login attempts global private auth records, memberships/organizations/environments/audit/role requests/outbox scoped by RLS. Consumers: API/worker. Tests: runtime-role cross-tenant isolation, forbidden audit mutation, failed transaction rollback. Files: migrations/001_foundation.sql, apps/api/app/db.py; tests/integration/test_database.py.
3. Authentication/API: server-stored OIDC state/PKCE, opaque sessions/CSRF, membership rechecks, role proposal/independent approval/execution. Tests: invalid state, replay, unauthenticated access, forged tenant, self-promotion, stale approval, revoked membership. Files: auth.py, main.py; tests/api/test_foundation.py.
4. Worker: lease and idempotent local audit-notification processing, no connector writes. Files: apps/worker/main.py; database integration tests.
5. Shell: login, organization selector, foundation status, members, role requests, audit, clearly planned navigation. Files: apps/web/src, package.json, browser tests. Design: navy/cyan approved palette, compact navigation, evidence-style status ledger rather than fabricated IAM metrics. Keyboard and mobile layouts required.
6. Local setup and verification: generated unique secrets/realm, Compose PostgreSQL/Keycloak, migration/bootstrap CLI; run API/database/security/browser tests, build, lint and scans; document limitations and commit.

Review focus: tenant context reuse, revoked membership, attacker-controlled role fields, audit rollback, interrupted/replayed login. Each is exercised in the consuming boundary tests. Authentication trusts validated subject only, never token role claims.

## Execution ledger

- Phase 0 approved by user. Expanded bounded foundation plan; no new approval required for the previously authorized local Phase 1 scope.
- Pre-flight: session -> membership -> scoped DB -> audit/outbox all share server-validated actor and organization IDs. Role-change requests are separate from future IAM changes and cannot bypass independent approval.
- Local npm wrapper is broken; use the installed npm CLI directly. Bundled Python creates project-only .venv. Docker availability is being checked.
- Implementation of tasks 1–5 complete. Regressions for forged-cookie rate-limit reset and approval revocation during lock wait reproduced red, fixed, green.
- Verification (2026-09-30): API restarted on current code; pytest 35 passed; Playwright 4 passed against real Keycloak/PostgreSQL; build, ruff, pip-audit and npm audit clean; worker `--once` smoke run exit 0. Native PostgreSQL and portable Keycloak used; Docker not required. Results in TESTING.md, setup and limitations in INSTALLATION.md.
- Known limitation: synthetic realm has no OTP, so browser sessions cannot satisfy the MFA gate for approve/execute; covered by API tests with seeded MFA sessions.
