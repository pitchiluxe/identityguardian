"""Phase 23: read-only Microsoft Entra ID connector against a mocked Microsoft Graph."""

import json
import logging
from urllib.parse import urlparse

import httpx
import pytest

from apps.api.app.connectors.base import ConnectorUnavailable, RateLimited
from apps.api.app.connectors.entra import EntraConnector

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET = "entra-CANARY-secret-0123456789"  # secret-scan: allow - synthetic canary
CONFIG = dict(tenant_id=TENANT, client_id=CLIENT)
GRAPH = "https://graph.microsoft.com/v1.0"

TENANT_DATA = {
    "/users": [
        dict(
            id="u1",
            displayName="Ada Admin",
            userPrincipalName="ada@t.example",
            accountEnabled=True,
            department="IT",
            jobTitle="Engineer",
            userType="Member",
        ),
        dict(
            id="u2",
            displayName="Gus Guest",
            userPrincipalName="gus@t.example",
            accountEnabled=False,
            department=None,
            jobTitle=None,
            userType="Guest",
        ),
    ],
    "/groups": [
        dict(id="g1", displayName="Finance", securityEnabled=True),
        dict(id="g2", displayName="Payroll Team", securityEnabled=True),
    ],
    "/groups/g1/members": [
        {"@odata.type": "#microsoft.graph.user", "id": "u1"},
        {"@odata.type": "#microsoft.graph.group", "id": "g2"},
    ],
    "/groups/g2/members": [{"@odata.type": "#microsoft.graph.user", "id": "u2"}],
    "/directoryRoles": [dict(id="r1", displayName="Global Administrator")],
    "/directoryRoles/r1/members": [{"@odata.type": "#microsoft.graph.user", "id": "u1"}],
    "/servicePrincipals": [dict(id="sp1", displayName="Payroll", appId="app-1")],
    "/servicePrincipals/sp1/appRoleAssignedTo": [
        dict(principalId="u2", principalType="User"),
        dict(principalId="g1", principalType="Group"),
    ],
}


class FakeMicrosoft:
    def __init__(self, data=None, script=None):
        self.data = TENANT_DATA if data is None else data
        self.script = list(script or [])  # optional forced responses, consumed in order
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.script:
            status = self.script.pop(0)
            if status is not None:
                return httpx.Response(status, json={"error": {"message": "nope " + SECRET}})
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        path = request.url.path.removeprefix("/v1.0")
        return httpx.Response(200, json={"value": self.data.get(path, [])})


def connector(fake):
    return EntraConnector(CONFIG, SECRET, http=httpx.Client(transport=httpx.MockTransport(fake)))


def read_all(conn):
    cursor, objects, pages = None, [], 0
    while True:
        page = conn.read(cursor)
        objects += page.objects
        pages += 1
        assert pages < 100
        if page.next_cursor is None:
            return objects, page
        cursor = page.next_cursor


def test_reads_tenant_into_canonical_objects_with_only_safe_requests(caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeMicrosoft()
    objects, last = read_all(connector(fake))
    nodes = {o["object_id"]: o["body"] for o in objects if o["object_type"] == "node"}
    rels = {
        (o["body"]["rel"], o["body"]["src"], o["body"]["dst"])
        for o in objects
        if o["object_type"] == "relationship"
    }
    assert nodes["entra:u1"]["kind"] == "identity" and nodes["entra:u1"]["subtype"] == "employee"
    assert nodes["entra:u2"]["subtype"] == "guest"
    assert nodes["entra:u2"]["revisions"][0]["status"] == "disabled"
    assert "synthetic" not in nodes["entra:u1"]["revisions"][0]["attributes"]
    assert nodes["entra:r1"]["kind"] == "role" and nodes["entra:sp1"]["kind"] == "application"
    assert {
        ("HAS_ACCOUNT", "entra:u1", "entra-acct:u1"),
        ("USER_MEMBER_OF_GROUP", "entra:u1", "entra:g1"),
        ("GROUP_INHERITS_GROUP", "entra:g2", "entra:g1"),
        ("USER_MEMBER_OF_GROUP", "entra:u2", "entra:g2"),
        ("USER_HAS_ROLE", "entra:u1", "entra:r1"),
        ("SERVICE_ACCOUNT_ACCESS_APPLICATION", "entra:u2", "entra:sp1"),
    } <= rels
    assert last.provenance["skipped_group_app_assignments"] == 1
    for request in fake.requests:
        host, method = request.url.host, request.method
        assert (method, host) in {
            ("POST", "login.microsoftonline.com"),
            ("GET", "graph.microsoft.com"),
        }
        if host == "login.microsoftonline.com":
            assert urlparse(str(request.url)).path == f"/{TENANT}/oauth2/v2.0/token"
    assert SECRET not in caplog.text


def test_throttling_raises_rate_limited():
    with pytest.raises(RateLimited):
        connector(FakeMicrosoft(script=[None, 429])).read(None)


def test_rejected_credentials_give_fixed_message_without_secret():
    with pytest.raises(ConnectorUnavailable) as caught:
        connector(FakeMicrosoft(script=[401])).read(None)
    assert str(caught.value) == "Microsoft rejected the app credentials or permissions"
    assert SECRET not in repr(caught.value)


def test_expired_token_is_refreshed_once():
    fake = FakeMicrosoft(script=[None, 401])  # token ok, first Graph call 401, then normal
    page = connector(fake).read(None)
    assert (
        page.objects and sum(r.url.host == "login.microsoftonline.com" for r in fake.requests) == 2
    )


def test_empty_tenant_completes():
    objects, last = read_all(connector(FakeMicrosoft(data={})))
    assert objects == [] and last.next_cursor is None


@pytest.mark.parametrize("bad", ["not-a-guid", "evil.example/x", ""])
def test_config_must_be_guids(bad):
    with pytest.raises(ValueError):
        EntraConnector(dict(tenant_id=bad, client_id=CLIENT), SECRET)
    with pytest.raises(ValueError):
        EntraConnector(dict(tenant_id=TENANT, client_id=bad), SECRET)


def test_cursor_is_opaque_json_without_secret():
    page = connector(FakeMicrosoft()).read(None)
    assert page.next_cursor and SECRET not in page.next_cursor
    assert "tok" not in page.next_cursor  # the access token never enters a stored cursor
    json.dumps(page.provenance)
