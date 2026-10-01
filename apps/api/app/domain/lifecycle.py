"""Joiner / mover / leaver intelligence (ROADMAP Phase 11).

Plans are deterministic recommendations with evidence. Every action that would change access is
a proposal that must be simulated, independently approved and executed like any other change.
"""

from .access import effective_access
from .findings import is_privileged, peers_holding
from .graph import Snapshot, node_json

GRANT_TYPES = {"USER_MEMBER_OF_GROUP", "USER_HAS_ROLE"}
LIFECYCLE_RULES = "jml-2026.09-1"


def approved_baseline(conn, environment_id, department):
    return conn.execute(
        "SELECT * FROM jml_baselines WHERE environment_id=%s AND department=%s AND status='APPROVED'",
        (environment_id, department),
    ).fetchone()


def department_node(snap, identity):
    edge = next((e for e in snap.out[identity] if e.type == "IDENTITY_IN_DEPARTMENT"), None)
    return edge.dst if edge else None


def direct_grants(snap, identity):
    return [e for e in snap.out[identity] if e.type in GRANT_TYPES]


def action(kind, label, rationale, proposal=None, evidence=None, decision=None):
    return dict(
        kind=kind,
        label=label,
        rationale=rationale,
        proposal=proposal,
        evidence_ids=evidence or [],
        decision=decision,
    )


def joiner_plan(snap: Snapshot, conn, environment_id, identity, event):
    department = event["details"].get("department") or snap.nodes[identity].attributes.get(
        "department"
    )
    baseline = approved_baseline(conn, environment_id, department)
    held = {snap.nodes[e.dst].external_id: e for e in direct_grants(snap, identity)}
    actions = []
    if not baseline:
        return dict(
            status="NO_APPROVED_BASELINE",
            department=department,
            baseline=None,
            actions=[
                action(
                    "info",
                    "No approved baseline",
                    f"No approved joiner baseline exists for {department}; nothing is "
                    "provisioned automatically.",
                )
            ],
        )
    for group in baseline["groups"]:
        if group not in held:
            actions.append(
                action(
                    "add",
                    f"Add {group}",
                    f"Approved {department} baseline v{baseline['version']} includes it.",
                    proposal=dict(
                        kind="add_relationship",
                        type="USER_MEMBER_OF_GROUP",
                        src=snap.nodes[identity].external_id,
                        dst=group,
                    ),
                    decision="ADD",
                )
            )
    for external_id, edge in held.items():
        if external_id in baseline["groups"]:
            actions.append(
                action(
                    "retain",
                    f"Retain {snap.nodes[edge.dst].name}",
                    "In approved baseline.",
                    evidence=[edge.observation_id],
                    decision="RETAIN",
                )
            )
        elif snap.nodes[edge.dst].name != "All-Staff":
            actions.append(
                action(
                    "review",
                    f"Review {snap.nodes[edge.dst].name}",
                    "Outside the approved baseline for the joiner's department.",
                    proposal=dict(kind="remove_relationship", relationship=edge.relationship_id),
                    evidence=[edge.observation_id],
                    decision="REVIEW",
                )
            )
    return dict(
        status="PLANNED",
        department=department,
        baseline=dict(version=baseline["version"], groups=baseline["groups"]),
        actions=actions,
    )


def mover_plan(snap: Snapshot, conn, environment_id, identity, event):
    moved_at = event["effective_at"]
    details = event["details"]
    new_department = details.get("to_department")
    old_department = details.get("from_department")
    new_baseline = approved_baseline(conn, environment_id, new_department)
    old_baseline = approved_baseline(conn, environment_id, old_department)
    dept = department_node(snap, identity)
    access = effective_access(snap, identity, conn)
    actions = []
    for edge in direct_grants(snap, identity):
        group = snap.nodes[edge.dst]
        evidence = [edge.observation_id, str(event["observation_id"])]
        in_new = bool(new_baseline and group.external_id in new_baseline["groups"])
        in_old = bool(old_baseline and group.external_id in old_baseline["groups"])
        peers, holding = peers_holding(snap, identity, dept, edge.dst) if dept else (0, 0)
        common = peers and holding / peers >= 0.5
        reaches = [
            e
            for e in access["entries"]
            if any(
                p["hops"][0]["edge"]["relationship_id"] == edge.relationship_id for p in e["paths"]
            )
        ]
        privileged = any(is_privileged(e) for e in reaches)
        context = (
            f"granted {edge.valid_from.date()} ({edge.attributes.get('origin')}"
            f"{', ' + edge.attributes['ticket'] if edge.attributes.get('ticket') else ''}); "
            f"{holding}/{peers} {new_department} peers hold it"
        )
        if edge.valid_from >= moved_at or in_new or common:
            why = (
                "acquired for the new role"
                if edge.valid_from >= moved_at
                else "in the approved new-department baseline"
                if in_new
                else "common among new peers"
            )
            actions.append(
                action(
                    "retain",
                    f"Retain {group.name}",
                    f"{why}; {context}.",
                    evidence=evidence,
                    decision="RETAIN",
                )
            )
        elif in_old or privileged:
            actions.append(
                action(
                    "remove",
                    f"Remove {group.name}",
                    f"Predates the {old_department} → {new_department} move, "
                    f"{'belongs to the previous department baseline' if in_old else 'reaches privileged access'}; "
                    f"{context}.",
                    proposal=dict(kind="remove_relationship", relationship=edge.relationship_id),
                    evidence=evidence,
                    decision="REMOVE",
                )
            )
        else:
            actions.append(
                action(
                    "review",
                    f"Review {group.name}",
                    f"Predates the move and is not in the new baseline; {context}.",
                    proposal=dict(kind="remove_relationship", relationship=edge.relationship_id),
                    evidence=evidence,
                    decision="REVIEW",
                )
            )
    if new_baseline:
        held = {snap.nodes[e.dst].external_id for e in direct_grants(snap, identity)}
        for group in new_baseline["groups"]:
            if group not in held:
                actions.append(
                    action(
                        "add",
                        f"Add {group}",
                        f"In approved {new_department} baseline v{new_baseline['version']}.",
                        proposal=dict(
                            kind="add_relationship",
                            type="USER_MEMBER_OF_GROUP",
                            src=snap.nodes[identity].external_id,
                            dst=group,
                        ),
                        decision="ADD",
                    )
                )
    note = (
        None
        if new_baseline
        else f"No approved {new_department} baseline; retain decisions rely on peers."
    )
    return dict(
        status="PLANNED",
        from_department=old_department,
        to_department=new_department,
        note=note,
        actions=actions,
    )


