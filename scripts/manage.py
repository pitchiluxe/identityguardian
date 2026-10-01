"""Privileged local migration/bootstrap command; never used by the API."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
ORG = UUID("10000000-0000-4000-8000-000000000001")
ENV = UUID("20000000-0000-4000-8000-000000000001")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "bootstrap"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"], connect_timeout=5) as conn:
        if args.command == "migrate":
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY)")
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='guardian_app'").fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE guardian_app LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS"
                    ).format(sql.Literal(os.environ["RUNTIME_PASSWORD"]))
                )
            if not conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname='guardian_worker'"
            ).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE guardian_worker LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS"
                    ).format(sql.Literal(os.environ["WORKER_PASSWORD"]))
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
