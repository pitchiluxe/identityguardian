"""Phase 18: the repository contains no credentials; the scanner detects planted ones."""

from scripts.secret_scan import ROOT, scan, tracked_files


def test_repository_has_no_secrets():
    assert scan(tracked_files(ROOT)) == []


def test_scanner_detects_planted_credentials(tmp_path):
    begin = "-----BEGIN " + "PRIVATE KEY-----"
    samples = {
        "key.pem": begin,
        "aws.txt": "id = AKIA" + "Q" * 16,
        "cfg.py": "client_secret = '" + "a" * 32 + "'",
        "db.txt": "postgresql://user:" + "p" * 12 + "@db.example/x",
        ".env": "ANY=1",
    }
    for name, text in samples.items():
        (tmp_path / name).write_text(text)
    found = {f[2] for f in scan(sorted(tmp_path.iterdir()))}
    assert found == {
        "private key",
        "AWS access key",
        "assigned secret",
        "connection string with password",
        "environment file is tracked",
    }


def test_scanner_detects_ai_provider_keys(tmp_path):
    (tmp_path / "a.txt").write_text("key " + "sk-ant-" + "api03-" + "A" * 40)
    (tmp_path / "o.txt").write_text("key " + "sk-" + "proj-" + "B" * 40)
    found = {f[2] for f in scan(sorted(tmp_path.iterdir()))}
    assert found == {"Anthropic API key", "OpenAI API key"}
