# Phase 1 foundation work packages

Status: proposed work breakdown for Phase 0 review, not an executable code plan or authorization to proceed. Expand each task into exact migrations, interfaces and tests after design approval. Do not implement later-phase features during this phase.

1. **Repository/runtime foundation.** Create apps/web, apps/api, apps/worker, contracts, migrations and tests with pinned compatible dependencies, lockfiles and local service configuration. Verify clean startup and health; no default credentials. Update INSTALLATION.md with commands actually tested.
2. **Database isolation.** Implement organizations, environments, Users, memberships, platform capabilities, sessions, audit and outbox. Separate migration/runtime roles, composite scoped FKs and RLS. Test two tenants with real runtime-role connections, writes, pooling and transaction rollback.
3. **OIDC and sessions.** Implement code/PKCE/state/nonce verification, opaque cookies, logout, expiry and one-time local administrator bootstrap. Test invalid issuer/audience/nonce, replay, fixation, membership revocation and missing MFA assurance.
4. **Authorization.** Implement centralized capability/object scope checks and independent privileged role-change review. Test normal-user forged IDs/fields, self-promotion, cross-tenant requests and unauthorized audit/export access.
5. **Audit and job foundation.** Atomic audit intent/outbox; append-only app permissions, redaction, correlation, leases/idempotency. Test transaction failure, duplicate delivery and secret redaction. No external IAM writes.
6. **Shell and verification.** Accessible navigation, organization/environment label, profile/logout, explicit planned pages and real loading/denied/error states. Test browser login, scope restrictions, CSRF and session expiration. Run relevant regression/security checks, document evidence and commit phase-owned files.

Expected outputs: apps/api/app/auth, authorization, organizations and audit modules; initial SQL migrations; apps/web/src shell/session UI; worker job foundation; tests/security isolation and escalation suite; tests/e2e login/scope flow. Exact filenames and contracts are finalized in the bounded Phase 1 implementation plan.

Review focus: pooled tenant context, revoked membership, forged privileged fields, failed audit transaction and interrupted authentication flow. Exit only when these are exercised, tests pass and limitations are documented. No graph, AI or connector claim at this gate.
