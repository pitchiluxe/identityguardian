-- Phase 16: connector framework (mock providers first; real adapters require separate approval).
ALTER TABLE connectors DROP CONSTRAINT connectors_kind_check;
ALTER TABLE connectors ADD CONSTRAINT connectors_kind_check CHECK (kind IN ('sandbox','mock_entra','mock_okta'));
ALTER TABLE connectors DROP CONSTRAINT connectors_organization_id_environment_id_kind_key;
ALTER TABLE connectors
 ADD COLUMN config jsonb NOT NULL DEFAULT '{}',
 ADD COLUMN secret_ref text,
 ADD COLUMN secret_envelope jsonb,
 ADD COLUMN health text NOT NULL DEFAULT 'UNKNOWN' CHECK (health IN ('UNKNOWN','HEALTHY','DEGRADED','FAILING')),
 ADD COLUMN last_cursor text,
 ADD COLUMN created_by uuid REFERENCES users;
CREATE UNIQUE INDEX connectors_name ON connectors(organization_id, environment_id, name);

ALTER TABLE sync_runs ADD COLUMN cursor_token text, ADD COLUMN pages integer NOT NULL DEFAULT 0,
 ADD COLUMN retries integer NOT NULL DEFAULT 0;

ALTER TABLE outbox DROP CONSTRAINT outbox_event_type_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_event_type_check
 CHECK (event_type IN ('role_change_recorded','change_execution_requested','connector_sync_requested'));

CREATE TABLE webhook_deliveries (
 organization_id uuid NOT NULL, connector_id uuid NOT NULL, delivery_id text NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (organization_id, connector_id, delivery_id),
 FOREIGN KEY (organization_id, connector_id) REFERENCES connectors(organization_id, id)
);
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON webhook_deliveries USING (organization_id = app_org()) WITH CHECK (organization_id = app_org());

GRANT UPDATE(config, secret_ref, secret_envelope, health, last_cursor) ON connectors TO guardian_app;
GRANT SELECT, INSERT ON webhook_deliveries TO guardian_app;
GRANT UPDATE(cursor_token, pages, retries) ON sync_runs TO guardian_app;
GRANT SELECT, UPDATE(health, last_cursor) ON connectors TO guardian_worker;
GRANT UPDATE(cursor_token, pages, retries) ON sync_runs TO guardian_worker;
