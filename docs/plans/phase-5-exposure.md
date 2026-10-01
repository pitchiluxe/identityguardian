# Phase 5 — defensive exposure paths

Approved by the user on 2026-09-30. Depends on Phases 3–4.

## Bounded plan

1. `domain/exposure.py` (`exposure-2026.09-1`): transitions are (a) an effective permission with `CAN_RESET_CREDENTIAL` over another identity and (b) `CAN_ASSUME_ROLE`. Each transition carries its enabling grant lineage. Conditions are evaluated against evidence: `target_mfa_registered` is CONDITIONAL when the target has MFA and POTENTIAL when evidence shows none; unsupported conditions → UNKNOWN. Ownership never implies impersonation. Terminated targets with access are flagged as leaver gaps.
2. Destinations are high/critical resources the starting identity does not already hold. Identity-level visited sets prevent cycles; bounds on transitions (≤3), paths and time return `complete=false`.
3. Every path includes defensive controls and the statement that potential exposure is not exploitation. No exploit steps, credential harvesting or scans.
4. Route `GET …/attack-paths` (`findings:read`); web Attack paths page with step chain, factors and controls.

## Verification ledger (2026-09-30)

- `tests/api/test_exposure.py` (4): Erick → reset Sofia → Customer Data is CONDITIONAL with the HelpDesk-L2 TKT-2210 grant as evidence; already-held payroll not reported; target without MFA becomes POTENTIAL; Ben flagged as terminated target; Chen break-glass requires `mfa_required` + `approval_ticket`; ownership never creates a step; path bound reports partial; destination filter; viewer 403.
- Playwright `paths.spec.ts` passed. Full pytest recorded in the commit message.
