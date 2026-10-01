# Phase 3 — effective access and lineage

Approved by the user on 2026-09-30. Depends on Phase 2.

## Bounded plan

1. `domain/access.py`: forward DFS over active grant edges (membership, nesting, role, permission, resource, machine/agent grants) with per-path visited sets; source-native `expires_at` honoured at the effective time; explicit `DENY_ASSIGNMENT` on the identity or any (nested) group overrides; supported conditions → CONDITIONAL, unsupported → UNKNOWN; permission without resource scope is still an entitlement. Bounds (depth 8, 100 paths, 10,000 expansions, 2 s) return `complete=false` with a reason.
2. Reverse query: candidate identities by reverse grant discovery, then forward lineage per candidate (deny checks need the candidate's memberships).
3. Usage context per resource: last observed use and coverage windows; "no observed use during coverage", never "never used".
4. Routes `GET …/identities/{id}/access`, `GET …/resources/{id}/principals` (capability `access:read`; viewer excluded), both bitemporal and enveloped with evidence IDs.
5. Web: Access page with identity picker, effective-time selector, per-entitlement routes rendered as lineage chains with ticket/approver/dates/conditions/deny, usage note and "who else can access".

## Acceptance

Direct/nested/conditional/deny/alternative-path tests; evidence provenance shown.

## Verification ledger (2026-09-30)

- `tests/api/test_access.py` (7): Erick → Finance-Legacy → ERP-Operators → ERP Application Administrator → Manage payroll configuration → Payroll with TKT-1042/approver and nested-origin label; Tom's two ERP routes; alternate payroll route counted separately; Sofia ALLOW + CONDITIONAL routes and UNKNOWN for an unsupported condition; explicit deny overrides a grant; Eng-Platform/Eng-SRE cycle terminates; path bound reports partial; Kim's delegated grant expires at its source-native time; historical usage; principals for Payroll; viewer 403; non-identity 422; cross-environment 404.
- pytest 51 passed; Playwright 9 passed (+ setup project seeding the synthetic environment), including `access.spec.ts`.
