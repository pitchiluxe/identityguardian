import os
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv

from apps.api.app.db import Database

load_dotenv()
pytestmark = pytest.mark.integration


@pytest.fixture
def database():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("Run scripts/local_setup.py and scripts/manage.py migrate first")
    return Database(url)


def test_runtime_cannot_read_other_organization_or_unscoped_rows(database):
    with database.transaction() as conn:
        assert conn.execute("SELECT * FROM organizations").fetchall() == []
    with database.transaction(str(uuid4())) as conn:
        assert conn.execute("SELECT * FROM memberships").fetchall() == []
    with database.transaction() as conn:
        row = conn.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert not row["rolsuper"] and not row["rolbypassrls"]


def test_audit_cannot_be_updated_or_deleted(database):
    for operation in ("DELETE FROM audit_events", "UPDATE audit_events SET result='forged'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with database.transaction() as conn:
                conn.execute(operation)


def test_runtime_cannot_promote_itself_without_api_or_cross_scope(database):
    with database.transaction() as conn:
        assert (
            conn.execute(
                "UPDATE memberships SET roles=ARRAY['org_admin'] RETURNING user_id"
            ).fetchall()
            == []
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with database.transaction() as conn:
            conn.execute("INSERT INTO organizations VALUES (%s,'forged')", (uuid4(),))
