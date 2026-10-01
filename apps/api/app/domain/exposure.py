"""Defensive exposure paths (GRAPH.md, THREAT_MODEL.md).

A path is a sequence of evidenced transitions from a starting identity to a sensitive resource:
  - entitlement: the identity's own effective access (lineage from access.py)
  - credential_reset: an effective permission with CAN_RESET_CREDENTIAL over another identity
  - assume_role: a CAN_ASSUME_ROLE edge from the identity to a role
Ownership edges never imply impersonation. Potential exposure is not successful exploitation:
outputs describe prerequisites and defensive controls, never exploitation steps.
"""

import time

from .access import Bounds, edge_active, effective_access, walk
from .graph import Snapshot, edge_json, node_json
from .types import SUPPORTED_CONDITIONS

SENSITIVE = {"critical", "high"}
STATUS_ORDER = {"POTENTIAL": 0, "CONDITIONAL": 1, "UNKNOWN": 2}
RULES_VERSION = "exposure-2026.09-1"


def evaluate_conditions(snap, edge, target=None):
    """Return (status, factors). Conditions that block without further evidence -> CONDITIONAL."""
    status, factors = "POTENTIAL", []
    for cond in edge.attributes.get("conditions") or []:
        kind = cond.get("type") if isinstance(cond, dict) else None
        if kind not in SUPPORTED_CONDITIONS:
            factors.append(dict(type=kind, effect="unsupported condition; outcome UNKNOWN"))
            status = "UNKNOWN"
            continue
        if kind == "target_mfa_registered" and target is not None:
            if snap.nodes[target].attributes.get("mfa_registered"):
                factors.append(
                    dict(
                        type=kind,
                        effect="target has MFA registered; a password reset "
                        "alone does not satisfy sign-in",
                    )
                )
                status = "CONDITIONAL" if status == "POTENTIAL" else status
            else:
                factors.append(
                    dict(
                        type=kind,
                        effect="target has no MFA registered (evidence: identity attribute)",
                    )
                )
            continue
        factors.append(dict(type=kind, effect="control must be satisfied at use time"))
        status = "CONDITIONAL" if status == "POTENTIAL" else status
    return status, factors


def worst(a, b):
    return a if STATUS_ORDER[a] >= STATUS_ORDER[b] else b


def controls_for(step):
    if step["kind"] == "credential_reset":
        return [
            "Require MFA re-verification or manager approval for credential resets",
            "Narrow the reset scope so it excludes identities with sensitive access",
            "Review the grant that confers the reset permission",
        ]
    if step["kind"] == "assume_role":
        return [
            "Keep break-glass assumption gated by MFA and a ticket; alert on use",
            "Time-bound the eligibility and review it periodically",
        ]
    return ["Review whether this entitlement is still required (least privilege)"]


def transitions(snap: Snapshot, identity: str, bounds: Bounds):
    """Exposure transitions available to an identity, each with its enabling lineage."""
    out = []
    for path in walk(snap, identity, bounds):
        last = path[-1]
        permission = (
            last.dst
            if snap.nodes[last.dst].kind == "permission"
            else next((e.dst for e in path if snap.nodes[e.dst].kind == "permission"), None)
        )
        if not permission:
            continue
        for edge in snap.out[permission]:
            if edge.type == "CAN_RESET_CREDENTIAL" and edge_active(edge, snap.effective_at):
                if edge.dst == identity or snap.nodes[edge.dst].kind != "identity":
                    continue
                out.append(dict(kind="credential_reset", target=edge.dst, via=path, edge=edge))
    for edge in snap.out[identity]:
        if edge.type == "CAN_ASSUME_ROLE" and edge_active(edge, snap.effective_at):
            out.append(dict(kind="assume_role", target=edge.dst, via=[], edge=edge))
    # Deduplicate same transition reached through several grant routes.
    seen, unique = set(), []
    for t in out:
        k = (t["kind"], t["target"], t["edge"].id)
        if k not in seen:
            seen.add(k)
            unique.append(t)
    return unique


def sensitive_entries(snap, identity, conn):
    access = effective_access(snap, identity, conn)
    return [
        e
        for e in access["entries"]
        if e["resource"]
        and e["resource"]["attributes"].get("sensitivity") in SENSITIVE
        and e["decision"] in {"ALLOW", "CONDITIONAL", "UNKNOWN"}
    ]


def role_entries(snap, role, bounds):
    """Resources reachable from an assumable role."""
    results = []
    for rp in snap.out[role]:
        if rp.type != "ROLE_HAS_PERMISSION":
            continue
        for pa in snap.out[rp.dst]:
            if pa.type == "PERMISSION_ACCESS_RESOURCE":
                results.append(([rp, pa], snap.nodes[pa.dst]))
    return results


