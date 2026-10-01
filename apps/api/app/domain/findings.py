"""Deterministic, rule-based identity findings (labelled RULE-BASED, never model output).

Each finding has a stable key (rule, version, subject, object) so reviews and reports can bind to
it. Usage statements always carry their telemetry coverage; no observed use is not proof of
never-used access.
"""

from datetime import datetime, timedelta

from ..security import digest
from .access import edge_active, effective_access
from .graph import Snapshot, edge_json, node_json

RULES_VERSION = "rules-2026.09-1"
PRIVILEGED_ACTIONS = {"administer", "manage_config", "reset_password", "operate"}
DORMANT_DAYS = 90
UNUSED_DAYS = 60
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def key(rule, *parts):
    return digest(":".join([rule, RULES_VERSION, *map(str, parts)]))[:24]


def is_privileged(entry):
    resource, permission = entry["resource"], entry["permission"]
    action = (permission or {}).get("attributes", {}).get("action") or entry["action"]
    sensitivity = (resource or {}).get("attributes", {}).get("sensitivity")
    return action in PRIVILEGED_ACTIONS or sensitivity == "critical"


def usage_statement(usage, since=None):
    if not usage or not usage["coverage"]:
        return dict(state="UNKNOWN", text="Usage unknown: no telemetry coverage for this target.")
    relevant = [c for c in usage["coverage"] if not since or c["covered_to"] > since]
    if not relevant:
        return dict(state="UNKNOWN", text="Usage unknown: no telemetry coverage for the period.")
    windows = ", ".join(
        f"{c['covered_from'].date()}→{c['covered_to'].date()} ({c['completeness']})"
        for c in relevant
    )
    last = usage["last_observed_use"]
    if last and (not since or last >= since):
        return dict(
            state="OBSERVED",
            last=last,
            text=f"Last observed use {last.isoformat()}; coverage {windows}.",
        )
    partial = any(c["completeness"] != "complete" for c in relevant)
    return dict(
        state="NOT_OBSERVED_PARTIAL" if partial else "NOT_OBSERVED",
        last=last,
        text=f"No observed use {'since ' + since.date().isoformat() + ' ' if since else ''}during "
        f"coverage {windows}. This does not prove the access was never used.",
    )


def peers_holding(snap: Snapshot, identity: str, department: str, group: str):
    peers = [
        e.src
        for e in snap.inc[department]
        if e.type == "IDENTITY_IN_DEPARTMENT"
        and e.src != identity
        and snap.nodes[e.src].status != "terminated"
    ]
    holding = sum(
        1
        for p in peers
        if any(
            e.type in {"USER_MEMBER_OF_GROUP", "USER_HAS_ROLE"} and e.dst == group
            for e in snap.out[p]
        )
    )
    return len(peers), holding


def routes_through(snap, identity, first_edge, conn):
    """Effective entitlements reached through one starting edge (other routes listed too)."""
    reached = {}
    full = effective_access(snap, identity, conn)
    for entry in full["entries"]:
        through = [p for p in entry["paths"] if p["hops"][0]["edge"]["id"] == first_edge.id]
        if through:
            reached[(entry["resource"] or entry["permission"])["id"]] = dict(entry, paths=through)
    return list(reached.values())


