"""Bitemporal graph snapshots and bounded traversal.

A snapshot answers: which nodes/edges were effective at `effective_at`, according to what the
platform knew at `known_at`. Both default to now. Results carry a graph version for binding.
"""

import time
from collections import defaultdict
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


@dataclass
class Snapshot:
    effective_at: datetime
    known_at: datetime
    nodes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    out: dict = field(default_factory=lambda: defaultdict(list))
    inc: dict = field(default_factory=lambda: defaultdict(list))
    version: str = ""

    def index(self):
        self.out, self.inc = defaultdict(list), defaultdict(list)
        for edge in self.edges:
            if edge.src in self.nodes and edge.dst in self.nodes:
                self.out[edge.src].append(edge)
                self.inc[edge.dst].append(edge)
        return self

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


def load(conn, environment_id, effective_at=None, known_at=None) -> Snapshot:
    t, k = utc(effective_at), utc(known_at)
    snapshot = Snapshot(t, k)
    rows = conn.execute(
        "SELECT n.id, n.external_id, n.kind, n.subtype, r.name, r.status, r.attributes "
        "FROM twin_nodes n JOIN node_revisions r ON r.node_id=n.id "
        "WHERE n.environment_id=%s AND r.recorded_from<=%s AND (r.recorded_to IS NULL OR r.recorded_to>%s) "
        "AND r.valid_from<=%s AND (r.valid_to IS NULL OR r.valid_to>%s)",
        (environment_id, k, k, t, t),
    ).fetchall()
    for r in rows:
        snapshot.nodes[str(r["id"])] = Node(
            str(r["id"]),
            r["external_id"],
            r["kind"],
            r["subtype"],
            r["name"],
            r["status"],
            r["attributes"],
        )
    rows = conn.execute(
        "SELECT rr.id, r.id AS relationship_id, r.type, r.classification, r.from_node, r.to_node, "
        "rr.attributes, rr.valid_from, rr.valid_to, rr.observation_id, rr.end_inferred "
        "FROM relationships r JOIN relationship_revisions rr ON rr.relationship_id=r.id "
        "WHERE r.environment_id=%s AND rr.recorded_from<=%s AND (rr.recorded_to IS NULL OR rr.recorded_to>%s) "
        "AND rr.valid_from<=%s AND (rr.valid_to IS NULL OR rr.valid_to>%s)",
        (environment_id, k, k, t, t),
    ).fetchall()
    for r in rows:
        expires = (r["attributes"] or {}).get("expires_at")
        if expires and datetime.fromisoformat(expires) <= t:
            continue  # source-native TTL: an expired grant is not effective even before revocation
        snapshot.edges.append(
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
            )
        )
    watermark = conn.execute(
        "SELECT max(recorded_from) AS m, count(*) AS n FROM relationship_revisions rr "
        "JOIN relationships r ON r.id=rr.relationship_id WHERE r.environment_id=%s "
        "AND rr.recorded_from<=%s",
        (environment_id, k),
    ).fetchone()
    snapshot.version = digest(f"{environment_id}:{watermark['m']}:{watermark['n']}")[:16]
    return snapshot.index()


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
