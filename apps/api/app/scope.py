"""Request scope: session -> active membership -> capability -> environment in that organization."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb

from .auth import authenticate, membership


@dataclass
class Scope:
    conn: object
    user: dict
    member: dict
    org: UUID
    environment: dict | None
    correlation: UUID

    @property
    def env_id(self):
        return self.environment["id"]

    @property
    def user_id(self):
        return self.user["user_id"]

    def audit(
        self,
        action,
        target,
        justification,
        before=None,
        after=None,
        approval=None,
        result="succeeded",
    ):
        self.conn.execute(
            "INSERT INTO audit_events(id,organization_id,actor_id,action,target,before_state,"
            "after_state,justification,approval_id,result,correlation_id) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                self.org,
                self.user_id,
                action,
                str(target),
                Jsonb(before or {}),
                Jsonb(after or {}),
                justification,
                approval,
                result,
                self.correlation,
            ),
        )


@contextmanager
def scoped(request: Request, org: UUID, env: UUID | None, capability: str):
    user = authenticate(request)
    with request.app.state.db.transaction(org) as conn:
        member = membership(conn, user["user_id"], capability)
        environment = None
        if env is not None:
            environment = conn.execute("SELECT * FROM environments WHERE id=%s", (env,)).fetchone()
            if not environment:
                raise HTTPException(404, "Environment not found")
        yield Scope(conn, user, member, org, environment, request.state.correlation)


def envelope(scope: Scope, data, snapshot=None, completeness=None, evidence_ids=None, **extra):
    body = dict(
        data=data,
        correlation_id=str(scope.correlation),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    if scope.environment:
        body["environment"] = dict(
            id=str(scope.environment["id"]),
            name=scope.environment["name"],
            kind=scope.environment["kind"],
        )
    if snapshot is not None:
        body["snapshot"] = snapshot.describe()
    if completeness is not None:
        body["completeness"] = completeness
    if evidence_ids is not None:
        body["evidence_ids"] = sorted(set(evidence_ids))
    body.update(extra)
    return body
