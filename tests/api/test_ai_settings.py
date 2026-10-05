"""Phase 24: per-user AI provider choice, per-user keys, and the org hosted-AI policy."""

import base64
import logging
import os

import psycopg
import pytest

from apps.api.app.ai import registry
from tests.api.conftest import as_user
from tests.api.test_investigations import Fake, ask, fact_ids

CANARY = "sk-ant-CANARY-0123456789abcdefghijklmnopqrstu"  # secret-scan: allow - synthetic canary


@pytest.fixture(autouse=True)
def master_key(client):
    client.app.state.settings.secret_master_key = base64.b64encode(os.urandom(32)).decode()


def settings_url(twin):
    return f"/api/v1/organizations/{twin['org']}/ai"


def put(client, twin, who, path, body, base=None):
    headers = as_user(client, twin["people"], who)
    return client.put((base or settings_url(twin)) + path, headers=headers, json=body)


def post(client, twin, who, path, body=None):
    headers = as_user(client, twin["people"], who)
    return client.post(settings_url(twin) + path, headers=headers, json=body or {})


def save_key(client, twin, who, provider="anthropic", key=CANARY):
    headers = as_user(client, twin["people"], who)
    return client.put(f"/api/v1/ai/keys/{provider}", headers=headers, json={"api_key": key})


def get_settings(client, twin, who):
    as_user(client, twin["people"], who)
    return client.get(settings_url(twin) + "/settings")


def enable_claude(client, twin, who="investigator"):
    assert put(client, twin, "admin", "/policy", {"allow_hosted_ai": True}).status_code == 200
    assert save_key(client, twin, who).status_code == 200
    assert post(client, twin, who, "/acknowledge-hosted").status_code == 200
    assert put(client, twin, who, "/settings", {"provider": "anthropic"}).status_code == 200


def test_defaults_are_local_ollama_with_hosted_disabled(client, twin):
    data = get_settings(client, twin, "investigator").json()["data"]
    assert data["provider"] == "ollama" and data["allow_hosted_ai"] is False
    assert data["keys"] == {"anthropic": {"saved": False}, "openai": {"saved": False}}
    assert set(data["ollama"]) >= {"reachable", "model"}


def test_only_org_admin_controls_hosted_policy(client, twin):
    for who in ("viewer", "investigator", "approver"):
        assert put(client, twin, who, "/policy", {"allow_hosted_ai": True}).status_code == 403
    assert put(client, twin, "admin", "/policy", {"allow_hosted_ai": True}).status_code == 200
    assert get_settings(client, twin, "viewer").json()["data"]["allow_hosted_ai"] is True


def test_hosted_choice_refused_without_policy_or_key(client, twin):
    assert (
        put(client, twin, "investigator", "/settings", {"provider": "anthropic"}).status_code == 409
    )
    put(client, twin, "admin", "/policy", {"allow_hosted_ai": True})
    response = put(client, twin, "investigator", "/settings", {"provider": "anthropic"})
    assert response.status_code == 409 and "API key" in response.json()["detail"]
    save_key(
        client,
        twin,
        "investigator",
        "openai",
        "sk-proj-0123456789abcdefghij",  # secret-scan: allow - synthetic canary
    )  # secret-scan: allow - synthetic canary
    response = put(client, twin, "investigator", "/settings", {"provider": "openai"})
    assert response.status_code == 409 and "model" in response.json()["detail"]


def test_keys_never_leave_the_server_and_stay_per_user(client, twin, caplog):
    caplog.set_level(logging.DEBUG)
    saved = save_key(client, twin, "investigator")
    assert saved.status_code == 200 and saved.json()["data"] == {"last4": CANARY[-4:]}
    mine = get_settings(client, twin, "investigator")
    theirs = get_settings(client, twin, "viewer")
    assert mine.json()["data"]["keys"]["anthropic"] == {"saved": True, "last4": CANARY[-4:]}
    assert theirs.json()["data"]["keys"]["anthropic"] == {"saved": False}
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        audit = conn.execute(
            "SELECT string_agg(before_state::text || after_state::text || justification || target, ' ') "
            "FROM audit_events WHERE organization_id=%s",
            (twin["org"],),
        ).fetchone()[0]
        stored = conn.execute("SELECT envelope::text FROM user_ai_keys").fetchall()
    for text in (saved.text, mine.text, theirs.text, caplog.text, audit or "", str(stored)):
        assert CANARY not in text and CANARY[8:30] not in text


