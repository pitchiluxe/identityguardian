"""Phase 19: depth and path bounds prune one branch; they never hide routes on other branches."""

from datetime import datetime, timezone

from apps.api.app.domain.access import Bounds, principals_for, walk
from apps.api.app.domain.graph import Edge, Node, Snapshot

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
KIND = {"idn": "identity", "grp": "group", "role": "role", "perm": "permission", "res": "resource"}


def snapshot(edges):
    snap = Snapshot(datetime.now(timezone.utc), datetime.now(timezone.utc))
    for src, _, dst in edges:
        for node in (src, dst):
            snap.nodes[node] = Node(node, node, KIND[node.split("-")[0]], "", node, "active", {})
    for i, (src, rel, dst) in enumerate(edges):
        snap.edges.append(Edge(f"e{i}", f"r{i}", rel, "grant", src, dst, {}, START, None, "obs"))
    return snap.index()


# Listed first, the deep branch is explored first: identity -> 3 nested groups -> role ...
DEEP = [
    ("idn-a", "USER_MEMBER_OF_GROUP", "grp-1"),
    ("grp-1", "GROUP_INHERITS_GROUP", "grp-2"),
    ("grp-2", "GROUP_INHERITS_GROUP", "grp-3"),
    ("grp-3", "GROUP_HAS_ROLE", "role-deep"),
    ("role-deep", "ROLE_HAS_PERMISSION", "perm-deep"),
    ("perm-deep", "PERMISSION_ACCESS_RESOURCE", "res-deep"),
]
SHALLOW = [
    ("idn-a", "USER_MEMBER_OF_GROUP", "grp-4"),
    ("grp-4", "GROUP_HAS_ROLE", "role-x"),
    ("role-x", "ROLE_HAS_PERMISSION", "perm-x"),
    ("perm-x", "PERMISSION_ACCESS_RESOURCE", "res-x"),
]


def test_depth_limit_prunes_branch_but_keeps_other_routes():
    bounds = Bounds(depth=4).start()
    paths = walk(snapshot(DEEP + SHALLOW), "idn-a", bounds)
    assert [p[-1].dst for p in paths] == ["res-x"]
    assert bounds.reason == "Depth limit 4 reached" and not bounds.stopped


def test_reverse_depth_limit_keeps_shallow_principals():
    edges = [
        ("perm-x", "PERMISSION_ACCESS_RESOURCE", "res-x"),
        ("role-x", "ROLE_HAS_PERMISSION", "perm-x"),
        ("grp-4", "GROUP_HAS_ROLE", "role-x"),
        ("grp-1", "GROUP_INHERITS_GROUP", "grp-4"),  # deep inheritance chain into grp-4
        ("grp-2", "GROUP_INHERITS_GROUP", "grp-1"),
        ("idn-b", "USER_MEMBER_OF_GROUP", "grp-2"),
        ("idn-a", "USER_MEMBER_OF_GROUP", "grp-4"),
    ]
    result = principals_for(snapshot(edges), "res-x", Bounds(depth=4))
    assert [p["identity"]["external_id"] for p in result["principals"]] == ["idn-a"]
    assert result["complete"] is False and "Depth limit" in result["truncation_reason"]
    complete = principals_for(snapshot(edges), "res-x", Bounds(depth=8))
    assert {p["identity"]["external_id"] for p in complete["principals"]} == {"idn-a", "idn-b"}
    assert complete["complete"] is True


def test_expansion_limit_stops_search_and_wins_reason():
    bounds = Bounds(depth=4, nodes=1).start()
    walk(snapshot(DEEP + SHALLOW), "idn-a", bounds)
    assert bounds.stopped and bounds.reason == "Expansion limit 1 reached"


def test_reverse_search_still_applies_group_denies():
    edges = SHALLOW + [("grp-4", "DENY_ASSIGNMENT", "perm-x")]
    snap = snapshot(edges)
    snap.edges[-1].classification = "deny"
    result = principals_for(snap.index(), "res-x")
    assert [p["decision"] for p in result["principals"]] == ["DENY"]
    assert principals_for(snapshot(SHALLOW), "res-x")["principals"][0]["decision"] == "ALLOW"
