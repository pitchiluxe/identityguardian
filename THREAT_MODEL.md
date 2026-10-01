# Threat model

Design assessment, not discovered vulnerabilities. Phase 18 validation of each row against implemented mitigations and tests, with unresolved risks, is in [docs/security/phase-18-assessment.md](docs/security/phase-18-assessment.md). Assets: identity topology, credentials, approvals, sessions, evidence, history and lab isolation. Adversaries include anonymous attackers, malicious normal users, compromised administrators, malicious source content and compromised connectors/models/infrastructure.

| Boundary / threat | Mitigation | Verification and residual risk |
|---|---|---|
| Browser/IdP spoofing | PKCE, state/nonce, token validation, secure sessions, MFA | Reject wrong issuer/audience/nonce; compromised endpoint remains risk |
| API privilege escalation | Capability/object/field checks; independent role-change approval | Manipulated IDs and self-promotion denied |
| Tenant data disclosure | RLS, composite FKs, scoped caches, transaction-local context | Test pooled scope, jobs, exports and citations; DB admin remains privileged |
| Approval tampering/replay | Immutable digest, expiry, version checks, idempotency | Reject stale, altered and concurrent execution |
| Malicious/incomplete ingestion | Provenance and authoritative coverage before deletion | Partial sync cannot imply absence; source may still lie |
| Prompt injection | Read-only query allowlist, pre-retrieval authorization, citation validation | Adversarial tests; model prose stays advisory |
| SSRF | Controlled endpoints, redirect validation, egress restrictions | Block arbitrary/internal metadata destinations |
| Audit repudiation | Append-only permissions, hash chain, external checkpoint | App cannot alter/delete; infrastructure compromise remains |
| Graph denial of service | Depth/node/time limits, quotas, cancellable jobs | Dense/cyclic fixtures; truncation visible |
| Uncertain external write | Idempotency, readback and reconciliation | Crash before/after write; recovery limited by source capabilities |
| JIT expiry outage | Native TTL where possible, durable retry and alerts | Restart/time-boundary tests; disconnected source residual risk |
| Lab escape | Scoped environments and sandbox-only execution capabilities | Manipulated environment IDs cannot reach production |
| Secret disclosure | References, encryption, redaction, key separation | Canary-secret scans; master-key compromise remains |
| False historical certainty | Bitemporal evidence and coverage watermark | Late evidence and missing history return explicit uncertainty |
| Authorized collusion | Separation of duties, narrow scope, audit and review | Collusion cannot be fully prevented by application controls |

Invariants: AI never authorizes; learner never targets production; ownership never automatically grants access; unconfirmed results never mean success; truncated search never proves absence; caller-supplied tenant never authorizes; relevant version changes invalidate approval; unsupported historical state is never invented.

Review on every trust-boundary or connector change. Phase 18 validates deployed behavior independently and records unresolved risks with owners.
