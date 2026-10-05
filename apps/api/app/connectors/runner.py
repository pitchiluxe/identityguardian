"""Connector sync jobs (worker). Each page commits atomically with its sync-run progress, so a
failure leaves a resumable cursor and never implies that unseen objects were deleted."""

import logging
import time
from uuid import UUID, uuid4

from ..domain.ingest import ORDER, Ingestor
from ..jsonutil import jsonb as Jsonb
from .base import ConnectorUnavailable, RateLimited
from .providers import build

MAX_RETRIES = 3


log = logging.getLogger("identityguardian.connectors")


def start_run(conn, connector, environment, actor_id, mode):
    previous = conn.execute(
        "SELECT * FROM sync_runs WHERE connector_id=%s ORDER BY started_at DESC LIMIT 1",
        (connector["id"],),
    ).fetchone()
    resume = (
        mode == "resume"
        and previous
        and previous["status"] == "PARTIAL"
        and previous["cursor_token"]
    )
    coverage = (
        "complete_authoritative" if mode == "full" and connector["authoritative"] else "partial"
    )
    run_id = uuid4()
    conn.execute(
        "INSERT INTO sync_runs(id,organization_id,environment_id,connector_id,actor_id,status,coverage,"
        "cursor_token) VALUES(%s,%s,%s,%s,%s,'RUNNING',%s,%s)",
        (
            run_id,
            environment["organization_id"],
            environment["id"],
            connector["id"],
            actor_id,
            coverage,
            previous["cursor_token"] if resume else None,
        ),
    )
    return run_id, (previous["cursor_token"] if resume else None)


def run_job(db, org: UUID, connector_id: UUID, mode: str, actor_id=None, backoff=0.05):
    with db.transaction(org) as conn:
        connector = conn.execute("SELECT * FROM connectors WHERE id=%s", (connector_id,)).fetchone()
        environment = conn.execute(
            "SELECT * FROM environments WHERE id=%s", (connector["environment_id"],)
        ).fetchone()
        run_id, cursor = start_run(conn, connector, environment, actor_id, mode)
    failed = lambda reason, totals=None, cursor=None, pages=0, retries=0: finish(  # noqa: E731
        db,
        org,
        connector,
        run_id,
        "PARTIAL",
        totals or dict(observed=0, unchanged=0, created=0, updated=0, tombstoned=0, rejected=0),
        cursor,
        pages,
        retries,
        [dict(object="(connector)", reason=reason)],
        "FAILING",
    )
    try:
        impl = build(connector)
    except ConnectorUnavailable as exc:
        return failed(str(exc))
    except Exception:  # noqa: BLE001 - never leave a RUNNING run and a redelivery loop behind
        log.exception("Connector %s could not be built", connector_id)
        return failed("Connector could not be started; see the worker log")
    seen, totals, retries, pages = (
        set(),
        dict(observed=0, unchanged=0, created=0, updated=0, tombstoned=0, rejected=0),
        0,
        0,
    )
    errors = []
    ingestor = None
    while True:
        attempt = 0
        while True:
            try:
                page = impl.read(cursor)
                break
            except RateLimited as exc:
                attempt += 1
                retries += 1
                if attempt > MAX_RETRIES:
                    return finish(
                        db,
                        org,
                        connector,
                        run_id,
                        "PARTIAL",
                        totals,
                        cursor,
                        pages,
                        retries,
                        errors + [dict(object="(page)", reason=str(exc))],
                        "DEGRADED",
                    )
                time.sleep(backoff * 2**attempt)  # bounded exponential backoff
            except Exception as exc:  # noqa: BLE001 - outside the connector contract
                if not isinstance(exc, ConnectorUnavailable):
                    log.exception("Connector %s failed unexpectedly", connector_id)
                    exc = ConnectorUnavailable("Connector failed unexpectedly; see the worker log")
                return finish(
                    db,
                    org,
                    connector,
                    run_id,
                    "PARTIAL",
                    totals,
                    cursor,
                    pages,
                    retries,
                    errors + [dict(object="(page)", reason=str(exc))],
                    "FAILING",
                )
        with db.transaction(org) as conn:
            if ingestor is None:  # existing state is loaded once per job, then kept current
                ingestor = Ingestor(conn, environment, run_id, source=connector["kind"]).prefetch()
            ingestor.conn = conn
            before = dict(ingestor.counts)
            errors_before = len(ingestor.errors)
            for row in sorted(page.objects, key=lambda r: (ORDER[r["object_type"]], r["version"])):
                ingestor.apply(row)
                seen.add(row["object_id"])
            for k, v in ingestor.counts.items():
                totals[k] += v - before[k]
            errors += ingestor.errors[errors_before:]
            pages += 1
            conn.execute(
                "UPDATE sync_runs SET observed=%s, unchanged=%s, created=%s, updated=%s, rejected=%s, "
                "cursor_token=%s, pages=%s, retries=%s WHERE id=%s",
                (
                    totals["observed"],
                    totals["unchanged"],
                    totals["created"],
                    totals["updated"],
                    totals["rejected"],
                    page.next_cursor,
                    pages,
                    retries,
                    run_id,
                ),
            )
        cursor = page.next_cursor
        if cursor is None:
            break
    with db.transaction(org) as conn:
        run = conn.execute("SELECT coverage FROM sync_runs WHERE id=%s", (run_id,)).fetchone()
        if run["coverage"] == "complete_authoritative":
            ingestor = Ingestor(conn, environment, run_id, source=connector["kind"])
            ingestor.reconcile_absent(seen)
            totals["tombstoned"] += ingestor.counts["tombstoned"]
    status = "PARTIAL" if totals["rejected"] else "SUCCEEDED"
    return finish(
        db,
        org,
        connector,
        run_id,
        status,
        totals,
        None,
        pages,
        retries,
        errors,
        "HEALTHY" if status == "SUCCEEDED" else "DEGRADED",
    )


def finish(db, org, connector, run_id, status, totals, cursor, pages, retries, errors, health):
    with db.transaction(org) as conn:
        conn.execute(
            "UPDATE sync_runs SET status=%s, observed=%s, unchanged=%s, created=%s, updated=%s, tombstoned=%s, "
            "rejected=%s, cursor_token=%s, pages=%s, retries=%s, errors=%s, finished_at=now() WHERE id=%s",
            (
                status,
                totals["observed"],
                totals["unchanged"],
                totals["created"],
                totals["updated"],
                totals["tombstoned"],
                totals["rejected"],
                cursor,
                pages,
                retries,
                Jsonb(errors[:50]),
                run_id,
            ),
        )
        conn.execute(
            "UPDATE connectors SET health=%s, last_cursor=%s WHERE id=%s",
            (health, cursor, connector["id"]),
        )
    return status
