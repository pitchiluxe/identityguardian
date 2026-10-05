"""Privileged local migration/bootstrap command; never used by the API."""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ORG = UUID("10000000-0000-4000-8000-000000000001")
ENV = UUID("20000000-0000-4000-8000-000000000001")


def status(conn, verify_audit):
    """Operator summary: counts and integrity only, never tenant content. Exit 1 on problems."""
    from apps.api.app.routes.audit_chain import verify_chain

    applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    missing = sorted(p.name for p in (ROOT / "migrations").glob("*.sql") if p.name not in applied)
    outbox = conn.execute(
        "SELECT count(*) FILTER (WHERE processed_at IS NULL), "
        "coalesce(extract(epoch FROM now()-min(created_at) FILTER (WHERE processed_at IS NULL)),0), "
        "count(*) FILTER (WHERE processed_at IS NULL AND attempts>=5) FROM outbox"
    ).fetchone()
    report = dict(
        migrations_applied=len(applied),
        migrations_missing=missing,
        organizations=conn.execute("SELECT count(*) FROM organizations").fetchone()[0],
        outbox_pending=outbox[0],
        outbox_oldest_pending_seconds=round(float(outbox[1])),
        outbox_retrying_events=outbox[2],
    )
    problems = bool(missing) or outbox[2] > 0
    if verify_audit:
        broken = []
        conn.row_factory = dict_row
        for (org,) in conn.execute("SELECT id FROM organizations").fetchall():
            with conn.transaction():
                conn.execute("SELECT set_config('app.org', %s, true)", (str(org),))
                if verify_chain(conn)["result"] != "INTACT":
                    broken.append(str(org))
        report["audit_chains_broken"] = broken
        problems = problems or bool(broken)
    report["status"] = "ATTENTION" if problems else "OK"
    print(json.dumps(report, indent=2))
    return 1 if problems else 0


def rotate_master_key(conn, settings, organization=None):
    """Re-wrap connector secrets under SECRET_MASTER_KEY, opening with retired keys from
    SECRET_MASTER_KEY_PREVIOUS. Idempotent; secrets are never printed. Returns counts; an
    envelope whose key is not configured is reported, never skipped silently."""
    from cryptography.exceptions import InvalidTag

    from apps.api.app.secrets_envelope import rewrap

    counts = dict(rewrapped=0, current=0, unavailable=0)
    rows = conn.execute(
        "SELECT id, organization_id, secret_envelope FROM connectors "
        "WHERE secret_envelope IS NOT NULL AND (%s::uuid IS NULL OR organization_id=%s)",
        (organization, organization),
    ).fetchall()
    for connector_id, org, envelope in rows:
        with conn.transaction():
            conn.execute("SELECT set_config('app.org', %s, true)", (str(org),))
            try:
                updated = rewrap(
                    envelope,
                    settings.secret_master_key,
                    f"connector:{connector_id}",
                    settings.secret_master_key_previous,
                )
            except (ValueError, InvalidTag):
                counts["unavailable"] += 1
                continue
            if updated is None:
                counts["current"] += 1
                continue
            conn.execute(
                "UPDATE connectors SET secret_envelope=%s WHERE id=%s",
                (Jsonb(updated), connector_id),
            )
            conn.execute(
                "INSERT INTO audit_events(id,organization_id,action,target,justification,result,"
                "correlation_id) VALUES(gen_random_uuid(),%s,'connector.secret_rewrapped',%s,"
                "'Operator master-key rotation','succeeded',gen_random_uuid())",
                (org, str(connector_id)),
            )
            counts["rewrapped"] += 1
    return counts


SYSTEM_INVITER = UUID("00000000-0000-4000-8000-00000000b007")


