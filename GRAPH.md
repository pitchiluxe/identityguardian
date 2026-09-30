# Identity graph semantics

Adapter operations: neighbors, paths, effective_access, simulate. Inputs include verified actor, organization, environment, resource scope, time/snapshot and limits. Outputs include nodes/edges, evidence IDs, timestamps, rule/graph versions and completeness.

| Relationship | Endpoints / meaning |
|---|---|
| USER_MEMBER_OF_GROUP | identity/account → group; active grant |
| GROUP_INHERITS_GROUP | group → group; nesting |
| GROUP_HAS_ROLE / USER_HAS_ROLE | group/identity → role; scoped grant |
| ROLE_HAS_PERMISSION | role → permission |
| PERMISSION_ACCESS_RESOURCE | permission → resource; scoped action |
| USER_OWNS_SERVICE_ACCOUNT | identity → machine; ownership does not imply impersonation |
| SERVICE_ACCOUNT_ACCESS_APPLICATION | machine → application; observed grant |
| AI_AGENT_USES_TOOL / AI_AGENT_ACCESS_DATA | agent → tool/resource; explicit grant |
| DEVICE_USED_BY_USER | device → identity; context |
| APPLICATION_TRUSTS_IDP | application → provider; trust alone is not access |
| IDENTITY_IN_DEPARTMENT / REPORTS_TO | identity → department/identity; context |
| CAN_RESET_CREDENTIAL / CAN_ASSUME_ROLE | permission/identity → account/role; conditional exposure |
| RESOURCE_DEPENDS_ON | application/resource → resource; operational dependency |

Validate endpoint types. Classify edges as grant, context, exposure or dependency; generic reachability is not effective permission.

Traverse active grants with cycle detection and preserve distinct lineages. Evaluate time, resource scopes, conditions and explicit denies using source-specific supported semantics. Unsupported conditions return CONDITIONAL/UNKNOWN, never ALLOW. Return proven allow, deny, conditional and unknown separately. Removing one route must retain alternative routes.

Explanations show entitlement, source, approver if known, dates, expiration, last-use coverage, ticket, justification and risk indicators. No observed usage is not proof of never-used access. Peer comparisons show sample size.

Default bounds: depth 8, 100 paths, 10,000 expanded nodes, 2 seconds. Per-path visited sets preserve alternative simple paths and stop cycles. Any bound returns complete=false with reason and longer-job option. Truncated traversal never proves absence or “every path.” Unauthorized nodes cannot leak through counts/citations.

Exposure rules require evidence for intermediary rights and prerequisites such as reset scope, MFA and delegation. Show transitions, destination, factors and defensive controls. Potential exposure is not successful exploitation. No exploits, credential harvesting or external scans.

Simulation overlays changes on an immutable snapshot, recomputes access and dependency closure, and reports identities, applications, resources, workflows, possible lockouts, residual routes, reduced privileges and unknowns. It cannot mutate production. Security improvement means changes in explained findings, not invented probability. Digest binds operation, scope, target/source versions, snapshot, parameters, policy version and expiry; relevant changes invalidate approval.

```mermaid
flowchart LR
  E[Erick · IT Support] -->|legacy grant / TKT-1042| F[Finance-Legacy]
  F -->|nested group| O[ERP-Operators]
  O -->|role| R[ERP Application Administrator]
  R -->|permission| P[Manage payroll configuration]
  P -->|resource scope| D[Payroll · SIMULATED]
```

Department is context only. Current HelpDesk-L2 reset privileges have a separate bounded scope; do not invent privileged reset targets. Test removal with an alternate payroll route to prove residual access is reported. Historical graph follows DATABASE.md.
