"""Generate secret files for the packaged stack (Phase 20) into the ignored .local/secrets/.

Refuses to overwrite existing files, so a rerun never rotates keys by accident (rotation is
`manage.py rotate-master-key`). Values are written, never printed.
"""

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".local" / "secrets"


def generate():
    postgres, runtime, worker = (secrets.token_urlsafe(32) for _ in range(3))
    host = "postgres:5432/identityguardian"
    signing = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    return dict(
        postgres_password=postgres,
        runtime_password=runtime,
        worker_password=worker,
        migration_database_url=f"postgresql://guardian_migrator:{postgres}@{host}",
        database_url=f"postgresql://guardian_app:{runtime}@{host}",
        worker_database_url=f"postgresql://guardian_worker:{worker}@{host}",
        secret_master_key=base64.b64encode(os.urandom(32)).decode(),
        audit_signing_key=base64.b64encode(signing).decode(),
    )


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    try:
        # The directory is the host-side gate. Files stay world-readable so non-root container
        # users (api uid 10001, postgres uid 999) can read their bind-mounted secret.
        TARGET.chmod(0o700)
    except OSError:  # Windows ACLs are inherited from the user profile
        pass
    existing = sorted(p.name for p in TARGET.iterdir())
    if existing:
        raise SystemExit(f"Refusing to overwrite existing secrets in {TARGET}: {existing}")
    for name, value in generate().items():
        path = TARGET / name
        path.write_text(value)
    print(f"Wrote {len(list(TARGET.iterdir()))} secret files to {TARGET} (values not shown).")


if __name__ == "__main__":
    main()
