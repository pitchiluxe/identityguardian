# Production Profile Implementation Plan (Phase 22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With `DEVELOPMENT=false` the platform shows no demo data, names, placeholders or simulation tooling. A real organization and its first admin are created by a one-time operator command.

**Architecture:**
- A FastAPI dependency `development_only` returns 404 for the synthetic seed, sandbox-sync and fault routes outside development.
- Connector creation refuses mock kinds in production.
- `session` and `overview` expose `deployment.mode`, and the web shell renders demo labels and tools only in development.
- `manage.py init-organization` creates the organization, a PRODUCTION environment and a bootstrap org_admin invite. The invite uses the Phase 21 table, with a new `bootstrap` flag that only the migration role can set.

**Tech Stack:** FastAPI, psycopg 3, PostgreSQL 17, React 19, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-production-profile-design.md`

## Global Constraints

- Production mode = `Settings.development is False` (it already forces HTTPS origins and Secure cookies).
- Development behaviour and all 285 existing tests stay unchanged.
- Hidden routes return **404** (`{"detail":"Not Found"}`), not 403, in production.
- No "Planned"/"scheduled for Phase" text anywhere. In production, no "synthetic"/"Contoso" text in the shell.
- No credentials are created or printed by `init-organization`, apart from the one-time invite path.
- Schema changes go in `migrations/025_bootstrap_invites.sql` with matching grants.

## Review Focus

1. A production deployment that still contains old Contoso rows: the UI must not show demo labels (they are driven by mode, not data) — pinned in Task 3 (labels depend only on `deployment.mode`).
2. `init-organization` run twice by mistake creates no second org — pinned in Task 4.
3. The runtime role cannot mint a bootstrap invite (`bootstrap=true`) — pinned in Task 4.
4. An org_admin in production calling the seed route directly gets 404, not 403 or 200 — pinned in Task 1.
5. A first admin who redeems the bootstrap invite lands with org_admin only — pinned in Task 4 via `redeem_invite`.

---

### Task 1: Development-only routes and mock connectors

**Files:**
- Modify: `apps/api/app/scope.py` (add `development_only`)
- Modify: `apps/api/app/routes/twin.py:65,83`, `apps/api/app/routes/changes.py:586`, `apps/api/app/routes/connectors.py:90,143`
- Test: `tests/api/test_production_profile.py`

**Interfaces:**
- Produces: `development_only(request: Request) -> None` (raises `HTTPException(404)` when `request.app.state.settings.development` is False); fixture `prod_client(shared_db)` in the new test file.

- [ ] **Step 1: Write the failing tests**

```python
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
        ("put", "/sandbox/faults", {"operation": "add_member", "mode": "fail", "remaining": 1}),
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
        json=dict(kind="mock_entra", name="x", endpoint="mock://mock_entra/x", authoritative=True),
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
```

Check the real body schemas of `SeedRequest`, the sandbox `FaultRequest` and `ConnectorRequest`. If a body is invalid, FastAPI returns 422 before the dependency runs; in that case put the dependency on the router decorator (it runs before body validation, as `require_session` does) and adjust the bodies to be valid.

- [ ] **Step 2: Run, expect FAIL** — `.venv/Scripts/python -m pytest -n 0 -q tests/api/test_production_profile.py` → the seed returns 200/409, not 404.

- [ ] **Step 3: Implement**

In `scope.py`:

```python
def development_only(request: Request):
    """Synthetic fixtures, sandbox tooling and mock providers do not exist in production."""
    if not request.app.state.settings.development:
        raise HTTPException(404, "Not Found")
```

Add `dependencies=[Depends(development_only)]` to the decorators of `twin.seed`, `twin` sandbox sync (`/connectors/sandbox/sync`), `changes.set_fault`, and `connectors` faults (`/connectors/{connector_id}/faults`). In `connectors.create`, before other checks:

```python
        if not settings.development:
            raise HTTPException(422, "Connector kind not available in production")
```

- [ ] **Step 4: Run, expect PASS**, plus `tests/security` (the authorization matrix must still pass in development mode).

- [ ] **Step 5: Commit** `feat(prod): development-only synthetic tooling and mock connectors`

### Task 2: Deployment mode in API responses; remove stale placeholders

**Files:**
- Modify: `apps/api/app/main.py` (`session`, `overview`)
- Test: `tests/api/test_production_profile.py`

- [ ] **Step 1: Failing tests**

```python
def test_session_and_overview_report_mode(client, prod_client, tenant):
    org, _, people = tenant
    for c, mode in ((client, "development"), (prod_client, "production")):
        as_user(c, people, "viewer")
        assert c.get("/api/v1/session").json()["deployment"] == {"mode": mode}
        overview = c.get(f"/api/v1/organizations/{org}/overview").json()
        assert overview["deployment"] == {"mode": mode}
        assert "phase" not in overview and "identity_data" not in overview
