# Phase 8 — JIT and controlled execution

Approved by the user on 2026-09-30. Depends on Phases 6–7.

## Bounded plan

1. Migration `007_execution_jit.sql`: `approvals` (digest, MFA evidence, 30-minute expiry), `executions` (one per request: idempotency), `jit_grants` (≤ 8 h by CHECK), `sandbox_faults` (LAB/SANDBOX connector fault injection), outbox event `change_execution_requested`, `pending_work_organizations()` (IDs only) for the worker, worker-role grants limited to execution, sandbox and ingestion.
2. API: submit (SIMULATED → IN_REVIEW, simulation current), decision (approve/reject; capability by kind; recent MFA; approver ≠ requester; digest match; stale or expired simulation marks STALE/EXPIRED), execute (capability by kind; MFA; executor ≠ approver; digest; approval expiry; PRODUCTION refused; QUEUED + execution + outbox + audit in one transaction, 202 with status URL), cancel, JIT request (simulate + submit in one bounded call), JIT grant listing with overdue flags, fault injection.
3. Worker (`domain/execution.py`, `apps/worker/main.py`): recheck bindings (approver authority, approval expiry, digest, target revision) and record durable intent before dispatch; sandbox connector write; read-back; ingest; SUCCEEDED only after confirmation. Connector failure → FAILED; lost response → RECONCILIATION_REQUIRED resolved by read-back; restart during EXECUTING → RECONCILIATION_REQUIRED. JIT grants carry a source-native `expires_at`; the worker revokes at expiry under the original approval, keeps REVOKE_PENDING while the source fails and reports overdue grants. Snapshot loading honours source-native expiry.
4. Local IdP: AMR mapper and `pwd`/`otp` references, TOTP enrolment for synthetic approvers/operators (`provision_local_users.py`). Browser tests compute TOTP and avoid code reuse.
5. Web: approval box (exact digest, MFA requirement), execute in sandbox, auto-refresh while pending, JIT access page.

## Corrections found during verification

- Ingestion compared a new observation against any historical digest, so a grant restored to an earlier state was ignored. Fixed by comparing with the latest observation per object (migration `008_observation_reappearance.sql`), with a regression test.
- "Load synthetic fixture" now resets the sandbox source to the fixture baseline, closing non-fixture relationships (recorded as history on the next sync).
- The development worker is scoped to the bootstrapped organization so it cannot race test tenants.

## Verification ledger (2026-09-30)

- `tests/api/test_execution.py` (9): full path with history, audit sequence, replay refusal; self-approval, viewer, tampered digest, missing MFA, approver-as-executor, reviewer denied; stale target and revoked approver refused by the worker; expired approval; connector failure and lost-response reconciliation; restart during execution; concurrent execute yields one 202 and one 409; JIT grant, native TTL, REVOKE_PENDING with overdue alert, retry to EXPIRED; PRODUCTION refused.
- pytest 81 passed. Playwright 17 passed twice consecutively, including `mfa.spec.ts` (Keycloak emits `pwd`+`otp`; password-only sessions do not) and `workflow.spec.ts` (DEMO steps 6–9 and the JIT flow across three MFA users).
