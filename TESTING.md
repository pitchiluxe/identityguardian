# Verification strategy

Phase 0 checks artifact completeness, consistency and local links. There are no application tests yet.

Proposed tools: pytest for API/domain/security against real PostgreSQL containers, Playwright for browser flows, Vitest for UI logic. Pin tools during implementation. Synthetic fixtures and controlled clocks only.

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
