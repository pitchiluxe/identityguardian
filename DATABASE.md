# Logical database model

Proposed schema, not executable migrations. UUID keys, UTC timestamps and half-open intervals `[from,to)`.

Tenant tables carry organization_id, environment_id, id, created_at and version. Composite unique keys and foreign keys enforce matching tenant/environment. Environment kind: LAB, SANDBOX, PRODUCTION. Platform User is a login principal; observed Identity is a twin entity. Observed IAM roles never grant platform roles.

| Entities | Fields and relationships |
|---|---|
| Organization, Environment | name, kind, status; environment belongs to organization |
| User, OrganizationMembership, PlatformRole, RolePermission | issuer+subject unique; active membership, scoped capabilities |
| Session | hashed opaque token, user, expiry, activity, authentication time/assurance |
| Identity | employee/contractor/guest/admin/machine/agent kind, name, status, department, manager identity, employment dates |
| Account | identity, connector, external ID, enabled, last sign-in; source/external ID unique |
| Department, BusinessUnit | parent, manager identity, name; hierarchy validation |
| Group, Role, Permission | external ID, name, action and resource scope |
| Application, Resource | owner, sensitivity, type, parent; database/server/cloud are resource kinds |
| Device, AuthenticationMethod | identity/account, posture and assurance metadata; no authentication secrets |
| MachineIdentity, ServiceAccount | identity unique, machine kind, owner, purpose, usage, dependencies |
| AIAgent | identity unique, owner, department, purpose, model, maximum privilege, credential scope, expiry; normalized tool/app/API/data allowlists and prohibited data |
| Credential, Certificate | account/machine, encrypted secret reference, fingerprint, creation/rotation/expiry/revocation, public metadata |
| Entitlement | subject, permission, resource, origin, grant/expiry/last-use, ticket, approver, justification, evidence |
| GraphNode, RelationshipRevision | typed entity reference, typed endpoints, conditions, evidence, temporal revisions |
| SourceObservation, EvidenceRecord | source ID, sanitized immutable payload, digest, received/effective times, coverage |
| AccessRequest, Simulation, Approval, Execution | operation, target versions, diff/digest, actor assurance, status, idempotency |
| AccessReview, ReviewItem, ReviewDecision | campaign, reviewer scope, evidence snapshot, recommendation, uncertainty, human decision |
| Policy, PolicyVersion, PolicyTest | immutable schema-versioned rules, exceptions/expiry, test/simulation/approval links |
| RiskFinding, AttackPath | rule version, evidence, graph version, conditions, ordered edge IDs, completeness |
| Incident, Ticket | source IDs, status, sanitized description, identity/resource references |
| EmploymentEvent | identity, join/move/leave, prior/new role, effective time, evidence, workflow |
| AuditEvent | sequence, actor, action, target, sanitized before/after, justification, approval, result, correlation, time, previous hash |
| Lab, LabAttempt, LabStepResult | scenario version, learner, isolated environment, submitted state, rubric, hints, score |
| Connector, Integration, SyncRun, SyncCursor | capability, secret reference, endpoint, health, authoritative scope, cursor |
| HistoricalSnapshot | graph version, effective/knowledge watermarks, coverage, checksum |
| Job, OutboxEvent, ReportArtifact | lease/retries/idempotency; export owner/scope/expiry and snapshot |

Manager is an identity reference. Workload, CI/CD, bot and Kubernetes accounts are machine kinds. Tools, providers and data classifications are typed graph nodes backed by normalized records. Assignment records and computed effective-access results are distinct.

## History

Each relationship revision contains logical ID, revision ID, endpoints/type, valid_from/to (source-effective interval), recorded_from/to (system knowledge interval), observation ID, conditions, confidence and source version. Close recorded intervals and insert revisions transactionally; preserve original evidence. Prevent overlapping effective ranges for one logical relationship within a knowledge-time slice. Late evidence creates a new recorded revision.

`effective_at=t, known_at=now` reconstructs best current knowledge of past access. `effective_at=t, known_at=k` reconstructs what was known at k. Label both. Missing history is UNKNOWN; never project current MFA/membership backward. Snapshots accelerate replay through a checksummed watermark; they are not the sole evidence.

## Constraints and access

Restrict deleting referenced evidence. Enforce unique source/external IDs, positive bounded JIT durations and ordered temporal/grant intervals. Missing owner is allowed and produces a finding. Preserve imported group cycles but traverse safely.

Index scoped source/type and destination/type edges, temporal ranges, evidence IDs, entitlement subject/resource, active approvals, due jobs/leases and audit scope/time/sequence. Partition after measurement.

RLS applies to reads and writes. Use verified transaction-local context; pooling must not leak scope. Runtime role cannot own tables or bypass RLS. Separate migration role. Audit application permissions are insert/read only. Outbox and domain mutation commit together; external confirmation requires reconciliation.

Proposed retention: audit/governance evidence and derived history 365 days; sanitized raw connector data 30 days; lab attempts 90 days. Retain evidence referenced by live decisions or explicitly redact with integrity metadata and visible gaps. Production legal/business requirements may override defaults. Backups follow retention; master keys are separate. Hash chains do not prevent database-administrator rewriting; independent signed checkpoints are a production gate.
