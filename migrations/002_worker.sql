CREATE TABLE event_receipts (
 event_id uuid PRIMARY KEY REFERENCES outbox(id),
 organization_id uuid NOT NULL REFERENCES organizations,
 received_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE event_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY receipt_scope ON event_receipts
 USING (organization_id::text=current_setting('app.org',true))
 WITH CHECK (organization_id::text=current_setting('app.org',true));
GRANT USAGE ON SCHEMA public TO guardian_worker;
GRANT SELECT ON outbox,event_receipts TO guardian_worker;
GRANT UPDATE(leased_until,attempts,processed_at) ON outbox TO guardian_worker;
GRANT INSERT ON event_receipts TO guardian_worker;
