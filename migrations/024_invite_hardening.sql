-- Phase 21 review fixes: the database itself enforces privileged approval and single use, and
-- refusals report their tenant so the caller can audit them.
ALTER TABLE invites ADD CONSTRAINT invites_privileged_approved CHECK (
 NOT roles && ARRAY['org_admin','approver','operator']
 OR status IN ('PENDING_APPROVAL','REVOKED') OR approver_id IS NOT NULL);
ALTER TABLE invites ADD CONSTRAINT invites_redeemed_by CHECK (
 (status = 'REDEEMED') = (redeemed_by IS NOT NULL));

CREATE FUNCTION invites_final_states() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
 IF OLD.status IN ('REDEEMED','REVOKED') AND NEW.status IS DISTINCT FROM OLD.status THEN
  RAISE EXCEPTION 'invite % is final (%)', OLD.id, OLD.status USING ERRCODE = 'check_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER invites_final_states BEFORE UPDATE ON invites
 FOR EACH ROW EXECUTE FUNCTION invites_final_states();

DROP FUNCTION redeem_invite(text, text, text, text, text);
CREATE FUNCTION redeem_invite(p_hash text, p_issuer text, p_subject text, p_name text, p_email text)
RETURNS TABLE(user_id uuid, organization_id uuid, invite_id uuid, reason text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE inv invites%ROWTYPE; uid uuid;
BEGIN
 SELECT * INTO inv FROM invites i WHERE i.token_hash = p_hash FOR UPDATE;
 IF NOT FOUND THEN
  RETURN QUERY SELECT NULL::uuid, NULL::uuid, NULL::uuid, 'invalid'::text; RETURN; END IF;
 IF inv.status IN ('REDEEMED','REVOKED') THEN
  RETURN QUERY SELECT NULL::uuid, inv.organization_id, inv.id, 'invalid'::text; RETURN; END IF;
 IF inv.expires_at <= now() THEN
  RETURN QUERY SELECT NULL::uuid, inv.organization_id, inv.id, 'expired'::text; RETURN; END IF;
 IF inv.status <> 'ACTIVE' THEN
  RETURN QUERY SELECT NULL::uuid, inv.organization_id, inv.id, 'not_approved'::text; RETURN; END IF;
 IF lower(btrim(coalesce(p_email, ''))) <> inv.email_normalized THEN
  RETURN QUERY SELECT NULL::uuid, inv.organization_id, inv.id, 'email_mismatch'::text; RETURN; END IF;
 SELECT u.id INTO uid FROM users u WHERE u.issuer = p_issuer AND u.subject = p_subject;
 IF uid IS NULL THEN
  uid := gen_random_uuid();
  INSERT INTO users VALUES (uid, p_issuer, p_subject,
   left(coalesce(nullif(btrim(p_name), ''), inv.email_normalized), 200));
 ELSIF EXISTS (SELECT 1 FROM memberships m
               WHERE m.organization_id = inv.organization_id AND m.user_id = uid) THEN
  RETURN QUERY SELECT NULL::uuid, inv.organization_id, inv.id, 'already_member'::text; RETURN;
 END IF;
 INSERT INTO memberships(organization_id, user_id, roles) VALUES (inv.organization_id, uid, inv.roles);
 UPDATE invites SET status = 'REDEEMED', redeemed_by = uid, redeemed_at = now() WHERE id = inv.id;
 INSERT INTO audit_events(id, organization_id, actor_id, action, target, after_state, justification,
  result, correlation_id)
 VALUES (gen_random_uuid(), inv.organization_id, uid, 'invite.redeemed', inv.id::text,
  jsonb_build_object('roles', inv.roles), 'Invitee registered and accepted the invite',
  'succeeded', gen_random_uuid());
 RETURN QUERY SELECT uid, inv.organization_id, inv.id, NULL::text;
END $$;
REVOKE ALL ON FUNCTION redeem_invite(text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION redeem_invite(text, text, text, text, text) TO guardian_app;