def step_json(snap, kind, frm, to, edges, status, factors):
    return dict(
        kind=kind,
        from_=node_json(snap.nodes[frm]),
        to=node_json(snap.nodes[to]),
        edges=[edge_json(e) for e in edges],
        status=status,
        factors=factors,
        evidence_ids=[e.observation_id for e in edges],
    )


def attack_paths(
    snap: Snapshot, conn, source=None, destination=None, max_steps=2, max_paths=100, seconds=4.0
):
    deadline = time.monotonic() + seconds
    reason = None
    results = []
    starts = (
        [source]
        if source
        else sorted(
            (
                n.id
                for n in snap.nodes.values()
                if n.kind == "identity" and n.status != "terminated"
            ),
            key=lambda n: snap.nodes[n].name,
        )
    )
    for start in starts:
        held = {e["resource"]["id"] for e in sensitive_entries(snap, start, conn)}
        stack = [(start, [], {start}, "POTENTIAL")]
        while stack:
            if time.monotonic() > deadline:
                reason = f"Time limit {seconds}s reached"
                break
            if len(results) >= max_paths:
                reason = f"Path limit {max_paths} reached"
                break
            current, steps, visited, status = stack.pop()
            if len(steps) >= max_steps:
                continue
            for t in transitions(snap, current, Bounds().start()):
                target = t["target"]
                if t["kind"] == "credential_reset":
                    if target in visited:
                        continue
                    cond_status, factors = evaluate_conditions(snap, t["edge"], target)
                    target_node = snap.nodes[target]
                    if target_node.status == "terminated":
                        factors.append(
                            dict(
                                type="terminated_target",
                                effect="target identity is "
                                "terminated but holds enabled access (leaver gap)",
                            )
                        )
                    step = step_json(
                        snap,
                        "credential_reset",
                        current,
                        target,
                        t["via"] + [t["edge"]],
                        cond_status,
                        factors,
                    )
                    path_status = worst(status, cond_status)
                    new_steps = steps + [step]
                    for entry in sensitive_entries(snap, target, conn):
                        rid = entry["resource"]["id"]
                        if rid in held or (destination and rid != destination):
                            continue
                        best = entry["paths"][0]
                        final = dict(
                            kind="entitlement",
                            from_=node_json(snap.nodes[target]),
                            to=entry["resource"],
                            edges=[h["edge"] for h in best["hops"]],
                            status="POTENTIAL" if best["status"] == "ALLOW" else best["status"],
                            factors=best["conditions"],
                            evidence_ids=best["evidence_ids"],
                        )
                        results.append(
                            make_path(
                                snap,
                                start,
                                new_steps + [final],
                                worst(
                                    path_status,
                                    "POTENTIAL" if best["status"] == "ALLOW" else "CONDITIONAL",
                                ),
                            )
                        )
                    stack.append((target, new_steps, visited | {target}, path_status))
                else:  # assume_role
                    cond_status, factors = evaluate_conditions(snap, t["edge"])
                    step = step_json(
                        snap, "assume_role", current, target, [t["edge"]], cond_status, factors
                    )
                    for edges, resource in role_entries(snap, target, None):
                        if (
                            resource.id in held
                            or resource.attributes.get("sensitivity") not in SENSITIVE
                        ):
                            continue
                        if destination and resource.id != destination:
                            continue
                        final = dict(
                            kind="entitlement",
                            from_=node_json(snap.nodes[target]),
                            to=node_json(resource),
                            edges=[edge_json(e) for e in edges],
                            status="POTENTIAL",
                            factors=[],
                            evidence_ids=[e.observation_id for e in edges],
                        )
                        results.append(
                            make_path(
                                snap, start, steps + [step, final], worst(status, cond_status)
                            )
                        )
        if reason:
            break
    results.sort(
        key=lambda p: (STATUS_ORDER[p["status"]], -p["sensitivity_rank"], p["source"]["name"])
    )
    return dict(
        paths=results,
        complete=reason is None,
        truncation_reason=reason,
        rules_version=RULES_VERSION,
        max_steps=max_steps,
    )


def make_path(snap, start, steps, status):
    destination = steps[-1]["to"]
    sensitivity = destination["attributes"].get("sensitivity")
    controls = []
    for step in steps:
        for c in controls_for(step):
            if c not in controls:
                controls.append(c)
    evidence = [e for s in steps for e in s["evidence_ids"]]
    return dict(
        source=node_json(snap.nodes[start]),
        destination=destination,
        status=status,
        sensitivity=sensitivity,
        sensitivity_rank={"critical": 2, "high": 1}.get(sensitivity, 0),
        steps=steps,
        defensive_controls=controls,
        statement=(
            "Potential exposure, not evidence of exploitation. Each transition is backed by "
            "observed grants; conditions listed must hold for the exposure to be usable."
        ),
        evidence_ids=sorted(set(evidence)),
        key="|".join([start] + [s["to"]["id"] for s in steps]),
    )
