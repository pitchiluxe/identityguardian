"""Bitemporal graph snapshots and bounded traversal.

A snapshot answers: which nodes/edges were effective at `effective_at`, according to what the
platform knew at `known_at`. Both default to now. Results carry a graph version for binding.
"""

import threading
import time
from collections import OrderedDict, defaultdict
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..security import digest

DEFAULT_LIMITS = dict(depth=8, paths=100, nodes=10_000, seconds=2.0)


@dataclass
class Node:
    id: str
    external_id: str
    kind: str
    subtype: str
    name: str
    status: str
    attributes: dict


@dataclass
class Edge:
    id: str
    relationship_id: str
    type: str
    classification: str
    src: str
    dst: str
    attributes: dict
    valid_from: datetime
    valid_to: datetime | None
    observation_id: str
    end_inferred: bool = False
    recorded_from: datetime | None = None


@dataclass
class Snapshot:
    effective_at: datetime
    known_at: datetime
    nodes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    out: dict = field(default_factory=lambda: defaultdict(list))
    inc: dict = field(default_factory=lambda: defaultdict(list))
    version: str = ""
    # Memoized derived results for this immutable snapshot (never shared with overlays).
    cache: dict = field(default_factory=dict)

    def index(self):
        self.out, self.inc = defaultdict(list), defaultdict(list)
        for edge in self.edges:
            if edge.src in self.nodes and edge.dst in self.nodes:
                self.out[edge.src].append(edge)
                self.inc[edge.dst].append(edge)
        return self

    def at(self, effective_at, known_at):
        clone = copy(self)
        clone.effective_at, clone.known_at, clone.cache = effective_at, known_at, {}
        return clone

    def by_external(self, external_id):
        return next((n for n in self.nodes.values() if n.external_id == external_id), None)

    def describe(self):
        return dict(
            effective_at=self.effective_at.isoformat(),
            known_at=self.known_at.isoformat(),
            graph_version=self.version,
        )