```

- [ ] **Step 2: Run, expect FAIL** (KeyError `deployment`).
- [ ] **Step 3: Implement.** Add `"deployment": {"mode": "development" if app.state.settings.development else "production"}` to both responses. Remove `"phase": 1` and `"identity_data": "Not ingested — Phase 2 planned"` from `overview`. Grep the web app for `identity_data` and `overview.phase`, and delete any use.
- [ ] **Step 4: PASS**, plus `tests/api/test_foundation.py`.
- [ ] **Step 5: Commit** `feat(prod): deployment mode in session and overview; drop stale phase fields`

### Task 3: Web shell without placeholders; demo tooling only in development

**Files:**
- Modify: `apps/web/src/api.ts` (`Session.deployment`, `Overview.deployment`)
- Modify: `apps/web/src/App.tsx` (remove the planned badge, planned fallback and planned subtitle; labels by mode; landing copy)
- Modify: `apps/web/src/pages/Integrations.tsx` (sandbox panel and mock registry only in development; production empty state)
- Modify: `apps/web/src/pages/index.tsx` (subtitles mentioning synthetic data only in development)
- Test: `tests/e2e/shell.spec.ts` (add an assertion) + a build grep in `tests/unit/test_web_text.py`

- [ ] **Step 1: Failing test** `tests/unit/test_web_text.py`:

```python
"""Phase 22: the shell ships no planned-feature placeholders."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "apps" / "web" / "src"


def test_no_planned_placeholders_in_web_source():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
    for needle in ("nav-planned", "is planned", "scheduled for Phase", "Planned for Phase"):
        assert needle not in text, needle


def test_synthetic_wording_only_behind_development_mode():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "BUILD_LABEL" not in app or "development" in app
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `Session` and `Overview` gain `deployment: { mode: 'development' | 'production' }`. `ctx` gets `dev: boolean`.
  - `navigation` keeps name, icon and group only. Drop the phase number and the planned span.
  - An unknown page renders the Dashboard: there is no planned fallback.
  - Sidebar bottom label: dev → "Local build · synthetic data / No production connectors"; prod → `${overview.organization.name} · ${environment.kind}`.
  - Landing note: dev → "Local development · synthetic organization"; prod → "Organization-scoped access by invitation."
  - Integrations: render the Contoso sandbox panel and `ConnectorRegistry` only when `ctx.dev`. Otherwise render `Panel title="Identity sources"` with `<p>No identity source connected yet.</p>`. Keep sync history in both modes.
  - index.tsx: subtitles containing "SYNTHETIC"/"Synthetic" become mode-aware via `ctx.dev`, or are reworded neutrally.
- [ ] **Step 4: Run** the unit test, `npm run build`, and the Playwright shell + invite specs.
- [ ] **Step 5: Commit** `feat(prod): shell without placeholders; demo tooling only in development`

### Task 4: Real organization bootstrap

**Files:**
- Create: `migrations/025_bootstrap_invites.sql`
- Modify: `scripts/manage.py` (`init-organization`; `bootstrap` refuses outside development)
- Test: `tests/integration/test_init_organization.py`

**Interfaces:**
- Produces: `init_organization(conn, name: str, admin_email: str, allow_additional=False) -> dict(organization_id, environment_id, invite_path)`.

- [ ] **Step 1: Failing tests**

```python
"""Phase 22: one-time real organization bootstrap with a bootstrap org_admin invite."""

import os
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.security import digest
from scripts.manage import init_organization

load_dotenv()
pytestmark = pytest.mark.integration
MIGRATOR, RUNTIME = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]


def test_init_creates_org_env_and_bootstrap_invite_once():
    name = f"Init Test {uuid4().hex[:6]}"
    with psycopg.connect(MIGRATOR) as conn:
        made = init_organization(conn, name, "First.Admin@Example.org ", allow_additional=True)
        with pytest.raises(SystemExit):
            init_organization(conn, name, "x@example.org")  # orgs exist; no --allow-additional
        org = made["organization_id"]
        assert conn.execute(
            "SELECT kind FROM environments WHERE organization_id=%s", (org,)
        ).fetchall() == [("PRODUCTION",)]
        token = made["invite_path"].rsplit("/", 1)[1]
        row = conn.execute(
            "SELECT status, roles, bootstrap, email_normalized FROM invites WHERE token_hash=%s",
            (digest(token),),
        ).fetchone()
    assert row == ("ACTIVE", ["org_admin"], True, "first.admin@example.org")
    with psycopg.connect(RUNTIME) as conn:
        result = conn.execute(
            "SELECT * FROM redeem_invite(%s,'https://idp.test',%s,'First Admin','first.admin@example.org')",
            (digest(token), str(uuid4())),
        ).fetchone()
    assert result[3] is None


def test_runtime_role_cannot_create_bootstrap_invites():
    with psycopg.connect(RUNTIME) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,digest,status,expires_at,bootstrap) "
            "VALUES (gen_random_uuid(),gen_random_uuid(),'a@b.c',ARRAY['org_admin'],'h',gen_random_uuid(),'d','ACTIVE',now(),true)"
        )
```

- [ ] **Step 2: Run, expect FAIL** (ImportError `init_organization`).
- [ ] **Step 3: Implement.**

Migration `025_bootstrap_invites.sql`:

```sql
-- Phase 22: the first org_admin of a real organization is invited by the operator bootstrap,
-- which has no second approver. Only the migration role can set bootstrap.
ALTER TABLE invites ADD COLUMN bootstrap boolean NOT NULL DEFAULT false;
ALTER TABLE invites DROP CONSTRAINT invites_privileged_approved;
ALTER TABLE invites ADD CONSTRAINT invites_privileged_approved CHECK (
 NOT roles && ARRAY['org_admin','approver','operator']
 OR status IN ('PENDING_APPROVAL','REVOKED') OR approver_id IS NOT NULL OR bootstrap);
REVOKE INSERT ON invites FROM guardian_app;
GRANT INSERT (id, organization_id, email_normalized, roles, token_hash, inviter_id, digest,
 justification, status, expires_at) ON invites TO guardian_app;
-- Fixed, non-loginable principal recorded as the inviter of bootstrap invites.
INSERT INTO users VALUES ('00000000-0000-4000-8000-00000000b007', 'urn:identityguardian:system',
 'operator-bootstrap', 'Operator bootstrap') ON CONFLICT DO NOTHING;
```

`manage.py`:

```python
SYSTEM_INVITER = UUID("00000000-0000-4000-8000-00000000b007")


def init_organization(conn, name, admin_email, allow_additional=False):
    """Create a real organization, its PRODUCTION environment and a one-time org_admin invite."""
    from datetime import datetime, timedelta, timezone

    from apps.api.app.routes.invites import invite_digest
    from apps.api.app.security import digest

    email = admin_email.strip().lower()
    conn.execute("SELECT pg_advisory_xact_lock(10002)")
    if not allow_additional and conn.execute("SELECT 1 FROM organizations").fetchone():
        raise SystemExit("Organizations already exist; pass --allow-additional to add another.")
    org, env, invite = uuid4(), uuid4(), uuid4()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=72)
    conn.execute("SELECT set_config('app.org', %s, true)", (str(org),))
    conn.execute("INSERT INTO organizations VALUES (%s,%s)", (org, name))
    conn.execute(
        "INSERT INTO environments(id,organization_id,name,kind) VALUES (%s,%s,'Production','PRODUCTION')",
        (env, org),
    )
    conn.execute(
        "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,digest,"
        "justification,status,expires_at,bootstrap) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,true)",
        (
            invite,
            org,
            email,
            ["org_admin"],
            digest(token),
            SYSTEM_INVITER,
            invite_digest(org, email, "org_admin", expires.isoformat()),
            "Operator bootstrap of the first administrator",
            expires,
        ),
    )
    for action, target in (("organization.initialized", org), ("invite.created", invite)):
        conn.execute(
            "INSERT INTO audit_events(id,organization_id,actor_id,action,target,justification,result,correlation_id) "
            "VALUES (gen_random_uuid(),%s,%s,%s,%s,'Operator init-organization','succeeded',gen_random_uuid())",
            (org, SYSTEM_INVITER, action, str(target)),
        )
    return dict(organization_id=org, environment_id=env, invite_path=f"/invite/{token}")
```

CLI: add `init-organization` to the choices with the `--name`, `--admin-email` and `--allow-additional` arguments. Print `invite_path` plus "Join with APP_ORIGIN; valid 72 hours, single use." `bootstrap` adds at the top: `if Settings().development is False: raise SystemExit("bootstrap creates SYNTHETIC data and is disabled outside development")`. Check whether `environments` has other NOT NULL columns, such as `lab_learner`, before relying on this INSERT.

- [ ] **Step 4: Migrate and run** `tests/integration/test_init_organization.py` and `tests/integration/test_invites_db.py`.
- [ ] **Step 5: Commit** `feat(prod): init-organization with operator bootstrap invite`

### Task 5: Threat model, docs, full verification

- [ ] THREAT_MODEL.md row: "Production profile (Phase 22)". Synthetic seeding, sandbox tooling and mock connectors are absent server-side outside development (404/422, tested). The bootstrap invite can be minted only by the migration role (column grant, tested).
- [ ] `docs/operations/deployment.md`: replace "no bootstrap step… manage.py against the migration URL" with the `init-organization` procedure.
- [ ] `USER_MANUAL.md` §6: a note that the very first admin gets their link from the operator who runs `init-organization`.
- [ ] `docs/plans/phase-22-production-profile.md`: bounded plan pointer plus a verification ledger with real output.
- [ ] Full run: ruff and format, secret scan, full pytest, `npm run build`, full Playwright. Record the counts.
- [ ] Commit `docs(prod): phase 22 threat model, runbook and ledger`.
