"""Effective access with lineage (GRAPH.md).

Each lineage is a simple path of active grant edges from an identity to an entitlement target.
Per-path visited sets stop cycles while preserving alternative routes. Explicit denies override.
Supported conditions make a path CONDITIONAL; unsupported conditions make it UNKNOWN — never
ALLOW. Any bound returns complete=False; truncated traversal never proves absence.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime

from .graph import DEFAULT_LIMITS, Snapshot, edge_json, node_json
from .types import SUPPORTED_CONDITIONS

TERMINAL_KINDS = {"resource", "application", "tool"}
ORDER = {"DENY": 0, "ALLOW": 1, "CONDITIONAL": 2, "UNKNOWN": 3}

# Which grant edge types may follow a node of a given kind.
NEXT = {
    "identity": {
        "USER_MEMBER_OF_GROUP",
        "USER_HAS_ROLE",
        "SERVICE_ACCOUNT_ACCESS_APPLICATION",
        "AI_AGENT_USES_TOOL",
        "AI_AGENT_ACCESS_DATA",
    },
    "group": {"GROUP_INHERITS_GROUP", "GROUP_HAS_ROLE"},
    "role": {"ROLE_HAS_PERMISSION"},
    "permission": {"PERMISSION_ACCESS_RESOURCE"},
}


@dataclass
class Bounds:
    depth: int = DEFAULT_LIMITS["depth"]
    paths: int = DEFAULT_LIMITS["paths"]
    nodes: int = DEFAULT_LIMITS["nodes"]
    seconds: float = DEFAULT_LIMITS["seconds"]
    expanded: int = 0
    found: int = 0
    reason: str | None = None
    deadline: float = field(default=0.0)

    def start(self):
        self.deadline = time.monotonic() + self.seconds
        return self

    def exceeded(self):
        if self.reason:
            return True
        if self.found >= self.paths:
            self.reason = f"Path limit {self.paths} reached"
        elif self.expanded >= self.nodes:
            self.reason = f"Expansion limit {self.nodes} reached"
        elif time.monotonic() > self.deadline:
            self.reason = f"Time limit {self.seconds}s reached"
        return bool(self.reason)


def edge_active(edge, at: datetime):
    expires = edge.attributes.get("expires_at")
    return not (expires and datetime.fromisoformat(expires) <= at)


def condition_status(edges):
    status, conditions = "ALLOW", []
    for edge in edges:
        for cond in edge.attributes.get("conditions") or []:
            kind = cond.get("type") if isinstance(cond, dict) else None
            conditions.append(dict(type=kind, edge=edge.id, supported=kind in SUPPORTED_CONDITIONS))
            if kind not in SUPPORTED_CONDITIONS:
                status = "UNKNOWN"
            elif status == "ALLOW":
                status = "CONDITIONAL"
    return status, conditions


def membership_closure(snap: Snapshot, identity: str):
    """Groups an identity belongs to directly or through nesting (cycle-safe)."""
    groups, stack = set(), [identity]
    while stack:
        node = stack.pop()
        for edge in snap.out[node]:
            if (
                edge.type in {"USER_MEMBER_OF_GROUP", "GROUP_INHERITS_GROUP"}
                and edge_active(edge, snap.effective_at)
                and edge.dst not in groups
            ):
                groups.add(edge.dst)
                stack.append(edge.dst)
    return groups


def denies_for(snap: Snapshot, identity: str):
    subjects = membership_closure(snap, identity) | {identity}
    return {
        edge.dst: edge
        for subject in subjects
        for edge in snap.out[subject]
        if edge.type == "DENY_ASSIGNMENT" and edge_active(edge, snap.effective_at)
    }


def walk(snap: Snapshot, identity: str, bounds: Bounds):
    """Yield every simple grant path (list of edges) from identity to an entitlement endpoint."""
    path, visited = [], {identity}

    def visit(node):
        if bounds.exceeded():
            return
        bounds.expanded += 1
        kind = snap.nodes[node].kind
        followed = False
        for edge in snap.out[node]:
            if edge.type not in NEXT.get(kind, ()) or not edge_active(edge, snap.effective_at):
                continue
            if edge.dst in visited:
                continue  # cycle on this path; alternative routes remain explored
            followed = True
            path.append(edge)
            dst_kind = snap.nodes[edge.dst].kind
            if dst_kind in TERMINAL_KINDS:
                bounds.found += 1
                yield_list.append(list(path))
            elif len(path) >= bounds.depth:
                bounds.reason = bounds.reason or f"Depth limit {bounds.depth} reached"
            else:
                visited.add(edge.dst)
                visit(edge.dst)
                visited.discard(edge.dst)
            path.pop()
            if bounds.exceeded():
                return
        if not followed and kind == "permission" and path:
            # Permission without a resource scope (e.g. a reset capability) is still an entitlement.
            bounds.found += 1
            yield_list.append(list(path))

    yield_list: list = []
    visit(identity)
    return yield_list


def hop_json(snap, edge):
    return dict(edge=edge_json(edge), to=node_json(snap.nodes[edge.dst]))


def summarize_path(snap, edges, denies):
    status, conditions = condition_status(edges)
    permission = next((e.dst for e in edges if snap.nodes[e.dst].kind == "permission"), None)
    if permission and permission in denies:
        status = "DENY"
    origin = edges[0].attributes.get("origin", "unknown")
    if len(edges) > 1 and edges[0].type == "USER_MEMBER_OF_GROUP":
        nested = any(e.type == "GROUP_INHERITS_GROUP" for e in edges)
        origin = f"{origin} via {'nested ' if nested else ''}group"
    return dict(
        status=status,
        hops=[hop_json(snap, e) for e in edges],
        conditions=conditions,
        evidence_ids=[e.observation_id for e in edges],
        origin=origin,
        denied_by=edge_json(denies[permission]) if status == "DENY" else None,
    )


def entitlement_key(snap, edges):
    last = edges[-1]
    target = snap.nodes[last.dst]
    permission = next(
        (snap.nodes[e.dst] for e in edges if snap.nodes[e.dst].kind == "permission"), None
    )
    action = (
        (permission.attributes.get("action") if permission else None)
        or last.attributes.get("action")
        or {"AI_AGENT_USES_TOOL": "invoke", "SERVICE_ACCOUNT_ACCESS_APPLICATION": "access"}.get(
            last.type, "access"
        )
    )
    resource = target if target.kind in TERMINAL_KINDS else None
    return (resource.id if resource else None, permission.id if permission else None, action)


def decide(paths):
    statuses = {p["status"] for p in paths}
    if "DENY" in statuses:
        return "DENY"
    for status in ("ALLOW", "CONDITIONAL", "UNKNOWN"):
        if status in statuses:
            return status
    return "UNKNOWN"


def usage_for(conn, identity_id, target_id, at):
    if conn is None or target_id is None:
        return None
    last = conn.execute(
        "SELECT max(occurred_at) AS last, count(*) AS n FROM usage_events WHERE identity_node=%s "
        "AND target_node=%s AND occurred_at<=%s",
        (identity_id, target_id, at),
    ).fetchone()
    coverage = conn.execute(
        "SELECT covered_from, covered_to, completeness, observation_id FROM usage_coverage "
        "WHERE target_node=%s AND covered_from<=%s ORDER BY covered_from",
        (target_id, at),
    ).fetchall()
    return dict(last_observed_use=last["last"], observed_events=last["n"], coverage=coverage)


def effective_access(snap: Snapshot, identity: str, conn=None, bounds: Bounds | None = None):
    if identity not in snap.nodes or snap.nodes[identity].kind != "identity":
        raise KeyError(identity)
    memo = (
        "access",
        identity,
        conn is not None,
        (bounds.depth, bounds.paths, bounds.nodes, bounds.seconds) if bounds else None,
    )
    if memo not in snap.cache:
        snap.cache[memo] = _effective_access(snap, identity, conn, bounds)
    return snap.cache[memo]


def _effective_access(snap: Snapshot, identity: str, conn, bounds: Bounds | None):
    bounds = (bounds or Bounds()).start()
    denies = denies_for(snap, identity)
    grouped: dict = {}
    for edges in walk(snap, identity, bounds):
        grouped.setdefault(entitlement_key(snap, edges), []).append(
            summarize_path(snap, edges, denies)
        )
    entries = []
    for (resource, permission, action), paths in grouped.items():
        paths.sort(key=lambda p: (ORDER[p["status"]], len(p["hops"])))
        entries.append(
            dict(
                resource=node_json(snap.nodes[resource]) if resource else None,
                permission=node_json(snap.nodes[permission]) if permission else None,
                action=action,
                decision=decide(paths),
                paths=paths,
                usage=usage_for(conn, identity, resource, snap.effective_at),
            )
        )
    entries.sort(key=lambda e: (ORDER[e["decision"]], (e["resource"] or e["permission"])["name"]))
    return dict(
        identity=node_json(snap.nodes[identity]),
        entries=entries,
        denies=[edge_json(e) for e in denies.values()],
        complete=bounds.reason is None,
        truncation_reason=bounds.reason,
        bounds=dict(
            depth=bounds.depth, paths=bounds.paths, nodes=bounds.nodes, seconds=bounds.seconds
        ),
    )


def principals_for(snap: Snapshot, target: str, bounds: Bounds | None = None):
    """Who can reach a target: reverse discovery of candidate identities, then forward lineage."""
    if target not in snap.nodes:
        raise KeyError(target)
    bounds = (bounds or Bounds()).start()
    candidates, stack, seen = set(), [target], {target}
    while stack and not bounds.exceeded():
        node = stack.pop()
        bounds.expanded += 1
        for edge in snap.inc[node]:
            if edge.classification != "grant" or edge.src in seen:
                continue
            seen.add(edge.src)
            if snap.nodes[edge.src].kind == "identity":
                candidates.add(edge.src)
            else:
                stack.append(edge.src)
    results = []
    for identity in sorted(candidates, key=lambda n: snap.nodes[n].name):
        inner = Bounds(
            depth=bounds.depth, paths=bounds.paths, nodes=bounds.nodes, seconds=bounds.seconds
        ).start()
        denies = denies_for(snap, identity)
        paths = [
            summarize_path(snap, edges, denies)
            for edges in walk(snap, identity, inner)
            if any(e.dst == target for e in edges)
        ]
        if inner.reason and not bounds.reason:
            bounds.reason = inner.reason
        if paths:
            paths.sort(key=lambda p: (ORDER[p["status"]], len(p["hops"])))
            results.append(
                dict(identity=node_json(snap.nodes[identity]), decision=decide(paths), paths=paths)
            )
    return dict(
        target=node_json(snap.nodes[target]),
        principals=results,
        complete=bounds.reason is None,
        truncation_reason=bounds.reason,
    )
