"""Lab actions: allowlisted, validated edits to ONE attempt's sandbox source.

Learners act directly (no approval workflow) because the environment is an isolated LAB clone.
Every action is recorded; validators grade the resulting state and the action log.
"""

from datetime import datetime, timedelta, timezone

from ..domain.ingest import run_sync
from ..jsonutil import jsonb as Jsonb

MFA_METHODS = {"totp", "webauthn", "sms"}
VERIFICATIONS = {"manager_callback", "id_document", "none"}
CONDITIONS = {"mfa_required", "device_compliant", "network_location"}
IDENTITY_KEYS = {"department", "manager", "title"}
ACTIONS = {
    "add_membership": {"identity", "group"},
    "remove_membership": {"identity", "group"},
    "assign_role": {"identity", "role"},
    "remove_role": {"identity", "role"},
    "create_role": {"role", "name", "permissions"},
    "set_identity": {"identity", "attributes"},
    "register_mfa": {"identity", "method"},
    "reset_password": {"identity", "verification"},
    "unlock_account": {"identity"},
    "disable_account": {"identity"},
    "set_owner": {"machine", "owner"},
    "rotate_credential": {"credential"},
    "add_condition": {"relationship", "condition"},
    "configure_sso": {"application", "issuer", "audience", "mappings"},
    "answer": {"question", "value"},
}
OPTIONAL = {"expires_at", "justification", "approver"}


class LabActionError(ValueError):
    pass


def _get(conn, env, object_id):
    row = conn.execute(
        "SELECT body, deleted FROM sandbox_objects WHERE environment_id=%s AND object_id=%s "
        "FOR UPDATE",
        (env, object_id),
    ).fetchone()
    return row


def _version(conn):
    return conn.execute("SELECT nextval('sandbox_version_seq') AS v").fetchone()["v"]


