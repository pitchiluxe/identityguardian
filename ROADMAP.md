# Phased implementation roadmap

Every phase requires architecture/dependency inspection, bounded plan, implementation, tests, security/regression checks, documentation and a phase-owned commit. Status (2026-10-05): Phases 0–20 are implemented locally. Each phase plan in `docs/plans/` ends with a verification ledger. Production acceptance is not granted (see `docs/operations/production-acceptance.md`). No timing estimates imply completed capability.

| Phase | Scope and dependencies | Acceptance gate |
|---|---|---|
| 0 | Requirements, architecture, models, boundaries, UI | Review package accepted before product code |
| 1 | Authentication, RBAC, organizations/users, audit, database, shell; 0 | OIDC login/logout, scoped sessions, runtime-role RLS, CSRF and normal-user escalation tests; first administrator bootstrap without shipped passwords |
| 2 | Digital twin, ingestion, profiles, explorer; 1 | Deterministic sandbox import, duplicate replay safety, clickable typed graph and tenant isolation |
| 3 | Effective access and lineage; 2 | Direct/nested/conditional/deny/alternative-path tests; evidence provenance shown |
| 4 | Privilege creep/history/timeline; 3 | Prior-role and dormant findings explain evidence and usage coverage |
| 5 | Defensive attack paths; 3–4 | Cycle-safe typed exposure rules, bounds/completeness, no exploitation |
| 6 | Evidence access reviews; 3–5 | Reviewer scope, evidence/uncertainty, decision trail; REMOVE proposes, never silently revokes |
| 7 | What-if engine; 3,6 | Immutable overlay, residual routes, dependencies/lockouts/unknowns; no base mutations |
| 8 | JIT and controlled execution; 6–7 | Separate approval, digest/version binding, sandbox execution, expiry/restart/reconciliation tests |
| 9 | Machine governance; 2–4,8 | Ownerless/aged/expiring credential evidence, dependency-aware proposal; no secret exposure |
| 10 | Agent registry; 9 | Owner/model/tool/app/API/data scopes, maximum privilege, expiry and activity queries |
| 11 | JML intelligence; 7–10 | Approved joiner baseline, mover retain/review/remove, leaver ownership/session/token dependencies and partial failure |
| 12 | Time Machine; temporal foundation 2 onward | Effective vs known-at reconstruction, late evidence, coverage gaps and post-removal history |
| 13 | Ollama investigator; 3,5,12 | Allowlisted authorized query planner, verified citations, injection/grounding/offline tests |
| 14 | Policy-as-code; 7–8,13 | Schema/operator validation, tests, scope simulation, independent approval before activation |
| 15 | Labs and instructor; 8,11–14 | Isolated attempts, 16 lab rubrics, progressive hints, deterministic scores and reports |
| 16 | Enterprise connector framework; sandbox interfaces from 2 | Contract suite, authoritative coverage, cursors/replay/reconciliation; mock providers first; real connectors separately approved |
| 17 | Reporting; 4–16 | Authorized redacted exports with evidence/snapshot, formula-injection protection and expiry |
| 18 | Security hardening; 1–17 | Authorization/threat-model validation, independent penetration assessment, unresolved-risk decisions |
| 19 | Performance; 18 | Measured graph/database/load benchmarks, scoped cache invalidation, correct bounded results |
| 20 | Production packaging; 18–19 | Containers, monitoring, key management, backup/restore drill, deployment/recovery runbooks and production acceptance |

Historical capture begins with Phase 2; Phase 12 adds reconstruction UX. Sandbox ingestion is needed before Phase 16's expanded framework. Deterministic recommendations precede the model integration and must be labeled rule-based.

## Policy proposal contract

Machine-readable policy includes schema version, name, purpose, scope, typed conditions, supported action, expiring exceptions and tests. Example: contractor + permanent Global Administrator assignment → reject proposed grant / flag existing assignment for review. Flagging does not revoke existing access. Reject unknown operators; no arbitrary code. Validate → test positive/negative/exception cases → simulate twin impact → approve digest → activate version. Reversion is another reviewed policy version.

## Reporting scope

Identity Exposure, Privileged Access, Dormant Identity, Machine Identity, AI Agent Governance, Access Review, JML, Privilege Creep, Attack Path, Policy Compliance and Lab Completion. Exported conclusions cite original evidence and distinguish inferred/partial results.
