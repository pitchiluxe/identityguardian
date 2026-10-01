"""Phase 6: reviewer scope, evidence/uncertainty, decision trail; REMOVE proposes, never revokes."""

from uuid import uuid4

from tests.api.conftest import as_user


def campaign(
    client, twin, rules=("PRIOR_ROLE_RETAINED", "TERMINATED_WITH_ACCESS"), reviewer="reviewer"
):
    headers = as_user(client, twin["people"], "admin")
    return client.post(
        twin["base"] + "/reviews",
        headers=headers,
        json=dict(
            name="Q3 retained access", rules=list(rules), reviewer_id=twin["people"][reviewer]["id"]
        ),
    )


def items(client, twin, campaign_id, who="reviewer"):
    as_user(client, twin["people"], who)
    return client.get(twin["base"] + f"/reviews/{campaign_id}").json()["data"]["items"]


def test_campaign_items_carry_evidence_recommendation_and_uncertainty(client, twin):
    created = campaign(client, twin)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["item_count"] >= 2
    rows = items(client, twin, data["id"])
    erick = next(
        i for i in rows if i["evidence"]["grant"]["attributes"].get("ticket") == "TKT-1042"
    )
    assert erick["recommendation"] == "REMOVE"
    assert erick["recommendation_basis"].startswith("RULE-BASED")
    assert any("Peer comparison uses a small sample" in u for u in erick["uncertainty"])
    assert any("not proof of non-use" in u for u in erick["uncertainty"])
    finding = erick["evidence"]["findings"][0]
    assert finding["rule"] == "PRIOR_ROLE_RETAINED" and finding["evidence_ids"]
    assert erick["status"] == "PENDING" and erick["reviewer_name"] == "reviewer"


def test_reviewer_scope_and_capabilities(client, twin):
    data = campaign(client, twin).json()["data"]
    item = items(client, twin, data["id"])[0]
    url = twin["base"] + f"/reviews/{data['id']}/items/{item['id']}/decision"
    body = dict(decision="KEEP", justification="Still required for duties", expected_version=1)
    headers = as_user(client, twin["people"], "viewer")
    assert client.post(url, json=body, headers=headers).status_code == 403
    headers = as_user(client, twin["people"], "admin")
    assert client.post(url, json=body, headers=headers).status_code == 403  # no review:decide
    headers = as_user(client, twin["people"], "admin")
    bad = client.post(
        twin["base"] + "/reviews",
        headers=headers,
        json=dict(
            name="x campaign",
            rules=["PRIOR_ROLE_RETAINED"],
            reviewer_id=twin["people"]["viewer"]["id"],
        ),
    )
    assert bad.status_code == 422
    assert (
        client.post(
            twin["base"] + "/reviews",
            headers=headers,
            json=dict(
                name="x campaign", rules=["MADE_UP"], reviewer_id=twin["people"]["reviewer"]["id"]
            ),
        ).status_code
        == 422
    )
    other = f"/api/v1/organizations/{twin['org']}/environments/{twin['other_env']}"
    headers = as_user(client, twin["people"], "reviewer")
    assert (
        client.post(
            other + f"/reviews/{data['id']}/items/{item['id']}/decision", json=body, headers=headers
        ).status_code
        == 404
    )


def test_remove_creates_draft_proposal_without_revoking(client, twin):
    data = campaign(client, twin).json()["data"]
    erick = next(
        i
        for i in items(client, twin, data["id"])
        if i["evidence"]["grant"]["attributes"].get("ticket") == "TKT-1042"
    )
    headers = as_user(client, twin["people"], "reviewer")
    url = twin["base"] + f"/reviews/{data['id']}/items/{erick['id']}/decision"
    stale = client.post(
        url,
        headers=headers,
        json=dict(
            decision="REMOVE", justification="No longer needed after move", expected_version=9
        ),
    )
    assert stale.status_code == 409
    decided = client.post(
        url,
        headers=headers,
        json=dict(
            decision="REMOVE", justification="No longer needed after move", expected_version=1
        ),
    )
    assert decided.status_code == 200, decided.text
    change = decided.json()["data"]["change_request"]
    assert change["status"] == "DRAFT" and change["origin"] == "review"
    assert change["target"]["external_id"] == "mem-erick-grp-finance-legacy"
    again = client.post(
        url,
        headers=headers,
        json=dict(decision="KEEP", justification="Changed my mind", expected_version=2),
    )
    assert again.status_code == 409
    as_user(client, twin["people"], "investigator")
    groups = {
        r["other"]["external_id"]
        for r in client.get(twin["base"] + "/nodes/idn-erick").json()["data"]["relationships"]
    }
    assert "grp-finance-legacy" in groups  # access unchanged by the review decision
    drafts = client.get(twin["base"] + "/change-requests", params={"status": "DRAFT"}).json()[
        "data"
    ]
    assert [d["id"] for d in drafts] == [change["id"]]
    as_user(client, twin["people"], "admin")
    audit = client.get(f"/api/v1/organizations/{twin['org']}/audit").json()
    actions = [e["action"] for e in audit]
    assert "review.decided" in actions and "change.proposed" in actions


def test_reviewer_cannot_be_campaign_owner(client, twin):
    headers = as_user(client, twin["people"], "admin")
    response = client.post(
        twin["base"] + "/reviews",
        headers=headers,
        json=dict(
            name="self",
            rules=["PRIOR_ROLE_RETAINED"],
            reviewer_id=twin["people"]["admin"]["id"],
            idempotency=str(uuid4()),
        ),
    )
    assert response.status_code == 422  # unknown field rejected before any write
