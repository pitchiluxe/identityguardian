"""Phase 17: authorized, redacted, expiring report exports with evidence and snapshot metadata."""

import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ..domain.reports import REPORT_TYPES, build, redact, to_csv
from ..jsonutil import dumps
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from ..security import digest
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_type: str = Field(pattern="^[a-z_]+$")
    format: Literal["csv", "json"] = "csv"
    redaction: Literal["standard", "full"] = "standard"
    expires_hours: int = Field(24, ge=1, le=168)


@router.get(ENV + "/reports")
def reports(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "report:read") as scope:
        rows = scope.conn.execute(
            "SELECT r.id, r.report_type, r.format, r.redaction, r.created_at, r.expires_at, r.row_count, r.digest, "
            "r.downloads, CASE WHEN r.expires_at<=now() THEN 'EXPIRED' ELSE r.status END AS status, "
            "u.display_name AS created_by_name, r.snapshot FROM report_artifacts r JOIN users u ON u.id=r.created_by "
            "WHERE r.environment_id=%s ORDER BY r.created_at DESC LIMIT 50",
            (env,),
        ).fetchall()
        return envelope(scope, dict(types=REPORT_TYPES, reports=rows))


@router.post(ENV + "/reports", status_code=201)
def create(org: UUID, env: UUID, body: ReportRequest, request: Request):
    if body.report_type not in REPORT_TYPES:
        raise HTTPException(422, "Unknown report type")
    with scoped(request, org, env, "report:create") as scope:
        if body.redaction == "full" and "audit:read" not in scope.caps:
            raise HTTPException(403, "Unredacted exports require audit authority")
        snap = snapshot_for(scope)
        columns, rows, notes = build(body.report_type, snap, scope.conn, scope.env_id)
        rows = [{c: redact(row.get(c), c, body.redaction) for c in columns} for row in rows]
        created = datetime.now(timezone.utc)
        metadata = dict(
            report=REPORT_TYPES[body.report_type],
            environment=scope.environment["name"],
            environment_kind=scope.environment["kind"],
            generated_at=created.isoformat(),
            effective_at=snap.effective_at.isoformat(),
            known_at=snap.known_at.isoformat(),
            graph_version=snap.version,
            redaction=body.redaction,
            rows=len(rows),
            notes=" | ".join(notes) or "none",
            data="SYNTHETIC" if scope.environment["kind"] != "PRODUCTION" else "",
        )
        content = (
            to_csv(columns, rows, metadata)
            if body.format == "csv"
            else json.dumps(
                dict(metadata=metadata, columns=columns, rows=json.loads(dumps(rows))), indent=2
            )
        )
        row = scope.conn.execute(
            "INSERT INTO report_artifacts(id,organization_id,environment_id,report_type,format,redaction,created_by,"
            "created_at,expires_at,snapshot,row_count,content,digest) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id, report_type, format, redaction, created_at, expires_at, row_count, digest",
            (
                uuid4(),
                org,
                env,
                body.report_type,
                body.format,
                body.redaction,
                scope.user_id,
                created,
                created + timedelta(hours=body.expires_hours),
                Jsonb(dict(snap.describe(), notes=notes)),
                len(rows),
                content,
                digest(content),
            ),
        ).fetchone()
        scope.audit(
            "report.created",
            row["id"],
            REPORT_TYPES[body.report_type],
            after=dict(
                format=body.format,
                redaction=body.redaction,
                rows=len(rows),
                expires_at=row["expires_at"].isoformat(),
            ),
        )
        return envelope(scope, row)


@router.get(ENV + "/reports/{report_id}/download")
def download(org: UUID, env: UUID, report_id: UUID, request: Request):
    with scoped(request, org, env, "report:read") as scope:
        row = scope.conn.execute(
            "SELECT * FROM report_artifacts WHERE id=%s AND environment_id=%s", (report_id, env)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Report not found")
        if row["expires_at"] <= datetime.now(timezone.utc) or row["content"] is None:
            raise HTTPException(410, "Report expired; generate a new one")
        if digest(row["content"]) != row["digest"]:
            raise HTTPException(409, "Report integrity check failed")
        scope.conn.execute(
            "UPDATE report_artifacts SET downloads=downloads+1 WHERE id=%s", (report_id,)
        )
        scope.audit(
            "report.downloaded",
            report_id,
            row["report_type"],
            after=dict(redaction=row["redaction"]),
        )
        media = "text/csv; charset=utf-8" if row["format"] == "csv" else "application/json"
        name = f"{row['report_type']}-{row['created_at']:%Y%m%dT%H%M}Z.{row['format']}"
        return Response(
            row["content"],
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "X-Content-SHA256": row["digest"],
            },
        )
