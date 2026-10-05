-- Phase 23 review: a connector read that could not cover its whole source (e.g. the Entra
-- app cap) downgrades its run to partial coverage so absence never closes relationships.
GRANT UPDATE (coverage) ON sync_runs TO guardian_worker;
