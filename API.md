# Proposed API contract

No endpoints implemented. Version `/api/v1`, typed JSON and generated OpenAPI/client contracts. Actor comes from session, not payload. Validate organization/environment against membership.

| Family | Behavior / capability |
|---|---|
| `/auth/login`, `/auth/callback`, `/auth/logout`, `/session` | OIDC/session; logout POST with CSRF |
| `/organizations/{org}/environments/{env}/identities` | scoped paginated inventory; identity:read |
| `/.../identities/{id}/access` | evidence-backed access; access:read |
| `/.../graph/paths` | bounded typed traversal; graph:read |
| `/.../simulations` | POST immutable overlay; change:simulate |
| `/.../change-requests` | POST canonical proposal; change:propose |
| `/.../change-requests/{id}/approvals` | POST independent approval/digest; change:approve + recent MFA |
| `/.../change-requests/{id}/execute` | POST approved action; change:execute + recent MFA |
| `/.../reviews`, `/.../jit-requests`, `/.../lifecycle` | separate workflow capabilities |
| `/.../history` | effective_at/known_at; history:read |
| `/.../investigations/query` | allowlisted intent; investigation:run |
| `/.../policies` | propose/test/simulate/approve/activate |
| `/.../labs/attempts` | learner-only attempts and validation |
| `/.../reports`, `/.../audit-events`, `/.../connectors` | separate export/audit/integration capabilities |

Ellipsis abbreviates tenant/environment prefix, not literal routes. Reject unknown mutation fields. CSRF, Idempotency-Key and expected version/If-Match protect mutations. Same key/different payload conflicts. Cursor pagination max 100 with stable scoped ordering.

Envelope: data, correlation_id, snapshot_version, evidence_ids, freshness and completeness where relevant. Errors have stable code, safe message, correlation and field errors, never secrets/stacks. 401 unauthenticated; 403 capability denied; 404 missing/inaccessible object without existence leak; 409 stale/invalid transition; 422 validation; 429 throttled; 503 unavailable. Jobs return 202 with authorized status URL; each poll rechecks scope.

Execution references approved request/digest/version, never arbitrary connector command. Pending is not success. Reports authorize both creation and download.
