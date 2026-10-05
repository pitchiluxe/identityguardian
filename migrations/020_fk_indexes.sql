-- Phase 19: indexes supporting foreign-key checks. Without them, deleting or purging referenced
-- rows (retention, administrative cleanup) scans the referencing tables once per row.
CREATE INDEX IF NOT EXISTS relrev_relationship ON relationship_revisions(organization_id, relationship_id);
CREATE INDEX IF NOT EXISTS relrev_observation ON relationship_revisions(organization_id, observation_id);
CREATE INDEX IF NOT EXISTS noderev_observation ON node_revisions(organization_id, observation_id);
CREATE INDEX IF NOT EXISTS nodes_first_observation ON twin_nodes(organization_id, first_observation_id);
CREATE INDEX IF NOT EXISTS rel_from_node ON relationships(organization_id, from_node);
CREATE INDEX IF NOT EXISTS rel_to_node ON relationships(organization_id, to_node);
CREATE INDEX IF NOT EXISTS review_items_relationship ON review_items(organization_id, relationship_id);
CREATE INDEX IF NOT EXISTS review_items_identity ON review_items(organization_id, identity_node);
CREATE INDEX IF NOT EXISTS usage_target ON usage_events(organization_id, target_node);
CREATE INDEX IF NOT EXISTS usage_observation ON usage_events(organization_id, observation_id);
CREATE INDEX IF NOT EXISTS coverage_observation ON usage_coverage(organization_id, observation_id);
CREATE INDEX IF NOT EXISTS employment_identity ON employment_events(organization_id, identity_node);
CREATE INDEX IF NOT EXISTS employment_observation ON employment_events(organization_id, observation_id);
