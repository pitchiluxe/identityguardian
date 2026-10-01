-- A source object may return to an earlier state (e.g. a removed grant restored). Replay
-- idempotency compares against the latest observation per object, so identical historical
-- content must be insertable again as new evidence.
ALTER TABLE observations DROP CONSTRAINT observations_organization_id_environment_id_source_external_key;
CREATE INDEX observation_latest ON observations(organization_id, environment_id, source, external_id, received_at DESC);