def rotate_ai_keys(conn, settings, user=None):
    """Re-wrap users' AI provider keys (Phase 24) under SECRET_MASTER_KEY. Same contract as
    rotate_master_key: idempotent, never prints keys, and reports envelopes it cannot open."""
    from cryptography.exceptions import InvalidTag

    from apps.api.app.ai.registry import key_context
    from apps.api.app.secrets_envelope import rewrap

    counts = dict(rewrapped=0, current=0, unavailable=0)
    rows = conn.execute(
        "SELECT user_id, provider, envelope FROM user_ai_keys "
        "WHERE (%s::uuid IS NULL OR user_id=%s)",
        (user, user),
    ).fetchall()
    for user_id, provider, envelope in rows:
        try:
            updated = rewrap(
                envelope,
                settings.secret_master_key,
                key_context(user_id, provider),
                settings.secret_master_key_previous,
            )
        except (ValueError, InvalidTag):
            counts["unavailable"] += 1
            continue
        if updated is None:
            counts["current"] += 1
            continue
        conn.execute(
            "UPDATE user_ai_keys SET envelope=%s WHERE user_id=%s AND provider=%s",
            (Jsonb(updated), user_id, provider),
        )
        counts["rewrapped"] += 1
    return counts


def init_organization(conn, name, admin_email, approver_email, allow_additional=False):
    """Create a real organization, its PRODUCTION environment and two one-time bootstrap invites:
    the first org_admin and an independent approver. Without the approver, privileged invites,
    role changes and approvals could never be completed (two-person rule)."""
    from datetime import datetime, timedelta, timezone

    from apps.api.app.routes.invites import invite_digest
    from apps.api.app.security import digest

    name = name.strip()
    emails = [e.strip().lower() for e in (admin_email, approver_email)]
    if not name:
        raise SystemExit("Organization name is required.")
    if emails[0] == emails[1]:
        raise SystemExit("The approver must be a different person from the administrator.")
    conn.execute("SELECT pg_advisory_xact_lock(10002)")
    if not allow_additional and conn.execute("SELECT 1 FROM organizations").fetchone():
        raise SystemExit("Organizations already exist; pass --allow-additional to add another.")
    org, env = uuid4(), uuid4()
    expires = datetime.now(timezone.utc) + timedelta(hours=72)
    conn.execute("SELECT set_config('app.org', %s, true)", (str(org),))
    conn.execute("INSERT INTO organizations VALUES (%s,%s)", (org, name))
    conn.execute(
        "INSERT INTO environments(id,organization_id,name,kind) "
        "VALUES (%s,%s,'Production','PRODUCTION')",
        (env, org),
    )
    audit_sql = (
        "INSERT INTO audit_events(id,organization_id,actor_id,action,target,after_state,"
        "justification,result,correlation_id) VALUES (gen_random_uuid(),%s,%s,%s,%s,%s,"
        "'Operator init-organization','succeeded',gen_random_uuid())"
    )
    conn.execute(
        audit_sql,
        (org, SYSTEM_INVITER, "organization.initialized", str(org), Jsonb({"name": name})),
    )
    paths = {}
    for email, role in zip(emails, ("org_admin", "approver")):
        invite, token = uuid4(), secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO invites(id,organization_id,email_normalized,roles,token_hash,inviter_id,"
            "digest,justification,status,expires_at,bootstrap) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,true)",
            (
                invite,
                org,
                email,
                [role],
                digest(token),
                SYSTEM_INVITER,
                invite_digest(org, email, role, expires.isoformat()),
                f"Operator bootstrap of the first {role}",
                expires,
            ),
        )
        conn.execute(
            audit_sql,
            (
                org,
                SYSTEM_INVITER,
                "invite.created",
                str(invite),
                Jsonb({"email": email, "roles": [role], "status": "ACTIVE", "bootstrap": True}),
            ),
        )
        paths[role] = f"/invite/{token}"
    return dict(
        organization_id=org,
        environment_id=env,
        invite_path=paths["org_admin"],
        approver_invite_path=paths["approver"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "migrate",
            "bootstrap",
            "analyze",
            "status",
            "rotate-master-key",
            "init-organization",
        ],
    )
    parser.add_argument("--name", help="init-organization: organization name")
    parser.add_argument("--admin-email", help="init-organization: first administrator's email")
    parser.add_argument(
        "--approver-email", help="init-organization: first approver (different person)"
    )
    parser.add_argument("--allow-additional", action="store_true", help="init-organization")
    parser.add_argument("--organization", type=UUID, help="rotate-master-key: one organization")
    parser.add_argument("--verify-audit", action="store_true", help="status: verify audit chains")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    from apps.api.app.config import Settings, secret

    if args.command == "bootstrap" and not Settings().development:
        # Refuse before touching the database: synthetic data never reaches a production DB.
        raise SystemExit("bootstrap creates SYNTHETIC data and is disabled outside development")
    with psycopg.connect(secret("MIGRATION_DATABASE_URL"), connect_timeout=5) as conn:
        if args.command == "status":
            raise SystemExit(status(conn, args.verify_audit))
        if args.command == "init-organization":
            if not (args.name and args.admin_email and args.approver_email):
                raise SystemExit(
                    "init-organization needs --name, --admin-email and --approver-email"
                )
            made = init_organization(
                conn, args.name, args.admin_email, args.approver_email, args.allow_additional
            )
            print(f"Organization {made['organization_id']} created with a Production environment.")
            print(f"First administrator invite (single use, 72 hours): {made['invite_path']}")
            print(f"First approver invite (single use, 72 hours): {made['approver_invite_path']}")
            print("Prefix it with APP_ORIGIN and send it only to that person.")
            return
        if args.command == "rotate-master-key":
            from apps.api.app.config import Settings

            counts = rotate_master_key(conn, Settings(), args.organization)
            ai = rotate_ai_keys(conn, Settings()) if args.organization is None else None
            print(json.dumps(dict(connectors=counts, ai_keys=ai)))
            raise SystemExit(1 if counts["unavailable"] or (ai and ai["unavailable"]) else 0)
        if args.command == "analyze":
            # Refresh planner statistics after bulk loads; stale statistics produce bad plans.
            conn.execute("ANALYZE")
            print("Statistics refreshed.")
            return
        if args.command == "migrate":
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY)")
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='guardian_app'").fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE guardian_app LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS"
                    ).format(sql.Literal(secret("RUNTIME_PASSWORD")))
                )
            if not conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname='guardian_worker'"
            ).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE guardian_worker LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS"
                    ).format(sql.Literal(secret("WORKER_PASSWORD")))
                )
            for path in sorted((ROOT / "migrations").glob("*.sql")):
                if not conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)
                ).fetchone():
                    conn.execute(path.read_text(), prepare=False)
                    conn.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))
                    print("Applied", path.name)
        else:
            conn.execute("SELECT pg_advisory_xact_lock(10001)")
            if conn.execute("SELECT 1 FROM organizations").fetchone():
                raise SystemExit("Bootstrap already completed; refusing to overwrite memberships.")
            conn.execute(
                "INSERT INTO organizations VALUES (%s,'Contoso Global Technologies')", (ORG,)
            )
            conn.execute(
                "INSERT INTO environments VALUES (%s,%s,'Foundation sandbox','LAB')", (ENV, ORG)
            )
            for person in json.loads((ROOT / ".local/bootstrap.json").read_text()):
                conn.execute(
                    "INSERT INTO users VALUES (%s,%s,%s,%s)",
                    (
                        person["id"],
                        os.environ["OIDC_ISSUER_URL"],
                        person["id"],
                        person["username"].title() + " Contoso",
                    ),
                )
                conn.execute(
                    "INSERT INTO memberships(organization_id,user_id,roles) VALUES (%s,%s,%s)",
                    (ORG, person["id"], person["roles"]),
                )
            conn.execute(
                "INSERT INTO audit_events(id,organization_id,action,target,justification,result,correlation_id) "
                "VALUES(gen_random_uuid(),%s,'organization.bootstrap',%s,'Explicit local synthetic bootstrap','succeeded',gen_random_uuid())",
                (ORG, str(ORG)),
            )
            print("Bootstrapped synthetic organization; no production connection.")


if __name__ == "__main__":
    main()
