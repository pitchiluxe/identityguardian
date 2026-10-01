# Phase 4 — privilege creep, history and timeline

Approved by the user on 2026-09-30. Depends on Phase 3.

## Bounded plan

1. `domain/findings.py` (rules `rules-2026.09-1`, labelled RULE-BASED): PRIOR_ROLE_RETAINED (grant predating a move event, still active, held by under half of current-department peers with sample size shown), TERMINATED_WITH_ACCESS, DORMANT_PRIVILEGED (no sign-in for 90 days while privileged), UNUSED_PRIVILEGED_ENTITLEMENT (no observed use within ≥60 days of complete coverage). Stable finding keys for later binding. Usage statements always cite coverage windows and say absence of observed use is not proof of non-use.
2. Identity timeline: employment events, grant starts/ends (inferred ends labelled), usage summaries, each with evidence IDs; bitemporal `known_at`.
3. Routes `GET …/findings` (`findings:read`, filters by rule/identity, counts) and `GET …/identities/{id}/timeline` (`history:read`).
4. Web: Privilege radar page, finding cards with lineage and coverage, dashboard rule counts, profile timeline.
5. Performance correction found during verification: migration `004_rls_uuid_policies.sql` replaces text-cast RLS predicates with an index-usable `organization_id = app_org()` comparison (same semantics: missing setting matches nothing) and adds scoped indexes.

## Verification ledger (2026-09-30)

- `tests/api/test_findings.py` (6): Erick's finding with TKT-1042, move evidence, peers 0/1, privileged payroll reach and NOT_OBSERVED usage; stable keys; HelpDesk-L2/All-Staff not attributed; Ben critical leaver; Dave dormant (Kim at 89 days not); unused payroll for Erick but not Tom; removal clears current finding while effective-time history retains it; viewer 403 and filters; ordered timeline.
- Suite time regressed to 342 s with two timing failures as tenant data accumulated; root cause was the cast in RLS predicates. After migration 004: pytest 57 passed in 86 s. Playwright 10 passed including `radar.spec.ts`.
