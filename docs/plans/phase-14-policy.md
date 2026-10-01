# Phase 14 — policy-as-code

Approved by the user on 2026-09-30. Depends on Phases 7–8 and 13.

## Bounded plan

1. `domain/policy.py`: declarative schema v1 (name, purpose, scope, typed conditions with all/any up to depth 3 and 20 leaves, action `flag` | `reject_proposed`, expiring exceptions, tests). Fields and operators are allowlisted (eq, neq, in, not_in, exists, missing, contains, before, after with timezone); unknown keys, fields, operators or actions are rejected; at least one violation and one no-violation test are required. No code is ever evaluated.
2. Migration `014_policies.sql`: `policies`, versioned `policy_versions` (DRAFT → TESTED/TEST_FAILED → SIMULATED → APPROVED/REJECTED → ACTIVE → SUPERSEDED), DB CHECK approver ≠ proposer, one ACTIVE version per policy.
3. Routes: propose (new policy or new version, used for reversion), test, simulate (scan existing grants; approval digest binds definition, test results, matches and graph version), decision (`policy:approve`, MFA, independent, digest, unchanged twin), activate.
4. Enforcement: active FLAG policies add POLICY_VIOLATION findings (never revoke); active REJECT_PROPOSED policies are evaluated for simulated additions and block submission. The active policy set's version is bound into every change digest and rechecked at approval and in the worker, so a policy change makes pending approvals STALE.
5. Web: Policies page (JSON definition, lifecycle steps, test results, scope matches, approve exact digest, activate).

## Verification ledger (2026-09-30)

- `tests/api/test_policies.py` (6): unknown operator/field/key, single test, naive date and unsupported action rejected; viewer 403; full lifecycle flags Grace's permanent Global Administrator without revoking it, wrong digest 409, proposer cannot approve; failing tests block simulation; active and expired exceptions; REJECT_PROPOSED blocks a permanent Directory-Admins proposal and activation marks an in-review change STALE at approval; reversion is a new reviewed version superseding the old one.
- Playwright `policies.spec.ts`: admin drafts/tests/simulates, approver (MFA) approves the digest, admin activates.

## Correction after the Phase 14 commit

The Phase 14 commit was made while the parallel suite was intermittently failing (the gate in the commit command did not check pytest's exit status). Investigation showed `ConnectionTimeout` under concurrent load: every request opened a new PostgreSQL connection. Fix (separate commit): `psycopg_pool` with tenant scope still transaction-local, `RESET ALL` on return (committed so the pool keeps the connection), pools closed on application shutdown, a single-connection pool test proving scope never carries over (including after an error), the AI rate-limit test made window-boundary safe, and browser locators scoped. Suite: 131 passed with no warnings; Playwright 23 passed.
