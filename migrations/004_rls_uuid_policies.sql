-- Recreate tenant policies so the organization predicate is index-usable.
-- `organization_id::text = setting` forced a cast on every row; comparing to a uuid lets the
-- planner use the leading organization_id column of composite indexes. Semantics are unchanged:
-- a missing or empty setting yields NULL, which matches no rows.
CREATE FUNCTION app_org() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.org', true), '')::uuid $$;
GRANT EXECUTE ON FUNCTION app_org() TO guardian_app, guardian_worker;

DROP POLICY organization_scope ON organizations;
CREATE POLICY organization_scope ON organizations USING (id = app_org());

DROP POLICY receipt_scope ON event_receipts;
CREATE POLICY receipt_scope ON event_receipts USING (organization_id = app_org())
 WITH CHECK (organization_id = app_org());

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['environments','memberships','audit_events','role_requests','outbox',
   'sandbox_objects','connectors','sync_runs','observations','twin_nodes','node_revisions',
   'relationships','relationship_revisions','usage_events','usage_coverage','employment_events'] LOOP
  EXECUTE format('DROP POLICY tenant_scope ON %I', t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())', t);
 END LOOP;
END $$;

CREATE INDEX relrev_org_rel ON relationship_revisions(organization_id, relationship_id) WHERE recorded_to IS NULL;
CREATE INDEX noderev_org_node ON node_revisions(organization_id, node_id);
CREATE INDEX twin_nodes_env ON twin_nodes(organization_id, environment_id, source, external_id);
CREATE INDEX usage_cov_target ON usage_coverage(organization_id, target_node);
CREATE INDEX employment_env ON employment_events(organization_id, environment_id, effective_at);
