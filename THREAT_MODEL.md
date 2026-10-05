# Threat model

Design assessment, not discovered vulnerabilities. Phase 18 validation of each row against implemented mitigations and tests, with unresolved risks, is in [docs/security/phase-18-assessment.md](docs/security/phase-18-assessment.md). Assets: identity topology, credentials, approvals, sessions, evidence, history and lab isolation. Adversaries include anonymous attackers, malicious normal users, compromised administrators, malicious source content and compromised connectors/models/infrastructure.

| Boundary / threat | Mitigation | Verification and residual risk |
|---|---|---|
| Browser/IdP spoofing | PKCE, state/nonce, token validation, secure sessions, MFA | Reject wrong issuer/audience/nonce; compromised endpoint remains risk |
| API privilege escalation | Capability/object/field checks; independent role-change approval | Manipulated IDs and self-promotion denied |
| Tenant data disclosure | RLS, composite FKs, scoped caches, transaction-local context | Test pooled scope, jobs, exports and citations; DB admin remains privileged |
| Shared snapshot cache (Phase 19) | Process-level cache keyed by environment id and a graph version computed under the caller's RLS context; populated only after route authorization; LRU-bounded | `tests/api/test_snapshot_cache.py`: foreign tenant derives a different key and loads nothing; cached result equals uncached; any recorded change misses. Cache memory per process is a sizing risk |
| TLS reverse proxy (Phase 20) | Caddy terminates TLS and caps every body, including chunked bodies, at 1 MB. The API trusts `X-Forwarded-*` only from the proxy's fixed IP, so rate limits key on the real client rather than the proxy. The database sits on an internal network with no published port | Local container acceptance per the Phase 20 ledger. A misconfigured `FORWARDED_ALLOW_IPS` would let clients spoof their address and dodge per-IP quotas |
| Unauthenticated probes (Phase 20) | `/health` never touches the database. `/ready` returns status plus a fixed reason, never versions, counts or connection details. The proxy hides `/ready` externally | `tests/api/test_operations.py`: no tenant or connection data in any probe response, fails closed when the database is down |
| Packaged secrets and key rotation (Phase 20) | Secrets are mounted files, never in the image (`.dockerignore` allowlist). Envelopes carry a key id; a withdrawn key fails closed (503, nothing accepted). Rotation re-wraps data keys only and is audited | `tests/unit/test_key_rotation.py`, the rotation test in `tests/api/test_connectors.py`. Keys sit on the host filesystem until a KMS exists (U5) |
| Operator CLI and backups (Phase 20) | `manage.py status/rotate-master-key` and `scripts.backup` need the migration URL (superuser, U7). Status prints counts only. Backup passwords go through `PGPASSWORD`, not argv. The drill verifies the SHA-256 before restoring | `tests/unit/test_backup.py`. Backups hold all tenants' data and must be stored encrypted and off-platform (U6) |
| Invite registration (Phase 21) | Credentials are created at the IdP (own password, mandatory TOTP enrolment); access comes only from an invite. The token is 32 random bytes, stored as a SHA-256 hash, shown once, single-use, valid 72 h and revocable. Roles are read only from the stored invite. Privileged roles (org_admin/approver/operator) need an approver ≠ inviter (DB CHECK) with recent MFA and a digest binding. Redemption is one row-locked `SECURITY DEFINER` function, the only runtime path that inserts users. Every unusable token gets the same generic page | `tests/integration/test_invites_db.py`, `tests/api/test_invites.py`, `tests/api/test_invite_login.py`, `tests/e2e/invite.spec.ts`. Residual: no SMTP locally, so the email match is consistency only and possession of the link is the real factor until email verification exists (PLANNED). Open IdP registration creates IdP accounts with no platform access |
| Approval tampering/replay | Immutable digest, expiry, version checks, idempotency | Reject stale, altered and concurrent execution |
| Malicious/incomplete ingestion | Provenance and authoritative coverage before deletion | Partial sync cannot imply absence; source may still lie |
| Prompt injection | Read-only query allowlist, pre-retrieval authorization, citation validation | Adversarial tests; model prose stays advisory |
| SSRF | Controlled endpoints, redirect validation, egress restrictions | Block arbitrary/internal metadata destinations |
| Audit repudiation | Append-only permissions, hash chain, external checkpoint | App cannot alter/delete; infrastructure compromise remains |
| Graph denial of service | Depth/node/time limits, quotas, cancellable jobs; depth/path bounds prune a branch, expansion/time stop the search | Dense/cyclic fixtures and a 10,000-identity benchmark (`docs/performance/`); truncation visible |
| Uncertain external write | Idempotency, readback and reconciliation | Crash before/after write; recovery limited by source capabilities |
| JIT expiry outage | Native TTL where possible, durable retry and alerts | Restart/time-boundary tests; disconnected source residual risk |
| Lab escape | Scoped environments and sandbox-only execution capabilities | Manipulated environment IDs cannot reach production |
| Secret disclosure | References, encryption, redaction, key separation | Canary-secret scans; master-key compromise remains |
| False historical certainty | Bitemporal evidence and coverage watermark | Late evidence and missing history return explicit uncertainty |
| Authorized collusion | Separation of duties, narrow scope, audit and review | Collusion cannot be fully prevented by application controls |

Invariants: AI never authorizes; learner never targets production; ownership never automatically grants access; unconfirmed results never mean success; truncated search never proves absence; caller-supplied tenant never authorizes; relevant version changes invalidate approval; unsupported historical state is never invented.

Review on every trust-boundary or connector change. Phase 18 validates deployed behavior independently and records unresolved risks with owners.
