# Phase 15 — labs and instructor

Approved by the user on 2026-09-30. Depends on Phases 8 and 11–14.

## Bounded plan

1. Migration `015_labs.sql`: `environments.lab_learner/lab_attempt`; `lab_attempts` and `lab_actions`; the runtime role may insert environments only through a RESTRICTIVE policy requiring `kind='LAB'` and a learner.
2. Scoping: a lab environment is visible only to its learner (404 to others) or `lab:manage`; inside their own lab a learner gains analysis capabilities (identity/graph/access/findings/history read) that never apply elsewhere. `GET …/capabilities` exposes the effective set to the UI.
3. `labs/actions.py`: fifteen allowlisted action types applied to the attempt's sandbox source and ingested; temporary access capped at 8 hours; `answer` records diagnoses without changes.
4. `labs/catalog.py` (`labs-2026.09-1`): sixteen labs from LABS.md with scenario setup, deterministic validators, safety rules and misconceptions, three progressive hints (concept → diagnostic question → relevant setting) and worked solutions. Rubric correctness 50 / least privilege 25 / evidence-workflow 25, pass mark 70, any safety failure blocks passing.
5. Routes: catalog, start (clone + setup + full sync), list, view, act, reset (attempt only), progressive hints, submit (deterministic report), solution (after completion or explicit, recorded), instructor explanation (model cites validator results R#/S#; invented scores rejected; deterministic fallback offline), report.
6. Web: Labs page (catalog, attempts, action editor with templates, hints, instructor, reset, submit, report, solution, "Explore this lab environment").

## Verification ledger (2026-10-01)

- `tests/api/test_labs.py` (36): all 16 worked solutions pass; one negative or safety case per lab does not pass; catalog has 16 labs and viewers are denied; another learner gets 404 for the attempt, its environment and actions while `lab:manage` may observe; the learner's lab change never reaches the main environment and lab environments are hidden from other learners' environment lists; reset, hint progression, solution gating, report, post-submit 409 and unknown action 422; instructor claims must cite results and an invented score is rejected; offline instructor falls back to deterministic feedback.
- pytest 167 passed. Playwright `labs.spec.ts` (learner completes Group management with 100/100 and explores the lab environment) and updated `login.spec.ts` passed.
