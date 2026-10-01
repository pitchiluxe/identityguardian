-- Phase 7: immutable what-if simulations bound to exact versions.
CREATE TABLE simulations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 change_request_id uuid, operations jsonb NOT NULL, base_graph_version text NOT NULL,
 source_versions jsonb NOT NULL, policy_version text NOT NULL, parameters jsonb NOT NULL,
 result jsonb NOT NULL, digest text NOT NULL, created_by uuid NOT NULL REFERENCES users,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id),
 FOREIGN KEY (organization_id, change_request_id) REFERENCES change_requests(organization_id, id)
);
ALTER TABLE change_requests ADD COLUMN simulation_id uuid, ADD COLUMN digest text,
 ADD FOREIGN KEY (organization_id, simulation_id) REFERENCES simulations(organization_id, id);

ALTER TABLE simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON simulations USING (organization_id = app_org())
 WITH CHECK (organization_id = app_org());
CREATE INDEX simulations_change ON simulations(organization_id, change_request_id, created_at DESC);

GRANT SELECT, INSERT ON simulations TO guardian_app;
GRANT UPDATE(simulation_id, digest) ON change_requests TO guardian_app;
