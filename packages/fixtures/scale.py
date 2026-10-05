"""Deterministic SYNTHETIC scale dataset for performance benchmarks (not a realistic org chart).

Default: 10,000 identities and roughly 100,000 relationships, including nested groups, a few
group cycles, conditional and denied grants and temporal history.
"""

import random

BASE = "2025-01-01T00:00:00+00:00"


def build(identities=10_000, groups=500, roles=200, permissions=400, resources=300, seed=7):
    rng = random.Random(seed)
    objects = []

    def node(oid, kind, name, subtype="", **attributes):
        objects.append(
            dict(
                type="node",
                id=oid,
                kind=kind,
                subtype=subtype,
                name=name,
                revisions=[dict(valid_from=BASE, status="active", attributes=attributes)],
            )
        )

    def rel(oid, kind, src, dst, **attributes):
        attributes.setdefault("origin", "role")
        objects.append(
            dict(
                type="relationship",
                id=oid,
                rel=kind,
                src=src,
                dst=dst,
                valid_from=BASE,
                valid_to=None,
                attributes=attributes,
            )
        )

    for d in range(20):
        node(f"s-dept-{d}", "department", f"Department {d:02d}")
    for r in range(resources):
        node(
            f"s-res-{r}",
            "resource",
            f"Resource {r:03d}",
            "database",
            sensitivity=rng.choice(["low", "medium", "high", "critical"]),
        )
    for p in range(permissions):
        node(
            f"s-perm-{p}",
            "permission",
            f"Permission {p:03d}",
            rng.choice(["read", "administer", "operate"]),
            action=rng.choice(["read", "administer", "operate"]),
        )
        rel(f"s-pa-{p}", "PERMISSION_ACCESS_RESOURCE", f"s-perm-{p}", f"s-res-{p % resources}")
    for r in range(roles):
        node(f"s-role-{r}", "role", f"Role {r:03d}", "application_role")
        for k in rng.sample(range(permissions), 6):
            rel(f"s-rp-{r}-{k}", "ROLE_HAS_PERMISSION", f"s-role-{r}", f"s-perm-{k}")
    for g in range(groups):
        node(f"s-grp-{g}", "group", f"Group {g:03d}", "security")
        for k in rng.sample(range(roles), 2):
            rel(
                f"s-gr-{g}-{k}",
                "GROUP_HAS_ROLE",
                f"s-grp-{g}",
                f"s-role-{k}",
                **({"conditions": [{"type": "mfa_required"}]} if rng.random() < 0.05 else {}),
            )
        if g >= 50:  # nesting into lower-numbered groups keeps depth bounded
            for k in rng.sample(range(g), 1):
                rel(f"s-nest-{g}-{k}", "GROUP_INHERITS_GROUP", f"s-grp-{g}", f"s-grp-{k}")
    for g in range(0, 20, 2):  # a few cycles
        rel(f"s-cycle-{g}", "GROUP_INHERITS_GROUP", f"s-grp-{g}", f"s-grp-{g + 1}")
        rel(f"s-cycle-back-{g}", "GROUP_INHERITS_GROUP", f"s-grp-{g + 1}", f"s-grp-{g}")
    for i in range(identities):
        dept = i % 20
        node(
            f"s-idn-{i}",
            "identity",
            f"Scale Person {i:05d}",
            "employee",
            department=f"Department {dept:02d}",
            mfa_registered=rng.random() > 0.1,
            synthetic=True,
        )
        node(
            f"s-acct-{i}",
            "account",
            f"person{i:05d}@scale.example",
            "directory",
            enabled=True,
            last_sign_in="2026-09-01T00:00:00+00:00",
        )
        rel(f"s-has-{i}", "HAS_ACCOUNT", f"s-idn-{i}", f"s-acct-{i}")
        rel(f"s-dept-rel-{i}", "IDENTITY_IN_DEPARTMENT", f"s-idn-{i}", f"s-dept-{dept}")
        for k in rng.sample(range(groups), 8):
            rel(
                f"s-mem-{i}-{k}",
                "USER_MEMBER_OF_GROUP",
                f"s-idn-{i}",
                f"s-grp-{k}",
                origin=rng.choice(["role", "manager_approval", "legacy_entitlement"]),
            )
        if i % 97 == 0:
            rel(
                f"s-deny-{i}",
                "DENY_ASSIGNMENT",
                f"s-idn-{i}",
                f"s-perm-{i % permissions}",
                origin="direct_assignment",
            )
    return objects
