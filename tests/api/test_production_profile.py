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
