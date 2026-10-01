-- Phase 8: independent approval, controlled sandbox execution, JIT expiry and reconciliation.

CREATE TABLE approvals (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, change_request_id uuid NOT NULL,
 approver_id uuid NOT NULL REFERENCES users, decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT')),
 digest text NOT NULL, justification text NOT NULL CHECK (length(justification) >= 8),
 auth_time double precision NOT NULL, amr text[] NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, change_request_id) REFERENCES change_requests(organization_id, id)
);

CREATE TABLE executions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, change_request_id uuid NOT NULL,
 approval_id uuid NOT NULL, executor_id uuid NOT NULL REFERENCES users, digest text NOT NULL,
 status text NOT NULL CHECK (status IN ('QUEUED','EXECUTING','SUCCEEDED','FAILED','PARTIAL',
   'RECONCILIATION_REQUIRED','STALE','EXPIRED')),
 attempts integer NOT NULL DEFAULT 0, connector_result jsonb NOT NULL DEFAULT '{}',
 readback jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, change_request_id),  -- one execution per approved request (idempotency)
 FOREIGN KEY (organization_id, change_request_id) REFERENCES change_requests(organization_id, id),
 FOREIGN KEY (organization_id, approval_id) REFERENCES approvals(organization_id, id)
);

CREATE TABLE jit_grants (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 change_request_id uuid NOT NULL, source_object_id text NOT NULL,
 granted_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 status text NOT NULL CHECK (status IN ('ACTIVE','EXPIRED','REVOKE_PENDING')),
 revoked_at timestamptz, attempts integer NOT NULL DEFAULT 0, last_error text,
 CHECK (expires_at > granted_at AND expires_at <= granted_at + interval '8 hours'),
 UNIQUE (organization_id, change_request_id),
 FOREIGN KEY (organization_id, change_request_id) REFERENCES change_requests(organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

-- Sandbox connector fault injection (LAB/SANDBOX only) to exercise failure and reconciliation.
CREATE TABLE sandbox_faults (
 organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 operation text NOT NULL CHECK (operation IN ('remove_relationship','add_relationship')),
 mode text NOT NULL CHECK (mode IN ('fail_before_write','timeout_after_write')),
 remaining integer NOT NULL DEFAULT 1,
 PRIMARY KEY (organization_id, environment_id, operation),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

ALTER TABLE outbox DROP CONSTRAINT outbox_event_type_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_event_type_check
 CHECK (event_type IN ('role_change_recorded','change_execution_requested'));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['approvals','executions','jit_grants','sandbox_faults'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())',t);
 END LOOP;
END $$;

-- Minimal cross-tenant work discovery for the worker: organization IDs only.
CREATE FUNCTION pending_work_organizations() RETURNS SETOF uuid
LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT organization_id FROM outbox WHERE processed_at IS NULL
 UNION SELECT organization_id FROM jit_grants WHERE status IN ('ACTIVE','REVOKE_PENDING') AND expires_at <= now()
 UNION SELECT organization_id FROM executions WHERE status = 'RECONCILIATION_REQUIRED'
$$;
REVOKE ALL ON FUNCTION pending_work_organizations() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pending_work_organizations() TO guardian_worker;

-- API: proposal/approval/queueing only. It never writes the sandbox source during execution.
GRANT SELECT, INSERT ON approvals, executions TO guardian_app;
GRANT SELECT ON jit_grants TO guardian_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON sandbox_faults TO guardian_app;

-- Worker: executes approved requests against the sandbox connector and ingests the result.
GRANT SELECT ON environments, memberships, users, simulations, approvals, relationships,
 relationship_revisions, twin_nodes, node_revisions, connectors, sync_runs, observations,
 usage_events, usage_coverage, employment_events TO guardian_worker;
GRANT SELECT, UPDATE(status, version, updated_at) ON change_requests TO guardian_worker;
GRANT SELECT, UPDATE(status, attempts, connector_result, readback, error, updated_at) ON executions TO guardian_worker;
GRANT SELECT, INSERT, UPDATE(status, revoked_at, attempts, last_error) ON jit_grants TO guardian_worker;
GRANT SELECT, INSERT, UPDATE(body, version, deleted, updated_at) ON sandbox_objects TO guardian_worker;
GRANT SELECT, UPDATE(remaining) ON sandbox_faults TO guardian_worker;
GRANT INSERT ON audit_events TO guardian_worker;
GRANT INSERT ON observations, twin_nodes, node_revisions, relationships, relationship_revisions,
 usage_events, usage_coverage, employment_events, sync_runs, connectors TO guardian_worker;
GRANT UPDATE(recorded_to) ON node_revisions, relationship_revisions TO guardian_worker;
GRANT UPDATE(status, cursor_to, observed, unchanged, created, updated, tombstoned, rejected, errors,
 finished_at) ON sync_runs TO guardian_worker;
GRANT USAGE ON SEQUENCE sandbox_version_seq TO guardian_worker;
