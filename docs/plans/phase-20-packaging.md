# Phase 20 — production packaging

Depends on Phases 18–19. Acceptance gate (ROADMAP): containers, monitoring, key management, backup/restore drill, deployment/recovery runbooks and production acceptance.

Authorized by the user on 2026-10-05 ("Yes please") as **local packaging only**. Nothing is deployed, pushed or connected to a production system. Production acceptance is a checklist for the owner, not a claim that it was granted.

## Bounded plan

0. **Test stability (carried from Phase 19).** The API test fixture opens a new connection pool for every test. Under parallel load, PostgreSQL backend startup on Windows reached 9.2 s against the 10 s connect timeout. Fix: `create_app(settings, db=None)` accepts a shared `Database`, and an app closes only a database it created. The test suite shares one pool per xdist worker. Each test still gets its own app.
1. **Containers.**
   - `infra/docker/Dockerfile` is a multi-stage build. A Node stage builds the web shell. A Python slim runtime runs as non-root uid 10001 with a healthcheck, and the same image serves the API, the worker and migrations.
   - `.dockerignore` keeps `.env`, `.local/`, tests and VCS data out of the build context.
   - `infra/compose.production.yaml` includes a Caddy TLS reverse proxy with a 1 MB request-body limit (closes U2 at the proxy) and security headers. It adds a one-shot `migrate` service plus `api`, `worker` and `postgres`. PostgreSQL is on an internal network only, and secrets are supplied as Docker secret files.
   - No production IdP is shipped (U4). `OIDC_ISSUER_URL` must be an external HTTPS issuer.
2. **Secrets from files.** Settings read secrets from a mounted directory (`IG_SECRETS_DIR`, default `/run/secrets`) as well as from the environment, so keys need not be stored in environment variables.
3. **Key management.**
   - Connector-secret envelopes record a key id (`kid`). `SECRET_MASTER_KEY_PREVIOUS` holds retired keys for decryption only.
   - `manage.py rotate-master-key` re-wraps every data key under the current key. Ciphertext is untouched, the rewrap is idempotent and it is audited per organization.
   - Audit checkpoints already store their public key, so rotating the signing key keeps old checkpoints verifiable. The runbook documents this.
   - KMS/HSM integration remains out of scope (U5).
4. **Monitoring.**
   - `/api/v1/health` reports liveness without touching the database.
   - `/api/v1/ready` reports readiness: database reachable and every migration file applied. It returns 503 otherwise and exposes no tenant data.
   - `LOG_FORMAT=json` produces structured logs with correlation IDs for the API and worker.
   - `manage.py status` gives an operator summary across organizations: outbox backlog, oldest pending age, high-attempt events, and audit chain integrity per organization. Counts only, no tenant content.
5. **Backup/restore drill.**
   - `scripts/backup.py backup` writes a `pg_dump -Fc` archive and a SHA-256 manifest to the ignored `backups/` directory.
   - `scripts/backup.py drill` verifies the checksum and restores into a scratch database. It compares row counts for every table, verifies every organization's audit chain on the restored copy, then drops the scratch database.
   - The drill is executed and its measured result recorded.
6. **Runbooks.** `docs/operations/` covers deployment, monitoring, key management, backup/recovery and the production acceptance checklist, including the open gates U1–U12.
7. **Image scan (U12).** A scan is performed only if a scanner and the Docker daemon are available. Otherwise it is recorded as not performed.

Threat model: the new boundaries are the reverse proxy, unauthenticated readiness and the operator CLI. THREAT_MODEL.md is updated. New controls get negative tests: readiness leaks no data, a rotated key cannot decrypt without the previous key, and the drill detects a checksum mismatch.

## Verification ledger

- 2026-10-05: ruff check and format clean; secret scan 0 findings. New tests: `tests/unit/test_key_rotation.py` (6), `tests/unit/test_backup.py` (3), `tests/api/test_operations.py` (5), and the rotation test in `tests/api/test_connectors.py`. The new unit tests went red first (import errors) and were green after implementation.
- Full pytest run 1: 253 passed, 5 failed, 1 skipped. All five were worker/outbox tests. Cause: the demo worker had been started without `--organization`, so it processed the test organizations' outbox and JIT rows. With it stopped, `test_execution.py` + `test_connectors.py` gave 17 passed. The demo worker now runs scoped to the Contoso organization.
- Full pytest run 2: 256 passed, 2 failed (`test_snapshot_cache.py`, `PoolTimeout`: connect timeout exceeded), 1 skipped. That run overlapped the 5 GB restore drill, the live API and Keycloak on a host at about 94% CPU from other processes. Rerun of the file: 7 passed. The tests deliberately use private one-connection pools, so the shared-pool fix does not apply to them. Connection-start latency under load remains a known environmental flake.
- Backup: 572,001,839-byte archive in 332.6 s, SHA-256 recorded in the manifest.
- Restore drill: finished, and the wrapper process exited 0. The drill's JSON report (`"result"` PASS/FAIL) was **not read by the agent**: reading that output was blocked by the session permission policy. Owner confirmation: `type` the scratch `drill.txt` or re-run `python -m scripts.backup drill`. Until then, the drill result is UNCONFIRMED.
- Container build, packaged-stack smoke test and image scan (U12): NOT PERFORMED. The Docker daemon was unreachable at first and a later status check was blocked by the session permission policy. The Dockerfile and compose file are unverified artifacts. The first `docker compose -f infra/compose.production.yaml up --build` must be treated as their test.
- Phase status: packaging artifacts and runbooks delivered; acceptance items above remain open. Not production-accepted.
- Playwright: not re-run in this phase.
