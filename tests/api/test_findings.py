"""Phase 4: privilege creep, dormant, leaver and unused findings explain evidence and coverage."""

from tests.api.conftest import as_user
from tests.api.support import source_update, sync


def findings(client, twin, **params):
    as_user(client, twin["people"], "reviewer")
    response = client.get(twin["base"] + "/findings", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def by_rule(result, rule):
    return [f for f in result["data"] if f["rule"] == rule]


def test_prior_role_finding_for_erick_explains_evidence_and_coverage(client, twin):
    result = findings(client, twin)
    prior = by_rule(result, "PRIOR_ROLE_RETAINED")
    assert [f["identity"]["external_id"] for f in prior] == ["idn-erick"]
    finding = prior[0]
    assert finding["severity"] == "high" and finding["basis"] == "RULE-BASED"
    assert finding["grant"]["attributes"]["ticket"] == "TKT-1042"
    assert finding["event"]["details"]["from_department"] == "Finance"
    assert finding["peers"] == {"sample_size": 1, "holding": 0}
    payroll = next(r for r in finding["reaches"] if r["target_id"] == "res-payroll")
    assert payroll["privileged"] is True
    usage = next(u for u in finding["usage"] if u["target"] == "Payroll · SIMULATED")
    assert usage["state"] == "NOT_OBSERVED" and "does not prove" in usage["text"]
    assert set(finding["evidence_ids"]) <= set(result["evidence_ids"])
    again = findings(client, twin)
    assert [f["key"] for f in again["data"]] == [f["key"] for f in result["data"]]


def test_justified_and_common_grants_are_not_attributed_to_previous_role(client, twin):
    prior = by_rule(findings(client, twin), "PRIOR_ROLE_RETAINED")
    groups = {f["grant"]["dst"] for f in prior}
    titles = " ".join(f["title"] for f in prior)
    assert len(groups) == 1 and "HelpDesk-L2" not in titles and "All-Staff" not in titles


def test_leaver_dormant_and_unused_findings(client, twin):
    result = findings(client, twin)
    leaver = by_rule(result, "TERMINATED_WITH_ACCESS")
    assert [f["identity"]["external_id"] for f in leaver] == ["idn-ben"]
    assert leaver[0]["severity"] == "critical" and leaver[0]["accounts"]
    dormant = {f["identity"]["external_id"] for f in by_rule(result, "DORMANT_PRIVILEGED")}
    assert dormant == {"idn-dave"}
    unused = {
        (f["identity"]["external_id"], f["reaches"][0]["target_id"])
        for f in by_rule(result, "UNUSED_PRIVILEGED_ENTITLEMENT")
    }
    assert ("idn-erick", "res-payroll") in unused
    assert ("idn-tom", "res-payroll") not in unused  # Tom's use is observed
    assert result["counts"]["TERMINATED_WITH_ACCESS"] == 1


def test_removal_clears_current_finding_but_history_retains_it(client, twin):
    def remove(body):
        body["valid_to"] = "2026-09-29T12:00:00+00:00"
        return body, True

    source_update(twin["env"], "mem-erick-grp-finance-legacy", remove)
    sync(client, twin)
    assert by_rule(findings(client, twin), "PRIOR_ROLE_RETAINED") == []
    past = findings(client, twin, effective_at="2026-09-15T00:00:00Z")
    assert len(by_rule(past, "PRIOR_ROLE_RETAINED")) == 1


def test_findings_authorization_and_filters(client, twin):
    as_user(client, twin["people"], "viewer")
    assert client.get(twin["base"] + "/findings").status_code == 403
    only = findings(client, twin, rule="DORMANT_PRIVILEGED")
    assert {f["rule"] for f in only["data"]} == {"DORMANT_PRIVILEGED"}
    erick = findings(client, twin, identity="idn-erick")
    assert {f["identity"]["external_id"] for f in erick["data"]} == {"idn-erick"}


def test_timeline_orders_move_grants_and_usage(client, twin):
    as_user(client, twin["people"], "auditor")
    response = client.get(twin["base"] + "/identities/idn-erick/timeline")
    assert response.status_code == 200, response.text
    events = response.json()["data"]["events"]
    kinds = [e["kind"] for e in events]
    assert "employment.move" in kinds and "usage.summary" in kinds
    legacy = next(e for e in events if "TKT-1042" in e["text"])
    move = next(e for e in events if e["kind"] == "employment.move")
    assert legacy["at"] < move["at"]
    assert [e["at"] for e in events] == sorted(e["at"] for e in events)
