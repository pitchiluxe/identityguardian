-- Phase 14: versioned policy-as-code with tests, simulation and independent approval.
CREATE TABLE policies (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 name text NOT NULL, created_by uuid NOT NULL REFERENCES users, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
CREATE TABLE policy_versions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, policy_id uuid NOT NULL, version integer NOT NULL,
 definition jsonb NOT NULL, definition_digest text NOT NULL,
 status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','TESTED','TEST_FAILED','SIMULATED',
   'APPROVED','REJECTED','ACTIVE','SUPERSEDED')),
 test_results jsonb, simulation jsonb, approval_digest text, graph_version text,
 proposed_by uuid NOT NULL REFERENCES users, approved_by uuid REFERENCES users, approved_at timestamptz,
 activated_by uuid REFERENCES users, activated_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (approved_by IS NULL OR approved_by <> proposed_by),
 UNIQUE (organization_id, policy_id, version),
 FOREIGN KEY (organization_id, policy_id) REFERENCES policies(organization_id, id)
);
CREATE UNIQUE INDEX one_active_policy_version ON policy_versions(organization_id, policy_id) WHERE status='ACTIVE';
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['policies','policy_versions'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())',t);
 END LOOP;
END $$;
GRANT SELECT, INSERT ON policies, policy_versions TO guardian_app;
GRANT UPDATE(status, test_results, simulation, approval_digest, graph_version, approved_by, approved_at,
 activated_by, activated_at) ON policy_versions TO guardian_app;
GRANT SELECT ON policies, policy_versions TO guardian_worker;
