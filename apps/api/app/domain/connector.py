"""Sandbox connector write path (INTEGRATIONS.md contract): validate, apply exact approved
operation, read back. Writes go to the simulated source system only, never to the twin.
"""

from datetime import datetime, timezone

from ..jsonutil import jsonb as Jsonb


class ConnectorError(Exception):
    """Definitive failure: the source was not changed."""


def consume_fault(conn, environment_id, operation):
    """Consume one injected fault in its own transaction (so a failed write cannot replay it)."""
    row = conn.execute(
        "SELECT mode, remaining FROM sandbox_faults WHERE environment_id=%s AND operation=%s "
        "AND remaining>0 FOR UPDATE",
        (environment_id, operation),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE sandbox_faults SET remaining=remaining-1 WHERE environment_id=%s "
            "AND operation=%s",
            (environment_id, operation),
        )
        return row["mode"]
    return None


def _version(conn):
    return conn.execute("SELECT nextval('sandbox_version_seq') AS v").fetchone()["v"]


def remove_relationship(conn, environment_id, external_id, effective_at=None, fault=None):
    """Idempotent: an already-removed relationship is reported as applied."""
    effective_at = effective_at or datetime.now(timezone.utc)
    if fault == "fail_before_write":
        raise ConnectorError("Sandbox source rejected the removal (injected fault)")
    row = conn.execute(
        "SELECT body, deleted FROM sandbox_objects WHERE environment_id=%s AND object_id=%s FOR UPDATE",
        (environment_id, external_id),
    ).fetchone()
    if not row:
        raise ConnectorError("Relationship does not exist at the source")
    if not row["deleted"]:
        body = dict(row["body"], valid_to=effective_at.isoformat())
        conn.execute(
            "UPDATE sandbox_objects SET body=%s, deleted=true, version=%s, updated_at=now() "
            "WHERE environment_id=%s AND object_id=%s",
            (Jsonb(body), _version(conn), environment_id, external_id),
        )
    return dict(
        operation="remove_relationship",
        object_id=external_id,
        effective_at=effective_at.isoformat(),
        lost_response=fault == "timeout_after_write",
    )


def add_relationship(
    conn,
    organization_id,
    environment_id,
    object_id,
    rel_type,
    src,
    dst,
    attributes,
    effective_at=None,
    fault=None,
):
    effective_at = effective_at or datetime.now(timezone.utc)
    if fault == "fail_before_write":
        raise ConnectorError("Sandbox source rejected the grant (injected fault)")
    existing = conn.execute(
        "SELECT 1 FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
        (environment_id, object_id),
    ).fetchone()
    if not existing:
        body = dict(
            type="relationship",
            id=object_id,
            rel=rel_type,
            src=src,
            dst=dst,
            valid_from=effective_at.isoformat(),
            valid_to=None,
            attributes=attributes,
        )
        conn.execute(
            "INSERT INTO sandbox_objects(organization_id,environment_id,object_id,object_type,body,"
            "version) VALUES(%s,%s,%s,'relationship',%s,%s)",
            (organization_id, environment_id, object_id, Jsonb(body), _version(conn)),
        )
    return dict(
        operation="add_relationship",
        object_id=object_id,
        effective_at=effective_at.isoformat(),
        lost_response=fault == "timeout_after_write",
    )


def read_back(conn, environment_id, object_id):
    row = conn.execute(
        "SELECT body, deleted, version FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
        (environment_id, object_id),
    ).fetchone()
    return (
        None
        if not row
        else dict(
            present=not row["deleted"],
            deleted=row["deleted"],
            version=row["version"],
            valid_to=row["body"].get("valid_to"),
        )
    )
