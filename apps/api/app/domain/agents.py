"""AI-agent registry (DATABASE.md AIAgent): declared scopes versus effective access.

Declared values (owner, model, purpose, maximum privilege, credential scope, expiry, allowed
tools/data, prohibited data) come from the registry source. Effective tools and data come from
the lineage engine. Differences are reported as rule-based findings; nothing is auto-revoked.
"""

from datetime import datetime, timedelta

from .access import effective_access
from .findings import key, machine_context
from .graph import Snapshot, node_json

AGENT_RULES = "agents-2026.09-1"
EXPIRY_WARNING_DAYS = 30


def agent_profile(snap: Snapshot, conn, node_id):
    node, owners, credentials, dependents, _ = machine_context(snap, node_id)
    attrs = node.attributes
    access = effective_access(snap, node_id, conn)
    tools, data = {}, {}
    for entry in access["entries"]:
        target = entry["resource"]
        if not target or entry["decision"] == "DENY":
            continue
        if target["kind"] == "tool":
            tools[target["name"]] = entry
        classification = target["attributes"].get("data_classification")
        if classification:
            data.setdefault(classification, []).append(entry)
    allowed_tools = set(attrs.get("allowed_tools") or [])
    allowed_data = set(attrs.get("allowed_data") or [])
    prohibited = set(attrs.get("prohibited_data") or [])
    expires = attrs.get("expires_at")
    days_left = (datetime.fromisoformat(expires) - snap.effective_at).days if expires else None
    activity = conn.execute(
        "SELECT t.name, count(*) AS events, max(u.occurred_at) AS last FROM usage_events u "
        "JOIN twin_nodes t ON t.id=u.target_node WHERE u.identity_node=%s AND u.occurred_at<=%s "
        "GROUP BY t.name ORDER BY t.name",
        (node_id, snap.effective_at),
    ).fetchall()
    return dict(
        identity=node_json(node),
        declared=dict(
            owner=attrs.get("owner"),
            department=attrs.get("department"),
            model=attrs.get("model"),
            purpose=attrs.get("purpose"),
            maximum_privilege=attrs.get("max_privilege"),
            credential_scope=attrs.get("credential_scope"),
            expires_at=expires,
            allowed_tools=sorted(allowed_tools),
            allowed_data=sorted(allowed_data),
            prohibited_data=sorted(prohibited),
        ),
        owners=[node_json(o) for o in owners],
        credentials=[node_json(c) for c, _ in credentials],
        effective=dict(
            tools=sorted(tools),
            data={k: sorted({(e["resource"]["name"]) for e in v}) for k, v in data.items()},
            entitlements=len(access["entries"]),
        ),
        excess_tools=sorted(set(tools) - allowed_tools),
        excess_data=sorted(set(data) - allowed_data),
        prohibited_access=sorted(set(data) & prohibited),
        expiry=dict(
            expires_at=expires,
            days_left=days_left,
            state="UNKNOWN"
            if days_left is None
            else "EXPIRED"
            if days_left < 0
            else "EXPIRING"
            if days_left <= EXPIRY_WARNING_DAYS
            else "VALID",
        ),
        activity=[dict(target=a["name"], events=a["events"], last=a["last"]) for a in activity],
        _access=access,
    )


def agent_findings(snap: Snapshot, conn):
    out = []
    for node in snap.nodes.values():
        if node.kind != "identity" or node.subtype != "agent":
            continue
        profile = agent_profile(snap, conn, node.id)
        access = profile.pop("_access")
        evidence = [
            e for entry in access["entries"] for p in entry["paths"] for e in p["evidence_ids"]
        ]
        reaches = [
            dict(
                target=entry["resource"]["name"],
                target_id=entry["resource"]["external_id"],
                decision=entry["decision"],
                privileged=False,
                paths=entry["paths"],
            )
            for entry in access["entries"]
            if entry["resource"]
        ]
        base = dict(identity=profile["identity"], usage=[], reaches=reaches, evidence_ids=evidence)
        if profile["prohibited_access"]:
            out.append(
                dict(
                    base,
                    key=key("AGENT_PROHIBITED_DATA", node.id, *profile["prohibited_access"]),
                    rule="AGENT_PROHIBITED_DATA",
                    severity="critical",
                    title=f"{node.name} can reach prohibited data: {', '.join(profile['prohibited_access'])}",
                    summary=(
                        "Effective access includes data classes the registry prohibits for "
                        f"this agent ({', '.join(profile['declared']['prohibited_data'])})."
                    ),
                    recommendation="Propose REMOVE of the grant that confers prohibited access",
                )
            )
        excess = profile["excess_tools"] + profile["excess_data"]
        if excess:
            out.append(
                dict(
                    base,
                    key=key("AGENT_SCOPE_EXCEEDED", node.id, *excess),
                    rule="AGENT_SCOPE_EXCEEDED",
                    severity="high",
                    title=f"{node.name} exceeds its declared scope",
                    summary=(
                        f"Undeclared tools: {', '.join(profile['excess_tools']) or 'none'}; "
                        f"undeclared data: {', '.join(profile['excess_data']) or 'none'}. "
                        f"Declared maximum privilege: {profile['declared']['maximum_privilege']}."
                    ),
                    recommendation="REVIEW: update the registration or remove the excess grant",
                )
            )
        state = profile["expiry"]["state"]
        if state in {"EXPIRED", "EXPIRING"} and profile["effective"]["entitlements"]:
            out.append(
                dict(
                    base,
                    key=key(
                        "AGENT_REGISTRATION_" + state, node.id, profile["expiry"]["expires_at"]
                    ),
                    rule="AGENT_REGISTRATION_" + state,
                    severity="critical" if state == "EXPIRED" else "medium",
                    title=f"{node.name} registration {'expired' if state == 'EXPIRED' else 'expires soon'}"
                    f" ({profile['expiry']['expires_at'][:10]})",
                    summary=(
                        f"{profile['effective']['entitlements']} effective entitlement(s) remain "
                        "attached to this agent."
                    ),
                    recommendation="Renew through review or propose removal of grants",
                )
            )
    return out


def activity(conn, node_id, start: datetime, end: datetime):
    if end <= start or end - start > timedelta(days=366):
        raise ValueError("Activity window must be positive and at most 366 days")
    events = conn.execute(
        "SELECT t.name AS target, t.kind, u.occurred_at, u.observation_id FROM usage_events u "
        "JOIN twin_nodes t ON t.id=u.target_node WHERE u.identity_node=%s AND u.occurred_at>=%s "
        "AND u.occurred_at<%s ORDER BY u.occurred_at DESC LIMIT 500",
        (node_id, start, end),
    ).fetchall()
    coverage = conn.execute(
        "SELECT t.name AS target, c.covered_from, c.covered_to, c.completeness FROM usage_coverage c "
        "JOIN twin_nodes t ON t.id=c.target_node WHERE c.covered_to>%s AND c.covered_from<%s "
        "AND c.target_node IN (SELECT target_node FROM usage_events WHERE identity_node=%s "
        "UNION SELECT r.to_node FROM relationships r WHERE r.from_node=%s)",
        (start, end, node_id, node_id),
    ).fetchall()
    return dict(
        events=events,
        coverage=coverage,
        statement="Only events inside listed coverage windows are observable; outside them "
        "activity is unknown.",
    )
