# AI providers: Ollama (default), Claude and ChatGPT — design (Phase 24)

2026-10-05 · Design approved in chat by the user ("approve 24", with the "Org admin switch" egress decision) · Spec awaiting user review

## Intent

Users can choose **Ollama** (default, local), **Claude** (Anthropic) or **ChatGPT** (OpenAI) for AI features: the investigator and the lab instructor. They enter their own API keys on a **Settings** page. Ollama must be installed on the machine that runs the API, and the UI says so plainly when it isn't.

This reverses a Phase 13 invariant ("cloud-hosted models are refused: evidence must stay local"). The decision is the user's, made on 2026-10-05. The new rule is: **local by default; hosted only when an org_admin enables it for the organization.**

## Decisions

| Topic | Decision |
|---|---|
| Who allows egress | Org setting `allow_hosted_ai`, **off** by default. Only `org_admin` can change it (new capability `ai:configure`). Every change is audited |
| Keys | **Per user**, one per provider (`anthropic`, `openai`). AES-256-GCM envelope with the existing master key and `kid` (Phase 20 rotation applies). Context `ai-key:<user_id>:<provider>` |
| Provider choice | Per user, per organization: `ollama` (default), `anthropic` or `openai`. A hosted choice is refused when the org switch is off or the user has no key |
| Claude | Official `anthropic` Python SDK. Default model `claude-opus-5-5`; the user may enter another model ID. Adaptive thinking (the default on this model) with `output_config.effort` set explicitly to `medium`, plus structured JSON output via `output_config.format`. **Refusal fallback enabled by default** (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) per Anthropic guidance for this model; a final `stop_reason == "refusal"` is surfaced as "The model declined this request". Typed SDK exceptions map to clear user messages (invalid key, rate limited, unavailable) |
| ChatGPT | Official `openai` Python SDK in its own module. **The model ID is a required field the user enters**: there is no built-in default, because model names change and a guessed one fails. Structured JSON output |
| Ollama | Existing `OllamaProvider`, now the default. Per-user model name; the base URL stays server configuration (loopback or allowlist). Clear "Ollama is not installed or not running" messaging with the `ollama pull <model>` command |
| Egress warning | Before a user's first hosted call in an organization, the UI requires an explicit acknowledgement: "Evidence for this question will be sent to Anthropic/OpenAI". The acknowledgement is stored and audited |

## Architecture

- `apps/api/app/ai/provider.py` keeps `OllamaProvider`. New `ai/anthropic_provider.py` and `ai/openai_provider.py` implement the same interface: `complete(messages, schema) -> (parsed, ms)`, `name`, `model`, `version()`.
- The `validate_endpoint` refusal of `:cloud` models stays for Ollama. Hosted providers never use an Ollama URL.
- `ai/registry.py` provides `provider_for(conn, settings, user_id, org) -> Provider | Unavailable(reason)`. It reads the org switch, the user's choice and the decrypted key, and caches nothing secret across requests.
- `investigations.py` and `labs.py` call `provider_for(...)` instead of `app.state.llm`. All existing grounding is unchanged: pre-retrieval authorization, the evidence-as-data prompt, citation, number and name validation, and no tools or execution authority.
- Each investigation and lab hint records `provider`, `model` and `provider_version` (already partly recorded) so answers can be traced.

### Data (migration `025_ai_settings.sql`)

- `organization_ai_settings(organization_id PK, allow_hosted_ai bool default false, updated_by, updated_at)`: RLS-scoped; the runtime role may read, and update only through the route.
- `user_ai_settings(organization_id, user_id, provider text check in (ollama,anthropic,openai) default 'ollama', ollama_model text, anthropic_model text, openai_model text, hosted_ack_at timestamptz, PK(org,user))`: RLS-scoped.
- `user_ai_keys(user_id, provider check in (anthropic,openai), envelope jsonb, last4 text, created_at, PK(user_id, provider))`. Keys are per user across organizations. Access is through narrow definer functions keyed by the session user, so one user can never read another's row.

### API

| Route | Capability | Notes |
|---|---|---|
| `GET /organizations/{org}/ai/settings` | `overview:read` | Returns the org switch, the user's provider and models, `has_key` with `last4` per provider, and Ollama status (`installed/running`, models available). Never returns keys |
| `PUT /organizations/{org}/ai/settings` | `overview:read` | The user's own provider and models. Hosted choice → 409 if the org switch is off or no key exists |
| `PUT /organizations/{org}/ai/policy` | `ai:configure` | `{allow_hosted_ai}`; audited. Turning it off immediately forces affected users back to Ollama at call time |
| `PUT /ai/keys/{provider}` | session | `{api_key}`: validated by length and shape, then sealed. The response is `{last4}` only. Audited without the key |
| `DELETE /ai/keys/{provider}` | session | Audited |
| `POST /organizations/{org}/ai/test` | `overview:read` | Runs a tiny fixed prompt with no tenant evidence against the chosen provider and reports success or a classified error |
| `POST /organizations/{org}/ai/acknowledge-hosted` | `overview:read` | Records the egress acknowledgement |

### Web

A new **Settings** navigation item (Operations group) with an **AI** section:
- A provider radio with an Ollama status badge and install help: <https://ollama.com/download> and `ollama pull qwen2.5:7b`.
- Key fields shown as "Key ending ••••a1b2 — Replace / Remove". Keys are never echoed.
- Model fields and a **Test connection** button.
- An org_admin-only "Allow hosted AI providers for this organization" toggle with the egress explanation.
- The Investigations and AI assistant pages show which provider and model answered.

## Security

New THREAT_MODEL.md rows:
- **API-key storage:** envelope-encrypted, per user, never returned or logged. Rotation is covered by `rotate-master-key`.
- **Evidence egress:** org-gated, acknowledged by the user and audited. Only the already-authorized evidence bundle is sent.
- **Hosted-model prompt injection:** same grounding validation; output is advisory only.
- **SSRF:** the hosted SDKs use fixed vendor endpoints, and users cannot set a base URL.

AI.md is updated to the new invariant. The secret scan gains patterns for `sk-ant-` and `sk-` keys.

## Tests (negative first)

1. A hosted provider is refused when the org switch is off. Choosing it returns 409, and calling it at run time falls back to an "unavailable" status. Nothing is sent: a mock transport asserts no request.
2. Only org_admin can change `allow_hosted_ai`. The authorization matrix covers it.
3. User A cannot read or use user B's key, through routes or direct SQL as the runtime role.
4. Keys never appear in any API response, audit event, log line (captured with caplog) or exception message. A canary key is used.
5. Without the acknowledgement, a hosted call is refused.
6. Claude provider: the request uses `claude-opus-5-5` by default, `output_config` effort plus format and the fallback beta. Refusal maps to the declined message. Typed errors map to user messages. All tested with a mocked HTTP transport, so no real API calls are made in tests.
7. OpenAI provider: the request shape and error mapping, with a mocked transport.
8. Ollama remains the default for new users, and the existing investigation and lab tests pass unchanged.
9. The Settings UI E2E: set the provider to Ollama and see the status; with the org switch off, the hosted options are disabled.

## Dependencies

Add pinned `anthropic` (1.x) and `openai` to `requirements.lock`; pip-audit must stay clean. The Python SDK 1.x uses `httpx2`. The existing `httpx` stays for the other callers.

## Out of scope

Organization-wide shared keys, streaming answers, cost tracking and budgets, hosted embeddings, and other providers.
