"""Phase 16 connector contract suite (runs against every provider implementation)."""

import base64
import os

import pytest

from apps.api.app.connectors.base import (
    Capabilities,
    ConnectorUnavailable,
    RateLimited,
    UnsupportedOperation,
    validate_endpoint,
)
from apps.api.app.connectors.providers import PROVIDERS
from apps.api.app.secrets_envelope import open_envelope, seal

KEY = base64.b64encode(os.urandom(32)).decode()


def read_all(connector):
    cursor, pages, objects = None, 0, []
    while True:
        page = connector.read(cursor)
        pages += 1
        objects += page.objects
        assert page.provenance["synthetic"] is True
        if page.next_cursor is None:
            return objects, pages
        assert int(page.next_cursor) > int(cursor or 0)  # cursors only move forward
        cursor = page.next_cursor


@pytest.fixture(params=sorted(PROVIDERS))
def provider(request):
    return PROVIDERS[request.param]


def test_capabilities_declared(provider):
    caps = provider({}).capabilities()
    assert isinstance(caps, Capabilities) and caps.write == [] and caps.authoritative_scope
    assert caps.page_size > 0


def test_reads_are_paged_canonical_and_ordered(provider):
    objects, pages = read_all(provider({}))
    assert pages >= 2 and len({o["object_id"] for o in objects}) == len(objects)
    seen = set()
    for obj in objects:
        body = obj["body"]
        assert obj["object_type"] in {"node", "relationship"} and body["id"] == obj["object_id"]
        if body["type"] == "relationship":
            assert body["src"] in seen and body["dst"] in seen  # endpoints arrive first
            assert body["valid_from"].endswith("+00:00")
        seen.add(obj["object_id"])


def test_replay_is_deterministic(provider):
    assert read_all(provider({}))[0] == read_all(provider({}))[0]


def test_faults_and_throttling(provider):
    failing = provider({"fail_on_page": 2})
    first = failing.read(None)
    with pytest.raises(ConnectorUnavailable):
        failing.read(first.next_cursor)
    throttled = provider({"rate_limit_on_page": 1, "rate_limit_times": 2})
    for _ in range(2):
        with pytest.raises(RateLimited):
            throttled.read(None)
    assert throttled.read(None).objects


def test_writes_are_refused(provider):
    with pytest.raises(UnsupportedOperation):
        provider({}).apply({"op": "remove_relationship"})


@pytest.mark.parametrize(
    "url",
    [
        "http://graph.example.com",
        "https://169.254.169.254/latest",
        "https://127.0.0.1/api",
        "https://10.0.0.5",
        "file:///etc/passwd",
        "https://evil.example.net",
    ],
)
def test_endpoint_policy_blocks_ssrf(url):
    with pytest.raises(ValueError):
        validate_endpoint(url, ["graph.example.com"])


def test_endpoint_policy_allows_mock_and_allowlisted():
    validate_endpoint("mock://entra/contoso", [])
    validate_endpoint("https://graph.example.com/v1.0", ["graph.example.com"])


def test_secret_envelope():
    envelope = seal("webhook-secret-value", KEY, "connector:abc")
    assert "webhook-secret-value" not in str(envelope)
    assert open_envelope(envelope, KEY, "connector:abc") == "webhook-secret-value"
    with pytest.raises(Exception):
        open_envelope(envelope, KEY, "connector:other")  # bound to its context
    with pytest.raises(Exception):
        open_envelope(envelope, base64.b64encode(os.urandom(32)).decode(), "connector:abc")
    with pytest.raises(ValueError):
        seal("x", "", "connector:abc")
