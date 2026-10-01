"""Durable worker: outbox delivery, approved sandbox execution, JIT expiry and reconciliation.

Writes only to the sandbox connector (simulated source) and the twin it ingests. It never talks
to a real identity system. Every action rechecks authorization bindings before dispatch.
"""

import argparse
import logging
import os
import time
from uuid import UUID

from dotenv import load_dotenv

from apps.api.app.connectors.runner import run_job
from apps.api.app.db import Database
from apps.api.app.domain.execution import execute_change, expire_jit, purge_reports, reconcile

log = logging.getLogger("identityguardian.worker")


def process_one(db: Database, organization_id: UUID) -> bool:
    with db.transaction(organization_id) as conn:
        event = conn.execute(
            "SELECT id, event_type, payload FROM outbox WHERE processed_at IS NULL "
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
    if event["event_type"] == "change_execution_requested":
        # Recorded intent makes a crash here safe: re-delivery finds EXECUTING and reconciles.
        execute_change(db, organization_id, UUID(event["payload"]["change_request_id"]))
    elif event["event_type"] == "connector_sync_requested":
        payload = event["payload"]
        actor = UUID(payload["actor"]) if payload.get("actor") else None
        run_job(db, organization_id, UUID(payload["connector_id"]), payload["mode"], actor)
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


def tick(db: Database, organization_id: UUID):
    while process_one(db, organization_id):
        pass
    expire_jit(db, organization_id)
    reconcile(db, organization_id)
    purge_reports(db, organization_id)


def organizations(db: Database):
    with db.transaction() as conn:
        return [
            r["pending_work_organizations"]
            for r in conn.execute("SELECT pending_work_organizations()").fetchall()
        ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", type=UUID, help="limit to one organization")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    db = Database(os.environ["WORKER_DATABASE_URL"])
    while True:
        for org in [args.organization] if args.organization else organizations(db):
            try:
                tick(db, org)
            except Exception:  # keep serving other organizations; the failure is logged
                log.exception("Worker tick failed for organization %s", org)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