def test_hosted_answer_records_provider_and_switch_off_stops_egress(client, twin, monkeypatch):
    built = []
    fake = Fake(
        lambda m: {
            "insufficient_evidence": False,
            "claims": [
                {"text": "Payroll access exists.", "type": "fact", "citations": fact_ids(m)[:1]}
            ],
        }
    )
    fake.name, fake.model = "anthropic", "claude-opus-5-5"

    def factory(api_key, model="claude-opus-5-5", client=None):
        built.append(api_key)
        return fake

    monkeypatch.setattr(registry, "AnthropicProvider", factory)
    enable_claude(client, twin)
    first = ask(client, twin, "Who can access payroll?")
    assert first.status_code == 200, first.text
    assert first.json()["data"]["model"] == "anthropic:claude-opus-5-5" and built == [CANARY]
    calls = len(fake.calls)
    ollama = Fake(lambda m: {"insufficient_evidence": True, "claims": []})
    client.app.state.llm = ollama
    put(client, twin, "admin", "/policy", {"allow_hosted_ai": False})
    second = ask(client, twin, "Who can access payroll?").json()["data"]
    assert len(fake.calls) == calls  # no hosted egress after the switch-off
    assert len(ollama.calls) == 1 and second["model"] == "fake:fake-model"


def test_operator_ai_kill_switch_blocks_every_provider(client, twin, monkeypatch):
    monkeypatch.setattr(registry, "AnthropicProvider", lambda *a, **k: pytest.fail("no egress"))
    monkeypatch.setattr(registry, "OllamaProvider", lambda *a, **k: pytest.fail("no ollama"))
    enable_claude(client, twin)
    client.app.state.settings.ai_enabled = False
    data = ask(client, twin, "Who can access payroll?").json()["data"]
    assert data["status"] == "AI_UNAVAILABLE" and "AI disabled" in data["note"]
    put(
        client,
        twin,
        "investigator",
        "/settings",
        {"provider": "ollama", "ollama_model": "other:7b"},
    )
    assert ask(client, twin, "Who can access payroll?").json()["data"]["status"] == "AI_UNAVAILABLE"


def test_recorded_model_is_the_one_that_answered(client, twin, monkeypatch):
    fake = Fake(
        lambda m: {
            "insufficient_evidence": False,
            "claims": [
                {"text": "Payroll access exists.", "type": "fact", "citations": fact_ids(m)[:1]}
            ],
        }
    )
    fake.name, fake.model, fake.answered_by = "anthropic", "claude-opus-5-5", "claude-opus-4-8"
    monkeypatch.setattr(registry, "AnthropicProvider", lambda *a, **k: fake)
    enable_claude(client, twin)
    data = ask(client, twin, "Who can access payroll?").json()["data"]
    assert data["model"] == "anthropic:claude-opus-4-8"


def test_connection_test_uses_the_ai_quota(client, twin):
    client.app.state.settings.ai_limit_per_minute = 1
    client.app.state.llm = Fake(lambda m: {"ok": True})
    assert post(client, twin, "viewer", "/test").status_code == 200
    assert post(client, twin, "viewer", "/test").status_code == 429


def test_hosted_needs_acknowledgement_and_a_key(client, twin, monkeypatch):
    monkeypatch.setattr(registry, "AnthropicProvider", lambda *a, **k: pytest.fail("no egress"))
    put(client, twin, "admin", "/policy", {"allow_hosted_ai": True})
    save_key(client, twin, "investigator")
    put(client, twin, "investigator", "/settings", {"provider": "anthropic"})
    data = ask(client, twin, "Who can access payroll?").json()["data"]
    assert data["status"] == "AI_UNAVAILABLE" and "Confirm" in data["note"]
    post(client, twin, "investigator", "/acknowledge-hosted")
    headers = as_user(client, twin["people"], "investigator")
    assert client.delete("/api/v1/ai/keys/anthropic", headers=headers).status_code == 200
    data = ask(client, twin, "Who can access payroll?").json()["data"]
    assert data["status"] == "AI_UNAVAILABLE" and "No API key" in data["note"]
