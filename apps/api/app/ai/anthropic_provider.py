"""Claude (Anthropic) provider. Used only when an org_admin allows hosted AI and the user saved a key
and acknowledged that the authorized evidence bundle leaves the machine (AI.md). No tools, no
execution authority: the model returns JSON that is validated against the evidence like any other.
"""

import json
import time

import anthropic

from .provider import ProviderUnavailable

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, client=None):
        self.model = model or DEFAULT_MODEL
        self._client = client or anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=90.0)

    def version(self):
        return None

    def complete(self, messages, schema):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        started = time.monotonic()
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=turns,
                # Adaptive thinking is the default on this model; effort is set explicitly.
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": schema},
                },
                # Anthropic's recommended server-side fallback when a safety classifier declines.
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise ProviderUnavailable("Invalid API key") from None
        except anthropic.NotFoundError:
            raise ProviderUnavailable("Model not found") from None
        except anthropic.RateLimitError:
            raise ProviderUnavailable("Rate limited by the provider") from None
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            raise ProviderUnavailable("Provider unavailable") from None
        if response.stop_reason == "refusal":
            raise ProviderUnavailable("The model declined this request")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            raise ProviderUnavailable("Model returned non-JSON output") from None
        return parsed, round((time.monotonic() - started) * 1000)
