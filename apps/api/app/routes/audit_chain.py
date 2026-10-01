"""Phase 18: audit chain verification and Ed25519-signed checkpoints for external storage."""

import base64
import json
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_session
from ..scope import envelope, scoped

router = APIRouter(prefix="/api/v1/organizations/{org}", dependencies=[Depends(require_session)])

VERIFY_SQL = (
    "SELECT sequence, hash, prev_hash, lag(hash) OVER (ORDER BY sequence) AS lagged, "
    "encode(sha256(convert_to(prev_hash || '|' || audit_canonical(a), 'UTF8')), 'hex') AS recomputed "
    "FROM audit_events a ORDER BY sequence"
)


def checkpoint_message(org, sequence, digest):
    return json.dumps(
        dict(organization=str(org), sequence=sequence, hash=digest), sort_keys=True
    ).encode()


def signing_key(settings):
    if not settings.audit_signing_key:
        raise HTTPException(409, "Checkpoint signing is not configured (AUDIT_SIGNING_KEY)")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(settings.audit_signing_key))


def public_key_b64(key):
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def verify_chain(conn):
    rows = conn.execute(VERIFY_SQL).fetchall()
    for row in rows:
        if row["hash"] != row["recomputed"] or row["prev_hash"] != (row["lagged"] or "genesis"):
            return dict(result="BROKEN", first_broken_sequence=row["sequence"], events=len(rows))
    head = rows[-1] if rows else None
    return dict(
        result="INTACT",
        events=len(rows),
        head_sequence=head["sequence"] if head else 0,
        head_hash=head["hash"] if head else "genesis",
    )


def verify_checkpoint(conn, checkpoint):
    row = conn.execute(
        "SELECT hash FROM audit_events WHERE sequence=%s", (checkpoint["sequence"],)
    ).fetchone()
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(checkpoint["public_key"]))
    try:
        key.verify(
            base64.b64decode(checkpoint["signature"]),
            checkpoint_message(
                checkpoint["organization_id"], checkpoint["sequence"], checkpoint["hash"]
            ),
        )
        signature = "VALID"
    except InvalidSignature:
        signature = "INVALID"
    matches = bool(row) and row["hash"] == checkpoint["hash"]
    return dict(sequence=checkpoint["sequence"], signature=signature, chain_matches=matches)


@router.get("/audit/verify")
def verify(org: UUID, request: Request):
    with scoped(request, org, None, "audit:read") as scope:
        chain = verify_chain(scope.conn)
        checkpoints = scope.conn.execute(
            "SELECT * FROM audit_checkpoints ORDER BY sequence"
        ).fetchall()
        results = [verify_checkpoint(scope.conn, c) for c in checkpoints]
        ok = chain["result"] == "INTACT" and all(
            r["signature"] == "VALID" and r["chain_matches"] for r in results
        )
        return envelope(
            scope,
            dict(
                chain=chain,
                checkpoints=results,
                result="VERIFIED" if ok else "FAILED",
                limitation="Checkpoints held only in this database can be rewritten by a "
                "database administrator; keep exported copies elsewhere.",
            ),
        )


@router.post("/audit/checkpoints", status_code=201)
def checkpoint(org: UUID, request: Request):
    key = signing_key(request.app.state.settings)
    with scoped(request, org, None, "audit:read") as scope:
        chain = verify_chain(scope.conn)
        if chain["result"] != "INTACT":
            raise HTTPException(
                409, f"Audit chain broken at sequence {chain['first_broken_sequence']}"
            )
        signature = key.sign(checkpoint_message(org, chain["head_sequence"], chain["head_hash"]))
        row = scope.conn.execute(
            "INSERT INTO audit_checkpoints(id,organization_id,sequence,hash,signature,public_key,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                org,
                chain["head_sequence"],
                chain["head_hash"],
                base64.b64encode(signature).decode(),
                public_key_b64(key),
                scope.user_id,
            ),
        ).fetchone()
        return envelope(scope, dict(row, export_note="Store this checkpoint outside the platform."))
