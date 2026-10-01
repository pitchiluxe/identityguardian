"""Local model provider (AI.md). The model receives only an authorized evidence bundle; it has no
tools, credentials, sessions or write access. Endpoints are server configuration, never input."""

import ipaddress
import json
import time
from urllib.parse import urlparse

import httpx


class ProviderUnavailable(Exception):
    pass


def validate_endpoint(base_url: str, model: str, allowed_hosts: set[str]):
    host = urlparse(base_url).hostname or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback and host not in allowed_hosts:
        raise ValueError("Model endpoint must be loopback or explicitly allowlisted")
    if model.endswith(":cloud") or "-cloud" in model:
        raise ValueError("Cloud-hosted models are refused: evidence must stay local")


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 90.0, allowed_hosts=frozenset()):
        validate_endpoint(base_url, model, set(allowed_hosts))
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def version(self):
        try:
            with httpx.Client(timeout=5, follow_redirects=False) as client:
                tags = client.get(self.base_url + "/api/tags").json()
            match = next((m for m in tags.get("models", []) if m["name"] == self.model), None)
            return match["digest"][:12] if match else None
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    def complete(self, messages, schema):
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                response = client.post(
                    self.base_url + "/api/chat",
                    json=dict(
                        model=self.model,
                        stream=False,
                        format=schema,
                        messages=messages,
                        options=dict(temperature=0, num_ctx=8192),
                    ),
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ProviderUnavailable(f"{type(exc).__name__}") from None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raise ProviderUnavailable("Model returned non-JSON output") from None
        return parsed, round((time.monotonic() - started) * 1000)
