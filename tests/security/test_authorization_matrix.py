"""Phase 18: every endpoint x every role.

The capability each route requires is read from its own handler (`scoped(..., "capability")`),
so new routes join the matrix automatically. Properties checked:
  * anonymous callers get 401 on every protected route (before any body validation);
  * a role without the capability never succeeds (GET -> 403; mutations never 2xx);
  * a role with the capability is never refused with 403 for capability reasons;
  * another tenant's organization is never reachable (404);
  * nothing returns 5xx.
"""

import inspect
import re
from uuid import uuid4

import pytest

from apps.api.app.main import create_app
from apps.api.app.security import ROLE_CAPABILITIES
from tests.api.conftest import as_user

PUBLIC = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/callback",
    "/api/v1/organizations/{org}/environments/{env}/connectors/{connector_id}/webhook",
}
ROLES = [
    "viewer",
    "investigator",
    "reviewer",
    "approver",
    "operator",
    "admin",
    "auditor",
    "learner",
]
ROLE_OF = {"admin": ["org_admin", "operator"]}
DYNAMIC = {"overview:read"}  # handlers that refine authority inside (e.g. by change kind)
SCOPED = re.compile(r'scoped\(\s*request,\s*org,\s*[^,]+,\s*"([a-z:]+)"')
QUERY = dict(
    effective_at="2026-07-01T00:00:00Z",
    known_at="2026-09-30T00:00:00Z",
    node="idn-erick",
    level="1",
    **{"from": "2026-06-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"},
)


def routes():
    app = create_app()
    found = []

    def walk(items, prefix=""):
        for r in items:
            if hasattr(r, "methods") and hasattr(r, "path"):
                for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
                    found.append((method, prefix + r.path, r.endpoint))
            elif hasattr(r, "original_router"):
                walk(r.original_router.routes, prefix)

    walk(app.routes)
    return [r for r in found if r[1].startswith("/api/")]


ROUTES = routes()


def capability(endpoint):
    match = SCOPED.search(inspect.getsource(endpoint))
    return match.group(1) if match else None


def fill(path, org, env):
    values = dict(org=org, env=env, node_id="idn-erick", lab_id="onboarding")
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), str(uuid4())), path)


def call(client, method, url):
    if method == "GET":
        return client.get(url, params=QUERY)
    return client.request(method, url, json={})


def test_route_inventory_is_complete():
    paths = {p for _, p, _ in ROUTES}
    assert len(ROUTES) > 80
    unknown = [
        (m, p)
        for m, p, e in ROUTES
        if p not in PUBLIC
        and capability(e) is None
        and not p.startswith(
            (
                "/api/v1/session",
                "/api/v1/auth/",
                "/api/v1/organizations/{org}/role-requests",
                "/api/v1/organizations/{org}/overview",
                "/api/v1/organizations/{org}/members",
                "/api/v1/organizations/{org}/audit",
            )
        )
    ]
    assert unknown == [], unknown
    assert "/api/v1/organizations/{org}/environments/{env}/findings" in paths


def test_anonymous_is_rejected_everywhere(client, twin):
    client.cookies.clear()
    failures = []
    for method, path, _ in ROUTES:
        if path in PUBLIC:
            continue
        url = fill(path, twin["org"], twin["env"])
        response = (
            client.get(url, params=QUERY)
            if method == "GET"
            else client.request(method, url, json={})
        )
        if response.status_code != 401:
            failures.append((method, path, response.status_code))
    assert failures == []


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix(client, twin, role):
    headers = as_user(client, twin["people"], role)
    granted = set().union(*(ROLE_CAPABILITIES[r] for r in ROLE_OF.get(role, [role])))
    problems, checked, denied = [], 0, 0
    for method, path, endpoint in ROUTES:
        needed = capability(endpoint)
        if path in PUBLIC or needed is None or needed in DYNAMIC:
            continue
        url = fill(path, twin["org"], twin["env"])
        response = (
            client.get(url, params=QUERY)
            if method == "GET"
            else client.request(method, url, json={}, headers=headers)
        )
        status = response.status_code
        checked += 1
        denied += status == 403
        if status >= 500:
            problems.append((method, path, status, "server error"))
        elif needed in granted:
            if status == 403 and "role does not allow" in response.text:
                problems.append((method, path, status, f"refused although {role} holds {needed}"))
        elif 200 <= status < 300:
            problems.append((method, path, status, f"{role} succeeded without {needed}"))
        elif method == "GET" and status != 403:
            problems.append((method, path, status, f"expected 403 for {role} without {needed}"))
    assert problems == []
    assert checked >= 60, checked  # the matrix must not silently shrink
    assert denied > 0 or role == "admin"


def test_other_tenant_is_unreachable(client, twin):
    headers = as_user(client, twin["people"], "admin")
    leaks = []
    for method, path, _ in ROUTES:
        if path in PUBLIC or "{org}" not in path:
            continue
        url = fill(path, twin["other"], twin["other_env"])
        response = (
            client.get(url, params=QUERY)
            if method == "GET"
            else client.request(method, url, json={}, headers=headers)
        )
        if response.status_code not in {404, 422}:
            leaks.append((method, path, response.status_code))
    assert leaks == []
