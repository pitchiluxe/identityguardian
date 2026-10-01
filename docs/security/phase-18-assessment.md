# Phase 18 security assessment (internal)

Date: 2026-10-01 · Scope: local build at the Phase 18 commit · Data: SYNTHETIC only.

**This is a self-assessment by the building agent using automated tests and code review. It is not an independent penetration test.** An independent assessment is a production gate and has not been performed (see U1).

## Method

- Exhaustive authorization matrix (`tests/security/test_authorization_matrix.py`): 88 API routes inventoried from the application; the capability each route needs is read from its own handler; anonymous, eight roles and cross-tenant sweeps.
- Adversarial probes (`tests/security/test_probes.py`): headers/CSP/HSTS, CSRF/origin ordering, validation-error echo, oversized bodies, stored markup, error hygiene, open redirect, unsupported methods, session revocation and fixation.
- Audit integrity (`tests/api/test_audit_chain.py`): hash chain, insider edit detection, full-chain rewrite caught by a signed checkpoint, runtime role cannot update/delete audit.
- Static analysis: ruff with the bandit (`S`) rule set now enforced in CI configuration; all findings fixed or justified.
- Secret scanning: `scripts/secret_scan.py` over tracked files (enforced by `tests/unit/test_secret_scan.py`).
- Dependencies: `pip-audit` and `npm audit` (no known vulnerabilities on 2026-10-01); CycloneDX SBOMs in `docs/security/`.

## Fixed during this phase

| Issue | Fix | Evidence |
|---|---|---|
| Anonymous requests to mutation routes received 422 schema details before authentication | Router-level session dependency authenticates before body validation | Anonymous sweep: 401 on every protected route |
| FastAPI validation errors echoed submitted values (could include secrets) | Custom handler returns location/message/type only | `test_validation_errors_never_echo_input` |
| No request size limit | 1 MB limit on declared bodies (413) | `test_oversized_bodies_rejected` |
| Audit trail not tamper-evident | Per-organization SHA-256 chain set by trigger; Ed25519-signed checkpoints | `test_audit_chain.py` |
| Concatenated SQL flagged by static analysis | Literal alternatives (no runtime concatenation) | ruff `S` clean |

## Threat model validation

| Threat (THREAT_MODEL.md) | Implemented mitigation | Verification | Residual |
|---|---|---|---|
| Browser/IdP spoofing | OIDC code + PKCE, state/nonce, issuer/audience/signature checks, server sessions, MFA (`pwd`+`otp`) | `test_oidc.py`, `mfa.spec.ts` | Compromised endpoint; IdP runs in dev mode locally (U4) |
| API privilege escalation | Capability per route, independent approval, separation of requester/approver/executor | Authorization matrix, `test_execution.py` | Authorized collusion |
| Tenant disclosure | RLS on every tenant table with transaction-local scope; pooled scope test; environment and lab scoping | Cross-tenant sweep, pooled-connection test, lab isolation tests | Database administrator remains privileged (U7) |
| Approval tampering/replay | Digest binds target/source/graph/policy versions + expiry; idempotent executions | `test_execution.py`, `test_policies.py` | — |
| Malicious/incomplete ingestion | Provenance, sanitization, authoritative-only absence reconciliation | `test_twin.py`, `test_connectors.py`, canary test | A source may still lie |
| Prompt injection | Allowlisted intents, pre-retrieval authorization, evidence-as-data prompt, citation/number/name validation | `test_investigations.py`, `test_ai.py` | Restating untrusted quoted text cannot be prevented by grounding (U9) |
| SSRF | Connector endpoint policy (https, allowlist, no private/link-local); model endpoint loopback only | `test_connectors.py` unit suite, `test_ai.py` | — |
| Audit repudiation | Insert-only runtime grants, hash chain, signed checkpoints | `test_audit_chain.py` | Checkpoints must be exported off-platform (U6) |
| Graph denial of service | Depth/path/node/time bounds, hub collapse, rate limits | `test_access.py`, `test_twin.py` | Distributed rate limiting needed at scale (U8) |
| Uncertain external write | Durable intent, read-back, reconciliation | `test_execution.py` | Only the sandbox connector exists |
| JIT expiry outage | Native TTL, durable retry, overdue alerts | `test_execution.py` JIT case | Disconnected source |
| Lab escape | Learner-only LAB environments, 404 to others, restrictive insert policy | `test_labs.py` isolation | Labs share the database with other environments (U11) |
| Secret disclosure | Sanitized ingestion, AES-GCM envelopes, no secret in APIs/exports/logs, secret scan | canary test, envelope tests, secret scan | Keys live in local `.env` (U5) |
| False historical certainty | Bitemporal reconstruction, UNKNOWN before evidence, coverage notes | `test_history.py` | — |
| Authorized collusion | Separation of duties, audit | — | Cannot be fully prevented |

## Unresolved risks requiring owner decisions

| ID | Risk | Recommendation | Decision needed from |
|---|---|---|---|
| U1 | No independent penetration test | Commission an external assessment before any production use | Project owner |
| U2 | Chunked request bodies are not size-limited by the application | Enforce limits at the reverse proxy (Phase 20 packaging) | Owner / operations |
| U3 | No cross-source identity correlation; each connector's objects are distinct identities | Design correlation rules before connecting multiple real sources | Owner |
| U4 | Local Keycloak runs in development mode over loopback HTTP | Production IdP with TLS, hardened realm and MFA policy | Owner / IAM team |
| U5 | Master and signing keys are generated into the ignored `.env` | KMS/HSM with rotation before production secrets are stored | Owner / security |
| U6 | Audit checkpoints are stored in the same database unless exported | Schedule exports to write-once storage outside the platform | Owner / operations |
| U7 | A database superuser can bypass RLS and rewrite data | Separate DBA duties, restrict superuser access, rely on U6 for detection | Owner / operations |
| U8 | Rate limits are per application database; no gateway limits | Add gateway rate limiting in deployment | Operations |
| U9 | Model may restate untrusted text that is present in cited evidence | Keep AI output advisory; consider source-text quoting markers | Owner |
| U10 | Leaver sessions/tokens at the IdP cannot be confirmed from the sandbox | Integrate IdP session revocation when a real connector is approved | Owner |
| U11 | LAB environments share the database with other environments | Separate lab tenants/databases in production | Owner |
| U12 | No container/image scanning yet (no images built) | Covered by Phase 20 packaging | Phase 20 |

Until these decisions are recorded, the platform remains a local, synthetic-data system with no production approval.
