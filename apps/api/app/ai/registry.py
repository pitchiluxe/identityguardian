"""Choose the AI provider for this user in this organization (Phase 24).

Ollama is the default and the only option until an org_admin allows hosted providers. A hosted
provider also needs the user's saved key and their acknowledgement that the authorized evidence
bundle is sent to the vendor. Keys are opened per request and never cached or logged.
"""

from cryptography.exceptions import InvalidTag

from ..secrets_envelope import open_envelope
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .provider import OllamaProvider

HOSTED = ("anthropic", "openai")


def key_context(user_id, provider):
    return f"ai-key:{user_id}:{provider}"


def org_policy(conn):
    row = conn.execute("SELECT allow_hosted_ai FROM organization_ai_settings").fetchone()
    return bool(row and row["allow_hosted_ai"])


def user_choice(conn, user_id):
    return conn.execute("SELECT * FROM user_ai_settings WHERE user_id=%s", (user_id,)).fetchone()


def provider_for(request, scope):
    """Returns (provider, None) or (None, reason). The reason is safe to show to the user."""
    app = request.app
    settings = app.state.settings
    if not settings.ai_enabled:  # operator kill switch: no provider of any kind
        return None, "AI disabled"
    choice = user_choice(scope.conn, scope.user_id)
    provider = choice["provider"] if choice else "ollama"
    if provider in HOSTED and not org_policy(scope.conn):
        provider = "ollama"  # hosted disabled by the organization: answer locally instead
    if provider == "ollama":
        model = choice and choice["ollama_model"]
        if model and model != settings.ollama_model:
            try:
                return (
                    OllamaProvider(
                        settings.ollama_base_url,
                        model,
                        settings.ollama_timeout_seconds,
                        settings.ai_allowed_hosts,
                    ),
                    None,
                )
            except ValueError as exc:
                return None, str(exc)
        return app.state.llm, app.state.llm_error or (None if app.state.llm else "AI disabled")
    if not choice["hosted_ack_at"]:
        return None, "Confirm that evidence may be sent to the provider in Settings"
    envelope = scope.conn.execute(
        "SELECT ai_key_get(%s,%s) AS envelope", (request.cookies.get("ig_session", ""), provider)
    ).fetchone()["envelope"]
    if not envelope:
        return None, "No API key saved for this provider"
    try:
        api_key = open_envelope(
            envelope,
            settings.secret_master_key,
            key_context(scope.user_id, provider),
            settings.secret_master_key_previous,
        )
    except (ValueError, InvalidTag):
        return None, "The saved API key cannot be opened; save it again in Settings"
    if provider == "anthropic":
        return AnthropicProvider(api_key, choice["anthropic_model"] or "claude-opus-5-5"), None
    if not choice["openai_model"]:
        return None, "Enter an OpenAI model ID in Settings"
    return OpenAIProvider(api_key, choice["openai_model"]), None
