"""Phase 20: liveness/readiness probes and structured logs."""

import json
import logging

from apps.api.app.main import JsonFormatter


def test_liveness_needs_no_database(client):
    class Unreachable:
        def transaction(self, organization_id=None):
            raise AssertionError("liveness must not touch the database")

    client.app.state.db = Unreachable()
    response = client.get("/api/v1/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_readiness_reports_ready_without_data(client, tenant):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}  # no counts, versions or tenant data
    assert tenant[0] not in response.text


def test_readiness_fails_when_migrations_pending(client, monkeypatch):
    from apps.api.app import main

    monkeypatch.setattr(main, "expected_migrations", lambda: 10_000)
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "migrations pending"}


def test_readiness_fails_closed_when_database_down(client):
    import psycopg

    class Down:
        def transaction(self, organization_id=None):
            raise psycopg.OperationalError("connection refused to 10.0.0.5 user guardian_app")

    client.app.state.db = Down()
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "database unavailable"}
    assert "guardian_app" not in response.text and "10.0.0.5" not in response.text


def test_json_log_lines_carry_correlation_and_exception():
    record = logging.LogRecord("identityguardian", logging.ERROR, __file__, 1, "x %s", ("y",), None)
    record.correlation_id = "abc"
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    line = json.loads(JsonFormatter().format(record))
    assert line["level"] == "ERROR" and line["message"] == "x y"
    assert line["correlation_id"] == "abc" and "RuntimeError" in line["exception"]
    assert line["logger"] == "identityguardian" and line["time"].endswith("Z")
