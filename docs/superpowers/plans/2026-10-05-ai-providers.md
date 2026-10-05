# AI Providers Implementation Plan (Phase 24)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Users pick Ollama (the default), Claude or ChatGPT for the investigator and the lab instructor, and enter their own API keys in Settings. Hosted providers are used only when an org_admin allows them and the user has acknowledged that evidence will leave the machine.

**Architecture:**
- `app.state.llm` stays the server's default Ollama provider. Existing tests inject fakes there, and that keeps working.
- `ai/registry.provider_for(request, scope)` returns the provider for this user and organization, or an unavailable reason. The investigator and the instructor call it instead of reading `app.state.llm`.
- New `ai/anthropic_provider.py` and `ai/openai_provider.py` implement the existing interface: `complete(messages, schema) -> (dict, ms)`, plus `name`, `model` and `version()`. Their SDK client is injectable, so tests never touch the network.
- Keys are AES-GCM envelopes in `user_ai_keys`. The only access path is `SECURITY DEFINER` functions that take the **raw session token**: the runtime role can read `sessions.token_hash`, but cannot derive raw tokens.

**Tech Stack:** FastAPI, psycopg 3, PostgreSQL 17, `anthropic` 1.11.0 (uses httpx2), `openai` 3.24.0, React 19, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-ai-providers-design.md`

## Global Constraints

- Ollama is the default for every user and the only option while `allow_hosted_ai` is false.
- Claude: `client.beta.messages.create(model=<user model or "claude-opus-5-5">, max_tokens=16000, system=<system text>, messages=[user turns], output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Check `stop_reason == "refusal"` before reading content. Read JSON from the first `text` block. Never send `thinking` (adaptive is the default on Opus 5.5) and never send `temperature` (it returns 400).
- ChatGPT: `client.chat.completions.create(model=<required user model>, messages=..., response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": SCHEMA, "strict": False}})`.
- Keys are never returned, logged, put in an exception message or written to an audit event. Responses show only `last4`.
- Envelope context: `ai-key:<user_id>:<provider>`. Key validation: 20–300 characters, no whitespace.
- No real API calls in tests. Inject fake SDK clients.
- Migration file: `migrations/026_ai_settings.sql` (025 is taken).

## Review Focus

1. The org switch turned off while a user has Claude selected: the next question must use Ollama status or "unavailable", never Claude — pinned in Task 3.
2. A key that contains the canary string must not appear in any response, log or audit — pinned in Task 3 via caplog plus a response scan.
3. Ollama not running: the Settings status says "not running", with the install and pull hints — pinned in Task 3 (status uses `version()` and the tags endpoint).
4. A user removes their key while Claude is selected: the investigator reports "unavailable: no API key", not a crash — pinned in Task 3.
5. Claude refusal: the investigator falls back to deterministic facts with the reason "The model declined this request" — pinned in Task 2.

---

### Task 1: Schema, grants and key functions

**Files:** Create `migrations/026_ai_settings.sql`; Test `tests/integration/test_ai_settings_db.py`

**Interfaces — produces:**
- Tables `organization_ai_settings`, `user_ai_settings` (RLS by `app_org()`) and `user_ai_keys` (no runtime grants).
- Functions, all definer functions taking the raw session token:
  - `ai_key_put(p_token text, p_provider text, p_envelope jsonb, p_last4 text) RETURNS void`
  - `ai_key_get(p_token text, p_provider text) RETURNS jsonb`
  - `ai_key_meta(p_token text) RETURNS TABLE(provider text, last4 text)`
  - `ai_key_delete(p_token text, p_provider text) RETURNS boolean`
- Each resolves the user from a live session: `token_hash = encode(sha256(convert_to(p_token,'UTF8')),'hex') AND expires_at > now()`. With no live session they raise `insufficient_privilege`.

- [ ] **Step 1: Failing test**

```python
"""Phase 24: AI settings tables and session-bound key functions (runtime role)."""

import os
import secrets
import time
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.security import digest

load_dotenv()
pytestmark = pytest.mark.integration
MIGRATOR, RUNTIME = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]


def session_for():
    uid, token = uuid4(), secrets.token_urlsafe(32)
    with psycopg.connect(MIGRATOR) as conn:
        conn.execute("INSERT INTO users VALUES (%s,'test',%s,'K')", (uid, str(uid)))
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,auth_time,amr) "
            "VALUES(%s,%s,'c',now()+interval '1 hour',%s,ARRAY['pwd'])",
            (digest(token), uid, time.time()),
        )
    return uid, token


def test_keys_are_bound_to_the_live_session():
    _, alice = session_for()
    _, bob = session_for()
    with psycopg.connect(RUNTIME) as conn:
        conn.execute("SELECT ai_key_put(%s,'anthropic','{\"ct\":\"x\"}','a1b2')", (alice,))
        assert conn.execute("SELECT ai_key_get(%s,'anthropic')", (alice,)).fetchone()[0] == {
            "ct": "x"
        }
        assert conn.execute("SELECT ai_key_get(%s,'anthropic')", (bob,)).fetchone()[0] is None
        assert conn.execute("SELECT * FROM ai_key_meta(%s)", (alice,)).fetchall() == [
            ("anthropic", "a1b2")
        ]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "SELECT ai_key_get(%s,'anthropic')", (digest(alice),)
            )  # hash is not a token
        assert conn.execute("SELECT ai_key_delete(%s,'anthropic')", (alice,)).fetchone()[0] is True


def test_runtime_role_cannot_touch_key_table():
    with psycopg.connect(RUNTIME) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM user_ai_keys")


def test_settings_defaults_and_provider_check():
    org = uuid4()
    with psycopg.connect(MIGRATOR) as conn:
        conn.execute("INSERT INTO organizations VALUES (%s,'AI test')", (org,))
        conn.execute("INSERT INTO organization_ai_settings(organization_id) VALUES (%s)", (org,))
        assert (
            conn.execute(
                "SELECT allow_hosted_ai FROM organization_ai_settings WHERE organization_id=%s",
                (org,),
            ).fetchone()[0]
            is False
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO user_ai_settings(organization_id,user_id,provider) "
                "VALUES (%s,%s,'gemini')",
                (org, uuid4()),
            )
```

- [ ] **Step 2: Run, expect FAIL** (function does not exist).
- [ ] **Step 3: Migration**

```sql
-- Phase 24: per-organization hosted-AI policy, per-user provider choice, per-user API keys.
CREATE TABLE organization_ai_settings (
 organization_id uuid PRIMARY KEY REFERENCES organizations,
 allow_hosted_ai boolean NOT NULL DEFAULT false,
 updated_by uuid REFERENCES users, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE user_ai_settings (
 organization_id uuid NOT NULL REFERENCES organizations, user_id uuid NOT NULL,
 provider text NOT NULL DEFAULT 'ollama' CHECK (provider IN ('ollama','anthropic','openai')),
 ollama_model text, anthropic_model text, openai_model text, hosted_ack_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (organization_id, user_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['organization_ai_settings','user_ai_settings'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())', t);
 END LOOP; END $$;
GRANT SELECT, INSERT, UPDATE ON organization_ai_settings, user_ai_settings TO guardian_app;

CREATE TABLE user_ai_keys (
 user_id uuid NOT NULL REFERENCES users, provider text NOT NULL CHECK (provider IN ('anthropic','openai')),
 envelope jsonb NOT NULL, last4 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (user_id, provider));
REVOKE ALL ON user_ai_keys FROM PUBLIC;  -- no runtime grants: access only via the functions below

CREATE FUNCTION ai_session_user(p_token text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid uuid;
BEGIN
 SELECT user_id INTO uid FROM sessions
 WHERE token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex') AND expires_at > now();
 IF uid IS NULL THEN RAISE EXCEPTION 'no live session' USING ERRCODE = 'insufficient_privilege'; END IF;
 RETURN uid;
END $$;
CREATE FUNCTION ai_key_put(p_token text, p_provider text, p_envelope jsonb, p_last4 text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
 INSERT INTO user_ai_keys(user_id, provider, envelope, last4) VALUES (ai_session_user(p_token), p_provider, p_envelope, p_last4)
 ON CONFLICT (user_id, provider) DO UPDATE SET envelope = excluded.envelope, last4 = excluded.last4, created_at = now();
$$;
CREATE FUNCTION ai_key_get(p_token text, p_provider text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
 SELECT envelope FROM user_ai_keys WHERE user_id = ai_session_user(p_token) AND provider = p_provider;
$$;
CREATE FUNCTION ai_key_meta(p_token text) RETURNS TABLE(provider text, last4 text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
 SELECT provider, last4 FROM user_ai_keys WHERE user_id = ai_session_user(p_token) ORDER BY provider;
$$;
CREATE FUNCTION ai_key_delete(p_token text, p_provider text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
 WITH gone AS (DELETE FROM user_ai_keys WHERE user_id = ai_session_user(p_token) AND provider = p_provider RETURNING 1)
 SELECT EXISTS (SELECT 1 FROM gone);
$$;
REVOKE ALL ON FUNCTION ai_session_user(text), ai_key_put(text,text,jsonb,text), ai_key_get(text,text),
 ai_key_meta(text), ai_key_delete(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ai_key_put(text,text,jsonb,text), ai_key_get(text,text), ai_key_meta(text),
 ai_key_delete(text,text) TO guardian_app;
```

The function body references `ai_session_user` inside a definer function, so `guardian_app` does not need EXECUTE on it.

- [ ] **Step 4: Migrate, then run PASS.**
- [ ] **Step 5: Commit** `feat(ai): settings tables and session-bound key functions`

### Task 2: Claude and ChatGPT providers

**Files:** Create `apps/api/app/ai/anthropic_provider.py`, `apps/api/app/ai/openai_provider.py`; Test `tests/unit/test_hosted_providers.py`

**Interfaces — produces:**
- `AnthropicProvider(api_key, model="claude-opus-5-5", client=None)`
- `OpenAIProvider(api_key, model, client=None)`

Both implement `complete(messages, schema) -> (dict, int)` and raise `ProviderUnavailable(reason)`, where `reason` is a fixed user-facing string: "Invalid API key", "Rate limited by the provider", "Provider unavailable", "The model declined this request", "Model returned non-JSON output", "Model not found". `version()` returns None.

- [ ] **Step 1: Failing tests** (fake clients record kwargs and return SDK-shaped objects via `types.SimpleNamespace`). Required cases:
  1. Claude request shape:
     - `model == "claude-opus-5-5"`
     - `system` is the system text
     - `messages` contains user turns only
     - `output_config == {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}`
     - `betas == ["server-side-fallback-2026-07-01"]` and `fallbacks == "default"`
     - no `temperature` and no `thinking` keys
     - the parsed JSON is returned
  2. A Claude `stop_reason="refusal"` raises "The model declined this request".
  3. Claude errors `anthropic.AuthenticationError` and `RateLimitError` map to the fixed reasons. Build them with an `httpx2.Response` and `request` via the SDK constructor, `(message, response=..., body=None)`. The API key string must not appear in `str(exc)`.
  4. OpenAI request shape: `response_format` is json_schema; the model is required (`ValueError` when empty).
  5. OpenAI auth error mapping, and the key is not in the message.
- [ ] **Step 2: Run, expect FAIL** (ImportError).
- [ ] **Step 3: Implement** with the official SDKs. `anthropic.Anthropic(api_key=..., max_retries=1, timeout=90.0)` and `openai.OpenAI(api_key=..., max_retries=1, timeout=90.0)` are built lazily only when `client` is None. Catch a most-specific-first chain: `AuthenticationError`/`PermissionDeniedError` → "Invalid API key"; `NotFoundError` → "Model not found"; `RateLimitError` → rate limited; `APIStatusError`/`APIConnectionError` → "Provider unavailable". Raise `from None` so the SDK message, which may echo request data, is dropped.
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** `feat(ai): Claude and ChatGPT providers via official SDKs`

### Task 3: Registry, settings API and wiring

**Files:**
- Create `apps/api/app/ai/registry.py` and `apps/api/app/routes/ai_settings.py`.
- Modify `routes/__init__.py`, `routes/investigations.py` (`provider = provider_for(...)`), `routes/labs.py`, and `security.py` (add `ai:configure` to org_admin).
- Test `tests/api/test_ai_settings.py`.

**Interfaces:**
- `provider_for(request, scope) -> tuple[provider | None, str | None]`:
  - Ollama → `(app.state.llm, app.state.llm_error)`. With a per-user `ollama_model`, return a fresh `OllamaProvider(settings.ollama_base_url, model, ...)`.
  - Hosted → org switch false: `(None, "Hosted AI providers are disabled for this organization")`; no acknowledgement: `(None, "Confirm that evidence may be sent to the provider in Settings")`; no key: `(None, "No API key saved for this provider")`.
  - Otherwise it decrypts with `open_envelope(env, master, f"ai-key:{user}:{provider}", previous)` and builds the provider.
- Routes (all under the router-level session dependency):
  - `GET /organizations/{org}/ai/settings` returns `{allow_hosted_ai, provider, ollama_model, anthropic_model, openai_model, hosted_acknowledged, keys:{anthropic:{saved,last4}, openai:{...}}, ollama:{reachable, model, available_models}}`.
  - `PUT /organizations/{org}/ai/settings` takes `{provider, ollama_model?, anthropic_model?, openai_model?}`. It returns 409 for a hosted provider when the switch is off, no key exists, or (for openai) no model is set.
  - `PUT /organizations/{org}/ai/policy` takes `{allow_hosted_ai}` and needs `ai:configure`; audited.
  - `PUT /ai/keys/{provider}` takes `{api_key}` and returns `{last4}`; audited without the key.
  - `DELETE /ai/keys/{provider}` is audited.
  - `POST /organizations/{org}/ai/acknowledge-hosted` is audited.
  - `POST /organizations/{org}/ai/test` sends a fixed prompt with no tenant data.
- In the investigation and lab responses and records, `model` stays `"<provider>:<model>"`.

- [ ] **Step 1: Failing tests**:
  1. Defaults: provider is ollama, hosted is off.
  2. A viewer gets 403 on policy; an org_admin can toggle it.
  3. Choosing anthropic gets 409 while the switch is off, and 409 when no key is saved.
  4. A canary key `sk-ant-CANARY-…`: it never appears in any route response, the caplog text or audit rows (queried via the migrator), and `last4` is correct.
  5. User B does not see user A's key (`saved: false`).
  6. With Claude selected and a fake AnthropicProvider injected via monkeypatching `registry.AnthropicProvider`, the investigation records `anthropic:claude-opus-5-5`. After the policy is switched off, the next investigation reports `AI_UNAVAILABLE` with the disabled reason and the fake is not called.
  7. With no acknowledgement, the hosted provider is refused.
  8. Deleting the key gives the "No API key" reason.
  9. The existing investigation and lab tests pass unchanged (Ollama path).
  10. Both new route capabilities are present in the authorization matrix.
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement.** The session token for the key functions is `request.cookies["ig_session"]`. Ollama status uses `OllamaProvider.version()` plus a `GET {base}/api/tags` with a 3 s timeout; failure means `reachable: false`.
- [ ] **Step 4: PASS** plus `tests/security` and the investigation and lab suites.
- [ ] **Step 5: Commit** `feat(ai): per-user provider selection, keys and org hosted-AI policy`

### Task 4: Settings page

**Files:** Create `apps/web/src/pages/Settings.tsx`; modify `App.tsx` (nav item `Settings` in Operations) and `pages/index.tsx`; Test `tests/e2e/settings.spec.ts`

- [ ] **Step 1: Failing E2E** (alex): open Settings and see "Ollama" selected with a status line ("running" or "not running", with the install link). With hosted disabled, the Claude and ChatGPT radios are disabled with the explanation. As org_admin, the toggle is visible.
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** the page:
  - Provider radios, model inputs, key fields (password inputs that clear after saving), and "Key ending ••••x — Remove".
  - **Test connection**; an acknowledgement checkbox with the egress warning; the org_admin toggle with an explanation.
  - Ollama help: "Install Ollama from ollama.com/download, then run `ollama pull <model>`".
  - Investigations show `model` as "Answered by …".
- [ ] **Step 4: Build plus the E2E PASS.**
- [ ] **Step 5: Commit** `feat(ai): settings page for providers and keys`

### Task 5: Dependencies, docs, threat model, verification

- [ ] Add `anthropic==1.11.0` and `openai==3.24.0` (plus any new transitive packages from `pip freeze` diff) to `requirements.lock`; `pip_audit -r requirements.lock` clean.
- [ ] `scripts/secret_scan.py`: add patterns `sk-ant-[A-Za-z0-9_-]{20,}` and `sk-(proj-)?[A-Za-z0-9_-]{20,}` with a unit test.
- [ ] AI.md invariant update; THREAT_MODEL.md rows (key storage, egress, hosted injection, SSRF); USER_MANUAL.md section "AI providers" (Ollama install, keys, admin switch); `docs/plans/phase-24-ai-providers.md` ledger.
- [ ] Full ruff/format, secret scan, pytest, build, Playwright; record counts. Commit `docs(ai): phase 24 threat model, manual and ledger`.
