-- Phase 12: checksummed historical snapshots. They accelerate and verify replay; evidence stays
-- in observations and revisions, which remain the source of truth.
CREATE TABLE historical_snapshots (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 effective_at timestamptz NOT NULL, known_at timestamptz NOT NULL, graph_version text NOT NULL,
 node_count integer NOT NULL, edge_count integer NOT NULL, checksum text NOT NULL,
 coverage jsonb NOT NULL, created_by uuid NOT NULL REFERENCES users,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (known_at <= created_at + interval '1 minute'),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
ALTER TABLE historical_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE historical_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON historical_snapshots USING (organization_id = app_org())
 WITH CHECK (organization_id = app_org());
GRANT SELECT, INSERT ON historical_snapshots TO guardian_app;