def prior_role_findings(snap, conn, events):
    out = []
    for event in events:
        if event["kind"] != "move":
            continue
        identity = str(event["identity_node"])
        if identity not in snap.nodes or event["effective_at"] > snap.effective_at:
            continue
        department = next(
            (e.dst for e in snap.out[identity] if e.type == "IDENTITY_IN_DEPARTMENT"), None
        )
        for edge in snap.out[identity]:
            if edge.type not in {"USER_MEMBER_OF_GROUP", "USER_HAS_ROLE"}:
                continue
            if edge.valid_from >= event["effective_at"] or not edge_active(edge, snap.effective_at):
                continue
            peers, holding = (
                peers_holding(snap, identity, department, edge.dst) if department else (0, 0)
            )
            if peers and holding / peers >= 0.5:
                continue  # common in the new department: not attributed to the previous role
            reached = routes_through(snap, identity, edge, conn)
            privileged = [r for r in reached if is_privileged(r)]
            usage = [
                dict(
                    target=(r["resource"] or r["permission"])["name"],
                    **usage_statement(r["usage"], event["effective_at"]),
                )
                for r in reached
            ]
            out.append(
                dict(
                    key=key("PRIOR_ROLE_RETAINED", identity, edge.relationship_id),
                    rule="PRIOR_ROLE_RETAINED",
                    severity="high" if privileged else "medium",
                    identity=node_json(snap.nodes[identity]),
                    title=f"{snap.nodes[identity].name} retains {snap.nodes[edge.dst].name} from a previous role",
                    summary=(
                        f"Granted {edge.valid_from.date()} ({edge.attributes.get('origin')}, "
                        f"{edge.attributes.get('ticket') or 'no ticket'}) before the "
                        f"{event['details'].get('from_department')} → {event['details'].get('to_department')} "
                        f"move on {event['effective_at'].date()}. {holding} of {peers} current peers in "
                        f"{event['details'].get('to_department')} hold it."
                    ),
                    grant=edge_json(edge),
                    event=dict(
                        kind=event["kind"],
                        effective_at=event["effective_at"].isoformat(),
                        details=event["details"],
                        evidence_id=str(event["observation_id"]),
                    ),
                    peers=dict(sample_size=peers, holding=holding),
                    reaches=[
                        dict(
                            target=(r["resource"] or r["permission"])["name"],
                            target_id=(r["resource"] or r["permission"])["external_id"],
                            decision=r["decision"],
                            privileged=is_privileged(r),
                            paths=r["paths"],
                        )
                        for r in reached
                    ],
                    usage=usage,
                    recommendation="REVIEW" if not privileged else "REVIEW / propose REMOVE",
                    evidence_ids=[edge.observation_id, str(event["observation_id"])]
                    + [e for r in reached for p in r["paths"] for e in p["evidence_ids"]],
                )
            )
    return out


def dormant_findings(snap, conn):
    out = []
    cutoff = snap.effective_at - timedelta(days=DORMANT_DAYS)
    for node in snap.nodes.values():
        if (
            node.kind != "identity"
            or node.subtype in {"machine", "agent"}
            or node.status == "terminated"
        ):
            continue
        account = next(
            (snap.nodes[e.dst] for e in snap.out[node.id] if e.type == "HAS_ACCOUNT"), None
        )
        if not account or not account.attributes.get("last_sign_in"):
            continue
        last = datetime.fromisoformat(account.attributes["last_sign_in"])
        if last >= cutoff:
            continue
        access = effective_access(snap, node.id, conn)
        privileged = [e for e in access["entries"] if is_privileged(e) and e["decision"] != "DENY"]
        if not privileged:
            continue
        out.append(
            dict(
                key=key("DORMANT_PRIVILEGED", node.id),
                rule="DORMANT_PRIVILEGED",
                severity="high",
                identity=node_json(node),
                title=f"Dormant privileged identity: {node.name}",
                summary=(
                    f"Last directory sign-in {last.date()} ({(snap.effective_at - last).days} days "
                    f"before the evaluation time) while holding {len(privileged)} privileged "
                    f"entitlement(s). MFA registered: {node.attributes.get('mfa_registered')}."
                ),
                account=node_json(account),
                reaches=[
                    dict(
                        target=(e["resource"] or e["permission"])["name"],
                        target_id=(e["resource"] or e["permission"])["external_id"],
                        decision=e["decision"],
                        privileged=True,
                        paths=e["paths"],
                    )
                    for e in privileged
                ],
                usage=[
                    dict(
                        target=(e["resource"] or e["permission"])["name"],
                        **usage_statement(e["usage"]),
                    )
                    for e in privileged
                ],
                recommendation="REVIEW / propose REMOVE or disable",
                evidence_ids=[
                    p_e for e in privileged for p in e["paths"] for p_e in p["evidence_ids"]
                ],
            )
        )
    return out


