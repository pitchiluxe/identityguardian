"""Backup and restore drill (Phase 20). Privileged operator command; never used by the API.

    python -m scripts.backup backup           # pg_dump archive + SHA-256 manifest in backups/
    python -m scripts.backup drill [archive]  # verify, restore to a scratch database, compare, drop

The archive and the row counts in its manifest come from one exported snapshot, so the drill can
demand exact equality. Passwords go to the PostgreSQL tools through PGPASSWORD, never argv.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess  # noqa: S404 - fixed PostgreSQL client binaries, no shell
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BACKUPS = ROOT / "backups"


def tool(name):
    """PostgreSQL client binary from POSTGRES_BIN, PATH, or the default Windows install."""
    if os.environ.get("POSTGRES_BIN"):
        found = shutil.which(name, path=os.environ["POSTGRES_BIN"])
    else:
        found = shutil.which(name) or shutil.which(name, path=r"C:\Program Files\PostgreSQL\17\bin")
    if not found:
        raise SystemExit(f"{name} not found; set POSTGRES_BIN")
    return found


def connection_args(url, database=None):
    parsed = urlparse(url)
    env = {**os.environ, "PGPASSWORD": unquote(parsed.password or "")}
    args = ["-h", parsed.hostname or "127.0.0.1", "-p", str(parsed.port or 5432)]
    args += ["-U", unquote(parsed.username or ""), "-d", database or parsed.path.lstrip("/")]
    return args, env


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def table_counts(conn):
    tables = conn.execute(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ).fetchall()
    return {
        t["tablename"]: conn.execute(
            sql.SQL("SELECT count(*) AS n FROM {}.{}").format(
                sql.Identifier(t["schemaname"]), sql.Identifier(t["tablename"])
            )
        ).fetchone()["n"]
        for t in tables
    }


def backup(url):
    BACKUPS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archive = BACKUPS / f"identityguardian-{stamp}.dump"
    started = time.time()
    # Hold a snapshot open so the dump and the manifest counts describe the same instant.
    with psycopg.connect(url, row_factory=dict_row, autocommit=False) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        snapshot = conn.execute("SELECT pg_export_snapshot() AS s").fetchone()["s"]
        args, env = connection_args(url)
        subprocess.run(  # noqa: S603 - fixed binary and arguments
            [tool("pg_dump"), *args, "-Fc", "--snapshot", snapshot, "-f", str(archive)],
            env=env,
            check=True,
        )
        counts = table_counts(conn)
    manifest = dict(
        archive=archive.name,
        sha256=sha256(archive),
        bytes=archive.stat().st_size,
        created_utc=stamp,
        seconds=round(time.time() - started, 1),
        tables=counts,
    )
    archive.with_suffix(".json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: v for k, v in manifest.items() if k != "tables"}, indent=2))
    return archive


def verify_archive(archive, manifest):
    """Raise if the archive is not byte-identical to what the manifest recorded."""
    actual = sha256(archive)
    if actual != manifest["sha256"]:
        raise ValueError(f"Checksum mismatch for {archive.name}: archive altered or corrupt")


def compare_counts(expected, actual):
    """Tables whose restored row count differs (missing tables count as differing)."""
    names = set(expected) | set(actual)
    return sorted(n for n in names if expected.get(n) != actual.get(n))


def drill(url, archive=None):
    from apps.api.app.routes.audit_chain import verify_chain

    archive = archive or max(BACKUPS.glob("identityguardian-*.dump"), default=None)
    if archive is None:
        raise SystemExit("No archive found; run backup first")
    manifest = json.loads(archive.with_suffix(".json").read_text())
    started = time.time()
    verify_archive(archive, manifest)
    scratch = f"ig_restore_drill_{int(time.time())}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch)))
    report = dict(archive=archive.name, scratch_database=scratch)
    try:
        args, env = connection_args(url, scratch)
        subprocess.run(  # noqa: S603 - fixed binary and arguments
            [tool("pg_restore"), *args, "--exit-on-error", "--no-owner", str(archive)],
            env=env,
            check=True,
        )
        report["restore_seconds"] = round(time.time() - started, 1)
        restored_url = urlparse(url)._replace(path="/" + scratch).geturl()
        with psycopg.connect(restored_url, row_factory=dict_row) as conn:
            mismatched = compare_counts(manifest["tables"], table_counts(conn))
            broken = []
            organizations = conn.execute("SELECT id FROM organizations").fetchall()
            for row in organizations:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.org', %s, true)", (str(row["id"]),))
                    if verify_chain(conn)["result"] != "INTACT":
                        broken.append(str(row["id"]))
        report.update(
            tables=len(manifest["tables"]),
            rows=sum(manifest["tables"].values()),
            tables_mismatched=mismatched,
            organizations=len(organizations),
            audit_chains_broken=broken,
        )
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(scratch)))
    report["total_seconds"] = round(time.time() - started, 1)
    report["result"] = "PASS" if not mismatched and not broken else "FAIL"
    print(json.dumps(report, indent=2))
    return report


def main():
    from apps.api.app.config import secret

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backup", "drill"])
    parser.add_argument("archive", nargs="?", type=Path)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    url = secret("MIGRATION_DATABASE_URL")
    if args.command == "backup":
        backup(url)
    else:
        raise SystemExit(0 if drill(url, args.archive)["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
