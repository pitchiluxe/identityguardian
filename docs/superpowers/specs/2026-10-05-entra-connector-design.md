# Read-only Microsoft Entra ID connector — design (Phase 23)

2026-10-05 · Design approved in chat by the user ("approve") · Purpose: portfolio demonstration against the user's own free Entra test tenant

## Intent

IdentityGuardian reads a **real** Microsoft Entra ID tenant, **read-only**, and every existing analysis page works on that data. The tenant is the user's own free Azure test tenant with fictional users. Okta is a later phase.

## Decisions

| Topic | Decision |
|---|---|
| Auth | OAuth 2.0 client credentials: `POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`, scope `https://graph.microsoft.com/.default`. The token is cached in memory for one job only |
| Read-only | Only `GET https://graph.microsoft.com/v1.0/...` after the token request. Endpoints are fixed constants and never user input (no SSRF). `apply`/`read_back` stay unsupported |
| Permissions (user grants in Azure) | Application permissions: `User.Read.All`, `Group.Read.All`, `Directory.Read.All`, `Application.Read.All`, `RoleManagement.Read.Directory` |
| Config | `tenant_id` and `client_id` (GUIDs) in `connectors.config`. `client_secret` sealed into `connectors.secret_envelope` (context `connector:<id>`, rotation-aware). The secret is never returned |
| Where allowed | Kind `entra` is allowed in **SANDBOX and PRODUCTION** environments, in development **and** production mode. It is **not** allowed in LAB environments, which are training-only |
| Reads | users, groups, direct group members (users and groups), activated directory roles and their members, and enterprise apps (service principals, capped at 200) with their app-role assignments to users |
| Mapping | user → `identity` (subtype `guest` when `userType == "Guest"`, else `employee`) + `account` + `HAS_ACCOUNT`. Group → `group`. User member → `USER_MEMBER_OF_GROUP`. Group member → `GROUP_INHERITS_GROUP` (member group → containing group). Directory role → `role`, with `USER_HAS_ROLE` / `GROUP_HAS_ROLE`. Service principal → `application`; user assignment → `SERVICE_ACCOUNT_ACCESS_APPLICATION`. Group-to-app assignments are not representable in the graph rules: they are counted in provenance and skipped |
| Paging | A staged cursor (base64 JSON: stage, Graph `@odata.nextLink`, remaining queue of group/role/app IDs). Each `read()` performs one Graph request. The runner's existing resume, retry and coverage logic applies, and a complete read is authoritative for this tenant's scope |
| Errors | 429 → `RateLimited` (the runner backs off). 401/403 → `ConnectorUnavailable("Microsoft rejected the app credentials or permissions")`. Other errors → `ConnectorUnavailable("Microsoft Graph unavailable")`. Never echo response bodies or the secret |
| Attributes | `upn`, `department`, `title`, `user_type`, `enabled`; object IDs are prefixed `entra:`. **No** `synthetic` flag: this is real tenant data |

## UI

Integrations shows an **Identity sources** panel in every mode with **Connect Microsoft Entra ID**: Tenant ID, Client ID and Client secret (a password field, cleared after saving). Connected sources are listed with health, last run, and **Sync now** / **Resume** buttons. The mock registry stays development-only.

## Security

New THREAT_MODEL rows:
- **Client secret:** envelope-encrypted, never returned or logged, rotated by `rotate-master-key`.
- **Outbound:** fixed Microsoft hosts, GET-only Graph.
- **Malicious directory content:** names are treated as data, rendered escaped, and bounded by ingest validation.
- **Tenant data sensitivity:** real personal data in the database is covered by U6/U7 and backups.

## Tests (mocked HTTP transport; no real Microsoft calls)

1. Only the token POST and Graph GETs are sent: the transport asserts method and host.
2. Paging across users, groups, members, roles and apps produces the expected canonical objects, including a nested group and a role.
3. 429 → RateLimited; 401 → the fixed message, with the secret absent from all exceptions and logs.
4. Registration: the secret is sealed and absent from responses and audit; LAB is refused; the kind is allowed in production mode; viewers cannot create it; another tenant gets 404.
5. A worker sync with the mocked transport ingests the tenant, and the access pages see the identities.
6. A browser test: the Integrations page shows the Entra form in both modes, and the secret field is cleared after saving (submission is mocked server-side by a fake connector).

## Out of scope

Writing to Entra, sign-in logs (need P1), PIM eligibility, delta queries, Okta, and certificate credentials (a recommended later improvement over client secrets).
