-- Phase 21: invite-based registration. Credentials stay at the IdP; access comes only from an
-- invite. redeem_invite is the only runtime path that creates users/memberships from an invite.
CREATE TABLE invites (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 email_normalized text NOT NULL
  CHECK (email_normalized = lower(btrim(email_normalized)) AND email_normalized LIKE '%_@_%'),
 roles text[] NOT NULL CHECK (cardinality(roles) = 1 AND roles <@ ARRAY['viewer','investigator',
  'reviewer','approver','operator','org_admin','auditor','learner']),
 token_hash text NOT NULL UNIQUE, inviter_id uuid NOT NULL REFERENCES users,
 approver_id uuid REFERENCES users, approved_at timestamptz, digest text NOT NULL,
 justification text NOT NULL DEFAULT '',
 status text NOT NULL CHECK (status IN ('PENDING_APPROVAL','ACTIVE','REDEEMED','REVOKED')),
 expires_at timestamptz NOT NULL, redeemed_by uuid REFERENCES users, redeemed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (approver_id IS NULL OR approver_id <> inviter_id)
);
CREATE INDEX invites_scope ON invites(organization_id, created_at DESC);
CREATE INDEX invites_inviter ON invites(inviter_id);
CREATE INDEX invites_approver ON invites(approver_id);
CREATE INDEX invites_redeemed_by ON invites(redeemed_by);
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_scope ON invites USING (organization_id = app_org())
 WITH CHECK (organization_id = app_org());
GRANT SELECT, INSERT ON invites TO guardian_app;
GRANT UPDATE (status, approver_id, approved_at) ON invites TO guardian_app;

-- Server-side login attempts may carry the invite being redeemed (hash only).
ALTER TABLE login_attempts ADD COLUMN invite_hash text;

ALTER TABLE outbox DROP CONSTRAINT outbox_event_type_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_event_type_check CHECK (event_type IN
 ('role_change_recorded','change_execution_requested','connector_sync_requested','invite_recorded'));

-- Pre-redirect check for the public registration start: true only for ACTIVE, unexpired invites.
-- Returns a boolean only, so it cannot be used to read invite details.
CREATE FUNCTION invite_usable(p_hash text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
 SELECT EXISTS (SELECT 1 FROM invites WHERE token_hash = p_hash AND status = 'ACTIVE'
  AND expires_at > now());
$$;
REVOKE ALL ON FUNCTION invite_usable(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION invite_usable(text) TO guardian_app;

-- Redemption at the OIDC callback, in the caller's transaction. Refusals write nothing.
CREATE FUNCTION redeem_invite(p_hash text, p_issuer text, p_subject text, p_name text, p_email text)
RETURNS TABLE(user_id uuid, organization_id uuid, reason text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE inv invites%ROWTYPE; uid uuid;
BEGIN
 SELECT * INTO inv FROM invites i WHERE i.token_hash = p_hash FOR UPDATE;
 IF NOT FOUND OR inv.status IN ('REDEEMED','REVOKED') THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'invalid'::text; RETURN; END IF;
 IF inv.expires_at <= now() THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'expired'::text; RETURN; END IF;
 IF inv.status <> 'ACTIVE' THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'not_approved'::text; RETURN; END IF;
 IF lower(btrim(coalesce(p_email, ''))) <> inv.email_normalized THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'email_mismatch'::text; RETURN; END IF;
 SELECT u.id INTO uid FROM users u WHERE u.issuer = p_issuer AND u.subject = p_subject;
 IF uid IS NULL THEN
  uid := gen_random_uuid();
  INSERT INTO users VALUES (uid, p_issuer, p_subject,
   left(coalesce(nullif(btrim(p_name), ''), inv.email_normalized), 200));
 ELSIF EXISTS (SELECT 1 FROM memberships m
               WHERE m.organization_id = inv.organization_id AND m.user_id = uid) THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, 'already_member'::text; RETURN;
 END IF;
 INSERT INTO memberships(organization_id, user_id, roles) VALUES (inv.organization_id, uid, inv.roles);
 UPDATE invites SET status = 'REDEEMED', redeemed_by = uid, redeemed_at = now() WHERE id = inv.id;
 INSERT INTO audit_events(id, organization_id, actor_id, action, target, after_state, justification,
  result, correlation_id)
 VALUES (gen_random_uuid(), inv.organization_id, uid, 'invite.redeemed', inv.id::text,
  jsonb_build_object('roles', inv.roles), 'Invitee registered and accepted the invite',
  'succeeded', gen_random_uuid());
 RETURN QUERY SELECT uid, inv.organization_id, NULL::text;
END $$;
REVOKE ALL ON FUNCTION redeem_invite(text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION redeem_invite(text, text, text, text, text) TO guardian_app;
