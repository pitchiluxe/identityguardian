# Connector architecture

Working integration: **Microsoft Entra ID (read-only)**, see below. Development and labs also use sandbox/mock providers. Future targets: Active Directory, Okta, AWS IAM, Google Workspace, GitHub, ServiceNow, Slack, HRIS, PAM and SaaS.

Contract: discover capabilities; read entities/relationships with cursor; return provenance/coverage; validate proposal; apply exact approved operation if supported; read back result; compensate only where supported. Capabilities state read/write types, permission semantics, native TTL, idempotency and reversibility. UI reflects actual capability and health.

Ingestion stages observations → validates IDs/types/scope → computes diff → atomically commits records/history/audit → advances cursor. Partial/failed sync never deletes missing objects. Only complete authoritative coverage permits absence reconciliation; preserve tombstones/history. Replay is idempotent by source ID/version/digest. Show last successful sync and coverage gaps.

Sandbox adapters simulate memberships, roles, tickets, contextual policies and JIT expiry. SAML/OIDC/SCIM/MFA labs are protocol simulations, not actual federation or authentication protection.

Real adapters require least-privilege scopes, encrypted secret references, endpoint allowlists, bounded retries, source rate limits, signed webhook checks where supported and independent security review. Read-only pilots precede writes. Phase 0 approval does not activate production connectivity.

## Microsoft Entra ID (read-only, Phase 23)

Implemented. The kind is `entra`, using Microsoft Graph v1.0 with client credentials. It reads users, groups, direct group members (including nested groups), activated directory roles and their members, and enterprise apps (up to 200) with their user assignments. Group-to-app assignments are counted but not represented. It needs these Microsoft Graph **application** permissions with admin consent: `User.Read.All`, `Group.Read.All`, `Directory.Read.All`, `Application.Read.All` and `RoleManagement.Read.Directory`. It never writes. One Entra tenant per environment. If the 200-app cap is reached, the run is recorded as **partial** coverage, so nothing is closed by absence. Okta (real) is planned as a separate phase.

**Known limitations (deferred):**
- Relationships and identities read from Entra start at a fixed baseline date (2024-01-01), not when they were first seen. **Time-machine views of Entra data before the first sync are not trustworthy.**
- A user deleted in Entra is not marked deleted. Their access relationships close on the next complete sync, but the identity still shows as active.
- The enterprise-app filter (`tags/any(t:t eq 'WindowsAzureActiveDirectoryIntegratedApp')`) has not been verified against a live tenant.