def leaver_findings(snap, conn):
    out = []
    for node in snap.nodes.values():
        if node.kind != "identity" or node.status != "terminated":
            continue
        accounts = [snap.nodes[e.dst] for e in snap.out[node.id] if e.type == "HAS_ACCOUNT"]
        enabled = [a for a in accounts if a.attributes.get("enabled")]
        access = effective_access(snap, node.id, conn)
        grants = [e for e in access["entries"] if e["decision"] != "DENY"]
        if not enabled and not grants:
            continue
        out.append(
            dict(
                key=key("TERMINATED_WITH_ACCESS", node.id),
                rule="TERMINATED_WITH_ACCESS",
                severity="critical",
                identity=node_json(node),
                title=f"Terminated identity retains access: {node.name}",
                summary=(
                    f"Employment status terminated (effective {node.attributes.get('terminated_at', 'unknown')}). "
                    f"{len(enabled)} enabled account(s) and {len(grants)} effective entitlement(s) remain."
                ),
                accounts=[node_json(a) for a in enabled],
                reaches=[
                    dict(
                        target=(e["resource"] or e["permission"])["name"],
                        target_id=(e["resource"] or e["permission"])["external_id"],
                        decision=e["decision"],
                        privileged=is_privileged(e),
                        paths=e["paths"],
                    )
                    for e in grants
                ],
                usage=[],
                recommendation="Propose disable account and REMOVE remaining grants",
                evidence_ids=[p_e for e in grants for p in e["paths"] for p_e in p["evidence_ids"]],
            )
        )
    return out


def unused_findings(snap, conn):
    out = []
    for node in snap.nodes.values():
        if node.kind != "identity" or node.status == "terminated":
            continue
        access = effective_access(snap, node.id, conn)
        for entry in access["entries"]:
            if entry["decision"] != "ALLOW" or not entry["resource"] or not is_privileged(entry):
                continue
            usage = entry["usage"]
            complete = [
                c
                for c in (usage or {}).get("coverage", [])
                if c["completeness"] == "complete"
                and (c["covered_to"] - c["covered_from"]).days >= UNUSED_DAYS
            ]
            if not complete:
                continue
            window_start = min(c["covered_from"] for c in complete)
            if usage["last_observed_use"] and usage["last_observed_use"] >= window_start:
                continue
            resource = entry["resource"]
            out.append(
                dict(
                    key=key(
                        "UNUSED_PRIVILEGED_ENTITLEMENT",
                        node.id,
                        resource["id"],
                        (entry["permission"] or {}).get("id"),
                    ),
                    rule="UNUSED_PRIVILEGED_ENTITLEMENT",
                    severity="medium",
                    identity=node_json(node),
                    title=f"{node.name}: no observed use of {resource['name']}",
                    summary=(
                        f"{(entry['permission'] or {}).get('name', entry['action'])} on "
                        f"{resource['name']} via {len(entry['paths'])} route(s). "
                        f"{usage_statement(usage, window_start)['text']}"
                    ),
                    reaches=[
                        dict(
                            target=resource["name"],
                            target_id=resource["external_id"],
                            decision=entry["decision"],
                            privileged=True,
                            paths=entry["paths"],
                        )
                    ],
                    usage=[dict(target=resource["name"], **usage_statement(usage, window_start))],
                    recommendation="REVIEW",
                    evidence_ids=[e for p in entry["paths"] for e in p["evidence_ids"]],
                )
            )
    return out


CREDENTIAL_MAX_AGE_DAYS = 365
CREDENTIAL_EXPIRY_WARNING_DAYS = 30


def machine_context(snap: Snapshot, node_id: str):
    """Owner, credentials and dependents of a machine or agent identity (metadata only)."""
    node = snap.nodes[node_id]
    owners = [snap.nodes[e.src] for e in snap.inc[node_id] if e.type == "USER_OWNS_SERVICE_ACCOUNT"]
    credentials = [(snap.nodes[e.dst], e) for e in snap.out[node_id] if e.type == "HAS_CREDENTIAL"]
    dependents = [snap.nodes[e.src] for e in snap.inc[node_id] if e.type == "RESOURCE_DEPENDS_ON"]
    direct = [
        snap.nodes[e.dst]
        for e in snap.out[node_id]
        if e.type in {"SERVICE_ACCOUNT_ACCESS_APPLICATION", "AI_AGENT_ACCESS_DATA"}
    ]
    return node, owners, credentials, dependents, direct


