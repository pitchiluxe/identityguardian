"""Phase 19: the snapshot cache returns exactly the uncached result and invalidates on change."""

import os

import psycopg
import pytest

from apps.api.app.db import Database
from apps.api.app.domain import graph
from tests.api.support import source_update, sync


def ids(snap):
    return sorted(snap.nodes), sorted(e.id for e in snap.edges)


def test_cache_equals_uncached_and_invalidates(client, twin):
    db = Database(os.environ["DATABASE_URL"], max_size=1)
    try:
        with db.transaction(twin["org"]) as conn:
            for when in [None, "2026-05-01T00:00:00Z", "2026-09-15T00:00:00Z"]:
                fresh = graph.load(conn, twin["env"], when, use_cache=False)
                first = graph.load(conn, twin["env"], when)
                hits = graph.cache_stats["hits"]
                second = graph.load(conn, twin["env"], when)
                assert ids(fresh) == ids(first) == ids(second) and fresh.version == second.version
                assert graph.cache_stats["hits"] == hits + 1
            before = graph.load(conn, twin["env"])

        def remove(body):
            body["valid_to"] = "2026-09-29T12:00:00+00:00"
            return body, True

        source_update(twin["env"], "mem-erick-grp-finance-legacy", remove)
        sync(client, twin)
        with db.transaction(twin["org"]) as conn:
            after = graph.load(conn, twin["env"])
            assert after.version != before.version
            assert ids(after) == ids(graph.load(conn, twin["env"], use_cache=False))
            assert len(after.edges) == len(before.edges) - 1
    finally:
        db.close()


def test_cache_never_crosses_environments(client, twin):
    db = Database(os.environ["DATABASE_URL"], max_size=1)
    try:
        with db.transaction(twin["org"]) as conn:
            populated = graph.load(conn, twin["env"])
        with db.transaction(twin["other"]) as conn:
            empty = graph.load(conn, twin["other_env"])
        assert populated.nodes and not empty.nodes and populated.version != empty.version
    finally:
        db.close()


def test_warm_cache_never_serves_another_tenant(client, twin):
    """The version is computed under the caller's RLS context, so a foreign tenant asking for a
    cached environment id derives a different key and loads nothing."""
    db = Database(os.environ["DATABASE_URL"], max_size=1)
    try:
        with db.transaction(twin["org"]) as conn:
            warm = graph.load(conn, twin["env"])
            assert graph.load(conn, twin["env"]).version == warm.version and warm.nodes
        with db.transaction(twin["other"]) as conn:
            foreign = graph.load(conn, twin["env"])
        assert not foreign.nodes and not foreign.edges and foreign.version != warm.version
    finally:
        db.close()


def test_any_graph_write_changes_version(client, twin):
    """Invalidation is enforced by triggers, not by the ingest code path (migration 021)."""
    db = Database(os.environ["DATABASE_URL"], max_size=1)
    try:
        with db.transaction(twin["org"]) as conn:
            before = graph.load(conn, twin["env"])
        with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
            conn.execute(
                """UPDATE node_revisions SET attributes=attributes || '{"probe": true}' """
                "WHERE node_id=(SELECT id FROM twin_nodes WHERE environment_id=%s "
                "AND external_id='idn-tom') AND recorded_to IS NULL",
                (twin["env"],),
            )
        with db.transaction(twin["org"]) as conn:
            after = graph.load(conn, twin["env"])
        assert after.version != before.version
        assert after.by_external("idn-tom").attributes.get("probe") is True
    finally:
        db.close()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE graph_watermarks SET changes=0",
        "INSERT INTO graph_watermarks VALUES (%(org)s, %(env)s, 0)",
        "SELECT graph_touch(%(org)s, %(env)s)",
    ],
)
def test_runtime_role_cannot_forge_watermark(client, twin, statement):
    db = Database(os.environ["DATABASE_URL"], max_size=1)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.transaction(twin["org"]) as conn:
                conn.execute(statement, dict(org=twin["org"], env=twin["env"]))
    finally:
        db.close()
