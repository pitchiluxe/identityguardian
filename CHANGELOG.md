# Changelog

## 2026-09-30 — Phase 1 local foundation

Added FastAPI API with Keycloak OIDC (state, nonce, PKCE, server-stored login attempts), hashed opaque sessions with idle/absolute expiry, CSRF and origin checks, DB-backed rate limits and strict security headers. PostgreSQL migrations with forced row-level security, separate migration/runtime/worker roles and append-only audit grants. Independent platform-role change workflow (propose → approve with recent MFA → execute) with digest and version binding, last-administrator guard and atomic audit/outbox. Leased idempotent outbox worker with no external side effects. React shell with members, role requests, audit trail and explicitly planned navigation. Local setup scripts, Compose alternative, unit/API/integration/browser tests. Limitations in INSTALLATION.md. No identity ingestion, graph, AI or connector functionality.

## 2026-09-30 — Phase 0 review draft

Added architecture, logical data/graph models, security/threat design, UI/AI/API/connector specifications, traceability, roadmap, foundation work packages, demo/lab contracts, testing strategy and specialist instructions. Original prompt preserved. No application implementation or operational validation.
