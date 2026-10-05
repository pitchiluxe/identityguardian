"""ChatGPT (OpenAI) provider. Same gating and validation as the Claude provider. The model ID is
required user input: model names change and a guessed default would simply fail."""

import json
import time

import openai

from .provider import ProviderUnavailable


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, client=None):
        if not model or not model.strip():
            raise ValueError("An OpenAI model ID is required")
        self.model = model.strip()
        self.answered_by = self.model
        self._client = client or openai.OpenAI(api_key=api_key, max_retries=1, timeout=90.0)

    def version(self):
        return None

    def complete(self, messages, schema):
        started = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": schema, "strict": False},
                },
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise ProviderUnavailable("Invalid API key") from None
        except openai.NotFoundError:
            raise ProviderUnavailable("Model not found") from None
        except openai.RateLimitError:
            raise ProviderUnavailable("Rate limited by the provider") from None
        except (openai.APIStatusError, openai.APIConnectionError, openai.OpenAIError):
            raise ProviderUnavailable("Provider unavailable") from None
        if not getattr(response, "choices", None):
            raise ProviderUnavailable("Provider unavailable")
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise ProviderUnavailable("The model declined this request")
        try:
            parsed = json.loads(message.content or "")
        except json.JSONDecodeError:
            raise ProviderUnavailable("Model returned non-JSON output") from None
        return parsed, round((time.monotonic() - started) * 1000)
