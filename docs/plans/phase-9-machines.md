# Phase 9 — machine identity governance

Approved by the user on 2026-09-30. Depends on Phases 2–4 and 8.

## Bounded plan

1. Ingestion sanitization: keys that may carry secret material (password, client secret, private key, token values, OTP seeds…) are dropped recursively before evidence or attributes are stored; the observation records `_redacted_fields` paths only.
2. Rules: OWNERLESS_MACHINE (no active owner; severity by privileged reach; dependents listed), CREDENTIAL_EXPIRING (≤30 days or expired, dependents named), CREDENTIAL_AGED (>365 days since rotation; federated/secretless credentials excluded).
3. `GET …/machines` (identity:read): owners, credential metadata, dependents, direct access, privileged entitlements, last observed use, findings (only with findings:read).
4. Proposals: assign owner (`add_relationship` `USER_OWNS_SERVICE_ACCOUNT`; simulation shows no access change) and `rotate_credential` (migration 009). Rotation simulation lists dependents that must be updated and overlap guidance; source version binds the credential's current `rotated_at`; execution appends a metadata-only rotation revision at the sandbox source and confirms by read-back. A shared `versions_current` check serves approval and the worker.
5. Web: Machine identities page with propose-owner and propose-rotation actions.

## Verification ledger (2026-09-30)

- `tests/api/test_machines.py` (5): inventory (viewer sees inventory, not findings); svc-erp-sync ownerless/high with ERP dependent; cert-erp-sync expiring; aged credentials exclude the federated CI credential (false positive corrected during verification); owner assignment changes no access and resolves the finding through the full approval/execution path; rotation lists ERP as a dependent and resolves expiring/aged findings; rotation goes STALE when the source rotates after simulation; a canary secret never reaches observations, revisions or API responses.
- Playwright `machines.spec.ts` passed.
