import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from apps.api.app.config import Settings
from apps.api.app.main import create_app
from tests.api.test_foundation import login


def test_forged_cookies_cannot_reset_login_rate_limit():
    with TestClient(
        create_app(Settings()), base_url="http://localhost:8000", client=("192.0.2.99", 1234)
    ) as browser:
        responses = []
        for _ in range(61):
            browser.cookies.set("ig_session", secrets.token_urlsafe(32))
            responses.append(browser.get("/api/v1/auth/login", follow_redirects=False).status_code)
    assert 429 in responses


def test_execution_rechecks_approval_after_waiting_for_org_lock(client, tenant):
    org, _, people = tenant
    base = f"/api/v1/organizations/{org}/role-requests"
    headers = login(client, people, "admin")
    proposal = client.post(
        base,
        headers=headers,
        json={
            "target_id": people["viewer"]["id"],
            "roles": ["auditor"],
            "justification": "Evidence review",
            "expected_version": 1,
            "idempotency_key": str(uuid4()),
        },
    ).json()
    headers = login(client, people, "approver")
    assert (
        client.post(
            base + f"/{proposal['id']}/approve",
            headers=headers,
            json={"digest": proposal["digest"]},
        ).status_code
        == 200
    )
    headers = login(client, people, "admin")
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"], autocommit=True) as observer:
        observer.execute("SELECT pg_advisory_lock(hashtext(%s))", (org,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                client.post,
                base + f"/{proposal['id']}/execute",
                headers=headers,
                json={"digest": proposal["digest"]},
            )
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    waiting = observer.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE usename='guardian_app' "
                        "AND wait_event='advisory'"
                    ).fetchone()
                    if waiting:
                        break
                    time.sleep(0.02)
                assert waiting, "Execution did not reach the organization lock"
                observer.execute(
                    "UPDATE memberships SET active=false WHERE organization_id=%s AND user_id=%s",
                    (org, people["approver"]["id"]),
                )
            finally:
                observer.execute("SELECT pg_advisory_unlock(hashtext(%s))", (org,))
            assert future.result(timeout=10).status_code in {403, 404}
