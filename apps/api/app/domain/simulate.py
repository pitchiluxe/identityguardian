"""What-if engine: immutable overlays on a snapshot (GRAPH.md "Simulation").

The base snapshot is never mutated and nothing is written to the twin or the sandbox source.
Results report lost/retained/gained access per affected identity, residual routes, dependency
and lockout risks, finding deltas and explicit unknowns. "Security improvement" is expressed as
explained finding changes, never as an invented probability.
"""

import json
from copy import copy
from datetime import timedelta

from .access import effective_access, principals_for
from .findings import all_findings, is_privileged
from .graph import Edge, Snapshot, edge_json, node_json
from .types import RELATIONSHIPS, validate

UPSTREAM = {
    "USER_MEMBER_OF_GROUP",
    "GROUP_INHERITS_GROUP",
    "GROUP_HAS_ROLE",
    "USER_HAS_ROLE",
    "ROLE_HAS_PERMISSION",
    "PERMISSION_ACCESS_RESOURCE",
}
POLICY_VERSION = "policy:none"
APPROVAL_TTL = timedelta(minutes=30)


def overlay(base: Snapshot, removals: set, additions: list) -> Snapshot:
    snap = copy(base)
    snap.edges = [e for e in base.edges if e.relationship_id not in removals] + additions
    snap.version = base.version + "+sim"
    snap.cache = {}
    return snap.index()


def holders(snap: Snapshot, node: str):
    """Identities whose grants flow through `node` (reverse over grant edges, cycle-safe)."""
    if snap.nodes[node].kind == "identity":
        return {node}
    found, seen, stack = set(), {node}, [node]
    while stack:
        current = stack.pop()
        for edge in snap.inc[current]:
            if edge.type not in UPSTREAM or edge.src in seen:
                continue
            seen.add(edge.src)
            if snap.nodes[edge.src].kind == "identity":
                found.add(edge.src)
            else:
                stack.append(edge.src)
    return found


def key_of(entry):
    return (
        (entry["resource"] or {}).get("id"),
        (entry["permission"] or {}).get("id"),
        entry["action"],
    )


def label_of(entry):
    target = entry["resource"] or entry["permission"]
    perm = entry["permission"]["name"] if entry["permission"] else entry["action"]
    return f"{target['name']} · {perm}"


def build_operations(base: Snapshot, conn, operations):
    removals, additions, described, source_versions = set(), [], [], {}
    for i, op in enumerate(operations):
        if op["op"] == "remove_relationship":
            row = conn.execute(
                "SELECT id FROM relationships WHERE id::text=%s OR external_id=%s LIMIT 1",
                (op["relationship"], op["relationship"]),
            ).fetchone()
            current = [e for e in base.edges if row and e.relationship_id == str(row["id"])]
            if not current:
                raise ValueError(f"Relationship {op['relationship']} is not currently effective")
            edge = current[0]
            removals.add(edge.relationship_id)
            source_versions[edge.relationship_id] = edge.id  # current revision id
            described.append(
                dict(
                    op="remove_relationship",
                    relationship=edge_json(edge),
                    src=node_json(base.nodes[edge.src]),
                    dst=node_json(base.nodes[edge.dst]),
                )
            )
        elif op["op"] == "add_relationship":
            src, dst = base.by_external(op["src"]), base.by_external(op["dst"])
            if not src or not dst:
                raise ValueError("Unknown endpoint for added relationship")
            if op["type"] not in RELATIONSHIPS:
                raise ValueError("Unknown relationship type")
            classification = validate(op["type"], src.kind, dst.kind)
            attributes = dict(
                origin=op.get("origin", "temporary_privilege"),
                simulated=True,
                **({"expires_at": op["expires_at"]} if op.get("expires_at") else {}),
            )
            edge = Edge(
                f"sim-{i}",
                f"sim-{i}",
                op["type"],
                classification,
                src.id,
                dst.id,
                attributes,
                base.effective_at,
                None,
                "simulation",
            )
            additions.append(edge)
            described.append(
                dict(
                    op="add_relationship",
                    relationship=edge_json(edge),
                    src=node_json(src),
                    dst=node_json(dst),
                )
            )
        elif op["op"] == "rotate_credential":
            credential = base.by_external(op["credential"])
            if not credential or credential.kind != "credential":
                raise ValueError("Unknown credential")
            holder = next(
                (base.nodes[e.src] for e in base.inc[credential.id] if e.type == "HAS_CREDENTIAL"),
                None,
            )
            dependents = (
                [base.nodes[e.src] for e in base.inc[holder.id] if e.type == "RESOURCE_DEPENDS_ON"]
                if holder
                else []
            )
            uses = (
                [base.nodes[e.dst] for e in base.out[holder.id] if e.classification == "grant"]
                if holder
                else []
            )
            described.append(
                dict(
                    op="rotate_credential",
                    relationship=None,
                    credential=node_json(credential),
                    holder=node_json(holder) if holder else None,
                    impact=dict(
                        access_change="none — rotation replaces credential material only",
                        must_update=[n.name for n in dependents + uses],
                        guidance="Use bounded overlap: issue the new credential, update dependents, "
                        "then retire the old one. The platform never sees secret values.",
                    ),
                )
            )
            source_versions["credential:" + credential.id] = str(
                credential.attributes.get("rotated_at")
            )
        elif op["op"] == "disable_account":
            account = base.by_external(op["account"])
            if not account or account.kind != "account":
                raise ValueError("Unknown account")
            holder = next(
                (base.nodes[e.src] for e in base.inc[account.id] if e.type == "HAS_ACCOUNT"), None
            )
            described.append(
                dict(
                    op="disable_account",
                    relationship=None,
                    account=node_json(account),
                    holder=node_json(holder) if holder else None,
                    impact=dict(
                        access_change="sign-in through this account is blocked; grants stay at the "
                        "source until separately removed",
                        must_update=[],
                        guidance="Pair with removal of remaining grants and ownership transfer.",
                    ),
                )
            )
            source_versions[f"node:{account.id}:enabled"] = json.dumps(
                account.attributes.get("enabled")
            )
        else:
            raise ValueError("Unsupported operation")
    return removals, additions, described, source_versions


