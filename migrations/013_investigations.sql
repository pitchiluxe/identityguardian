-- Phase 13: grounded investigations. Model output is stored separately from immutable evidence.
CREATE TABLE investigations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 user_id uuid NOT NULL REFERENCES users, question text NOT NULL CHECK (length(question) <= 500),
 intent jsonb NOT NULL, bundle_digest text NOT NULL, bundle jsonb NOT NULL,
 status text NOT NULL CHECK (status IN ('VALIDATED','PARTIAL','FALLBACK','AI_UNAVAILABLE','CLARIFICATION','INSUFFICIENT')),
 model text, model_version text, latency_ms integer, claims jsonb NOT NULL, rejected jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
ALTER TABLE investigations ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON investigations USING (organization_id = app_org())
 WITH CHECK (organization_id = app_org());
CREATE INDEX investigations_user ON investigations(organization_id, user_id, created_at DESC);
GRANT SELECT, INSERT ON investigations TO guardian_app;