def leaver_plan(snap: Snapshot, conn, environment_id, identity, event):
    node = snap.nodes[identity]
    actions = []
    for edge in snap.out[identity]:
        if edge.type == "HAS_ACCOUNT" and snap.nodes[edge.dst].attributes.get("enabled"):
            account = snap.nodes[edge.dst]
            actions.append(
                action(
                    "disable",
                    f"Disable account {account.name}",
                    "Account is still enabled after the leave date.",
                    proposal=dict(kind="disable_account", account=account.external_id),
                    evidence=[edge.observation_id],
                    decision="DISABLE",
                )
            )
    for edge in direct_grants(snap, identity):
        actions.append(
            action(
                "remove",
                f"Remove {snap.nodes[edge.dst].name}",
                "Leavers retain no access.",
                proposal=dict(kind="remove_relationship", relationship=edge.relationship_id),
                evidence=[edge.observation_id],
                decision="REMOVE",
            )
        )
    manager = node.attributes.get("manager")
    for edge in snap.out[identity]:
        if edge.type == "USER_OWNS_SERVICE_ACCOUNT":
            owned = snap.nodes[edge.dst]
            actions.append(
                action(
                    "transfer",
                    f"Transfer ownership of {owned.name}",
                    f"Owned non-human identity needs an accountable owner; proposed successor: "
                    f"{manager or 'none recorded (manual choice required)'}.",
                    proposal=dict(
                        kind="add_relationship",
                        type="USER_OWNS_SERVICE_ACCOUNT",
                        src=manager,
                        dst=owned.external_id,
                    )
                    if manager
                    else None,
                    evidence=[edge.observation_id],
                    decision="TRANSFER",
                )
            )
            actions.append(
                action(
                    "remove",
                    f"Remove {node.name}'s ownership of {owned.name}",
                    "Ownership ends with employment.",
                    proposal=dict(kind="remove_relationship", relationship=edge.relationship_id),
                    evidence=[edge.observation_id],
                    decision="REMOVE",
                )
            )
        if edge.type == "HAS_CREDENTIAL":
            credential = snap.nodes[edge.dst]
            actions.append(
                action(
                    "rotate",
                    f"Rotate {credential.external_id}",
                    "Credential held by a leaver.",
                    proposal=dict(kind="rotate_credential", credential=credential.external_id),
                    evidence=[edge.observation_id],
                    decision="ROTATE",
                )
            )
    owned_resources = [
        n
        for n in snap.nodes.values()
        if n.kind in {"application", "resource"} and n.attributes.get("owner") == node.external_id
    ]
    for resource in owned_resources:
        actions.append(
            action(
                "reassign",
                f"Reassign owner of {resource.name}",
                "Resource owner attribute names the leaver; reassign at the source.",
                decision="MANUAL",
            )
        )
    exposures = [e for e in snap.inc[identity] if e.type == "CAN_RESET_CREDENTIAL"]
    if exposures:
        actions.append(
            action(
                "info",
                "Credential-reset exposure",
                f"{len(exposures)} reset permission(s) target this enabled leaver; "
                "disabling the account closes the gap.",
                evidence=[e.observation_id for e in exposures],
            )
        )
    actions.append(
        action(
            "unknown",
            "Sessions and tokens",
            "UNKNOWN: the sandbox source does not expose sessions or refresh tokens. "
            "Revoke them at the identity provider; the platform cannot confirm it.",
        )
    )
    return dict(status="PLANNED", actions=actions)


def plan_for(snap: Snapshot, conn, environment_id, event):
    identity = str(event["identity_node"])
    if identity not in snap.nodes:
        return dict(status="IDENTITY_NOT_EFFECTIVE", actions=[])
    build = {"join": joiner_plan, "move": mover_plan, "leave": leaver_plan}[event["kind"]]
    plan = build(snap, conn, environment_id, identity, event)
    plan.update(
        rules_version=LIFECYCLE_RULES,
        basis="RULE-BASED",
        identity=node_json(snap.nodes[identity]),
        event=dict(
            id=str(event["id"]),
            kind=event["kind"],
            effective_at=event["effective_at"].isoformat(),
            details=event["details"],
            evidence_id=str(event["observation_id"]),
        ),
    )
    return plan


def workflow_status(statuses):
    if not statuses:
        return "EMPTY"
    done = {"SUCCEEDED"}
    failed = {"FAILED", "STALE", "EXPIRED", "REJECTED", "CANCELLED", "PARTIAL"}
    if all(s in done for s in statuses):
        return "COMPLETED"
    if any(s in failed for s in statuses):
        return "PARTIAL" if any(s in done for s in statuses) else "FAILED"
    return "IN_PROGRESS"
