"""Phase 22: production mode exposes no synthetic seeding, sandbox tooling or mock connectors."""

import pytest
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from tests.api.conftest import as_user

PROD = dict(
    development=False,
    secure_cookies=True,
    app_origin="https://iam.example.com",
    oidc_issuer_url="https://idp.example.com/realms/identityguardian",
    read_limit_per_minute=5000,
    write_limit_per_minute=1000,
)


@pytest.fixture
def prod_client(shared_db):
    with TestClient(
        create_app(Settings(**PROD), db=shared_db), base_url="https://iam.example.com"
    ) as c:
        yield c


def headers(client, people, who):
    h = as_user(client, people, who)
    h["Origin"] = "https://iam.example.com"
    return h


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/sandbox/seed", {"variant": "standard", "confirm_synthetic": True}),
        ("post", "/connectors/sandbox/sync", {"mode": "full"}),
        (
            "put",
            "/sandbox/faults",
            {"operation": "remove_relationship", "mode": "fail_before_write", "remaining": 1},
        ),
    ],
)
def test_synthetic_tooling_is_absent_in_production(prod_client, twin, method, path, body):
    h = headers(prod_client, twin["people"], "admin")
    response = getattr(prod_client, method)(twin["base"] + path, headers=h, json=body)
    assert response.status_code == 404


def test_mock_connectors_refused_in_production(prod_client, twin):
    h = headers(prod_client, twin["people"], "admin")
    response = prod_client.post(
        twin["base"] + "/connectors",
        headers=h,
        json=dict(
            kind="mock_entra",
            name="Corporate directory",
            endpoint="mock://mock_entra/x",
            authoritative=True,
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Connector kind not available in production"


def test_development_keeps_tooling(client, twin):
    h = as_user(client, twin["people"], "admin")
    response = client.post(
        twin["base"] + "/sandbox/seed",
        headers=h,
        json={"variant": "standard", "confirm_synthetic": True},
    )
    assert response.status_code != 404


def test_session_and_overview_report_mode(client, prod_client, tenant):
    org, _, people = tenant
    for c, mode in ((client, "development"), (prod_client, "production")):
        as_user(c, people, "viewer")
        assert c.get("/api/v1/session").json()["deployment"] == {"mode": mode}
        overview = c.get(f"/api/v1/organizations/{org}/overview").json()
        assert overview["deployment"] == {"mode": mode}
        assert "phase" not in overview and "identity_data" not in overview


def test_existing_mock_connectors_cannot_sync_in_production(client, prod_client, twin):
    # A database once used in development may still hold mock connectors.
    created = client.post(
        twin["base"] + "/connectors",
        headers=as_user(client, twin["people"], "admin"),
        json=dict(
            kind="mock_entra",
            name="Leftover mock",
            endpoint="mock://mock_entra/x",
            authoritative=True,
        ),
    )
    assert created.status_code == 201, created.text
    connector = created.json()["data"]["id"]
    h = headers(prod_client, twin["people"], "admin")
    response = prod_client.post(
        twin["base"] + f"/connectors/{connector}/sync", headers=h, json={"mode": "full"}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Connector kind not available in production"


def test_settings_fail_closed_to_production(monkeypatch):
    monkeypatch.delenv("DEVELOPMENT", raising=False)
    settings = Settings(
        _env_file=None,
        secure_cookies=True,
        app_origin="https://iam.example.com",
        oidc_issuer_url="https://idp.example.com/realms/identityguardian",
    )
    assert settings.development is False


def test_production_compose_sets_mode_for_every_app_service():
    # YAML merge keys are shallow: a service's own `environment` replaces the anchor's, so each
    # application service must set the mode itself.
    import re
    from pathlib import Path

    compose = (
        Path(__file__).resolve().parents[2] / "infra" / "compose.production.yaml"
    ).read_text()
    for service in ("migrate", "api", "worker"):
        pattern = r"\n  " + service + r":\n(.*?)(?=\n  [a-z]+:\n|\nnetworks:)"
        block = re.search(pattern, compose, re.S)
        assert block and 'DEVELOPMENT: "false"' in block.group(1), service
