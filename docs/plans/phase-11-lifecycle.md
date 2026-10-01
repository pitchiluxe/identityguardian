# Phase 11 — JML intelligence

Approved by the user on 2026-09-30. Depends on Phases 7–10.

## Bounded plan

1. Migration `010_lifecycle.sql`: `jml_baselines` (versioned, PROPOSED → APPROVED/REJECTED/SUPERSEDED, DB CHECK approver ≠ proposer, one APPROVED per department), `lifecycle_workflows` (one per employment event), `disable_account` change kind. Migration `011_fault_operations.sql`: fault injection per connector operation.
2. `domain/lifecycle.py` (`jml-2026.09-1`, RULE-BASED): joiner compares direct grants with the approved baseline only (no baseline → nothing provisioned); mover classifies each direct grant RETAIN (acquired for new role, in new baseline, or common among new peers), REMOVE (predates move and in the old baseline or reaching privileged access) or REVIEW, and proposes missing new-baseline groups; leaver plans account disable, grant removal, ownership transfer to the manager plus removal of the leaver's ownership, credential rotation, resource owner reassignment (manual), reset-exposure context and an explicit UNKNOWN for sessions/tokens.
3. Connector `disable_account` (new account revision `enabled=false`), simulation/versioning (`node:<id>:enabled`), execution and read-back.
4. Routes: baselines (propose `policy:propose`; decide `policy:approve` + MFA, independent), events, plan, workflow creation (each selected action becomes a lifecycle-origin proposal, simulated and submitted via the shared `simulate_and_submit`), workflow status aggregation (COMPLETED / IN_PROGRESS / PARTIAL / FAILED).
5. Web: Lifecycle page (baselines, events, plan with evidence, workflow creation and status).

## Verification ledger (2026-09-30)

- `tests/api/test_lifecycle.py` (5): baseline independence, MFA approval, unknown-group 422, re-decision 409, supersession; joiner without baseline vs Engineering baseline (Grace's direct Global Administrator → REVIEW); Erick mover REMOVE Finance-Legacy with TKT-1042 evidence, RETAIN HelpDesk-L2/IT-Support/All-Staff; Ben leaver plan (disable, remove, ownership transfer to Olivia, reset exposure, sessions UNKNOWN); leaver workflow with an injected removal failure ends PARTIAL while the account disable succeeds.
- Verification found that `disable_account` consumed the `remove_relationship` fault; faults are now per operation.
- Playwright `lifecycle.spec.ts` passed.
