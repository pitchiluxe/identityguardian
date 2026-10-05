# Production profile — design (Phase 22)

2026-10-05 · Design approved in chat by the user ("approve 22") · Spec awaiting user review

## Intent

The user wants the platform "ready for production" for **real users on a hosted server**, with no demo names, placeholders or fake data visible. This phase delivers the application side. Hosting is Phase 25, and real identity data arrives with read-only Entra ID and Okta connectors in Phase 23.

Production mode is the existing `DEVELOPMENT=false` setting, which Phase 20 already requires for deployment (HTTPS, Secure cookies). Development and the automated tests keep the synthetic Contoso data: 285 tests depend on it, and labs are training by design.

## What changes in production mode

| Area | Today | Production |
|---|---|---|
| Demo organization | `manage.py bootstrap` creates Contoso and synthetic users | `bootstrap` refuses when `DEVELOPMENT=false`. New `manage.py init-organization` (below) |
| Seeding | `POST …/sandbox/seed` (Twin) and the changes-sandbox seed load the SYNTHETIC Contoso fixture | Both routes return **404**, as if they don't exist. The UI hides their buttons |
| Mock connectors | `mock_entra` and `mock_okta` offered in Integrations | Not offered. Creating one is refused with 422 "Connector kind not available". Phase 23 adds real `entra` and `okta` kinds |
| Shell labels | "Local build · synthetic data", "No production connectors", landing "Local development · synthetic organization" | Labels come from the server: organization name and environment kind (e.g. "Northwind · Production"). Landing copy describes the product, with no "synthetic" wording |
| Planned placeholders | `nav-planned` badges, a "scheduled for Phase N" fallback and a planned subtitle | **Removed in all modes.** Every navigation item has a page, so this code is dead |
| Integrations page | "Contoso sandbox directory" generator, "SYNTHETIC objects changed" | Hidden in production. Empty state: "No identity source connected yet." Connector options appear here once real connectors exist (Phase 23); no future-feature text is shown |
| Empty pages | Assume fixture data exists | Each data page shows a clear empty state that points to Integrations when no identities exist |

**Kept, because they are real features and not fakes:**
- The **what-if impact simulation** that precedes change approval.
- **Sandbox-only execution**: nothing writes to a real directory until a write connector is separately approved.
- **Labs**, labelled "Training lab" and isolated as today.

## First organization and first admin

`python scripts/manage.py init-organization --name "<Org name>" --admin-email <email>`:
- Requires the migration URL and refuses if any organization already exists. To add more organizations, pass `--allow-additional` explicitly.
- Creates the organization and one `PRODUCTION`-kind environment, named "Production" by default.
- Creates the first admin's **org_admin** invite through the Phase 21 invite table. It is ACTIVE without a second approver: the first admin has nobody to approve them. This is recorded as an operator bootstrap in the audit log, with the reason.
- Prints the one-time invite **path** (`/invite/<token>`) and nothing else secret. The operator joins it to `APP_ORIGIN`.
- Writes audit events `organization.initialized` and `invite.created`.

## Server-provided display context

`GET /api/v1/session` and `GET /organizations/{org}/overview` gain `deployment: {mode: "development" | "production"}`. The shell renders the development-only labels and controls only when `mode == "development"`, so production builds never show "synthetic" wording. The flag is display-only: the server enforces every restriction on its own.

## Security

- **Defense in depth.** Seed routes check the mode server-side, not just in the UI. The negative tests call them directly.
- **No shipped credentials.** The first admin registers their own password and TOTP through the invite flow.
- **THREAT_MODEL.md row:** production must not expose synthetic seeding or mock connectors. The risk is that demo data becomes mixed with real data.

## Tests

1. A production-mode app (`DEVELOPMENT=false`, Secure cookies, HTTPS origin) returns 404 for both seed routes, even for an org_admin with `sandbox:seed`.
2. A production-mode app refuses to create `mock_entra` and `mock_okta` connectors (422).
3. `session` and `overview` report `deployment.mode`.
4. `init-organization` creates exactly one organization, one environment and one active org_admin invite. It refuses a second run, and `--allow-additional` permits it. The invite redeems through the existing callback test helper.
5. `bootstrap` refuses when `DEVELOPMENT=false`.
6. The web build contains no `nav-planned` or "is planned" strings (a grep test in the Playwright setup or a small node check). In production mode, the E2E shell shows no "synthetic" text.
7. The full existing suite passes unchanged in development mode.

## Out of scope

Real connectors (Phase 23), AI providers (Phase 24), server provisioning, DNS, TLS issuance and production Keycloak (Phase 25), and removing Contoso from tests or labs.
