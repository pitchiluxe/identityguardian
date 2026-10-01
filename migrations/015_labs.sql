-- Phase 15: isolated learner-only lab attempts on cloned SYNTHETIC scenarios.
ALTER TABLE environments ADD COLUMN lab_learner uuid REFERENCES users, ADD COLUMN lab_attempt uuid;

CREATE TABLE lab_attempts (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 lab_id text NOT NULL, lab_version text NOT NULL, learner_id uuid NOT NULL REFERENCES users,
 status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUBMITTED')),
 started_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz,
 hints_used jsonb NOT NULL DEFAULT '[]', solution_viewed boolean NOT NULL DEFAULT false,
 resets integer NOT NULL DEFAULT 0, result jsonb,
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
CREATE TABLE lab_actions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, attempt_id uuid NOT NULL,
 action jsonb NOT NULL, outcome text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id, attempt_id) REFERENCES lab_attempts(organization_id, id)
);
CREATE INDEX lab_attempts_learner ON lab_attempts(organization_id, learner_id, started_at DESC);
CREATE INDEX lab_actions_attempt ON lab_actions(organization_id, attempt_id, created_at);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['lab_attempts','lab_actions'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())',t);
 END LOOP;
END $$;
-- The runtime role may create LAB environments for attempts (RLS keeps them in the caller's org).
-- RESTRICTIVE: combined with tenant_scope by AND, so runtime inserts can only ever be LAB.
CREATE POLICY lab_insert ON environments AS RESTRICTIVE FOR INSERT WITH CHECK (kind = 'LAB' AND lab_learner IS NOT NULL);
GRANT INSERT ON environments TO guardian_app;
GRANT SELECT, INSERT ON lab_attempts, lab_actions TO guardian_app;
GRANT UPDATE(status, submitted_at, hints_used, solution_viewed, resets, result) ON lab_attempts TO guardian_app;
