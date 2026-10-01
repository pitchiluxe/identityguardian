-- Phase 18: tamper-evident audit chain. A chain detects edits by anyone who cannot also recompute
-- every later hash; signed checkpoints stored outside the database detect even that.
ALTER TABLE audit_events ADD COLUMN sequence bigint, ADD COLUMN prev_hash text, ADD COLUMN hash text;

CREATE FUNCTION audit_canonical(e audit_events) RETURNS text LANGUAGE sql IMMUTABLE AS $$
 SELECT concat_ws('|', e.organization_id::text, e.sequence::text, coalesce(e.actor_id::text, ''), e.action,
   e.target, e.before_state::text, e.after_state::text, e.justification, coalesce(e.approval_id::text, ''),
   e.result, e.correlation_id::text, to_char(e.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'))
$$;

CREATE FUNCTION audit_chain() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE last record;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('audit:' || NEW.organization_id::text));
  SELECT sequence, hash INTO last FROM audit_events WHERE organization_id = NEW.organization_id
   ORDER BY sequence DESC LIMIT 1;
  NEW.sequence := coalesce(last.sequence, 0) + 1;
  NEW.prev_hash := coalesce(last.hash, 'genesis');
  NEW.hash := encode(sha256(convert_to(NEW.prev_hash || '|' || audit_canonical(NEW), 'UTF8')), 'hex');
  RETURN NEW;
END $$;

-- Backfill existing events in creation order per organization.
DO $$ DECLARE r audit_events; prev text; seq bigint; org uuid := NULL; BEGIN
 FOR r IN SELECT * FROM audit_events ORDER BY organization_id, created_at, id LOOP
  IF org IS DISTINCT FROM r.organization_id THEN org := r.organization_id; prev := 'genesis'; seq := 0; END IF;
  seq := seq + 1;
  r.sequence := seq;
  UPDATE audit_events SET sequence = seq, prev_hash = prev,
    hash = encode(sha256(convert_to(prev || '|' || audit_canonical(r), 'UTF8')), 'hex') WHERE id = r.id
   RETURNING hash INTO prev;
 END LOOP;
END $$;

ALTER TABLE audit_events ALTER COLUMN sequence SET NOT NULL, ALTER COLUMN hash SET NOT NULL,
 ALTER COLUMN prev_hash SET NOT NULL;
CREATE UNIQUE INDEX audit_sequence ON audit_events(organization_id, sequence);
CREATE TRIGGER audit_chain BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION audit_chain();

CREATE TABLE audit_checkpoints (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations, sequence bigint NOT NULL,
 hash text NOT NULL, signature text NOT NULL, public_key text NOT NULL, created_by uuid REFERENCES users,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE audit_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_checkpoints FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON audit_checkpoints USING (organization_id = app_org()) WITH CHECK (organization_id = app_org());
GRANT SELECT, INSERT ON audit_checkpoints TO guardian_app;
GRANT EXECUTE ON FUNCTION audit_canonical(audit_events) TO guardian_app;
