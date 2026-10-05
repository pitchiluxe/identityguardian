# Entra ID Connector Implementation Plan (Phase 23)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a read-only Microsoft Entra ID connector that ingests a real test tenant through the existing connector contract.

**Architecture:**
- `connectors/entra.py`: `EntraConnector(Connector)` with an injectable `httpx.Client`. A staged base64-JSON cursor does one Graph request per `read()` and maps results to canonical node/relationship rows.
- `providers.build()` builds `entra` connectors with the decrypted client secret, resolving settings from the app or the worker's environment.
- The connectors route accepts kind `entra` (tenant_id, client_id, client_secret) in SANDBOX/PRODUCTION environments in every mode.
- The Integrations page gains an **Identity sources** panel for all modes.

**Tech Stack:** httpx (existing), FastAPI, psycopg, React, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-entra-connector-design.md`

## Global Constraints

- Endpoints are fixed: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` and `https://graph.microsoft.com/v1.0`. `tenant_id` and `client_id` must be GUIDs (regex), so the tenant segment cannot inject a host.
- The connector sends no HTTP method except `POST` to the token URL and `GET` to Graph.
- No secret in responses, logs, exceptions or audit. Error messages are the fixed strings in the spec.
- Service principals are capped at 200. Group and role member pages follow `@odata.nextLink`.
- Canonical object IDs use the `entra:` prefix; the account node is `entra-acct:`. No `synthetic` attribute.
- Kind `entra` is refused in LAB environments (409) and allowed in development and production modes.

## Review Focus

1. A tenant with zero groups, roles or apps: the read completes, with no error and an authoritative coverage.
2. A guest user (`userType` Guest) maps to subtype `guest`.
3. A group that is a member of itself, or a cycle: ingestion stays bounded (existing traversal bounds), and the connector emits the edge once.
4. Token expiry mid-job (401 on a Graph call after a valid token): one re-token attempt, then a fixed error.
5. A display name with markup: stored as data and rendered escaped (React default).

---

### Task 1: EntraConnector (Graph client, paging, mapping)

**Files:** Create `apps/api/app/connectors/entra.py`; Test `tests/unit/test_entra_connector.py`

**Interfaces:** `EntraConnector(config: dict, client_secret: str, http: httpx.Client | None = None)`; `.source = "entra"`; `capabilities()`; `read(cursor) -> Page`.

Stages, in order:
1. `users`: `GET /users?$select=id,displayName,userPrincipalName,accountEnabled,department,jobTitle,userType&$top=100`
2. `groups`: `GET /groups?$select=id,displayName,securityEnabled&$top=100`, collecting group IDs into the queue.
3. `group_members`: for each queued group, `GET /groups/{id}/members?$select=id&$top=100`. Each member's `@odata.type` decides between a user and a group edge.
4. `roles`: `GET /directoryRoles?$select=id,displayName`, queueing role IDs.
5. `role_members`: `GET /directoryRoles/{id}/members?$select=id`.
6. `apps`: `GET /servicePrincipals?$select=id,displayName,appId&$top=100`, capped at 200, queueing app IDs.
7. `app_assignments`: `GET /servicePrincipals/{id}/appRoleAssignedTo?$top=100`. A `principalType` of `User` emits an edge; `Group` is counted and skipped.
8. Done → `next_cursor=None`.

Provenance: `dict(provider="entra", tenant=<tenant_id>, stage=..., skipped_group_app_assignments=n)`.

- [ ] **Step 1: Failing tests**, using `httpx.MockTransport` with a routing handler over a tiny fake tenant (2 users including 1 guest; groups `G1` and `G2`, where G2 is a member of G1; role "Global Administrator" with user 1; app "Payroll" assigned to user 2 and to group G1). Then:
  - Read until `next_cursor` is None and collect objects.
  - Assert the node kinds and subtypes, and the relationship triples: `USER_MEMBER_OF_GROUP`, `GROUP_INHERITS_GROUP` (G2→G1), `USER_HAS_ROLE`, `SERVICE_ACCOUNT_ACCESS_APPLICATION`; group→app skipped and counted.
  - Assert every request method/host is in {POST login token, GET graph}.
  - Assert the secret does not appear in caplog or in `repr` of any exception.
  - Separate tests:
    - 429 → `RateLimited`.
    - 401 twice → `ConnectorUnavailable` with the fixed message.
    - 401 once then 200 → re-token and continue.
    - Empty tenant → completes.
    - Invalid GUID config → `ValueError`.
- [ ] **Step 2: FAIL** (ImportError).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** `feat(entra): read-only Microsoft Graph connector`

### Task 2: Registration, secret handling and worker build

**Files:**
- Modify `apps/api/app/routes/connectors.py`: `ConnectorRequest` becomes a discriminated union. The existing mock body stays; add `EntraRequest(kind="entra", name, tenant_id, client_id, client_secret, authoritative=True)`. Production refuses only mock kinds. LAB refuses `entra`. The secret is sealed. The `has_secret` flag stays.
- Modify `apps/api/app/connectors/providers.py`: `build(row, settings=None)`.
- Modify `apps/api/app/connectors/runner.py`: pass settings, defaulting to `Settings()` in the worker.
- Modify `scripts/manage.py`: rotation already covers `connectors.secret_envelope`.
- Test: `tests/api/test_entra_registration.py`.

- [ ] **Step 1: Failing tests:**
  - An admin creates an `entra` connector in a SANDBOX environment. The response has no secret; audit rows have no secret; `has_secret` is true.
  - LAB → 409. Viewer → 403. Bad GUID → 422. Other organization → 404.
  - Production-mode client: `entra` allowed (201) while `mock_entra` stays 422.
  - A sync job: monkeypatch `entra.EntraConnector` to inject a mock-transport client. `process_one(worker)` ingests, and the identities endpoint lists the fake users.
  - The runner builds with the decrypted secret: assert the factory got the secret.
- [ ] **Steps 2–5:** FAIL → implement → PASS (+ the connectors and security suites) → commit `feat(entra): register Entra connectors with sealed client secret`.

### Task 3: Identity sources UI

**Files:** Create `apps/web/src/pages/IdentitySources.tsx`; modify `Integrations.tsx` to render it in all modes, with the dev tools still dev-only; Test `tests/e2e/entra.spec.ts`.

- [ ] Steps:
  - The E2E fails first: as alex in development mode, Integrations shows the "Connect Microsoft Entra ID" form, with Tenant ID, Client ID and Client secret fields.
  - Implement: on submit, POST `/connectors` with kind `entra`, clear the secret field and list the sources with Sync now.
  - Run build + E2E. A real sync is not exercised in E2E: there is no tenant, and the API test covers it.
  - Commit `feat(entra): identity sources panel`.

### Task 4: Docs, threat model, verification

- [ ] THREAT_MODEL rows; INTEGRATIONS.md section; USER_MANUAL section "Connect your Microsoft Entra test tenant" (the Azure steps from the chat, the "never share the secret" warning, and where to paste it); `docs/plans/phase-23-entra.md` ledger.
- [ ] Full ruff, secret scan, pytest, build and Playwright; record the counts; commit.
