-- Phase 9: credential rotation proposals (metadata only; the platform never holds secret values).
ALTER TABLE change_requests DROP CONSTRAINT change_requests_kind_check;
ALTER TABLE change_requests ADD CONSTRAINT change_requests_kind_check
 CHECK (kind IN ('remove_relationship','add_relationship','jit_grant','rotate_credential'));
