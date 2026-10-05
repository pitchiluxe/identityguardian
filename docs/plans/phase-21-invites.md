# Phase 21 — invite-based registration

Post-roadmap feature requested and approved by the user on 2026-10-05. Spec: `docs/superpowers/specs/2026-10-05-invite-registration-design.md`. Plan: `docs/superpowers/plans/2026-10-05-invite-registration.md`.

People register their own IdP credentials (password plus mandatory TOTP). Platform access comes only from an invite, and privileged invites need an independent approver. Email delivery is PLANNED: the admin copies a one-time link.

## Verification ledger
- 2026-10-05: new tests. `tests/integration/test_invites_db.py` (12, including the concurrent-redeem lock, runtime-role bypass and self-approval CHECK); `tests/api/test_invites.py` (5); `tests/api/test_invite_login.py` (5: register → callback → exact invited role, generic invalid page, email mismatch, no-invite 403 preserved, deep link leaks nothing). Each went red first (missing table/function, 405/404 routes) before implementation.
- `tests/e2e/invite.spec.ts` against real local Keycloak: alex creates a viewer invite, a new browser context registers, enrols TOTP and lands in the workspace. 1 passed.
- Full run: ruff check/format clean, secret scan 0 findings; pytest 279 passed, 1 skipped; Playwright 28 passed, 1 skipped (opt-in capture).
- Transient: one auth-suite run during Task 3 had 2 fixture errors (503, DB connect timeout under host load). Rerun 36 passed.
- Final whole-branch review by a fresh reviewer (Opus): 0 Critical, 4 Important, 8 Minor. All four Important findings were fixed test-first, each test watched failing before the fix:
  1. Refused redemptions are audited in the tenant (`invite.redemption_refused`).
  2. `migrations/024_invite_hardening.sql` adds DB CHECKs for privileged approval and REDEEMED ⇔ redeemed_by, plus a final-state trigger.
  3. "I already have an account" carries the invite (`mode=login`).
  4. The invite landing page is shown to signed-in users.
- After the fixes: pytest 285 passed; invite E2E 2 passed; ruff clean. Eight Minor findings are deferred and listed in the session report: freshness check, token_hash column grant, tokens in access logs, success-audit correlation/outbox, inactive re-invite, concurrent new-subject race, test gaps, trailing slash and raw-JSON 403.
