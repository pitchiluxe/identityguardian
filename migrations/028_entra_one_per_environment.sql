-- Phase 23 review: one Entra tenant per environment. Connectors of a kind share the ingest
-- source, so two tenants in one environment would tombstone each other's relationships.
-- A trigger (not a unique index) so existing rows are never rewritten or deleted by a migration.
CREATE FUNCTION connectors_one_entra_per_environment() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
 IF NEW.kind = 'entra' AND EXISTS (
   SELECT 1 FROM connectors c WHERE c.organization_id = NEW.organization_id
   AND c.environment_id = NEW.environment_id AND c.kind = 'entra' AND c.id <> NEW.id) THEN
  RAISE EXCEPTION 'environment already has an Entra ID connector' USING ERRCODE = 'unique_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER connectors_one_entra_per_environment BEFORE INSERT OR UPDATE OF kind, environment_id
 ON connectors FOR EACH ROW EXECUTE FUNCTION connectors_one_entra_per_environment();
