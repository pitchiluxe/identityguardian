-- Phase 24: per-organization hosted-AI policy, per-user provider choice, per-user API keys.
CREATE TABLE organization_ai_settings (
 organization_id uuid PRIMARY KEY REFERENCES organizations,
 allow_hosted_ai boolean NOT NULL DEFAULT false,
 updated_by uuid REFERENCES users, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE user_ai_settings (
 organization_id uuid NOT NULL REFERENCES organizations, user_id uuid NOT NULL,
 provider text NOT NULL DEFAULT 'ollama' CHECK (provider IN ('ollama','anthropic','openai')),
 ollama_model text, anthropic_model text, openai_model text, hosted_ack_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (organization_id, user_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['organization_ai_settings','user_ai_settings'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())', t);
 END LOOP; END $$;
GRANT SELECT, INSERT, UPDATE ON organization_ai_settings, user_ai_settings TO guardian_app;

CREATE TABLE user_ai_keys (
 user_id uuid NOT NULL REFERENCES users, provider text NOT NULL CHECK (provider IN ('anthropic','openai')),
 envelope jsonb NOT NULL, last4 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (user_id, provider));
REVOKE ALL ON user_ai_keys FROM PUBLIC;  -- no runtime grants: access only via the functions below

CREATE FUNCTION ai_session_user(p_token text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid uuid;
BEGIN
 SELECT user_id INTO uid FROM sessions
 WHERE token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex') AND expires_at > now();
 IF uid IS NULL THEN RAISE EXCEPTION 'no live session' USING ERRCODE = 'insufficient_privilege'; END IF;
 RETURN uid;
END $$;
CREATE FUNCTION ai_key_put(p_token text, p_provider text, p_envelope jsonb, p_last4 text) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
 INSERT INTO user_ai_keys(user_id, provider, envelope, last4) VALUES (ai_session_user(p_token), p_provider, p_envelope, p_last4)
 ON CONFLICT (user_id, provider) DO UPDATE SET envelope = excluded.envelope, last4 = excluded.last4, created_at = now();
$$;
CREATE FUNCTION ai_key_get(p_token text, p_provider text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
 SELECT envelope FROM user_ai_keys WHERE user_id = ai_session_user(p_token) AND provider = p_provider;
$$;
CREATE FUNCTION ai_key_meta(p_token text) RETURNS TABLE(provider text, last4 text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
 SELECT provider, last4 FROM user_ai_keys WHERE user_id = ai_session_user(p_token) ORDER BY provider;
$$;
CREATE FUNCTION ai_key_delete(p_token text, p_provider text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
 WITH gone AS (DELETE FROM user_ai_keys WHERE user_id = ai_session_user(p_token) AND provider = p_provider RETURNING 1)
 SELECT EXISTS (SELECT 1 FROM gone);
$$;
REVOKE ALL ON FUNCTION ai_session_user(text), ai_key_put(text,text,jsonb,text), ai_key_get(text,text),
 ai_key_meta(text), ai_key_delete(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ai_key_put(text,text,jsonb,text), ai_key_get(text,text), ai_key_meta(text),
 ai_key_delete(text,text) TO guardian_app;
