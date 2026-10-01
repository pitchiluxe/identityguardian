-- Phase 2: identity digital twin, sandbox source, immutable observations and bitemporal history.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Simulated external source system. Written only by explicit synthetic seeding and sandbox execution.
CREATE TABLE sandbox_objects (
 organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 object_id text NOT NULL, object_type text NOT NULL
   CHECK (object_type IN ('node','relationship','usage','coverage','employment_event')),
 body jsonb NOT NULL, version bigint NOT NULL, deleted boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (organization_id, environment_id, object_id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);
CREATE SEQUENCE sandbox_version_seq;
GRANT USAGE ON SEQUENCE sandbox_version_seq TO guardian_app;

CREATE TABLE connectors (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('sandbox')), name text NOT NULL,
 capabilities jsonb NOT NULL, authoritative boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, environment_id, kind),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

CREATE TABLE sync_runs (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 connector_id uuid NOT NULL, actor_id uuid REFERENCES users,
 status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED')),
 coverage text NOT NULL CHECK (coverage IN ('complete_authoritative','partial')),
 cursor_from bigint NOT NULL DEFAULT 0, cursor_to bigint,
 observed integer NOT NULL DEFAULT 0, unchanged integer NOT NULL DEFAULT 0,
 created integer NOT NULL DEFAULT 0, updated integer NOT NULL DEFAULT 0,
 tombstoned integer NOT NULL DEFAULT 0, rejected integer NOT NULL DEFAULT 0,
 errors jsonb NOT NULL DEFAULT '[]', started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 FOREIGN KEY (organization_id, connector_id) REFERENCES connectors(organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

-- Immutable sanitized evidence. Replay of identical content is a no-op.
CREATE TABLE observations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 source text NOT NULL, sync_run_id uuid REFERENCES sync_runs, object_type text NOT NULL,
 external_id text NOT NULL, source_version bigint NOT NULL, payload jsonb NOT NULL,
 digest text NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, environment_id, source, external_id, digest),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

CREATE TABLE twin_nodes (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 source text NOT NULL, external_id text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('identity','account','group','role','permission','resource',
   'application','device','department','tool','provider','credential')),
 subtype text NOT NULL DEFAULT '', name text NOT NULL,
 first_observation_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, environment_id, source, external_id),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id),
 FOREIGN KEY (organization_id, first_observation_id) REFERENCES observations(organization_id, id)
);

-- Attribute history: valid_* is source-effective time, recorded_* is platform knowledge time.
CREATE TABLE node_revisions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, node_id uuid NOT NULL,
 name text NOT NULL, status text NOT NULL, attributes jsonb NOT NULL,
 valid_from timestamptz NOT NULL, valid_to timestamptz,
 recorded_from timestamptz NOT NULL DEFAULT now(), recorded_to timestamptz,
 observation_id uuid NOT NULL,
 CHECK (valid_to IS NULL OR valid_to > valid_from),
 FOREIGN KEY (organization_id, node_id) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, observation_id) REFERENCES observations(organization_id, id),
 EXCLUDE USING gist (node_id WITH =,
   tstzrange(valid_from, valid_to) WITH &&) WHERE (recorded_to IS NULL)
);

CREATE TABLE relationships (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 source text NOT NULL, external_id text NOT NULL, type text NOT NULL,
 classification text NOT NULL CHECK (classification IN ('grant','context','exposure','dependency','deny')),
 from_node uuid NOT NULL, to_node uuid NOT NULL,
 UNIQUE (organization_id, environment_id, source, external_id),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, from_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, to_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

CREATE TABLE relationship_revisions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, relationship_id uuid NOT NULL,
 attributes jsonb NOT NULL, valid_from timestamptz NOT NULL, valid_to timestamptz,
 end_inferred boolean NOT NULL DEFAULT false,
 recorded_from timestamptz NOT NULL DEFAULT now(), recorded_to timestamptz,
 observation_id uuid NOT NULL,
 CHECK (valid_to IS NULL OR valid_to > valid_from),
 FOREIGN KEY (organization_id, relationship_id) REFERENCES relationships(organization_id, id),
 FOREIGN KEY (organization_id, observation_id) REFERENCES observations(organization_id, id),
 EXCLUDE USING gist (relationship_id WITH =,
   tstzrange(valid_from, valid_to) WITH &&) WHERE (recorded_to IS NULL)
);

