import os
from uuid import uuid4

import psycopg
from dotenv import load_dotenv

from apps.api.app.db import Database
from apps.worker.main import process_one

load_dotenv()


def test_worker_consumes_once_and_cannot_read_sessions():
    org, event = uuid4(), uuid4()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute("INSERT INTO organizations VALUES(%s,'Worker test')", (org,))
        conn.execute(
            "INSERT INTO outbox(id,organization_id,event_type,payload) "
            "VALUES(%s,%s,'role_change_recorded','{}')",
            (event, org),
        )
    db = Database(os.environ["WORKER_DATABASE_URL"])
    assert process_one(db, org) is True
    assert process_one(db, org) is False
    with db.transaction(org) as conn:
        assert conn.execute("SELECT count(*) AS n FROM event_receipts").fetchone()["n"] == 1
    import pytest

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with db.transaction(org) as conn:
            conn.execute("SELECT * FROM sessions")
    db.close()


def test_expired_lease_recovered_and_concurrent_delivery_is_idempotent():
    from concurrent.futures import ThreadPoolExecutor

    org, event = uuid4(), uuid4()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        conn.execute("INSERT INTO organizations VALUES(%s,'Worker recovery test')", (org,))
        conn.execute(
            "INSERT INTO outbox(id,organization_id,event_type,payload,leased_until,attempts) "
            "VALUES(%s,%s,'role_change_recorded','{}',now()-interval '1 second',1)",
            (event, org),
        )
    db = Database(os.environ["WORKER_DATABASE_URL"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: process_one(db, org), range(2)))
    assert sorted(outcomes) == [False, True]
    with db.transaction(org) as conn:
        assert conn.execute("SELECT count(*) AS n FROM event_receipts").fetchone()["n"] == 1
        row = conn.execute(
            "SELECT attempts,processed_at FROM outbox WHERE id=%s", (event,)
        ).fetchone()
        assert row["attempts"] == 2 and row["processed_at"] is not None
    db.close()
