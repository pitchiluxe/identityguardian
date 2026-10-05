# Phase 23 — read-only Microsoft Entra ID connector

Approved by the user on 2026-10-05 ("approve"). It is a portfolio demonstration against the user's own free Entra test tenant. Spec: `docs/superpowers/specs/2026-10-05-entra-connector-design.md`. Plan: `docs/superpowers/plans/2026-10-05-entra-connector.md`.

## Verification ledger
- 2026-10-05: new tests:
  - `tests/unit/test_entra_connector.py` (9): canonical mapping including guests, nested groups, directory roles and user app assignments, with group-to-app assignments skipped and counted; only POST to the token URL and GET to Graph; no secret in logs, exceptions or cursors; 429 → RateLimited; 401 → fixed message; an expired token is refreshed once; an empty tenant completes; GUID validation.
  - `tests/api/test_entra_registration.py` (4): secret sealed and absent from responses, listings, audit and stored rows; LAB refused, viewer refused, bad GUID or empty secret refused; Entra allowed in production mode while mocks are refused; a worker sync builds with the decrypted secret and ingests the tenant.
  - `tests/e2e/entra.spec.ts` (1).
- Full verification: ruff clean, secret scan 0 findings, Playwright 30 passed / 1 skipped. pytest 342 passed, 1 failed: the recurring `test_policies` 409.
- **Root cause of the recurring 409 found and fixed (separate commit):** `snapshot_for()` turned a missing `known_at` into "now". `graph.load()` treated a request as current only if no ~15 ms Windows clock tick passed before its own check, so under load simulate and approve got different version formats. A regression test now forces a tick between the two reads; the snapshot, policy, twin, history and access suites pass (37).