def utc(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return value.astimezone(timezone.utc)


NODE_SQL = (
    "SELECT n.id, n.external_id, n.kind, n.subtype, r.name, r.status, r.attributes, r.valid_from, r.valid_to "
    "FROM twin_nodes n JOIN node_revisions r ON r.node_id=n.id WHERE n.environment_id=%s "
)
EDGE_SQL = (
    "SELECT rr.id, r.id AS relationship_id, r.type, r.classification, r.from_node, r.to_node, "
    "rr.attributes, rr.valid_from, rr.valid_to, rr.observation_id, rr.end_inferred, rr.recorded_from "
    "FROM relationships r JOIN relationship_revisions rr ON rr.relationship_id=r.id WHERE r.environment_id=%s "
)
CURRENT = "AND {a}.recorded_to IS NULL"
KNOWN_AT = "AND {a}.recorded_from<=%s AND ({a}.recorded_to IS NULL OR {a}.recorded_to>%s)"

# Process-level cache of current-knowledge rows, keyed by environment and graph version. Callers
# are authorized for the environment before load() runs; a new version (any recorded change)
# simply misses the cache, so invalidation is scoped to the environment that changed.
_CACHE: OrderedDict = OrderedDict()
_BUILT: OrderedDict = OrderedDict()
_CACHE_LOCK = threading.Lock()
CACHE_ENTRIES = 6
cache_stats = dict(hits=0, misses=0)


# Current knowledge is versioned by a trigger-maintained counter (migration 021): every write to
# the environment's nodes, relationships or revisions increments it.
VERSION_CURRENT = "SELECT changes FROM graph_watermarks WHERE environment_id=%(env)s"
VERSION_KNOWN_AT = (
    "SELECT (SELECT max(rr.recorded_from) FROM relationship_revisions rr JOIN relationships r "
    "ON r.id=rr.relationship_id WHERE r.environment_id=%(env)s AND rr.recorded_from<=%(k)s) AS rm, "
    "(SELECT count(*) FROM relationship_revisions rr JOIN relationships r ON r.id=rr.relationship_id "
    "WHERE r.environment_id=%(env)s AND rr.recorded_from<=%(k)s) AS rn, "
    "(SELECT max(nr.recorded_from) FROM node_revisions nr JOIN twin_nodes n ON n.id=nr.node_id "
    "WHERE n.environment_id=%(env)s AND nr.recorded_from<=%(k)s) AS nm, "
    "(SELECT count(*) FROM node_revisions nr JOIN twin_nodes n ON n.id=nr.node_id "
    "WHERE n.environment_id=%(env)s AND nr.recorded_from<=%(k)s) AS nn"
)


def graph_version(conn, environment_id, known_at=None) -> str:
    """Identifies a knowledge state: any recorded node or relationship change yields a new value."""
    if known_at is None:
        row = conn.execute(VERSION_CURRENT, dict(env=environment_id)).fetchone()
        return digest(f"{environment_id}:current:{row['changes'] if row else 0}")[:16]
    row = conn.execute(VERSION_KNOWN_AT, dict(env=environment_id, k=known_at)).fetchone()
    return digest(f"{environment_id}:{row['rm']}:{row['rn']}:{row['nm']}:{row['nn']}")[:16]


def _rows(conn, environment_id, known_at):
    if known_at is None:
        nodes = conn.execute(NODE_SQL + CURRENT.format(a="r"), (environment_id,)).fetchall()
        edges = conn.execute(EDGE_SQL + CURRENT.format(a="rr"), (environment_id,)).fetchall()
    else:
        nodes = conn.execute(
            NODE_SQL + KNOWN_AT.format(a="r"), (environment_id, known_at, known_at)
        ).fetchall()
        edges = conn.execute(
            EDGE_SQL + KNOWN_AT.format(a="rr"), (environment_id, known_at, known_at)
        ).fetchall()
    node_items = [
        (
            r["valid_from"],
            r["valid_to"],
            Node(
                str(r["id"]),
                r["external_id"],
                r["kind"],
                r["subtype"],
                r["name"],
                r["status"],
                r["attributes"],
            ),
        )
        for r in nodes
    ]
    edge_items = []
    for r in edges:
        expires = (r["attributes"] or {}).get("expires_at")
        edge_items.append(
            (
                datetime.fromisoformat(expires) if expires else None,
                Edge(
                    str(r["id"]),
                    str(r["relationship_id"]),
                    r["type"],
                    r["classification"],
                    str(r["from_node"]),
                    str(r["to_node"]),
                    r["attributes"],
                    r["valid_from"],
                    r["valid_to"],
                    str(r["observation_id"]),
                    r["end_inferred"],
                    r["recorded_from"],
                ),
            )
        )
    return node_items, edge_items


def load(conn, environment_id, effective_at=None, known_at=None, use_cache=True) -> Snapshot:
    t, k = utc(effective_at), utc(known_at)
    current = known_at is None or k >= datetime.now(timezone.utc)
    version = graph_version(conn, environment_id, None if current else k)
    key = (str(environment_id), version)
    cacheable = current and use_cache
    cached = None
    if cacheable:
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached:
                _CACHE.move_to_end(key)
                cache_stats["hits"] += 1
    if cached is None:
        cached = _rows(conn, environment_id, None if current else k)
        # Rows and version come from separate statements; a commit in between would pair newer
        # rows with an older version, so such a load is served but never cached.
        cacheable = cacheable and graph_version(conn, environment_id) == version
        if cacheable:
            with _CACHE_LOCK:
                cache_stats["misses"] += 1
                _CACHE[key] = cached
                while len(_CACHE) > CACHE_ENTRIES:
                    _CACHE.popitem(last=False)
    if cacheable:
        with _CACHE_LOCK:
            built = _BUILT.get(key)
        # A built snapshot stays exact until the next validity or expiry boundary after it.
        if built and built[0] <= t < built[1]:
            return built[2].at(t, k)
    node_items, edge_items = cached
    snapshot = Snapshot(t, k)
    horizon = datetime.max.replace(tzinfo=timezone.utc)
    for valid_from, valid_to, node in node_items:
        if valid_from <= t and (valid_to is None or valid_to > t):
            snapshot.nodes[node.id] = node
            if valid_to is not None:
                horizon = min(horizon, valid_to)
        elif valid_from > t:
            horizon = min(horizon, valid_from)
    for expires, edge in edge_items:
        if edge.valid_from > t:
            horizon = min(horizon, edge.valid_from)
        elif (edge.valid_to is None or edge.valid_to > t) and not (expires and expires <= t):
            snapshot.edges.append(edge)
            for boundary in (edge.valid_to, expires):
                if boundary is not None:
                    horizon = min(horizon, boundary)
    snapshot.version = version
    snapshot.index()
    if cacheable:
        with _CACHE_LOCK:
            _BUILT[key] = (t, horizon, snapshot)
            while len(_BUILT) > CACHE_ENTRIES:
                _BUILT.popitem(last=False)
    return snapshot


def node_json(node: Node):
    return dict(
        id=node.id,
        external_id=node.external_id,
        kind=node.kind,
        subtype=node.subtype,
        name=node.name,
        status=node.status,
        attributes=node.attributes,
    )


def edge_json(edge: Edge):
    return dict(
        id=edge.id,
        relationship_id=edge.relationship_id,
        type=edge.type,
        classification=edge.classification,
        src=edge.src,
        dst=edge.dst,
        attributes=edge.attributes,
        valid_from=edge.valid_from.isoformat(),
        valid_to=edge.valid_to.isoformat() if edge.valid_to else None,
        evidence_id=edge.observation_id,
        end_inferred=edge.end_inferred,
        recorded_from=edge.recorded_from.isoformat() if edge.recorded_from else None,
    )


def neighborhood(snapshot: Snapshot, start: str, depth=2, max_nodes=150, kinds=None, hub_degree=12):
    """Undirected bounded neighbourhood for the explorer. Truncation is reported.

    High-degree nodes (e.g. All-Staff) reached beyond the start are shown but not expanded; they
    are listed in `collapsed` so the view never implies their other relationships are absent.
    """
    if start not in snapshot.nodes:
        raise KeyError(start)
    deadline = time.monotonic() + DEFAULT_LIMITS["seconds"]
    seen, frontier, edges = {start}, [start], {}
    complete, reason, collapsed = True, None, {}
    for _ in range(depth):
        nxt = []
        for node in frontier:
            degree = len(snapshot.out[node]) + len(snapshot.inc[node])
            if node != start and degree > hub_degree:
                collapsed[node] = degree
                continue
            for edge in snapshot.out[node] + snapshot.inc[node]:
                other = edge.dst if edge.src == node else edge.src
                if kinds and snapshot.nodes[other].kind not in kinds:
                    continue
                if other not in seen:
                    if len(seen) >= max_nodes:
                        complete, reason = False, f"Node limit {max_nodes} reached"
                        continue
                    seen.add(other)
                    nxt.append(other)
                edges[edge.id] = edge
            if time.monotonic() > deadline:
                complete, reason = False, "Time limit reached"
                break
        frontier = nxt
        if not complete and reason == "Time limit reached":
            break
    edges = {k: e for k, e in edges.items() if e.src in seen and e.dst in seen}
    return dict(
        nodes=[node_json(snapshot.nodes[n]) for n in seen],
        edges=[edge_json(e) for e in edges.values()],
        complete=complete,
        truncation_reason=reason,
        depth=depth,
        collapsed=[dict(id=n, name=snapshot.nodes[n].name, degree=d) for n, d in collapsed.items()],
    )
