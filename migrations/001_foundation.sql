CREATE TABLE users (
 id uuid PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
 display_name text NOT NULL, UNIQUE(issuer, subject)
);
CREATE TABLE organizations (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE environments (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 name text NOT NULL, kind text NOT NULL CHECK (kind IN ('LAB','SANDBOX','PRODUCTION')),
 UNIQUE(organization_id,id)
);
CREATE TABLE memberships (
 organization_id uuid NOT NULL REFERENCES organizations, user_id uuid NOT NULL REFERENCES users,
 roles text[] NOT NULL, active boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1,
 PRIMARY KEY(organization_id,user_id),
 CHECK(roles <@ ARRAY['viewer','investigator','reviewer','approver','operator','org_admin','auditor','learner'])
);
CREATE TABLE sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users, csrf_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), last_seen timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL, auth_time double precision NOT NULL, amr text[] NOT NULL
);
CREATE TABLE login_attempts (
 token_hash text PRIMARY KEY, state text NOT NULL, nonce text NOT NULL, verifier text NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE TABLE audit_events (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 actor_id uuid REFERENCES users, action text NOT NULL, target text NOT NULL,
 before_state jsonb NOT NULL DEFAULT '{}', after_state jsonb NOT NULL DEFAULT '{}',
 justification text NOT NULL, approval_id uuid, result text NOT NULL,
 correlation_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE role_requests (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 target_id uuid NOT NULL, requester_id uuid NOT NULL REFERENCES users,
 roles text[] NOT NULL, previous_roles text[] NOT NULL, expected_version integer NOT NULL,
 justification text NOT NULL, digest text NOT NULL,
 status text NOT NULL DEFAULT 'IN_REVIEW' CHECK(status IN ('IN_REVIEW','APPROVED','EXECUTED')),
 approver_id uuid REFERENCES users, approved_at timestamptz, expires_at timestamptz NOT NULL,
 idempotency_key uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(organization_id,target_id) REFERENCES memberships(organization_id,user_id),
 UNIQUE(organization_id,requester_id,idempotency_key),
 CHECK(roles <@ ARRAY['viewer','investigator','reviewer','approver','operator','org_admin','auditor','learner']),
 CHECK(approver_id IS NULL OR (approver_id <> requester_id AND approver_id <> target_id))
);
CREATE TABLE outbox (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations,
 event_type text NOT NULL CHECK(event_type = 'role_change_recorded'), payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
 leased_until timestamptz, attempts integer NOT NULL DEFAULT 0
);
CREATE TABLE rate_limits (bucket text PRIMARY KEY, window_id bigint NOT NULL, count integer NOT NULL);
CREATE INDEX audit_scope_time ON audit_events(organization_id,created_at DESC);
CREATE INDEX job_pending ON outbox(organization_id,created_at) WHERE processed_at IS NULL;

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY organization_scope ON organizations USING (id::text = current_setting('app.org',true));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['environments','memberships','audit_events','role_requests','outbox'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id::text = current_setting(''app.org'',true)) WITH CHECK (organization_id::text = current_setting(''app.org'',true))',t);
 END LOOP;
END $$;

-- RLS is not authorization to select a tenant. API checks membership first.
-- Narrow SECURITY DEFINER discovery returns only memberships for a known session principal.
CREATE FUNCTION user_organizations(uid uuid) RETURNS TABLE(id uuid,name text)
LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $$
 SELECT o.id,o.name FROM organizations o JOIN memberships m ON m.organization_id=o.id
 WHERE m.user_id=uid AND m.active ORDER BY o.name;
$$;
REVOKE ALL ON FUNCTION user_organizations(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO guardian_app;
GRANT SELECT ON organizations,environments,memberships,audit_events TO guardian_app;
GRANT UPDATE(roles,version) ON memberships TO guardian_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON sessions,login_attempts,rate_limits TO guardian_app;
GRANT SELECT ON users TO guardian_app;
GRANT SELECT,INSERT,UPDATE ON role_requests,outbox TO guardian_app;
GRANT INSERT ON audit_events TO guardian_app;
GRANT EXECUTE ON FUNCTION user_organizations(uuid) TO guardian_app;
