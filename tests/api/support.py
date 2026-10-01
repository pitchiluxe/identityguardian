"""Helpers that act as the simulated external source (migration role) in tests."""

import os

import psycopg
from psycopg.types.json import Jsonb

MIGRATION = os.environ.get("MIGRATION_DATABASE_URL")


def source_update(env, object_id, change=None, delete_row=False):
    with psycopg.connect(MIGRATION) as conn:
        if delete_row:
            conn.execute(
                "DELETE FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
                (env, object_id),
            )
            return
        body = conn.execute(
            "SELECT body FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
            (env, object_id),
        ).fetchone()[0]
        body, deleted = change(body)
        conn.execute(
            "UPDATE sandbox_objects SET body=%s, deleted=%s, version=nextval('sandbox_version_seq') "
            "WHERE environment_id=%s AND object_id=%s",
            (Jsonb(body), deleted, env, object_id),
        )


def source_add(org, env, obj):
    with psycopg.connect(MIGRATION) as conn:
        conn.execute(
            "INSERT INTO sandbox_objects(organization_id,environment_id,object_id,object_type,body,"
            "version) VALUES(%s,%s,%s,%s,%s,nextval('sandbox_version_seq'))",
            (org, env, obj["id"], obj["type"], Jsonb(obj)),
        )


def membership(oid, who, group, since="2026-01-01T00:00:00+00:00", **attributes):
    attributes.setdefault("origin", "direct_assignment")
    return dict(
        type="relationship",
        id=oid,
        rel="USER_MEMBER_OF_GROUP",
        src=who,
        dst=group,
        valid_from=since,
        valid_to=None,
        attributes=attributes,
    )


def sync(client, twin, mode="incremental"):
    from tests.api.conftest import as_user

    headers = as_user(client, twin["people"], "admin")
    response = client.post(
        twin["base"] + "/connectors/sandbox/sync", json={"mode": mode}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def run_change(client, twin, worker, proposal, finish=True):
    """Propose -> simulate -> submit -> independent approval -> execution -> worker."""
    from uuid import uuid4

    from apps.worker.main import process_one
    from tests.api.conftest import as_user

    def post(who, path, body, status):
        headers = as_user(client, twin["people"], who)
        response = client.post(twin["base"] + path, json=body, headers=headers)
        assert response.status_code == status, response.text
        return response.json()["data"]

    def current(change_id):
        as_user(client, twin["people"], "investigator")
        return client.get(twin["base"] + f"/change-requests/{change_id}").json()["data"]

    created = post(
        "investigator", "/change-requests", dict(proposal, idempotency_key=str(uuid4())), 201
    )
    simulation = post("investigator", "/simulations", {"change_request_id": created["id"]}, 201)
    change = current(created["id"])["change"]
    post(
        "investigator",
        f"/change-requests/{created['id']}/submit",
        {"expected_version": change["version"]},
        200,
    )
    post(
        "approver",
        f"/change-requests/{created['id']}/decision",
        dict(digest=simulation["digest"], decision="APPROVE", justification="Reviewed simulation"),
        200,
    )
    if finish:
        post(
            "operator",
            f"/change-requests/{created['id']}/execute",
            {"digest": simulation["digest"]},
            202,
        )
        process_one(worker, twin["org"])
    return current(created["id"]), simulation
