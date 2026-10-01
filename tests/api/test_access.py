"""Phase 3: direct/nested/conditional/deny/alternative-path lineage with provenance."""

from tests.api.conftest import as_user
from tests.api.support import membership, source_add, source_update, sync


def access(client, twin, who, **params):
    as_user(client, twin["people"], "investigator")
    response = client.get(twin["base"] + f"/identities/{who}/access", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def entry(result, resource=None, permission=None):
    for item in result["data"]["entries"]:
        if resource and (item["resource"] or {}).get("external_id") != resource:
            continue
        if permission and (item["permission"] or {}).get("external_id") != permission:
            continue
        return item
    return None


def chain(path):
    return [hop["to"]["external_id"] for hop in path["hops"]]


def test_nested_legacy_route_to_payroll_with_provenance(client, twin):
    result = access(client, twin, "idn-erick")
    payroll = entry(result, "res-payroll", "perm-payroll-config")
    assert payroll["decision"] == "ALLOW" and len(payroll["paths"]) == 1
    path = payroll["paths"][0]
    assert chain(path) == [
        "grp-finance-legacy",
        "grp-erp-operators",
        "role-erp-admin",
        "perm-payroll-config",
        "res-payroll",
    ]
    first = path["hops"][0]["edge"]["attributes"]
    assert first["ticket"] == "TKT-1042" and first["approver"] == "idn-ana"
    assert path["origin"] == "legacy_entitlement via nested group"
    assert set(path["evidence_ids"]) <= set(result["evidence_ids"])
    usage = payroll["usage"]
    assert usage["observed_events"] == 0
    assert usage["coverage"][0]["completeness"] == "complete"
    assert result["completeness"] == "complete"


def test_alternative_routes_are_reported_separately(client, twin):
    result = access(client, twin, "idn-tom")
    erp = entry(result, "app-erp", "perm-erp-use")
    routes = sorted(chain(p)[0] for p in erp["paths"])
    assert routes == ["grp-erp-operators", "grp-finance-analysts"]
    source_add(
        twin["org"],
        twin["env"],
        membership(
            "mem-erick-payroll-alt", "idn-erick", "grp-payroll-approvers", ticket="TKT-2301"
        ),
    )
    sync(client, twin)
    payroll = entry(access(client, twin, "idn-erick"), "res-payroll", "perm-payroll-config")
    assert len(payroll["paths"]) == 2


def test_conditional_and_unsupported_conditions_never_allow(client, twin):
    crm = entry(access(client, twin, "idn-sofia"), "res-customer-data", "perm-customer-read")
    statuses = sorted(p["status"] for p in crm["paths"])
    assert statuses == ["ALLOW", "CONDITIONAL"] and crm["decision"] == "ALLOW"
    conditional = next(p for p in crm["paths"] if p["status"] == "CONDITIONAL")
    assert conditional["conditions"][0]["type"] == "device_compliant"

    def remove_plain(body):
        body["valid_to"] = "2026-09-29T00:00:00+00:00"
        return body, True

    def unsupported(body):
        body["attributes"]["conditions"] = [{"type": "geo_fence"}]
        return body, False

    source_update(twin["env"], "mem-sofia-grp-sales-team", remove_plain)
    source_update(twin["env"], "ur-sofia-crm-cond", unsupported)
    sync(client, twin)
    crm = entry(access(client, twin, "idn-sofia"), "res-customer-data", "perm-customer-read")
    assert crm["decision"] == "UNKNOWN"
    assert crm["paths"][0]["conditions"][0]["supported"] is False


def test_explicit_deny_overrides_grant(client, twin):
    source_add(
        twin["org"],
        twin["env"],
        membership("mem-grace-payroll", "idn-grace", "grp-payroll-approvers"),
    )
    sync(client, twin)
    payroll = entry(access(client, twin, "idn-grace"), "res-payroll", "perm-payroll-config")
    assert payroll["decision"] == "DENY"
    assert payroll["paths"][0]["denied_by"]["type"] == "DENY_ASSIGNMENT"


def test_cycles_terminate_and_bounds_report_incomplete(client, twin):
    result = access(client, twin, "idn-chen")
    repos = entry(result, "res-repos", "perm-repo-admin")
    assert repos["decision"] == "ALLOW"
    assert all(len(set(chain(p))) == len(chain(p)) for p in repos["paths"])
    assert len(repos["paths"]) == 1  # the Eng-Platform <-> Eng-SRE cycle adds no route
    limited = access(client, twin, "idn-tom", max_paths=1)
    assert limited["data"]["complete"] is False and limited["completeness"] == "partial"
    assert "Path limit" in limited["data"]["truncation_reason"]


def test_source_native_expiry_and_history(client, twin):
    before = entry(
        access(client, twin, "idn-kim", effective_at="2026-10-01T00:00:00Z"),
        "res-ledger",
        "perm-ledger-read",
    )
    assert before["decision"] == "ALLOW"
    after = access(client, twin, "idn-kim", effective_at="2026-11-01T00:00:00Z")
    assert entry(after, "res-ledger", "perm-ledger-read") is None
    past = access(client, twin, "idn-erick", effective_at="2026-05-01T00:00:00Z")
    erp = entry(past, "app-erp", "perm-erp-use")
    assert erp["usage"]["observed_events"] > 0


def test_principals_for_payroll_and_authorization(client, twin):
    as_user(client, twin["people"], "investigator")
    result = client.get(twin["base"] + "/resources/res-payroll/principals").json()
    names = {p["identity"]["external_id"]: p["decision"] for p in result["data"]["principals"]}
    assert names == {
        "idn-erick": "ALLOW",
        "idn-tom": "ALLOW",
        "idn-svc-erp-sync": "ALLOW",
        "idn-ana": "ALLOW",
    }
    as_user(client, twin["people"], "viewer")
    assert client.get(twin["base"] + "/resources/res-payroll/principals").status_code == 403
    assert client.get(twin["base"] + "/identities/idn-erick/access").status_code == 403
    as_user(client, twin["people"], "investigator")
    assert client.get(twin["base"] + "/identities/grp-erp-operators/access").status_code == 422
    other = f"/api/v1/organizations/{twin['org']}/environments/{twin['other_env']}"
    assert client.get(other + "/identities/idn-erick/access").status_code == 404
