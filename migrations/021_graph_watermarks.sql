-- Phase 19: per-environment change counter that versions the twin for snapshot caching.
-- Maintained by triggers, so every write to nodes, relationships or their revisions changes the
-- version regardless of which code path wrote it. Reading one row replaces aggregating every
-- revision of the environment on each request. Historical (known_at) versions still aggregate.
CREATE TABLE graph_watermarks (
 organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 changes bigint NOT NULL DEFAULT 0,
 PRIMARY KEY (organization_id, environment_id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id) ON DELETE CASCADE
);
ALTER TABLE graph_watermarks ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_watermarks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON graph_watermarks
 USING (organization_id::text = current_setting('app.org', true))
 WITH CHECK (organization_id::text = current_setting('app.org', true));
GRANT SELECT ON graph_watermarks TO guardian_app, guardian_worker;

CREATE FUNCTION graph_touch(org uuid, env uuid) RETURNS void LANGUAGE sql
 SECURITY DEFINER SET search_path=public,pg_temp AS $$
 INSERT INTO graph_watermarks(organization_id, environment_id, changes) VALUES (org, env, 1)
 ON CONFLICT (organization_id, environment_id) DO UPDATE SET changes = graph_watermarks.changes + 1
$$;
REVOKE ALL ON FUNCTION graph_touch(uuid, uuid) FROM PUBLIC;

CREATE FUNCTION graph_touch_direct() RETURNS trigger LANGUAGE plpgsql
 SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE r record := coalesce(NEW, OLD);
BEGIN
  PERFORM graph_touch(r.organization_id, r.environment_id);
  RETURN NULL;
END $$;

CREATE FUNCTION graph_touch_node_revision() RETURNS trigger LANGUAGE plpgsql
 SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE r record := coalesce(NEW, OLD);
BEGIN
  PERFORM graph_touch(n.organization_id, n.environment_id) FROM twin_nodes n WHERE n.id = r.node_id;
  RETURN NULL;
END $$;

CREATE FUNCTION graph_touch_relationship_revision() RETURNS trigger LANGUAGE plpgsql
 SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE r record := coalesce(NEW, OLD);
BEGIN
  PERFORM graph_touch(x.organization_id, x.environment_id) FROM relationships x
   WHERE x.id = r.relationship_id;
  RETURN NULL;
END $$;

CREATE TRIGGER graph_touch AFTER INSERT OR UPDATE OR DELETE ON twin_nodes
 FOR EACH ROW EXECUTE FUNCTION graph_touch_direct();
CREATE TRIGGER graph_touch AFTER INSERT OR UPDATE OR DELETE ON relationships
 FOR EACH ROW EXECUTE FUNCTION graph_touch_direct();
CREATE TRIGGER graph_touch AFTER INSERT OR UPDATE OR DELETE ON node_revisions
 FOR EACH ROW EXECUTE FUNCTION graph_touch_node_revision();
CREATE TRIGGER graph_touch AFTER INSERT OR UPDATE OR DELETE ON relationship_revisions
 FOR EACH ROW EXECUTE FUNCTION graph_touch_relationship_revision();

-- Existing environments start at their current revision count (grouped, one pass per table).
INSERT INTO graph_watermarks(organization_id, environment_id, changes)
SELECT organization_id, environment_id, sum(n) FROM (
 SELECT r.organization_id, r.environment_id, count(*) AS n
  FROM relationship_revisions rr JOIN relationships r ON r.id = rr.relationship_id
  GROUP BY r.organization_id, r.environment_id
 UNION ALL
 SELECT n.organization_id, n.environment_id, count(*)
  FROM node_revisions nr JOIN twin_nodes n ON n.id = nr.node_id
  GROUP BY n.organization_id, n.environment_id
) counts GROUP BY organization_id, environment_id;
