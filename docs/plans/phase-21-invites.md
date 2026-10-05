# Phase 21 — invite-based registration

Post-roadmap feature requested and approved by the user on 2026-10-05. Spec: `docs/superpowers/specs/2026-10-05-invite-registration-design.md`. Plan: `docs/superpowers/plans/2026-10-05-invite-registration.md`.

People register their own IdP credentials (password plus mandatory TOTP). Platform access comes only from an invite, and privileged invites need an independent approver. Email delivery is PLANNED: the admin copies a one-time link.

## Verification ledger
- 2026-10-05: new tests. `tests/integration/test_invites_db.py` (12, including the concurrent-redeem lock, runtime-role bypass and self-approval CHECK); `tests/api/test_invites.py` (5); `tests/api/test_invite_login.py` (5: register → callback → exact invited role, generic invalid page, email mismatch, no-invite 403 preserved, deep link leaks nothing). Each went red first (missing table/function, 405/404 routes) before implementation.
- `tests/e2e/invite.spec.ts` against real local Keycloak: alex creates a viewer invite, a new browser context registers, enrols TOTP and lands in the workspace. 1 passed.
- Full run: ruff check/format clean, secret scan 0 findings; pytest 279 passed, 1 skipped; Playwright 28 passed, 1 skipped (opt-in capture).
- Transient: one auth-suite run during Task 3 had 2 fixture errors (503, DB connect timeout under host load). Rerun 36 passed.
