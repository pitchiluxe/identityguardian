# Phase 18 — security hardening

Approved by the user on 2026-09-30. Depends on Phases 1–17.

## Bounded plan

1. Authenticate before body validation (router-level session dependency; cached per request, re-validated after the Phase 1 lock wait).
2. Validation errors return field location/message/type only; 1 MB body limit (413).
3. Tamper-evident audit: migration `019_audit_chain.sql` adds a per-organization sequence and SHA-256 chain (trigger, backfilled for existing events); `GET /audit/verify` and Ed25519-signed `POST /audit/checkpoints` for off-platform storage; `AUDIT_SIGNING_KEY` generated locally.
4. Exhaustive authorization matrix and adversarial probes under `tests/security/`.
5. Static analysis: ruff bandit (`S`) rules enforced; concatenated SQL replaced; justified suppressions only for fixed-binary subprocess calls and a non-secret descriptor.
6. `scripts/secret_scan.py` enforced by a unit test; dependency audits; CycloneDX SBOMs (`docs/security/sbom-*.cdx.json`).
7. Threat-model validation and unresolved-risk register: `docs/security/phase-18-assessment.md`; SECURITY.md and THREAT_MODEL.md status updated. Web: audit integrity panel.

## Acceptance

Authorization/threat-model validation — done (internal). Independent penetration assessment — **not performed; recorded as open production gate U1**. Unresolved-risk decisions — listed with recommendations (U1–U12) awaiting the owner.

## Verification ledger (2026-10-01)

- `tests/security/test_authorization_matrix.py` (11): route inventory (88 routes, every protected route has a declared capability), anonymous 401 everywhere, eight role sweeps over 67 routes each (no unauthorized success, GET denial is 403, authorized roles never refused), cross-tenant 404/422 for every organization route.
- `tests/security/test_probes.py` (9) and `tests/api/test_audit_chain.py` (3), `tests/unit/test_secret_scan.py` (2).
- pytest 232 passed; Playwright 27 passed (+1 opt-in capture skipped); ruff (incl. `S`) clean; secret scan 0 findings; pip-audit and npm audit report no known vulnerabilities.
