# Phase 7 — what-if engine

Approved by the user on 2026-09-30. Depends on Phases 3 and 6.

## Bounded plan

1. `domain/simulate.py`: overlay removals/additions on a shallow copy of the snapshot (base and database untouched); affected identities by reverse grant traversal; per identity lost / retained-with-residual-routes / gained entitlements; possible lockouts (no remaining ALLOW principal for a privileged target); dependencies via `RESOURCE_DEPENDS_ON` (targets and identities); finding deltas from the deterministic rules; explicit unknowns (conditional/unknown routes, bounds, unobserved dependencies).
2. Migration `006_simulations.sql`: immutable `simulations` rows (operations, base graph version, current revision IDs as source versions, policy version, result, digest, expiry); `change_requests.simulation_id/digest`.
3. Digest binds organization, environment, request, kind, target, parameters, operations, source versions, graph version, policy version and expiry (30 minutes).
4. Routes: `POST …/simulations` (`change:simulate`; ad-hoc operations or a change request → SIMULATED), `GET …/simulations/{id}`, `POST …/change-requests` (`change:propose`, manual remove/add), `GET …/change-requests/{id}` with bound simulation and decision trail.
5. Web: What-if simulator and Change requests pages sharing a simulation view.

## Verification ledger (2026-09-30)

- `tests/api/test_simulation.py` (6): removing Erick → Finance-Legacy affects only Erick, loses payroll configuration, no lockout, ERP dependents listed, PRIOR_ROLE_RETAINED resolved, unknowns present, row counts of observations/revisions/sandbox unchanged; alternate-path variant keeps payroll via Payroll-Approvers (1 route removed); removing both payroll role grants reports a payroll lockout; additions report gained privilege and invalid typed additions 409; change request → SIMULATED with digest, source versions and audit trail; re-simulation changes the digest; viewer/reviewer denied; bad input 422/409.
- Playwright `whatif.spec.ts`: investigator runs the simulation, creates a proposal and binds a simulation.
