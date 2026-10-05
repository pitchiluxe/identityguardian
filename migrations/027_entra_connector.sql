-- Phase 23: read-only Microsoft Entra ID connector kind (real tenant data; GET-only Graph).
ALTER TABLE connectors DROP CONSTRAINT connectors_kind_check;
ALTER TABLE connectors ADD CONSTRAINT connectors_kind_check
 CHECK (kind IN ('sandbox','mock_entra','mock_okta','entra'));