def simulate(conn, base: Snapshot, environment_id, operations):
    removals, additions, described, source_versions = build_operations(base, conn, operations)
    after = overlay(base, removals, additions)
    affected = set()
    for op in described:
        if not op["relationship"]:
            continue
        start = op["relationship"]["src"]
        affected |= holders(base, start) | holders(after, start)
    identities, lockouts, dependencies, unknowns = [], [], [], []
    lost_targets = {}
    incomplete = False
    for identity in sorted(affected, key=lambda n: base.nodes[n].name):
        before = {key_of(e): e for e in effective_access(base, identity, conn)["entries"]}
        result_after = effective_access(after, identity, conn)
        incomplete |= not result_after["complete"]
        now = {key_of(e): e for e in result_after["entries"]}
        lost, retained, gained = [], [], []
        for k, entry in before.items():
            if k not in now:
                lost.append(
                    dict(
                        entitlement=label_of(entry),
                        decision=entry["decision"],
                        privileged=is_privileged(entry),
                        removed_paths=entry["paths"],
                    )
                )
                if entry["resource"]:
                    lost_targets.setdefault(entry["resource"]["id"], []).append((identity, entry))
            elif len(now[k]["paths"]) < len(entry["paths"]):
                retained.append(
                    dict(
                        entitlement=label_of(entry),
                        decision=now[k]["decision"],
                        residual_paths=now[k]["paths"],
                        removed_routes=len(entry["paths"]) - len(now[k]["paths"]),
                    )
                )
            for p in (now.get(k) or entry)["paths"]:
                if p["status"] in {"CONDITIONAL", "UNKNOWN"}:
                    unknowns.append(
                        f"{base.nodes[identity].name} → {label_of(entry)}: route is "
                        f"{p['status']} ({', '.join(c['type'] or '?' for c in p['conditions'])})"
                    )
        for k, entry in now.items():
            if k not in before:
                gained.append(
                    dict(
                        entitlement=label_of(entry),
                        decision=entry["decision"],
                        privileged=is_privileged(entry),
                        paths=entry["paths"],
                    )
                )
        if lost or retained or gained:
            identities.append(
                dict(
                    identity=node_json(base.nodes[identity]),
                    lost=lost,
                    retained_with_residual_routes=retained,
                    gained=gained,
                )
            )
    for target, losses in lost_targets.items():
        privileged_losses = [e for _, e in losses if is_privileged(e)]
        if privileged_losses:
            before_admins = [
                p for p in principals_for(base, target)["principals"] if p["decision"] == "ALLOW"
            ]
            after_admins = [
                p for p in principals_for(after, target)["principals"] if p["decision"] == "ALLOW"
            ]
            if before_admins and not after_admins:
                lockouts.append(
                    dict(
                        resource=node_json(base.nodes[target]),
                        message="No identity retains ALLOW access after the change; "
                        "possible administrative lockout.",
                        before=len(before_admins),
                        after=0,
                    )
                )
        for edge in base.inc[target]:
            if edge.type == "RESOURCE_DEPENDS_ON":
                dependencies.append(
                    dict(
                        resource=node_json(base.nodes[edge.src]),
                        depends_on=node_json(base.nodes[target]),
                        affected_identities=[base.nodes[i].name for i, _ in losses],
                        note=edge.attributes.get("note"),
                    )
                )
        for identity, _ in losses:
            for edge in base.inc[identity]:
                if edge.type == "RESOURCE_DEPENDS_ON":
                    dependencies.append(
                        dict(
                            resource=node_json(base.nodes[edge.src]),
                            depends_on=node_json(base.nodes[identity]),
                            affected_identities=[base.nodes[identity].name],
                            note=edge.attributes.get("note")
                            or "Workflow depends on this identity's access",
                        )
                    )
    before_findings = {f["key"]: f for f in all_findings(base, conn, environment_id)}
    after_findings = {f["key"]: f for f in all_findings(after, conn, environment_id)}
    resolved = [
        dict(key=k, rule=f["rule"], title=f["title"], severity=f["severity"])
        for k, f in before_findings.items()
        if k not in after_findings
    ]
    introduced = [
        dict(key=k, rule=f["rule"], title=f["title"], severity=f["severity"])
        for k, f in after_findings.items()
        if k not in before_findings
    ]
    if incomplete:
        unknowns.append("A traversal bound was reached; additional affected access may exist.")
    unknowns.append(
        "Dependencies outside the sandbox model (application-local accounts, cached "
        "tokens, scripts) are not observed and may be affected."
    )
    return dict(
        operations=described,
        affected_identities=identities,
        possible_lockouts=lockouts,
        dependencies=dependencies,
        findings=dict(
            resolved=resolved,
            introduced=introduced,
            statement=f"{len(resolved)} finding(s) resolved, {len(introduced)} introduced "
            "(deterministic rules; not a probability of compromise).",
        ),
        unknowns=sorted(set(unknowns)),
        base=base.describe(),
        mutated_base=False,
    ), source_versions
