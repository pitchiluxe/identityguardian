"""Phase 5: cycle-safe typed exposure rules, bounds/completeness, defensive framing only."""

from tests.api.conftest import as_user
from tests.api.support import source_update, sync


def paths(client, twin, **params):
    as_user(client, twin["people"], "investigator")
    response = client.get(twin["base"] + "/attack-paths", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def route(path):
    return [s["to"]["external_id"] for s in path["steps"]]


def test_reset_exposure_is_conditional_on_target_mfa(client, twin):
    result = paths(client, twin, source="idn-erick")
    to_customer = [
        p for p in result["data"]["paths"] if route(p) == ["idn-sofia", "res-customer-data"]
    ]
    assert len(to_customer) == 1
    path = to_customer[0]
    assert path["status"] == "CONDITIONAL"
    reset = path["steps"][0]
    assert reset["kind"] == "credential_reset"
    assert [e["type"] for e in reset["edges"]][-1] == "CAN_RESET_CREDENTIAL"
    assert reset["edges"][0]["attributes"]["ticket"] == "TKT-2210"  # HelpDesk-L2 grant evidence
    assert any(f["type"] == "target_mfa_registered" for f in reset["factors"])
    assert "not evidence of exploitation" in path["statement"]
    assert path["defensive_controls"] and set(path["evidence_ids"]) <= set(result["evidence_ids"])
    # Erick already holds payroll directly: it is not reported as a new exposure destination.
    assert all(p["destination"]["external_id"] != "res-payroll" for p in result["data"]["paths"])


def test_missing_target_mfa_makes_exposure_potential_and_leaver_gap_flagged(client, twin):
    def no_mfa(body):
        for rev in body["revisions"]:
            rev["attributes"]["mfa_registered"] = False
        return body, False

    source_update(twin["env"], "idn-olivia", no_mfa)
    sync(client, twin)
    result = paths(client, twin, source="idn-erick")
    olivia = [p for p in result["data"]["paths"] if route(p)[0] == "idn-olivia"]
    assert olivia and olivia[0]["status"] == "POTENTIAL"
    ben = [p for p in result["data"]["paths"] if route(p)[0] == "idn-ben"]
    assert ben and any(f["type"] == "terminated_target" for f in ben[0]["steps"][0]["factors"])


def test_assume_role_requires_controls_and_ownership_never_implies_access(client, twin):
    chen = paths(client, twin, source="idn-chen")["data"]["paths"]
    breakglass = [p for p in chen if p["steps"][0]["kind"] == "assume_role"]
    assert breakglass and breakglass[0]["destination"]["external_id"] == "app-directory"
    assert breakglass[0]["status"] == "CONDITIONAL"
    assert {f["type"] for f in breakglass[0]["steps"][0]["factors"]} == {
        "mfa_required",
        "approval_ticket",
    }
    maria = paths(client, twin, source="idn-maria")["data"]["paths"]
    assert all(s["kind"] != "ownership" for p in maria for s in p["steps"])
    assert not any("svc-backup" in route(p) for p in maria)


def test_bounds_and_destination_filter(client, twin):
    limited = paths(client, twin, max_paths=1)
    assert limited["data"]["complete"] is False and limited["completeness"] == "partial"
    one_step = paths(client, twin, source="idn-erick", max_steps=1)
    assert all(len(p["steps"]) <= 2 for p in one_step["data"]["paths"])
    filtered = paths(client, twin, destination="res-customer-data")
    assert filtered["data"]["paths"]
    assert {p["destination"]["external_id"] for p in filtered["data"]["paths"]} == {
        "res-customer-data"
    }
    as_user(client, twin["people"], "viewer")
    assert client.get(twin["base"] + "/attack-paths").status_code == 403
