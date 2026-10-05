"""Phase 20: master-key identifiers and rotation for connector-secret envelopes."""

import base64
import os

import pytest

from apps.api.app.secrets_envelope import key_id, open_envelope, rewrap, seal


def new_key():
    return base64.b64encode(os.urandom(32)).decode()


def test_envelope_records_key_id_not_key():
    key = new_key()
    envelope = seal("s3cret-value", key, "connector:a")
    assert envelope["kid"] == key_id(key)
    assert key not in str(envelope) and "s3cret-value" not in str(envelope)


def test_rotated_key_needs_previous_key_until_rewrapped():
    old, new = new_key(), new_key()
    envelope = seal("s3cret-value", old, "connector:a")
    with pytest.raises(ValueError, match="not configured"):
        open_envelope(envelope, new, "connector:a")  # retired key withdrawn: cannot decrypt
    assert open_envelope(envelope, new, "connector:a", previous=[old]) == "s3cret-value"

    rotated = rewrap(envelope, new, "connector:a", previous=[old])
    assert rotated["kid"] == key_id(new)
    assert rotated["ct"] == envelope["ct"]  # only the data key is re-wrapped
    assert open_envelope(rotated, new, "connector:a") == "s3cret-value"
    assert rewrap(rotated, new, "connector:a") is None  # idempotent


def test_rewrap_keeps_context_binding():
    old, new = new_key(), new_key()
    envelope = seal("s3cret-value", old, "connector:a")
    with pytest.raises(Exception):
        rewrap(envelope, new, "connector:b", previous=[old])


def test_legacy_envelope_without_key_id_opens_and_rewraps():
    old, new = new_key(), new_key()
    envelope = seal("s3cret-value", old, "connector:a")
    del envelope["kid"]  # Phase 16 envelopes predate key identifiers
    assert open_envelope(envelope, old, "connector:a") == "s3cret-value"
    rotated = rewrap(envelope, new, "connector:a", previous=[old])
    assert open_envelope(rotated, new, "connector:a") == "s3cret-value"


def test_secret_reads_environment_then_mounted_file(tmp_path, monkeypatch):
    from apps.api.app.config import secret

    monkeypatch.setenv("IG_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("WORKER_DATABASE_URL", raising=False)
    with pytest.raises(KeyError, match="not configured"):
        secret("WORKER_DATABASE_URL")
    (tmp_path / "worker_database_url").write_text("postgresql://from-file\n")
    assert secret("WORKER_DATABASE_URL") == "postgresql://from-file"
    monkeypatch.setenv("WORKER_DATABASE_URL", "postgresql://from-env")
    assert secret("WORKER_DATABASE_URL") == "postgresql://from-env"


def test_settings_read_mounted_secret_files(tmp_path, monkeypatch):
    from apps.api.app.config import Settings

    (tmp_path / "audit_signing_key").write_text("file-value")
    monkeypatch.delenv("AUDIT_SIGNING_KEY", raising=False)
    settings = Settings(_env_file=None, _secrets_dir=tmp_path)
    assert settings.audit_signing_key == "file-value"
