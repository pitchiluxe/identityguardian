# Backup and recovery runbook

## Backup

```
python -m scripts.backup backup
```

- Runs `pg_dump -Fc` under an exported REPEATABLE READ snapshot. The manifest's per-table row counts therefore describe exactly the archived state.
- Writes `backups/identityguardian-<UTC>.dump` and a `.json` manifest with the SHA-256, size, duration and row counts. `backups/` is git-ignored.
- The password reaches `pg_dump` through `PGPASSWORD`, never the process argument list.
- Database roles are cluster-level and not included. They are recreated by `manage.py migrate` from the role password secrets.

Copy the archive and manifest to storage outside the platform host, ideally write-once. Export the signed audit checkpoints alongside them (U6). Retention and an off-site schedule are owner decisions and are not configured here.

## Restore drill (run after every backup and before every upgrade)

```
python -m scripts.backup drill [backups/identityguardian-<UTC>.dump]
```

1. Verifies the archive SHA-256 against its manifest. A mismatch stops the drill before any restore.
2. Restores into a new scratch database, `ig_restore_drill_<epoch>`, with `--exit-on-error`.
3. Compares every table's row count with the manifest. Any difference or missing table fails the drill.
4. Re-verifies every organization's audit hash chain on the restored copy.
5. Drops the scratch database, including on failure, and prints a JSON report. Exits 1 on FAIL.

## Recovery procedure (real incident)

1. Stop writers: `docker compose -f infra/compose.production.yaml stop api worker`.
2. Preserve the damaged database (`pg_dump` or a volume snapshot) for investigation. Do not drop it first.
3. Choose the newest archive whose drill passed. Run the drill on it again.
4. Restore it into a new database. Point the secret URLs at it, or rename databases during the outage window.
5. Run `manage.py migrate` (recreates roles if missing) and `manage.py status --verify-audit`. Both must report OK.
6. Start `api` and `worker`. Confirm `/api/v1/ready` and the worker healthcheck.
7. Record the data-loss window: events after the archive's `created_utc` are lost. Compare with exported checkpoints to show the audit trail before that point is intact.

The worker is idempotent (event receipts, leases), so re-delivering outbox rows from the restored state is safe. Sandbox executions in flight are reconciled on restart.

## Measured drill

See the Phase 20 verification ledger in `docs/plans/phase-20-packaging.md` for the executed drill and its timings.
