-- Administrators may create SANDBOX environments; LAB environments remain learner attempts only.
-- PRODUCTION environments can never be created by the runtime role.
DROP POLICY lab_insert ON environments;
CREATE POLICY runtime_insert ON environments AS RESTRICTIVE FOR INSERT
 WITH CHECK (kind = 'SANDBOX' AND lab_learner IS NULL OR kind = 'LAB' AND lab_learner IS NOT NULL);
