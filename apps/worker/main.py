"""Durable local receipt worker. No notification or IAM connector side effects."""

import argparse
import os
import time
from uuid import UUID

from dotenv import load_dotenv

from apps.api.app.db import Database


def process_one(db: Database, organization_id: UUID) -> bool:
    with db.transaction(organization_id) as conn:
        event = conn.execute(
            "SELECT id FROM outbox WHERE processed_at IS NULL "
            "AND (leased_until IS NULL OR leased_until<now()) "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if not event:
            return False
        conn.execute(
            "UPDATE outbox SET leased_until=now()+interval '30 seconds',"
            "attempts=attempts+1 WHERE id=%s",
            (event["id"],),
        )
    # A crash after claim leaves an expiring lease. Receipt and completion commit atomically.
    with db.transaction(organization_id) as conn:
        conn.execute("SELECT id FROM outbox WHERE id=%s FOR UPDATE", (event["id"],))
        conn.execute(
            "INSERT INTO event_receipts(event_id,organization_id) VALUES(%s,%s) "
            "ON CONFLICT(event_id) DO NOTHING",
            (event["id"], organization_id),
        )
        conn.execute(
            "UPDATE outbox SET processed_at=now(),leased_until=NULL WHERE id=%s", (event["id"],)
        )
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    db = Database(os.environ["WORKER_DATABASE_URL"])
    while True:
        process_one(db, args.organization)
        if args.once:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
