# Security design

Status (2026-10-01): the controls below are implemented for the local synthetic build and verified by automated tests; see [docs/security/phase-18-assessment.md](docs/security/phase-18-assessment.md) for evidence, residual risks and the open production gates. No independent penetration test has been performed.

Treat browsers, connector records, tickets and model outputs as untrusted. Bind APIs, exports, jobs, graph queries, caches and citations to verified organization/environment/resource scope. Server authorization is mandatory; UI hiding is insufficient. RLS and composite foreign keys add isolation. Lab environments cannot reference production connector credentials.

| Platform role | Authority |
|---|---|
| Viewer | Read explicitly assigned scope |
| Investigator | Read evidence and propose/simulate changes |
| Reviewer | Decide assigned certification items; removal creates proposal |
| Approver | Independently approve exact simulated IAM requests |
| Operator | Execute approved actions in assigned scope |
| Organization administrator | Manage configuration/membership; no approval bypass or self-promotion |
| Auditor | Read scoped redacted audit/evidence |
| Lab learner/instructor | Assigned isolated lab only |

Capabilities and resource scopes are explicit. Multiple roles never allow self-approval. Privileged platform-role changes require independent approval. Optional policy separates approver from executor. Infrastructure superuser maintenance is out-of-band and audited, never a browser role.

## Authentication

OIDC code + PKCE, state/nonce checks, signature/issuer/audience/expiry/algorithm validation. Map issuer+subject to User; source-directory groups are not platform-role authority. Opaque server sessions, Secure/HttpOnly/SameSite cookies over HTTPS, rotation on login/assurance change. Proposed idle timeout 30 minutes, absolute timeout 8 hours; membership removal revokes access. High-risk approval/execution requires verified MFA within 5 minutes; inability to verify assurance blocks action.

Cookie-authenticated mutations require CSRF token and Origin checks; GET never mutates. Strict CORS allowlist. Authorize every object, field and worker action. Proposed limits: 60 reads/minute/user, 10 mutations/minute/user, 5 AI jobs/minute/user, plus login/IP abuse protection and tenant quotas.

## Approval and execution

DRAFT → SIMULATED → IN_REVIEW → APPROVED → QUEUED → EXECUTING → SUCCEEDED. Alternatives: REJECTED, EXPIRED, CANCELLED, STALE, FAILED, PARTIAL, RECONCILIATION_REQUIRED. Server enforces transitions and optimistic locking.

Approval expires after 30 minutes by default and binds proposal digest. Changed target, duration, parameters, source or policy version requires resimulation/reapproval. Recheck approver membership at execution. Idempotency prevents replay/concurrent duplicate action. Audit intent must persist before dispatch; no invented success on uncertain connector response.

JIT uses policy-bounded duration and contextual checks. Prefer source-native expiring grants; durable worker, retries and reconciliation supplement expiry. Overdue revocations alert operators. Disconnected sources mean revocation is unconfirmed, not guaranteed. Original bounded approval authorizes expiry revocation, never silent extension.

## Secrets and operational controls

No credentials in Git, fixtures, logs or reports. Store encrypted secret envelopes with separately managed master-key reference; credential records expose metadata only. Rotation uses versioned references and bounded overlap. No production secrets before key-management review. Empty `.env.example` is allowed; local environment files are ignored.

Typed inputs, bounded queries, parameterized SQL, no model-generated executable queries. Allowlist outbound hosts and validate redirects against SSRF. CSP, HTTPS HSTS, frame/content-type protections and sanitized rendering. Exports prevent spreadsheet formula injection, enforce field redaction and expire. Metrics exclude sensitive source content.

Audit records actor/action/time/context/target/before/after/justification/approval/result/correlation. Original evidence and AI explanations are separate. Append-only application permissions and independent signed checkpoints address different threats. Production gates include dependency/secret/container scans, SBOM, isolation tests, independent penetration testing, backup restore, monitoring and incident response.

Report vulnerabilities privately to maintainers via the hosting platform's private channel when configured; never publish credentials in issues.
