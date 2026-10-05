"""Phase 20: backup drill integrity checks (the full drill is run and recorded separately)."""

import json

import pytest

from scripts.backup import compare_counts, connection_args, sha256, verify_archive


def test_tampered_archive_is_rejected(tmp_path):
    archive = tmp_path / "identityguardian-x.dump"
    archive.write_bytes(b"PGDMP archive bytes")
    manifest = dict(sha256=sha256(archive))
    verify_archive(archive, manifest)
    archive.write_bytes(b"PGDMP archive bytez")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_archive(archive, manifest)


def test_count_comparison_reports_missing_and_changed_tables():
    expected = dict(audit_events=10, outbox=2, sessions=0)
    assert compare_counts(expected, dict(expected)) == []
    assert compare_counts(expected, dict(audit_events=9, outbox=2)) == ["audit_events", "sessions"]


def test_password_goes_to_environment_not_arguments():
    args, env = connection_args("postgresql://guardian_migrator:p%40ss@127.0.0.1:55432/ig", "x")
    assert env["PGPASSWORD"] == "p@ss"
    assert not any("p@ss" in a or "p%40ss" in a for a in args)
    assert args[-1] == "x"
    json.dumps(args)
