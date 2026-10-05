"""Sandbox ingestion: source objects -> immutable observations -> bitemporal twin records.

Partial syncs never imply absence. Only a full sync from an authoritative connector may close
relationships that disappeared from the source, and those closures are marked end_inferred.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from packages.fixtures import contoso

from ..security import digest
from .types import ORIGINS, validate

SOURCE = "sandbox"
NODE_KINDS = {
    "identity",
    "account",
    "group",
    "role",
    "permission",
    "resource",
    "application",
    "device",
    "department",
    "tool",
    "provider",
    "credential",
}
PREFETCH_THRESHOLD = 200
ORDER = {"node": 0, "relationship": 1, "employment_event": 2, "coverage": 3, "usage": 4}
CAPABILITIES = {
    "read": ["node", "relationship", "usage", "coverage", "employment_event"],
    "write": ["remove_relationship", "add_relationship"],
    "permission_semantics": "group nesting, role assignment, explicit deny, simple conditions",
    "native_ttl": True,
    "idempotent_writes": True,
    "reversible": "re-adding a removed relationship is a new approved action",
    "authoritative_scope": "entire sandbox environment",
}


# Field names that may carry secret material. Values are dropped before anything is stored;
# only the field path is kept so the redaction itself is visible evidence.
SENSITIVE_KEYS = (
    "password",
    "secret_value",
    "client_secret",
    "private_key",
    "token_value",
    "access_token",
    "refresh_token",
    "api_key_value",
    "otp_seed",
)


def sanitize(value, path="", removed=None):
    removed = [] if removed is None else removed
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            if any(s in key.lower() for s in SENSITIVE_KEYS):
                removed.append(here)
                continue
            clean[key] = sanitize(item, here, removed)[0]
        return clean, removed
    if isinstance(value, list):
        return [sanitize(item, f"{path}[{i}]", removed)[0] for i, item in enumerate(value)], removed
    return value, removed


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def parse_time(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def seed_sandbox(conn, environment, alternate_path=False):
    """Reset the sandbox source to the SYNTHETIC fixture baseline. Never touches the twin.

    Relationships that are not part of the fixture (e.g. executed changes or JIT grants) are
    closed at the source; the next sync records that as history rather than deleting evidence.
    """
    if environment["kind"] not in {"LAB", "SANDBOX"}:
        raise PermissionError("Synthetic data may only be loaded into LAB or SANDBOX environments")
    changed = 0
    objects = contoso.build(alternate_path=alternate_path)
    wanted = {obj["id"] for obj in objects}
    extras = conn.execute(
        "SELECT object_id, body FROM sandbox_objects WHERE environment_id=%s AND NOT deleted "
        "AND object_type='relationship'",
        (environment["id"],),
    ).fetchall()
    for row in extras:
        if row["object_id"] in wanted:
            continue
        version = conn.execute("SELECT nextval('sandbox_version_seq') AS v").fetchone()["v"]
        body = dict(row["body"], valid_to=datetime.now(timezone.utc).isoformat())
        conn.execute(
            "UPDATE sandbox_objects SET body=%s, deleted=true, version=%s, updated_at=now() "
            "WHERE environment_id=%s AND object_id=%s",
            (Jsonb(body), version, environment["id"], row["object_id"]),
        )
        changed += 1
    for obj in objects:
        row = conn.execute(
            "SELECT body, deleted FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
            (environment["id"], obj["id"]),
        ).fetchone()
        if row and row["body"] == obj and not row["deleted"]:
            continue
        version = conn.execute("SELECT nextval('sandbox_version_seq') AS v").fetchone()["v"]
        if row:
            conn.execute(
                "UPDATE sandbox_objects SET body=%s, version=%s, deleted=false, updated_at=now() "
                "WHERE environment_id=%s AND object_id=%s",
                (Jsonb(obj), version, environment["id"], obj["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO sandbox_objects(organization_id,environment_id,object_id,object_type,"
                "body,version) VALUES(%s,%s,%s,%s,%s,%s)",
                (
                    environment["organization_id"],
                    environment["id"],
                    obj["id"],
                    obj["type"],
                    Jsonb(obj),
                    version,
                ),
            )
        changed += 1
    return changed


def ensure_connector(conn, environment):
    row = conn.execute(
        "SELECT * FROM connectors WHERE environment_id=%s AND kind='sandbox'", (environment["id"],)
    ).fetchone()
    if row:
        return row
    return conn.execute(
        "INSERT INTO connectors(id,organization_id,environment_id,kind,name,capabilities,authoritative) "
        "VALUES(%s,%s,%s,'sandbox','Contoso sandbox directory (SYNTHETIC)',%s,true) RETURNING *",
        (uuid4(), environment["organization_id"], environment["id"], Jsonb(CAPABILITIES)),
    ).fetchone()


class Ingestor:
    """Applies source rows. Every check runs before any write, so a rejected object leaves no
    partial state. `prefetch()` loads existing state in bulk for large batches."""

    def __init__(self, conn, environment, run_id, source=SOURCE):
        self.source = source
        self.conn, self.env, self.run_id = conn, environment, run_id
        self.org, self.env_id = environment["organization_id"], environment["id"]
        self.counts = dict(observed=0, unchanged=0, created=0, updated=0, tombstoned=0, rejected=0)
        self.errors = []
        self.node_cache = {}
        self.prefetched = False
        self.latest, self.rels, self.rel_current, self.node_current = {}, {}, {}, {}

    def prefetch(self):
        args = (self.org, self.env_id, self.source)
        for r in self.conn.execute(
            "SELECT external_id, id, kind, subtype FROM twin_nodes WHERE organization_id=%s "
            "AND environment_id=%s AND source=%s",
            args,
        ):
            self.node_cache[r["external_id"]] = dict(
                id=r["id"], kind=r["kind"], subtype=r["subtype"]
            )
        for r in self.conn.execute(
            "SELECT DISTINCT ON (external_id) external_id, digest FROM observations "
            "WHERE organization_id=%s AND environment_id=%s AND source=%s "
            "ORDER BY external_id, received_at DESC",
            args,
        ):
            self.latest[r["external_id"]] = r["digest"]
        for r in self.conn.execute(
            "SELECT external_id, id, type, from_node, to_node FROM relationships "
            "WHERE organization_id=%s AND environment_id=%s AND source=%s",
            args,
        ):
            self.rels[r["external_id"]] = r
        for r in self.conn.execute(
            "SELECT rr.relationship_id, rr.valid_from, rr.valid_to, rr.attributes "
            "FROM relationship_revisions rr JOIN relationships r ON r.id=rr.relationship_id "
            "WHERE r.organization_id=%s AND r.environment_id=%s AND r.source=%s "
            "AND rr.recorded_to IS NULL",
            args,
        ):
            self.rel_current.setdefault(r["relationship_id"], []).append(
                (r["valid_from"], r["valid_to"], r["attributes"])
            )
        for r in self.conn.execute(
            "SELECT nr.node_id, nr.valid_from, nr.valid_to, nr.status, nr.attributes, nr.name "
            "FROM node_revisions nr JOIN twin_nodes n ON n.id=nr.node_id "
            "WHERE n.organization_id=%s AND n.environment_id=%s AND n.source=%s "
            "AND nr.recorded_to IS NULL ORDER BY nr.valid_from",
            args,
        ):
            self.node_current.setdefault(r["node_id"], []).append(
                (r["valid_from"], r["valid_to"], r["status"], r["attributes"], r["name"])
            )
        self.prefetched = True
        return self

    def node(self, external_id):
        if external_id not in self.node_cache and not self.prefetched:
            self.node_cache[external_id] = self.conn.execute(
                "SELECT id, kind, subtype FROM twin_nodes WHERE environment_id=%s AND source=%s "
                "AND external_id=%s",
                (self.env_id, self.source, external_id),
            ).fetchone()
        return self.node_cache.get(external_id)

    def _latest_digest(self, external_id):
        if self.prefetched:
            return self.latest.get(external_id)
        row = self.conn.execute(
            "SELECT digest FROM observations WHERE organization_id=%s AND environment_id=%s "
            "AND source=%s AND external_id=%s ORDER BY received_at DESC LIMIT 1",
            (self.org, self.env_id, self.source, external_id),
        ).fetchone()
        return row["digest"] if row else None

    def _relationship(self, external_id):
        if self.prefetched:
            return self.rels.get(external_id)
        return self.conn.execute(
            "SELECT id, type, from_node, to_node FROM relationships WHERE environment_id=%s "
            "AND source=%s AND external_id=%s",
            (self.env_id, self.source, external_id),
        ).fetchone()

    def _rel_revisions(self, rel_id):
        if self.prefetched:
            return self.rel_current.get(rel_id, [])
        rows = self.conn.execute(
            "SELECT valid_from, valid_to, attributes FROM relationship_revisions "
            "WHERE relationship_id=%s AND recorded_to IS NULL",
            (rel_id,),
        ).fetchall()
        return [(r["valid_from"], r["valid_to"], r["attributes"]) for r in rows]

    def _node_revisions(self, node_id):
        if self.prefetched:
            return self.node_current.get(node_id, [])
        rows = self.conn.execute(
            "SELECT valid_from, valid_to, status, attributes, name FROM node_revisions "
            "WHERE node_id=%s AND recorded_to IS NULL ORDER BY valid_from",
            (node_id,),
        ).fetchall()
        return [
            (r["valid_from"], r["valid_to"], r["status"], r["attributes"], r["name"]) for r in rows
        ]

    def observe(self, row):
        payload, removed = sanitize(dict(row["body"], deleted=row["deleted"]))
        if removed:
            payload["_redacted_fields"] = sorted(removed)
        fingerprint = digest(canonical(payload))
        self.counts["observed"] += 1
        # Compare with the latest observation only: an object may return to an earlier state.
        if self._latest_digest(row["object_id"]) == fingerprint:
            self.counts["unchanged"] += 1
            return None
        return payload, fingerprint

    def record(self, row, payload, fingerprint):
        observation = uuid4()
        self.conn.execute(
            "INSERT INTO observations(id,organization_id,environment_id,source,sync_run_id,object_type,"
            "external_id,source_version,payload,digest) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                observation,
                self.org,
                self.env_id,
                self.source,
                self.run_id,
                row["object_type"],
                row["object_id"],
                row["version"],
                Jsonb(payload),
                fingerprint,
            ),
        )
        self.latest[row["object_id"]] = fingerprint
        return observation

    def reject(self, row, reason):
        self.counts["rejected"] += 1
        self.errors.append({"object": row["object_id"], "reason": reason})

    def apply(self, row):
        seen = self.observe(row)
        if not seen:
            return
        payload, fingerprint = seen
        try:
            getattr(self, "apply_" + row["object_type"])(row, payload, fingerprint)
        except (ValueError, KeyError, TypeError) as exc:  # always raised before any write
            self.reject(row, str(exc))

    def apply_node(self, row, payload, fingerprint):
        if payload["kind"] not in NODE_KINDS:
            raise ValueError("Unknown node kind")
        revisions = sorted(payload["revisions"], key=lambda r: r["valid_from"])
        if not revisions:
            raise ValueError("Node without revisions")
        name = payload["name"]
        node = self.node(row["object_id"])
        if node and node["kind"] != payload["kind"]:
            raise ValueError("Node kind cannot change")
        desired = []
        for i, rev in enumerate(revisions):
            end = revisions[i + 1]["valid_from"] if i + 1 < len(revisions) else None
            if payload["deleted"] and end is None:
                end = payload.get("deleted_at") or datetime.now(timezone.utc).isoformat()
            desired.append(
                (
                    parse_time(rev["valid_from"]),
                    parse_time(end),
                    rev.get("status", "active"),
                    rev.get("attributes", {}),
                )
            )
        observation = self.record(row, payload, fingerprint)
        if not node:
            node_id = uuid4()
            self.conn.execute(
                "INSERT INTO twin_nodes(id,organization_id,environment_id,source,external_id,kind,"
                "subtype,name,first_observation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    node_id,
                    self.org,
                    self.env_id,
                    self.source,
                    row["object_id"],
                    payload["kind"],
                    payload.get("subtype", ""),
                    name,
                    observation,
                ),
            )
            self.node_cache[row["object_id"]] = dict(
                id=node_id, kind=payload["kind"], subtype=payload.get("subtype", "")
            )
            self.counts["created"] += 1
            current = []
        else:
            node_id = node["id"]
            self.counts["updated"] += 1
            current = self._node_revisions(node_id)
        if [c[:4] for c in current] == desired and all(c[4] == name for c in current):
            return
        if current:
            self.conn.execute(
                "UPDATE node_revisions SET recorded_to=now() WHERE node_id=%s AND recorded_to IS NULL",
                (node_id,),
            )
        for valid_from, valid_to, status, attributes in desired:
            self.conn.execute(
                "INSERT INTO node_revisions(id,organization_id,node_id,name,status,attributes,"
                "valid_from,valid_to,observation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    self.org,
                    node_id,
                    name,
                    status,
                    Jsonb(attributes),
                    valid_from,
                    valid_to,
                    observation,
                ),
            )
        self.node_current[node_id] = [(*d, name) for d in desired]

    def apply_relationship(self, row, payload, fingerprint):
        src, dst = self.node(payload["src"]), self.node(payload["dst"])
        if not src or not dst:
            raise ValueError("Relationship endpoint has not been observed")
        classification = validate(payload["rel"], src["kind"], dst["kind"])
        attributes = dict(payload.get("attributes", {}))
        if attributes.get("origin") not in ORIGINS:
            attributes["origin"] = "unknown"
        rel = self._relationship(row["object_id"])
        identity = (payload["rel"], src["id"], dst["id"])
        if rel and (rel["type"], rel["from_node"], rel["to_node"]) != identity:
            raise ValueError("Relationship identity (type/endpoints) cannot change")
        valid_from = parse_time(payload["valid_from"])
        valid_to = parse_time(payload.get("valid_to"))
        inferred = False
        if payload["deleted"] and valid_to is None:
            valid_to, inferred = datetime.now(timezone.utc), True
        if valid_to is not None and valid_to <= valid_from:
            raise ValueError("Relationship ends before it starts")
        observation = self.record(row, payload, fingerprint)
        if not rel:
            rel_id = uuid4()
            self.conn.execute(
                "INSERT INTO relationships(id,organization_id,environment_id,source,external_id,type,"
                "classification,from_node,to_node) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    rel_id,
                    self.org,
                    self.env_id,
                    self.source,
                    row["object_id"],
                    payload["rel"],
                    classification,
                    src["id"],
                    dst["id"],
                ),
            )
            self.rels[row["object_id"]] = dict(
                id=rel_id, type=payload["rel"], from_node=src["id"], to_node=dst["id"]
            )
            self.counts["created"] += 1
            current = []
        else:
            rel_id = rel["id"]
            self.counts["updated"] += 1
            current = self._rel_revisions(rel_id)
        if current == [(valid_from, valid_to, attributes)]:
            return
        if current and valid_to is not None and payload["deleted"]:
            self.counts["tombstoned"] += 1
        self.close_and_insert(
            rel_id,
            attributes,
            valid_from,
            valid_to,
            inferred,
            observation,
            had_current=bool(current),
        )

    def close_and_insert(
        self, rel_id, attributes, valid_from, valid_to, inferred, observation, had_current=True
    ):
        if had_current:
            self.conn.execute(
                "UPDATE relationship_revisions SET recorded_to=now() WHERE relationship_id=%s "
                "AND recorded_to IS NULL",
                (rel_id,),
            )
        self.conn.execute(
            "INSERT INTO relationship_revisions(id,organization_id,relationship_id,attributes,"
            "valid_from,valid_to,end_inferred,observation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                self.org,
                rel_id,
                Jsonb(attributes),
                valid_from,
                valid_to,
                inferred,
                observation,
            ),
        )
        self.rel_current[rel_id] = [(valid_from, valid_to, attributes)]

    def _fact(self, row, payload, fingerprint, table, columns, values):
        exists = self.conn.execute(
            f"SELECT 1 FROM {table} WHERE environment_id=%s AND external_id=%s",  # noqa: S608
            (self.env_id, row["object_id"]),
        ).fetchone()
        if exists:
            raise ValueError("Immutable fact changed at source; stored evidence retained")
        observation = self.record(row, payload, fingerprint)
        names = ",".join(
            ["id", "organization_id", "environment_id", "external_id", *columns, "observation_id"]
        )
        marks = ",".join(["%s"] * (len(columns) + 5))
        self.conn.execute(
            f"INSERT INTO {table}({names}) VALUES({marks})",  # noqa: S608
            (uuid4(), self.org, self.env_id, row["object_id"], *values, observation),
        )
        self.counts["created"] += 1

    def apply_usage(self, row, payload, fingerprint):
        who, target = self.node(payload["identity"]), self.node(payload["target"])
        if not who or not target or who["kind"] != "identity":
            raise ValueError("Usage references unknown identity or target")
        self._fact(
            row,
            payload,
            fingerprint,
            "usage_events",
            ["identity_node", "target_node", "occurred_at"],
            [who["id"], target["id"], parse_time(payload["occurred_at"])],
        )

    def apply_coverage(self, row, payload, fingerprint):
        target = self.node(payload["target"])
        if not target:
            raise ValueError("Coverage references unknown target")
        if payload.get("completeness") not in {"complete", "partial"}:
            raise ValueError("Invalid completeness")
        self._fact(
            row,
            payload,
            fingerprint,
            "usage_coverage",
            ["target_node", "covered_from", "covered_to", "completeness"],
            [
                target["id"],
                parse_time(payload["covered_from"]),
                parse_time(payload["covered_to"]),
                payload["completeness"],
            ],
        )

    def apply_employment_event(self, row, payload, fingerprint):
        who = self.node(payload["identity"])
        if not who or payload.get("kind") not in {"join", "move", "leave"}:
            raise ValueError("Invalid employment event")
        self._fact(
            row,
            payload,
            fingerprint,
            "employment_events",
            ["identity_node", "kind", "effective_at", "details"],
            [
                who["id"],
                payload["kind"],
                parse_time(payload["effective_at"]),
                Jsonb(payload.get("details", {})),
            ],
        )

    def reconcile_absent(self, present_ids):
        """Close relationships missing from a complete authoritative source read."""
        rows = self.conn.execute(
            "SELECT r.id, r.external_id, rr.valid_from, rr.attributes, rr.observation_id "
            "FROM relationships r JOIN relationship_revisions rr ON rr.relationship_id=r.id "
            "WHERE r.environment_id=%s AND r.source=%s AND rr.recorded_to IS NULL "
            "AND rr.valid_to IS NULL",
            (self.env_id, self.source),
        ).fetchall()
        now = datetime.now(timezone.utc)
        for row in rows:
            if row["external_id"] in present_ids or row["valid_from"] >= now:
                continue
            self.close_and_insert(
                row["id"], row["attributes"], row["valid_from"], now, True, row["observation_id"]
            )
            # Record the absence as the latest observation: if the same relationship returns
            # with an identical payload, it must not be skipped as "unchanged" (re-granted access).
            marker = {"absent_in_authoritative_read": True}
            self.record(
                dict(object_type="relationship", object_id=row["external_id"], version=0),
                marker,
                digest(canonical(marker)),
            )
            self.counts["tombstoned"] += 1


def run_sync(conn, environment, actor_id, full=False):
    connector = ensure_connector(conn, environment)
    previous = conn.execute(
        "SELECT cursor_to FROM sync_runs WHERE connector_id=%s AND status='SUCCEEDED' "
        "ORDER BY started_at DESC LIMIT 1",
        (connector["id"],),
    ).fetchone()
    cursor_from = 0 if full or not previous else previous["cursor_to"] or 0
    run_id = uuid4()
    coverage = "complete_authoritative" if full and connector["authoritative"] else "partial"
    conn.execute(
        "INSERT INTO sync_runs(id,organization_id,environment_id,connector_id,actor_id,status,"
        "coverage,cursor_from) VALUES(%s,%s,%s,%s,%s,'RUNNING',%s,%s)",
        (
            run_id,
            environment["organization_id"],
            environment["id"],
            connector["id"],
            actor_id,
            coverage,
            cursor_from,
        ),
    )
    rows = conn.execute(
        "SELECT * FROM sandbox_objects WHERE environment_id=%s AND version>%s",
        (environment["id"], cursor_from),
    ).fetchall()
    rows.sort(key=lambda r: (ORDER[r["object_type"]], r["version"]))
    ingestor = Ingestor(conn, environment, run_id)
    if len(rows) > PREFETCH_THRESHOLD or full:
        ingestor.prefetch()
    for row in rows:
        ingestor.apply(row)
    if coverage == "complete_authoritative":
        ingestor.reconcile_absent(
            {r["object_id"] for r in rows if r["object_type"] == "relationship"}
        )
    cursor_to = max([r["version"] for r in rows], default=cursor_from)
    status = "PARTIAL" if ingestor.counts["rejected"] else "SUCCEEDED"
    return conn.execute(
        "UPDATE sync_runs SET status=%s, cursor_to=%s, observed=%s, unchanged=%s, created=%s, "
        "updated=%s, tombstoned=%s, rejected=%s, errors=%s, finished_at=now() WHERE id=%s "
        "RETURNING *",
        (
            status,
            cursor_to,
            *[
                ingestor.counts[k]
                for k in ("observed", "unchanged", "created", "updated", "tombstoned", "rejected")
            ],
            Jsonb(ingestor.errors[:50]),
            run_id,
        ),
    ).fetchone()
