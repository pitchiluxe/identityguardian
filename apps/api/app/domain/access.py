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
    stopped: bool = False
    deadline: float = field(default=0.0)

    def start(self):
        self.deadline = time.monotonic() + self.seconds
        return self

    def prune(self, reason):
        """Depth and path bounds cut one branch: the result is partial, other branches continue."""
        self.reason = self.reason or reason

    def exceeded(self):
        """Expansion and time bounds stop the whole search."""
        if not self.stopped:
            if self.expanded >= self.nodes:
                self.reason, self.stopped = f"Expansion limit {self.nodes} reached", True
            elif time.monotonic() > self.deadline:
                self.reason, self.stopped = f"Time limit {self.seconds}s reached", True
        return self.stopped

    def admit(self, per_target: dict, target: str) -> bool:
        """At most `paths` routes per entitlement target are kept; more mark the result partial."""
        if per_target.get(target, 0) >= self.paths:
            self.prune(f"Path limit {self.paths} per entitlement reached")
            return False
        per_target[target] = per_target.get(target, 0) + 1
        self.found += 1
        return True


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
                if bounds.admit(per_target, edge.dst):
                    yield_list.append(list(path))
            elif len(path) >= bounds.depth:
                bounds.prune(f"Depth limit {bounds.depth} reached")
            else:
                visited.add(edge.dst)
                visit(edge.dst)
                visited.discard(edge.dst)
            path.pop()
            if bounds.exceeded():
                return
        if not followed and kind == "permission" and path:
            # Permission without a resource scope (e.g. a reset capability) is still an entitlement.
            if bounds.admit(per_target, node):
                yield_list.append(list(path))

    yield_list: list = []
    per_target: dict = {}
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


def usage_for(conn, identity_id, targets, at):
    """Observed use and coverage per target, fetched for all targets in two queries."""
    targets = sorted({t for t in targets if t is not None})
    if conn is None or not targets:
        return {}
    usage = {t: dict(last_observed_use=None, observed_events=0, coverage=[]) for t in targets}
    for row in conn.execute(
        "SELECT target_node, max(occurred_at) AS last, count(*) AS n FROM usage_events "
        "WHERE identity_node=%s AND target_node=ANY(%s::uuid[]) AND occurred_at<=%s GROUP BY target_node",
        (identity_id, targets, at),
    ):
        entry = usage[str(row["target_node"])]
        entry["last_observed_use"], entry["observed_events"] = row["last"], row["n"]
    for row in conn.execute(
        "SELECT target_node, covered_from, covered_to, completeness, observation_id "
        "FROM usage_coverage WHERE target_node=ANY(%s::uuid[]) AND covered_from<=%s "
        "ORDER BY target_node, covered_from",
        (targets, at),
    ):
        target = str(row.pop("target_node"))
        usage[target]["coverage"].append(row)
    return usage


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
    usage = usage_for(conn, identity, [key[0] for key in grouped], snap.effective_at)
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
                usage=usage.get(resource),
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
    """Who can reach a target: reverse search over grant edges from the target to identities.

    Each found route is a simple path in forward order; denies and conditions are then evaluated
    per identity exactly as in effective_access. Bounds report partial results.
    """
    if target not in snap.nodes:
        raise KeyError(target)
    bounds = (bounds or Bounds()).start()
    found: dict = {}
    per_identity: dict = {}
    path: list = []
    visited = {target}

    def visit(node):
        if bounds.exceeded():
            return
        bounds.expanded += 1
        for edge in snap.inc[node]:
            source_kind = snap.nodes[edge.src].kind
            if edge.type not in NEXT.get(source_kind, ()) or not edge_active(
                edge, snap.effective_at
            ):
                continue
            if edge.src in visited:
                continue
            path.insert(0, edge)
            if source_kind == "identity":
                if bounds.admit(per_identity, edge.src):
                    found.setdefault(edge.src, []).append(list(path))
            elif len(path) >= bounds.depth:
                bounds.prune(f"Depth limit {bounds.depth} reached")
            else:
                visited.add(edge.src)
                visit(edge.src)
                visited.discard(edge.src)
            path.pop(0)
            if bounds.exceeded():
                return

    visit(target)
    # A deny matters only on a permission some found route passes through. Without any such
    # deny, the per-identity membership closure in denies_for cannot change a decision.
    on_routes = {
        e.dst
        for routes in found.values()
        for edges in routes
        for e in edges
        if snap.nodes[e.dst].kind == "permission"
    }
    deny_possible = any(
        e.type == "DENY_ASSIGNMENT" and edge_active(e, snap.effective_at)
        for permission in on_routes
        for e in snap.inc[permission]
    )
    results = []
    for identity in sorted(found, key=lambda n: snap.nodes[n].name):
        denies = denies_for(snap, identity) if deny_possible else {}
        paths = [summarize_path(snap, edges, denies) for edges in found[identity]]
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