CREATE TABLE usage_events (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 external_id text NOT NULL, identity_node uuid NOT NULL, target_node uuid NOT NULL,
 occurred_at timestamptz NOT NULL, observation_id uuid NOT NULL,
 UNIQUE (organization_id, environment_id, external_id),
 FOREIGN KEY (organization_id, identity_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, target_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, observation_id) REFERENCES observations(organization_id, id)
);

-- Telemetry coverage windows. Outside them usage is UNKNOWN, not absent.
CREATE TABLE usage_coverage (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 external_id text NOT NULL, target_node uuid NOT NULL,
 covered_from timestamptz NOT NULL, covered_to timestamptz NOT NULL,
 completeness text NOT NULL CHECK (completeness IN ('complete','partial')),
 observation_id uuid NOT NULL,
 CHECK (covered_to > covered_from),
 UNIQUE (organization_id, environment_id, external_id),
 FOREIGN KEY (organization_id, target_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, observation_id) REFERENCES observations(organization_id, id)
);

CREATE TABLE employment_events (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 external_id text NOT NULL, identity_node uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('join','move','leave')),
 effective_at timestamptz NOT NULL, details jsonb NOT NULL, observation_id uuid NOT NULL,
 UNIQUE (organization_id, environment_id, external_id),
 FOREIGN KEY (organization_id, identity_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, observation_id) REFERENCES observations(organization_id, id)
);

CREATE INDEX rel_from ON relationships(organization_id, environment_id, from_node, type);
CREATE INDEX rel_to ON relationships(organization_id, environment_id, to_node, type);
CREATE INDEX relrev_current ON relationship_revisions(relationship_id) WHERE recorded_to IS NULL;
CREATE INDEX relrev_time ON relationship_revisions(organization_id, recorded_from, recorded_to);
CREATE INDEX noderev_current ON node_revisions(node_id) WHERE recorded_to IS NULL;
CREATE INDEX node_kind ON twin_nodes(organization_id, environment_id, kind, name);
CREATE INDEX usage_lookup ON usage_events(organization_id, identity_node, target_node, occurred_at);
CREATE INDEX observation_ext ON observations(organization_id, environment_id, source, external_id);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['sandbox_objects','connectors','sync_runs','observations','twin_nodes',
   'node_revisions','relationships','relationship_revisions','usage_events','usage_coverage',
   'employment_events'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id::text = current_setting(''app.org'',true)) WITH CHECK (organization_id::text = current_setting(''app.org'',true))',t);
 END LOOP;
END $$;

GRANT SELECT ON sandbox_objects, connectors, sync_runs, observations, twin_nodes, node_revisions,
 relationships, relationship_revisions, usage_events, usage_coverage, employment_events TO guardian_app;
-- Observations, nodes and relationships are append-only for the runtime role; history closes
-- knowledge intervals rather than updating or deleting facts.
GRANT INSERT ON observations, twin_nodes, node_revisions, relationships, relationship_revisions,
 usage_events, usage_coverage, employment_events, sync_runs, connectors, sandbox_objects TO guardian_app;
GRANT UPDATE(recorded_to) ON node_revisions, relationship_revisions TO guardian_app;
GRANT UPDATE(status, cursor_to, observed, unchanged, created, updated, tombstoned, rejected, errors,
 finished_at) ON sync_runs TO guardian_app;
GRANT UPDATE(body, version, deleted, updated_at) ON sandbox_objects TO guardian_app;
