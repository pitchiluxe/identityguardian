-- Phase 11: joiner baselines, lifecycle workflows and account-disable proposals.
CREATE TABLE jml_baselines (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 department text NOT NULL, groups text[] NOT NULL, version integer NOT NULL,
 status text NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED','APPROVED','SUPERSEDED','REJECTED')),
 justification text NOT NULL CHECK (length(justification) >= 8),
 proposed_by uuid NOT NULL REFERENCES users, approved_by uuid REFERENCES users,
 approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (approved_by IS NULL OR approved_by <> proposed_by),
 UNIQUE (organization_id, environment_id, department, version),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
CREATE UNIQUE INDEX one_approved_baseline ON jml_baselines(organization_id, environment_id, department)
 WHERE status = 'APPROVED';

CREATE TABLE lifecycle_workflows (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('join','move','leave')), identity_node uuid NOT NULL,
 event_id uuid NOT NULL, plan jsonb NOT NULL, change_request_ids uuid[] NOT NULL,
 created_by uuid NOT NULL REFERENCES users, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, event_id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

ALTER TABLE change_requests DROP CONSTRAINT change_requests_kind_check;
ALTER TABLE change_requests ADD CONSTRAINT change_requests_kind_check
 CHECK (kind IN ('remove_relationship','add_relationship','jit_grant','rotate_credential','disable_account'));
ALTER TABLE change_requests DROP CONSTRAINT change_requests_origin_check;
ALTER TABLE change_requests ADD CONSTRAINT change_requests_origin_check
 CHECK (origin IN ('manual','review','jit','lifecycle','policy','lab'));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['jml_baselines','lifecycle_workflows'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())',t);
 END LOOP;
END $$;
GRANT SELECT, INSERT ON jml_baselines, lifecycle_workflows TO guardian_app;
GRANT UPDATE(status, approved_by, approved_at) ON jml_baselines TO guardian_app;
