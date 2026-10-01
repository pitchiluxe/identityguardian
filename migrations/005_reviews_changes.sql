-- Phase 6: evidence-backed access reviews and canonical IAM change proposals.

CREATE TABLE change_requests (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('remove_relationship','add_relationship','jit_grant')),
 target jsonb NOT NULL, parameters jsonb NOT NULL DEFAULT '{}',
 justification text NOT NULL CHECK (length(justification) BETWEEN 8 AND 2000),
 origin text NOT NULL CHECK (origin IN ('manual','review','jit','lifecycle','policy','lab')),
 origin_ref text, requester_id uuid NOT NULL REFERENCES users,
 status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SIMULATED','IN_REVIEW','APPROVED',
   'QUEUED','EXECUTING','SUCCEEDED','REJECTED','EXPIRED','CANCELLED','STALE','FAILED','PARTIAL',
   'RECONCILIATION_REQUIRED')),
 version integer NOT NULL DEFAULT 1, idempotency_key uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, requester_id, idempotency_key),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

CREATE TABLE review_campaigns (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, environment_id uuid NOT NULL,
 name text NOT NULL CHECK (length(name) BETWEEN 3 AND 200), rules text[] NOT NULL,
 created_by uuid NOT NULL REFERENCES users, status text NOT NULL DEFAULT 'OPEN'
   CHECK (status IN ('OPEN','CLOSED')),
 due_at timestamptz NOT NULL, snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, id),
 FOREIGN KEY (organization_id, environment_id) REFERENCES environments(organization_id, id)
);

CREATE TABLE review_items (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, campaign_id uuid NOT NULL,
 identity_node uuid NOT NULL, relationship_id uuid NOT NULL, finding_keys text[] NOT NULL,
 evidence jsonb NOT NULL, recommendation text NOT NULL CHECK (recommendation IN ('KEEP','REVIEW','REMOVE')),
 recommendation_basis text NOT NULL, uncertainty jsonb NOT NULL,
 reviewer_id uuid NOT NULL REFERENCES users,
 status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DECIDED')),
 decision text CHECK (decision IN ('KEEP','REMOVE','ESCALATE')), decision_justification text,
 decided_by uuid REFERENCES users, decided_at timestamptz, change_request_id uuid,
 version integer NOT NULL DEFAULT 1,
 CHECK ((status = 'PENDING' AND decision IS NULL) OR (status = 'DECIDED' AND decision IS NOT NULL
   AND decided_by = reviewer_id AND length(decision_justification) >= 8)),
 UNIQUE (organization_id, campaign_id, relationship_id),
 FOREIGN KEY (organization_id, campaign_id) REFERENCES review_campaigns(organization_id, id),
 FOREIGN KEY (organization_id, identity_node) REFERENCES twin_nodes(organization_id, id),
 FOREIGN KEY (organization_id, relationship_id) REFERENCES relationships(organization_id, id),
 FOREIGN KEY (organization_id, change_request_id) REFERENCES change_requests(organization_id, id)
);

CREATE INDEX change_scope ON change_requests(organization_id, environment_id, status, created_at DESC);
CREATE INDEX review_items_reviewer ON review_items(organization_id, reviewer_id, status);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['change_requests','review_campaigns','review_items'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_scope ON %I USING (organization_id = app_org()) WITH CHECK (organization_id = app_org())',t);
 END LOOP;
END $$;

GRANT SELECT, INSERT ON change_requests, review_campaigns, review_items TO guardian_app;
GRANT UPDATE(status, version, updated_at) ON change_requests TO guardian_app;
GRANT UPDATE(status) ON review_campaigns TO guardian_app;
GRANT UPDATE(status, decision, decision_justification, decided_by, decided_at, change_request_id,
 version) ON review_items TO guardian_app;
