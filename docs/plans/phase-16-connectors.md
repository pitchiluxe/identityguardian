# Phase 16 — enterprise connector framework

Approved by the user on 2026-09-30. Builds on the sandbox interfaces from Phase 2.

## Bounded plan

1. `connectors/base.py`: the contract (capabilities, paged `read(cursor)` returning canonical node/relationship objects with provenance, optional apply/read-back — read-only by default), transient error types, and an endpoint policy (https only, allowlisted host, never private/loopback/link-local; `mock://` for mocks).
2. `connectors/providers.py` + `packages/fixtures/mock_providers.py`: deterministic SYNTHETIC Microsoft Entra ID-shaped and Okta-shaped payloads translated to canonical objects (25 per page), with injectable faults (`fail_on_page`, `rate_limit_on_page/_times`, `omit`). They never contact real services.
3. `connectors/runner.py`: worker job per sync; each page commits atomically with run progress and a resumable cursor; rate limits retry with bounded exponential backoff (3 retries); unavailability ends PARTIAL with the cursor saved; resume continues from it (partial coverage); only a complete authoritative full read reconciles absence (end inferred). The Ingestor now takes a source name.
4. Migrations `016_connectors.sql` (connector config, encrypted secret envelope, health, last cursor; sync run cursor/pages/retries; webhook deliveries; `connector_sync_requested` outbox event) and `017_sandbox_environments.sql` (runtime may create SANDBOX environments; LAB only for learners; never PRODUCTION).
5. `secrets_envelope.py`: AES-256-GCM envelope (random data key wrapped by a master key from server configuration, bound to a context); APIs only expose `has_secret`. `local_setup.py` now generates a local master key.
6. Routes: connector list/create (`connector:manage`, LAB/SANDBOX only for mocks, endpoint policy), fault configuration, queue sync (202), signed webhooks (HMAC-SHA256 over timestamp and body, ±5 minutes, one-time delivery IDs) that queue incremental syncs, sandbox environment creation.
7. Web: connector registry on Integrations; sandbox environment form on Administration.

## Verification ledger (2026-10-01)

- `tests/unit/test_connectors.py` (18): contract suite for both providers (capabilities, paging, forward-only cursors, canonical ordering with endpoints first, deterministic replay, faults/throttling, writes refused); endpoint policy blocks http, metadata IP, loopback, private, file and non-allowlisted hosts; envelope round trip, context binding, wrong key, no master key.
- `tests/api/test_connectors.py` (7): job sync ≥4 pages and replay unchanged with secrets never returned; failure on page 3 leaves PARTIAL with cursor 50, nothing tombstoned, resume succeeds and health returns to HEALTHY; throttling retried twice then bounded to PARTIAL; absence closed only by a complete authoritative read and never for a non-authoritative connector; webhook valid/duplicate/wrong secret/stale/tampered/no-secret; registry authorization, SSRF endpoint, PRODUCTION refusal; admins create SANDBOX environments and the runtime role cannot insert PRODUCTION.
- Verification found that running mock providers inside the main Contoso environment duplicated identities (no cross-source correlation); connector work now uses separate sandbox environments and the local test artifact was removed. Cross-source identity correlation remains a documented limitation.
- pytest 192 passed; Playwright 25 passed (1 opt-in capture skipped).
