-- Phase 17: authorized, redacted, expiring report artifacts.
CREATE TABLE report_artifacts (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 report_type text NOT NULL, format text NOT NULL CHECK (format IN ('csv','json')),
 redaction text NOT NULL CHECK (redaction IN ('standard','full')),
 created_by uuid NOT NULL REFERENCES users, created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL, snapshot jsonb NOT NULL, row_count integer NOT NULL,
 content text, digest text NOT NULL, downloads integer NOT NULL DEFAULT 0,
 status text NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE','EXPIRED')),
 CHECK (expires_at > created_at AND expires_at <= created_at + interval '7 days'),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
ALTER TABLE report_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_artifacts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON report_artifacts USING (organization_id = app_org()) WITH CHECK (organization_id = app_org());
CREATE INDEX report_expiry ON report_artifacts(status, expires_at);
GRANT SELECT, INSERT ON report_artifacts TO guardian_app;
GRANT UPDATE(downloads) ON report_artifacts TO guardian_app;
GRANT SELECT, UPDATE(content, status) ON report_artifacts TO guardian_worker;

CREATE OR REPLACE FUNCTION pending_work_organizations() RETURNS SETOF uuid
LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT organization_id FROM outbox WHERE processed_at IS NULL
 UNION SELECT organization_id FROM jit_grants WHERE status IN ('ACTIVE','REVOKE_PENDING') AND expires_at <= now()
 UNION SELECT organization_id FROM executions WHERE status = 'RECONCILIATION_REQUIRED'
 UNION SELECT organization_id FROM report_artifacts WHERE status = 'AVAILABLE' AND expires_at <= now()
$$;
