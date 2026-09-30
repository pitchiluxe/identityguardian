# Connector architecture

No working integrations yet. Initial implementations are sandbox/mock as requested. Future targets: Active Directory, Entra ID, Okta, AWS IAM, Google Workspace, GitHub, ServiceNow, Slack, HRIS, PAM and SaaS.

Contract: discover capabilities; read entities/relationships with cursor; return provenance/coverage; validate proposal; apply exact approved operation if supported; read back result; compensate only where supported. Capabilities state read/write types, permission semantics, native TTL, idempotency and reversibility. UI reflects actual capability and health.

Ingestion stages observations → validates IDs/types/scope → computes diff → atomically commits records/history/audit → advances cursor. Partial/failed sync never deletes missing objects. Only complete authoritative coverage permits absence reconciliation; preserve tombstones/history. Replay is idempotent by source ID/version/digest. Show last successful sync and coverage gaps.

Sandbox adapters simulate memberships, roles, tickets, contextual policies and JIT expiry. SAML/OIDC/SCIM/MFA labs are protocol simulations, not actual federation or authentication protection.

Real adapters require least-privilege scopes, encrypted secret references, endpoint allowlists, bounded retries, source rate limits, signed webhook checks where supported and independent security review. Read-only pilots precede writes. Phase 0 approval does not activate production connectivity.