def machine_findings(snap: Snapshot, conn):
    out = []
    now = snap.effective_at
    for node in snap.nodes.values():
        if node.kind != "identity" or node.subtype not in {"machine", "agent"}:
            continue
        _, owners, credentials, dependents, direct = machine_context(snap, node.id)
        active_owners = [o for o in owners if o.status != "terminated"]
        dependent_names = [d.name for d in dependents]
        if not active_owners:
            access = effective_access(snap, node.id, conn)
            privileged = [e for e in access["entries"] if is_privileged(e)]
            out.append(
                dict(
                    key=key("OWNERLESS_MACHINE", node.id),
                    rule="OWNERLESS_MACHINE",
                    severity="high" if privileged else "medium",
                    identity=node_json(node),
                    title=f"Non-human identity without an accountable owner: {node.name}",
                    summary=(
                        f"{node.subtype.title()} identity '{node.name}' ({node.attributes.get('purpose', 'no purpose recorded')}) "
                        f"has no active owner{' (owner terminated)' if owners else ''}. "
                        f"{len(privileged)} privileged entitlement(s); dependents: {', '.join(dependent_names) or 'none modelled'}."
                    ),
                    reaches=[
                        dict(
                            target=(e["resource"] or e["permission"])["name"],
                            target_id=(e["resource"] or e["permission"])["external_id"],
                            decision=e["decision"],
                            privileged=is_privileged(e),
                            paths=e["paths"],
                        )
                        for e in access["entries"]
                    ],
                    usage=[],
                    dependents=dependent_names,
                    recommendation="Propose an accountable owner (ownership never grants access)",
                    evidence_ids=[
                        e
                        for entry in access["entries"]
                        for p in entry["paths"]
                        for e in p["evidence_ids"]
                    ],
                )
            )
        for credential, edge in credentials:
            attrs = credential.attributes
            rotated = attrs.get("rotated_at") or attrs.get("created_at")
            expires = attrs.get("expires_at")
            facts = dict(
                credential=credential.external_id,
                type=credential.subtype,
                rotated_at=rotated,
                expires_at=expires,
            )
            if expires:
                left = (datetime.fromisoformat(expires) - now).days
                if left <= CREDENTIAL_EXPIRY_WARNING_DAYS:
                    out.append(
                        dict(
                            key=key("CREDENTIAL_EXPIRING", credential.id, expires),
                            rule="CREDENTIAL_EXPIRING",
                            severity="high" if left < 0 or dependents else "medium",
                            identity=node_json(node),
                            title=f"{credential.subtype.replace('_', ' ').title()} for {node.name} "
                            f"{'expired' if left < 0 else f'expires in {left} days'}",
                            summary=(
                                f"{credential.external_id} expires {expires[:10]}. Dependents that may fail "
                                f"on expiry: {', '.join(dependent_names) or 'none modelled'}. "
                                "Only metadata is stored; no secret material is available to the platform."
                            ),
                            credential=facts,
                            reaches=[],
                            usage=[],
                            dependents=dependent_names,
                            recommendation="Propose rotation before expiry and coordinate dependents",
                            evidence_ids=[edge.observation_id],
                        )
                    )
            # Federated credentials issue short-lived tokens and hold no long-lived secret.
            secretless = credential.subtype == "federated_credential"
            if (
                not secretless
                and rotated
                and (now - datetime.fromisoformat(rotated)).days > CREDENTIAL_MAX_AGE_DAYS
            ):
                age = (now - datetime.fromisoformat(rotated)).days
                out.append(
                    dict(
                        key=key("CREDENTIAL_AGED", credential.id, rotated),
                        rule="CREDENTIAL_AGED",
                        severity="medium",
                        identity=node_json(node),
                        title=f"{credential.external_id} not rotated for {age} days",
                        summary=(
                            f"Last rotation {rotated[:10]} exceeds the {CREDENTIAL_MAX_AGE_DAYS}-day "
                            f"policy. Dependents: {', '.join(dependent_names) or 'none modelled'}."
                        ),
                        credential=facts,
                        reaches=[],
                        usage=[],
                        dependents=dependent_names,
                        recommendation="Propose rotation with bounded overlap for dependents",
                        evidence_ids=[edge.observation_id],
                    )
                )
    return out


