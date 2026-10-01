# Phase 17 — reporting

Approved by the user on 2026-09-30. Depends on Phases 4–16.

## Bounded plan

1. `domain/reports.py`: eleven report types (Identity Exposure, Privileged Access, Dormant Identity, Machine Identity, AI Agent Governance, Access Review, JML, Privilege Creep, Attack Path, Policy Compliance, Lab Completion) built only from the deterministic engines; rows cite evidence IDs and state their basis; bounded or inferred results add notes.
2. Redaction profiles: `standard` masks e-mail/UPN local parts and replaces free text; `full` requires audit authority. CSV cells starting with `= + - @`, tab or CR are prefixed with `'`.
3. Migration `018_reports.sql`: `report_artifacts` with snapshot, digest, downloads, status and an expiry of at most 7 days (CHECK); the worker purges expired content and keeps metadata.
4. Routes: list (`report:read`), create (`report:create`; auditors may create), download (authorized, digest-verified, audited, 410 after expiry, attachment).
5. Web: Reports page (generate, list with snapshot/expiry/downloads, download).

## Verification ledger (2026-10-01)

- `tests/api/test_reports.py` (15): all eleven types export with snapshot metadata; privilege-creep rows cite evidence and coverage with free text redacted; formula injection neutralised (a source ticket `=HYPERLINK(…)` becomes `'=HYPERLINK…`); redaction function and profile authority; viewer/investigator denied; other-environment 404; audit trail of creation and download; invalid expiry 422; expired report 410 and worker purge.
- Playwright `reports.spec.ts` (auditor generates and downloads a standard-redacted report) and `login.spec.ts` (no module remains planned) passed.
