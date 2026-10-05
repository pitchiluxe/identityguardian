-- Phase 22: the first org_admin of a real organization is invited by the operator bootstrap,
-- which has no second approver. Only the migration role can set bootstrap.
ALTER TABLE invites ADD COLUMN bootstrap boolean NOT NULL DEFAULT false;
ALTER TABLE invites DROP CONSTRAINT invites_privileged_approved;
ALTER TABLE invites ADD CONSTRAINT invites_privileged_approved CHECK (
 NOT roles && ARRAY['org_admin','approver','operator']
 OR status IN ('PENDING_APPROVAL','REVOKED') OR approver_id IS NOT NULL OR bootstrap);
REVOKE INSERT ON invites FROM guardian_app;
GRANT INSERT (id, organization_id, email_normalized, roles, token_hash, inviter_id, digest,
 justification, status, expires_at) ON invites TO guardian_app;
-- Fixed, non-loginable principal recorded as the inviter of bootstrap invites.
INSERT INTO users VALUES ('00000000-0000-4000-8000-00000000b007', 'urn:identityguardian:system',
 'operator-bootstrap', 'Operator bootstrap') ON CONFLICT DO NOTHING;
