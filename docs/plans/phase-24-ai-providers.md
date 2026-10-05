# Phase 24 — AI providers (Ollama default, Claude, ChatGPT)

Approved by the user on 2026-10-05 ("approve 24", "proceed"). Spec: `docs/superpowers/specs/2026-10-05-ai-providers-design.md`. Plan: `docs/superpowers/plans/2026-10-05-ai-providers.md`.

## Verification ledger
- 2026-10-05: new tests:
  - `tests/integration/test_ai_settings_db.py` (3): key functions bound to a raw live session token; a session *hash* does not unlock keys; no runtime access to the key table; default policy off; provider CHECK.
  - `tests/unit/test_hosted_providers.py` (9): Claude request shape (`claude-opus-5-5`, `output_config` effort plus JSON schema, `server-side-fallback-2026-07-01` with `fallbacks="default"`, no temperature or thinking); refusal mapping; typed errors mapped to fixed reasons with the key never in the exception; non-JSON output; OpenAI request shape, required model and auth mapping.
  - `tests/api/test_ai_settings.py` (6): defaults; only org_admin controls the policy; hosted choice refused without policy, key or model; canary key absent from responses, logs, audit and stored rows, and isolated per user; a hosted answer records `anthropic:claude-opus-5-5`, and switching the policy off stops egress; acknowledgement and key are both required.
  - `tests/e2e/settings.spec.ts` (1).
  - `tests/unit/test_secret_scan.py` (+1): Anthropic and OpenAI key patterns.
- Dependencies: `anthropic==1.11.0`, `openai==3.24.0` (+ `docstring_parser`, `jiter`, `sniffio`). pip-audit: no known vulnerabilities.
- Full pytest: 321 passed, 1 failed. The failure was `test_synthetic_bootstrap_refuses_outside_development`: a ConnectionTimeout because `bootstrap` connected to the database before checking the mode. Fixed by refusing before connecting; the rerun passed.
- Full Playwright: 26 passed, 3 failed, 1 skipped. The run took 13.1 min against the usual ~5 min, on a heavily loaded host. The failures were 5 s visibility timeouts in `invite`, `settings` and `twin`. Rerunning those three specs: 5/5 passed. Recorded as load-sensitive flakes. The Settings page waits for an Ollama probe (3 s timeout) before rendering.
- ruff check/format clean; secret scan 0 findings; build clean.
- Final review by a fresh reviewer (Opus): 0 Critical, 7 Important, 10 Minor. All Important findings were fixed test-first:
  1. The `AI_ENABLED=false` kill switch now blocks every provider.
  2. `rotate-master-key` re-wraps AI keys.
  3. The threat model now states the runtime-role residual risk.
  4. The Claude fallback answer is parsed from the fallback block, and the model that answered is recorded.
  5. Hosted switch-off falls back to Ollama.
  6. `/ai/test` uses the AI quota and calls the model outside the DB transaction.
  7. Real-SDK tests over a mocked HTTP transport were added.

  The OpenAI empty reply and the stale "Local model" subtitle were also fixed. Affected suites: 184 passed.
