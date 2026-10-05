# Key management runbook

Keys live in secret files (`.local/secrets/` locally, mounted at `/run/secrets`). They are never in the image, the repository, logs or API responses. A KMS/HSM is not integrated (U5).

| Key | Used for | Rotation |
|---|---|---|
| `secret_master_key` | Wraps the per-secret data keys of connector secrets (AES-256-GCM envelopes) | Supported, see below |
| `audit_signing_key` | Ed25519 signatures on audit checkpoints | Replace the key. Each checkpoint stores its public key, so older checkpoints stay verifiable |
| Database passwords | Migrator, runtime and worker roles | `ALTER ROLE ... PASSWORD`, then update the secret file and restart |

## Rotating the master key

Each envelope records a non-secret key id (`kid`), which lets old and new keys coexist during rotation.

1. Back up first.
2. Generate a new key: `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`. Write it to the file without echoing it to shared terminals.
3. Configure the API, worker and operator with `SECRET_MASTER_KEY=<new>` and `SECRET_MASTER_KEY_PREVIOUS=["<old>"]`, then restart. Webhook verification keeps working with both keys.
4. Run `python scripts/manage.py rotate-master-key`. It re-wraps connector secrets **and** users' AI provider keys (Phase 24), and reports both as `{"connectors": {…}, "ai_keys": {…}}`. Each block is `{"rewrapped": n, "current": m, "unavailable": k}`, and the command exits 1 if any envelope could not be opened. Only data keys are re-wrapped; ciphertext is untouched. Each connector re-wrap writes a `connector.secret_rewrapped` audit event; AI key re-wraps are counted but not audited per user. Re-running the command is safe.
5. Once `unavailable` is 0, remove `SECRET_MASTER_KEY_PREVIOUS`, restart and destroy the old key.

If a key is withdrawn before re-wrapping, webhook verification fails closed: the server returns 503 and logs an error, and the event is never accepted. Envelopes from before Phase 20 have no `kid`. They are opened by trial with the current and previous keys and gain a `kid` when re-wrapped.

## Rotating the audit signing key

Generate a new Ed25519 key and replace `audit_signing_key`, then restart. Export the last checkpoint signed with the old key to write-once storage before switching (U6). `GET /audit/verify` checks each checkpoint against the public key stored with it.
