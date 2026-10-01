"""Phase 10: agent registry scopes, maximum privilege, expiry and activity queries."""

from tests.api.conftest import as_user
from tests.api.support import membership, source_add, sync


def registry(client, twin, who="viewer", **params):
    as_user(client, twin["people"], who)
    response = client.get(twin["base"] + "/agents", params=params)
    assert response.status_code == 200, response.text
    return {a["identity"]["external_id"]: a for a in response.json()["data"]}


def findings(client, twin, **params):
    as_user(client, twin["people"], "reviewer")
    return [
        f
        for f in client.get(twin["base"] + "/findings", params=params).json()["data"]
        if f["rule"].startswith("AGENT_")
    ]


def test_registry_declared_versus_effective(client, twin):
    agents = registry(client, twin)
    support = agents["idn-agent-support"]
    assert support["declared"]["model"] == "local-llm-support-v2"
    assert (
        support["declared"]["owner"] == "idn-sofia"
        and support["owners"][0]["external_id"] == "idn-sofia"
    )
    assert support["effective"]["tools"] == ["crm.read", "email.send"]
    assert support["effective"]["data"] == {"customer-data": ["Customer Data Store"]}
    assert support["excess_tools"] == [] and support["prohibited_access"] == []
    assert support["expiry"]["state"] == "VALID"
    assert {a["target"] for a in support["activity"]} == {"Customer Data Store", "email.send"}
    assert findings(client, twin) == []


def test_capability_queries(client, twin):
    assert set(registry(client, twin, tool="email.send")) == {"idn-agent-support"}
    assert set(registry(client, twin, data_classification="source-code")) == {"idn-agent-reviewer"}
    assert registry(client, twin, data_classification="payroll") == {}


def test_prohibited_and_excess_access_are_flagged(client, twin):
    source_add(
        twin["org"],
        twin["env"],
        membership("mem-agent-payroll", "idn-agent-support", "grp-payroll-approvers"),
    )
    sync(client, twin)
    support = registry(client, twin)["idn-agent-support"]
    assert support["prohibited_access"] == ["payroll"] and support["excess_data"] == ["payroll"]
    rules = {f["rule"]: f for f in findings(client, twin)}
    assert rules["AGENT_PROHIBITED_DATA"]["severity"] == "critical"
    assert "AGENT_SCOPE_EXCEEDED" in rules
    assert rules["AGENT_PROHIBITED_DATA"]["evidence_ids"]


def test_expiry_states_follow_effective_time(client, twin):
    later = registry(client, twin, effective_at="2026-12-10T00:00:00Z")["idn-agent-support"]
    assert later["expiry"]["state"] == "EXPIRING"
    expired = findings(client, twin, effective_at="2027-01-05T00:00:00Z")
    assert any(
        f["rule"] == "AGENT_REGISTRATION_EXPIRED" and f["severity"] == "critical" for f in expired
    )


def test_activity_window_queries(client, twin):
    as_user(client, twin["people"], "auditor")
    url = twin["base"] + "/agents/idn-agent-support/activity"
    data = client.get(
        url, params={"from": "2026-06-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"}
    ).json()["data"]
    assert data["events"] and all("2026-06" in e["occurred_at"] for e in data["events"])
    assert {c["target"] for c in data["coverage"]} >= {"Customer Data Store", "email.send"}
    assert "unknown" in data["statement"]
    assert (
        client.get(
            url, params={"from": "2026-07-01T00:00:00Z", "to": "2026-06-01T00:00:00Z"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            twin["base"] + "/agents/idn-erick/activity",
            params={"from": "2026-06-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"},
        ).status_code
        == 422
    )
    as_user(client, twin["people"], "viewer")
    assert (
        client.get(
            url, params={"from": "2026-06-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"}
        ).status_code
        == 403
    )
