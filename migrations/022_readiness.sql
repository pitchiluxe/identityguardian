-- Phase 20: readiness probes compare applied migrations with those shipped in the image.
-- schema_migrations holds file names only (no tenant data); runtime roles may read, never write.
GRANT SELECT ON schema_migrations TO guardian_app, guardian_worker;
