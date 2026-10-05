# Phase 22 — production profile

Approved by the user on 2026-10-05 ("approve 22", "proceed"). Spec: `docs/superpowers/specs/2026-10-05-production-profile-design.md`. Plan: `docs/superpowers/plans/2026-10-05-production-profile.md`.

With `DEVELOPMENT=false`, the platform shows no demo data, names, placeholders or simulation tooling, and a real organization starts from `manage.py init-organization`. Development and tests keep the synthetic Contoso data.

## Verification ledger
- 2026-10-05: new tests:
  - `tests/api/test_production_profile.py` (6): seed, sandbox sync and fault routes 404 in production; mock connectors 422; dev keeps tooling; `deployment.mode` in session and overview, with stale `phase`/`identity_data` removed.
  - `tests/integration/test_init_organization.py` (3): one org, PRODUCTION environment and bootstrap invite; refuses a second run; the invite redeems; the runtime role cannot set `bootstrap`; synthetic `bootstrap` refuses outside development (written after the guard, not seen red).
  - `tests/unit/test_web_text.py` (2): no planned placeholders; demo wording only on dev-gated lines.
- Full pytest: 297 passed, 1 failed (`test_policies.py::test_reject_proposed_blocks_new_grants_and_policy_change_invalidates_approval`, 409 "twin changed since simulation"). It passed 3/3 alone and 6/6 with its file in parallel. Cause not identified, and Phase 22 does not touch policy or graph code. Recorded as an unexplained flake.
- Playwright full: 27 passed, 1 failed (`shell.spec.ts` expected the removed "Local build · synthetic data" landing label; test updated, 3/3 pass), 1 skipped.
- `npm run build` clean; ruff check/format clean; secret scan 0 findings.