def all_findings(snap: Snapshot, conn, environment_id):
    events = conn.execute(
        "SELECT * FROM employment_events WHERE environment_id=%s AND effective_at<=%s "
        "ORDER BY effective_at",
        (environment_id, snap.effective_at),
    ).fetchall()
    results = (
        prior_role_findings(snap, conn, events)
        + leaver_findings(snap, conn)
        + dormant_findings(snap, conn)
        + unused_findings(snap, conn)
        + machine_findings(snap, conn)
    )
    for item in results:
        item["rules_version"] = RULES_VERSION
        item["basis"] = "RULE-BASED"
        item["evidence_ids"] = sorted(set(item["evidence_ids"]))
    results.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["rule"], f["title"]))
    return results


def timeline(snap: Snapshot, conn, identity):
    node = snap.nodes[identity]
    items = []
    for row in conn.execute(
        "SELECT kind, effective_at, details, observation_id FROM employment_events "
        "WHERE identity_node=%s",
        (identity,),
    ).fetchall():
        items.append(
            dict(
                at=row["effective_at"],
                kind=f"employment.{row['kind']}",
                text=", ".join(f"{k}: {v}" for k, v in row["details"].items()),
                evidence_id=str(row["observation_id"]),
            )
        )
    for row in conn.execute(
        "SELECT r.type, r.to_node, r.from_node, rr.valid_from, rr.valid_to, rr.attributes, "
        "rr.observation_id, rr.end_inferred FROM relationships r JOIN relationship_revisions rr "
        "ON rr.relationship_id=r.id WHERE (r.from_node=%s) AND rr.recorded_from<=%s "
        "AND (rr.recorded_to IS NULL OR rr.recorded_to>%s)",
        (identity, snap.known_at, snap.known_at),
    ).fetchall():
        other = conn.execute(
            "SELECT r.name, n.kind FROM twin_nodes n JOIN node_revisions r ON r.node_id=n.id "
            "WHERE n.id=%s ORDER BY r.valid_from DESC LIMIT 1",
            (row["to_node"],),
        ).fetchone()
        name = other["name"] if other else str(row["to_node"])
        ticket = row["attributes"].get("ticket")
        items.append(
            dict(
                at=row["valid_from"],
                kind="grant.start" if row["type"] != "IDENTITY_IN_DEPARTMENT" else "context.start",
                text=f"{row['type']} → {name}{' · ' + ticket if ticket else ''}",
                evidence_id=str(row["observation_id"]),
            )
        )
        if row["valid_to"]:
            items.append(
                dict(
                    at=row["valid_to"],
                    kind="grant.end",
                    text=f"{row['type']} → {name} ended{' (inferred)' if row['end_inferred'] else ''}",
                    evidence_id=str(row["observation_id"]),
                )
            )
    for row in conn.execute(
        "SELECT t.name, min(u.occurred_at) AS first, max(u.occurred_at) AS last, count(*) AS n "
        "FROM usage_events u JOIN twin_nodes t ON t.id=u.target_node WHERE u.identity_node=%s "
        "GROUP BY t.name",
        (identity,),
    ).fetchall():
        items.append(
            dict(
                at=row["last"],
                kind="usage.summary",
                text=f"{row['n']} observed uses of {row['name']} between "
                f"{row['first'].date()} and {row['last'].date()}",
                evidence_id=None,
            )
        )
    items.sort(key=lambda i: i["at"])
    return dict(identity=node_json(node), events=[dict(i, at=i["at"].isoformat()) for i in items])
