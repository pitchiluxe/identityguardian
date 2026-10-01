"""Start a project-local cluster with an existing Windows PostgreSQL installation."""

import os
import subprocess
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    binaries = Path(os.environ.get("POSTGRES_BIN", r"C:\Program Files\PostgreSQL\17\bin"))
    data = ROOT / ".local" / "postgres"
    if not (data / "PG_VERSION").exists():
        password = ROOT / ".local" / "postgres-init-password"
        password.write_text(os.environ["POSTGRES_PASSWORD"])
        try:
            subprocess.run(
                [
                    str(binaries / "initdb.exe"),
                    "-D",
                    str(data),
                    "-U",
                    "guardian_migrator",
                    "-A",
                    "scram-sha-256",
                    "--pwfile",
                    str(password),
                    "--encoding=UTF8",
                ],
                check=True,
            )
        finally:
            password.unlink(missing_ok=True)
    status = subprocess.run(
        [str(binaries / "pg_ctl.exe"), "-D", str(data), "status"], capture_output=True
    )
    if status.returncode:
        subprocess.run(
            [
                str(binaries / "pg_ctl.exe"),
                "-D",
                str(data),
                "-l",
                str(ROOT / ".local/postgres.log"),
                "-o",
                "-p 55432 -h 127.0.0.1",
                "start",
            ],
            check=True,
        )
    url = os.environ["MIGRATION_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(url, autocommit=True) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname='identityguardian'"
        ).fetchone():
            conn.execute("CREATE DATABASE identityguardian")
    print("Project-local PostgreSQL ready on loopback port 55432.")


if __name__ == "__main__":
    main()