def _put(conn, org, env, body, deleted=False):
    existing = conn.execute(
        "SELECT 1 FROM sandbox_objects WHERE environment_id=%s AND object_id=%s", (env, body["id"])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE sandbox_objects SET body=%s, deleted=%s, version=%s, updated_at=now() "
            "WHERE environment_id=%s AND object_id=%s",
            (Jsonb(body), deleted, _version(conn), env, body["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO sandbox_objects(organization_id,environment_id,object_id,object_type,body,"
            "version) VALUES(%s,%s,%s,%s,%s,%s)",
            (org, env, body["id"], body["type"], Jsonb(body), _version(conn)),
        )


def _node(conn, env, object_id, kind=None):
    row = _get(conn, env, object_id)
    if (
        not row
        or row["deleted"]
        or row["body"].get("type") != "node"
        or (kind and row["body"]["kind"] != kind)
    ):
        raise LabActionError(f"Unknown {kind or 'object'} {object_id}")
    return row["body"]


def update_node(conn, org, env, object_id, changes, kind=None, status=None):
    body = _node(conn, env, object_id, kind)
    now = datetime.now(timezone.utc)
    current = sorted(body["revisions"], key=lambda r: r["valid_from"])[-1]
    revision = dict(
        valid_from=max(now.isoformat(), current["valid_from"]),
        status=status or current["status"],
        attributes=dict(current["attributes"], **changes),
    )
    if revision["valid_from"] == current["valid_from"]:
        body["revisions"] = body["revisions"][:-1] + [revision]
    else:
        body["revisions"] = body["revisions"] + [revision]
    _put(conn, org, env, body)


def relationship(conn, org, env, rel_id, rel, src, dst, attributes):
    now = datetime.now(timezone.utc).isoformat()
    _put(
        conn,
        org,
        env,
        dict(
            type="relationship",
            id=rel_id,
            rel=rel,
            src=src,
            dst=dst,
            valid_from=now,
            valid_to=None,
            attributes=attributes,
        ),
    )


def end_relationship(conn, org, env, rel_id):
    row = _get(conn, env, rel_id)
    if not row or row["deleted"]:
        raise LabActionError("That relationship does not exist in this lab")
    body = dict(row["body"], valid_to=datetime.now(timezone.utc).isoformat())
    _put(conn, org, env, body, deleted=True)


def find_relationship(conn, env, rel, src, dst):
    row = conn.execute(
        "SELECT object_id FROM sandbox_objects WHERE environment_id=%s AND object_type='relationship' "
        "AND NOT deleted AND body->>'rel'=%s AND body->>'src'=%s AND body->>'dst'=%s",
        (env, rel, src, dst),
    ).fetchone()
    return row["object_id"] if row else None


def apply(conn, environment, action: dict):
    kind = action.get("type")
    if kind not in ACTIONS:
        raise LabActionError("Unsupported lab action")
    fields = set(action) - {"type"}
    if not ACTIONS[kind] <= fields or fields - ACTIONS[kind] - OPTIONAL:
        raise LabActionError(f"{kind} requires {sorted(ACTIONS[kind])}")
    org, env = environment["organization_id"], environment["id"]
    extra = {k: action[k] for k in OPTIONAL if k in action}
    if "expires_at" in extra:
        expires = datetime.fromisoformat(extra["expires_at"])
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise LabActionError("expires_at must be a future timestamp with timezone")
        if expires > datetime.now(timezone.utc) + timedelta(hours=8):
            raise LabActionError("Temporary access is limited to 8 hours")
    if kind in {"add_membership", "assign_role"}:
        rel = "USER_MEMBER_OF_GROUP" if kind == "add_membership" else "USER_HAS_ROLE"
        target = action["group"] if kind == "add_membership" else action["role"]
        _node(conn, env, action["identity"], "identity")
        _node(conn, env, target, "group" if kind == "add_membership" else "role")
        if find_relationship(conn, env, rel, action["identity"], target):
            raise LabActionError("Already granted")
        relationship(
            conn,
            org,
            env,
            f"lab-{kind}-{action['identity']}-{target}",
            rel,
            action["identity"],
            target,
            dict(
                origin="temporary_privilege" if "expires_at" in extra else "direct_assignment",
                **extra,
            ),
        )
    elif kind in {"remove_membership", "remove_role"}:
        rel = "USER_MEMBER_OF_GROUP" if kind == "remove_membership" else "USER_HAS_ROLE"
        target = action["group"] if kind == "remove_membership" else action["role"]
        found = find_relationship(conn, env, rel, action["identity"], target)
        if not found:
            raise LabActionError("No such grant to remove")
        end_relationship(conn, org, env, found)
    elif kind == "create_role":
        if not str(action["role"]).startswith("role-lab-") or not action["permissions"]:
            raise LabActionError("Lab roles use the 'role-lab-' prefix and need permissions")
        for perm in action["permissions"]:
            _node(conn, env, perm, "permission")
        now = datetime.now(timezone.utc).isoformat()
        _put(
            conn,
            org,
            env,
            dict(
                type="node",
                id=action["role"],
                kind="role",
                subtype="application_role",
                name=action["name"],
                revisions=[
                    dict(valid_from=now, status="active", attributes=dict(created_in_lab=True))
                ],
            ),
        )
        for perm in action["permissions"]:
            relationship(
                conn,
                org,
                env,
                f"lab-rp-{action['role']}-{perm}",
                "ROLE_HAS_PERMISSION",
                action["role"],
                perm,
                dict(origin="role"),
            )
    elif kind == "set_identity":
        if not isinstance(action["attributes"], dict) or set(action["attributes"]) - IDENTITY_KEYS:
            raise LabActionError(f"Only {sorted(IDENTITY_KEYS)} can be set")
        update_node(conn, org, env, action["identity"], action["attributes"], "identity")
    elif kind == "register_mfa":
        if action["method"] not in MFA_METHODS:
            raise LabActionError("Unsupported MFA method")
        node = _node(conn, env, action["identity"], "identity")
        methods = sorted(
            set(node["revisions"][-1]["attributes"].get("mfa_methods", [])) | {action["method"]}
        )
        update_node(
            conn,
            org,
            env,
            action["identity"],
            dict(mfa_registered=True, mfa_methods=methods),
            "identity",
        )
    elif kind == "reset_password":
        if action["verification"] not in VERIFICATIONS:
            raise LabActionError("Unsupported verification")
        update_node(
            conn,
            org,
            env,
            "acct-" + action["identity"].removeprefix("idn-"),
            dict(
                password_reset_at=datetime.now(timezone.utc).isoformat(),
                reset_verification=action["verification"],
            ),
            "account",
        )
    elif kind == "unlock_account":
        update_node(
            conn,
            org,
            env,
            "acct-" + action["identity"].removeprefix("idn-"),
            dict(locked=False, unlocked_at=datetime.now(timezone.utc).isoformat()),
            "account",
        )
    elif kind == "disable_account":
        update_node(
            conn,
            org,
            env,
            "acct-" + action["identity"].removeprefix("idn-"),
            dict(enabled=False),
            "account",
            status="disabled",
        )
    elif kind == "set_owner":
        _node(conn, env, action["machine"], "identity")
        _node(conn, env, action["owner"], "identity")
        relationship(
            conn,
            org,
            env,
            f"lab-own-{action['owner']}-{action['machine']}",
            "USER_OWNS_SERVICE_ACCOUNT",
            action["owner"],
            action["machine"],
            dict(origin="direct_assignment"),
        )
        update_node(conn, org, env, action["machine"], dict(owner=action["owner"]), "identity")
    elif kind == "rotate_credential":
        now = datetime.now(timezone.utc)
        update_node(
            conn,
            org,
            env,
            action["credential"],
            dict(rotated_at=now.isoformat(), expires_at=(now + timedelta(days=365)).isoformat()),
            "credential",
        )
    elif kind == "add_condition":
        if action["condition"] not in CONDITIONS:
            raise LabActionError("Unsupported condition")
        row = _get(conn, env, action["relationship"])
        if not row or row["deleted"] or row["body"].get("type") != "relationship":
            raise LabActionError("Unknown relationship")
        body = row["body"]
        conditions = list(body["attributes"].get("conditions") or [])
        if {"type": action["condition"]} not in conditions:
            conditions.append({"type": action["condition"]})
        body = dict(body, attributes=dict(body["attributes"], conditions=conditions))
        _put(conn, org, env, body)
    elif kind == "configure_sso":
        if not isinstance(action["mappings"], dict):
            raise LabActionError("mappings must be an object")
        update_node(
            conn,
            org,
            env,
            action["application"],
            dict(
                sso=dict(
                    protocol="oidc (simulated)",
                    issuer=action["issuer"],
                    audience=action["audience"],
                    mappings=action["mappings"],
                )
            ),
            "application",
        )
    # 'answer' records a diagnosis only; nothing at the source changes.
    if kind != "answer":
        run_sync(conn, environment, None)
    return "applied" if kind != "answer" else "recorded"
