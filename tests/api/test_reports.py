"""Phase 17: authorized redacted exports with evidence/snapshot, formula-injection protection, expiry."""

import csv
import io
import json
import os

import psycopg
import pytest

from apps.api.app.db import Database
from apps.api.app.domain.reports import REPORT_TYPES, redact, safe_cell
from apps.worker.main import tick
from tests.api.conftest import as_user
from tests.api.support import source_update, sync


def create(client, twin, report_type, who="admin", **extra):
    headers = as_user(client, twin["people"], who)
    return client.post(
        twin["base"] + "/reports", headers=headers, json=dict(report_type=report_type, **extra)
    )


def download(client, twin, report_id, who="auditor"):
    as_user(client, twin["people"], who)
    return client.get(twin["base"] + f"/reports/{report_id}/download")


@pytest.mark.parametrize("report_type", sorted(REPORT_TYPES))
def test_every_report_type_exports_with_snapshot_metadata(client, twin, report_type):
    created = create(client, twin, report_type)
    assert created.status_code == 201, created.text
    response = download(client, twin, created.json()["data"]["id"])
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    text = response.text
    assert (
        "# graph_version:" in text and "# effective_at:" in text and "# redaction: standard" in text
    )


def test_privilege_creep_rows_cite_evidence_and_coverage(client, twin):
    report = create(client, twin, "privilege_creep", format="json").json()["data"]
    body = json.loads(download(client, twin, report["id"]).text)
    erick = next(r for r in body["rows"] if r["rule"] == "PRIOR_ROLE_RETAINED")
    assert (
        erick["identity"] == "Erick Mensah"
        and erick["evidence_ids"]
        and "RULE-BASED" in erick["basis"]
    )
    assert erick["summary_text"] == "[redacted: free text]"  # standard redaction
    assert "not proof of non-use" in body["metadata"]["notes"]


def test_formula_injection_is_neutralised(client, twin):
    assert [safe_cell(v) for v in ["=1+1", "+cmd", "-2", "@SUM", "\tx", "safe"]] == [
        "'=1+1",
        "'+cmd",
        "'-2",
        "'@SUM",
        "'\tx",
        "safe",
    ]

    def poison(body):
        body["attributes"]["ticket"] = '=HYPERLINK("http://attacker.example","click")'
        return body, False

    source_update(twin["env"], "mem-erick-grp-finance-legacy", poison)
    sync(client, twin)
    report = create(client, twin, "privileged_access").json()["data"]
    rows = list(csv.reader(io.StringIO(download(client, twin, report["id"]).text)))
    cells = [c for row in rows for c in row]
    assert any(c.startswith("'=HYPERLINK") for c in cells)
    assert not any(c.startswith("=") for c in cells)


def test_redaction_and_authorization(client, twin):
    report = create(client, twin, "privileged_access").json()["data"]
    assert download(client, twin, report["id"]).status_code == 200
    assert redact("erick@contoso.example", "upn", "standard") == "e***@contoso.example"
    assert redact("erick@contoso.example", "upn", "full") == "erick@contoso.example"
    assert redact("Needed for close", "justification", "standard") == "[redacted: free text]"
    assert create(client, twin, "privileged_access", who="viewer").status_code == 403
    assert create(client, twin, "privileged_access", who="investigator").status_code == 403
    full = create(client, twin, "privilege_creep", who="auditor", redaction="full")
    assert full.status_code == 201
    assert download(client, twin, report["id"], who="viewer").status_code == 403
    assert download(client, twin, report["id"], who="investigator").status_code == 403
    other = f"/api/v1/organizations/{twin['org']}/environments/{twin['other_env']}/reports/{report['id']}/download"
    as_user(client, twin["people"], "auditor")
    assert client.get(other).status_code == 404
    assert create(client, twin, "made_up").status_code == 422
    as_user(client, twin["people"], "admin")
    audit = [e["action"] for e in client.get(f"/api/v1/organizations/{twin['org']}/audit").json()]
    assert "report.created" in audit and "report.downloaded" in audit


def test_reports_expire_and_content_is_purged(client, twin):
    report = create(client, twin, "jml", expires_hours=1).json()["data"]
    assert create(client, twin, "jml", expires_hours=500).status_code == 422
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE report_artifacts SET created_at=now()-interval '2 hours', "
            "expires_at=now()-interval '1 hour' WHERE id=%s",
            (report["id"],),
        )
    assert download(client, twin, report["id"]).status_code == 410
    worker = Database(os.environ["WORKER_DATABASE_URL"])
    try:
        tick(worker, twin["org"])
    finally:
        worker.close()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        content, status = conn.execute(
            "SELECT content, status FROM report_artifacts WHERE id=%s", (report["id"],)
        ).fetchone()
    assert content is None and status == "EXPIRED"
