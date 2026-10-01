"""Report builders (ROADMAP "Reporting scope"). Every row comes from the deterministic engines,
cites evidence IDs and states its basis; partial or inferred results are labelled."""

import csv
import io
import re

from .access import effective_access
from .agents import agent_profile
from .exposure import attack_paths
from .findings import all_findings, is_privileged, machine_context, usage_statement
from .graph import Snapshot

REPORT_TYPES = {
    "identity_exposure": "Identity Exposure",
    "privileged_access": "Privileged Access",
    "dormant_identity": "Dormant Identity",
    "machine_identity": "Machine Identity",
    "ai_agent_governance": "AI Agent Governance",
    "access_review": "Access Review",
    "jml": "JML",
    "privilege_creep": "Privilege Creep",
    "attack_path": "Attack Path",
    "policy_compliance": "Policy Compliance",
    "lab_completion": "Lab Completion",
}
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
FREE_TEXT = {"justification", "summary_text", "rationale"}
DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def redact(value, field, profile):
    if profile == "full" or value is None:
        return value
    if field in FREE_TEXT:
        return "[redacted: free text]"
    if isinstance(value, str):
        return EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value)
    return value


def safe_cell(value):
    """Neutralise spreadsheet formula injection: cells starting with = + - @ tab or CR."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(DANGEROUS) else text


def to_csv(columns, rows, metadata):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for key, value in metadata.items():
        writer.writerow([safe_cell(f"# {key}: {value}")])
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(row.get(c)) for c in columns])
    return buffer.getvalue()


def _findings(snap, conn, env, rules):
    return [f for f in all_findings(snap, conn, env) if f["rule"] in rules]


def _finding_rows(findings):
    return [
        dict(
            identity=f["identity"]["name"],
            identity_type=f["identity"]["subtype"],
            rule=f["rule"],
            severity=f["severity"],
            title=f["title"],
            summary_text=f["summary"],
            recommendation=f["recommendation"],
            basis=f"{f['basis']} {f['rules_version']}",
            evidence_ids=" ".join(f["evidence_ids"]),
        )
        for f in findings
    ]


FINDING_COLUMNS = [
    "identity",
    "identity_type",
    "rule",
    "severity",
    "title",
    "summary_text",
    "recommendation",
    "basis",
    "evidence_ids",
]


def build(report_type, snap: Snapshot, conn, environment_id):
    notes = []
    if report_type == "identity_exposure":
        paths = attack_paths(snap, conn, None, None, 2, 300)
        if not paths["complete"]:
            notes.append(f"Exposure search bounded: {paths['truncation_reason']}")
        findings = all_findings(snap, conn, environment_id)
        rows = []
        for n in sorted(snap.nodes.values(), key=lambda n: n.name):
            if n.kind != "identity":
                continue
            access = effective_access(snap, n.id, conn)
            rows.append(
                dict(
                    identity=n.name,
                    identity_type=n.subtype,
                    status=n.status,
                    entitlements=len(access["entries"]),
                    privileged=sum(1 for e in access["entries"] if is_privileged(e)),
                    findings=sum(1 for f in findings if f["identity"]["id"] == n.id),
                    exposure_paths=sum(1 for p in paths["paths"] if p["source"]["id"] == n.id),
                    completeness="complete" if access["complete"] else "partial",
                    basis="DETERMINISTIC",
                    evidence_ids=" ".join(
                        sorted(
                            {
                                e
                                for x in access["entries"]
                                for p in x["paths"]
                                for e in p["evidence_ids"]
                            }
                        )
                    ),
                )
            )
        return list(rows[0]) if rows else [], rows, notes
    if report_type == "privileged_access":
        rows = []
        for n in sorted(snap.nodes.values(), key=lambda n: n.name):
            if n.kind != "identity":
                continue
            for entry in effective_access(snap, n.id, conn)["entries"]:
                if not is_privileged(entry):
                    continue
                first = entry["paths"][0]["hops"][0]["edge"]["attributes"]
                target = entry["resource"] or entry["permission"]
                rows.append(
                    dict(
                        identity=n.name,
                        entitlement=target["name"],
                        permission=(entry["permission"] or {}).get("name", entry["action"]),
                        decision=entry["decision"],
                        routes=len(entry["paths"]),
                        origin=first.get("origin"),
                        ticket=first.get("ticket"),
                        approver=first.get("approver"),
                        usage=usage_statement(entry["usage"])["text"],
                        basis="OBSERVED grants",
                        evidence_ids=" ".join(e for p in entry["paths"] for e in p["evidence_ids"]),
                    )
                )
        columns = [
            "identity",
            "entitlement",
            "permission",
            "decision",
            "routes",
            "origin",
            "ticket",
            "approver",
            "usage",
            "basis",
            "evidence_ids",
        ]
        return columns, rows, notes
    if report_type in {"dormant_identity", "privilege_creep"}:
        rules = {
            "dormant_identity": {"DORMANT_PRIVILEGED", "TERMINATED_WITH_ACCESS"},
            "privilege_creep": {"PRIOR_ROLE_RETAINED", "UNUSED_PRIVILEGED_ENTITLEMENT"},
        }[report_type]
        notes.append(
            "Usage statements are bounded by telemetry coverage; no observed use is not proof of non-use."
        )
        return FINDING_COLUMNS, _finding_rows(_findings(snap, conn, environment_id, rules)), notes
    if report_type == "machine_identity":
        rows = []
        findings = all_findings(snap, conn, environment_id)
        for n in sorted(snap.nodes.values(), key=lambda n: n.name):
            if n.kind != "identity" or n.subtype != "machine":
                continue
            _, owners, credentials, dependents, _ = machine_context(snap, n.id)
            rows.append(
                dict(
                    identity=n.name,
                    machine_kind=n.attributes.get("machine_kind"),
                    owner=", ".join(o.name for o in owners) or "NONE",
                    credentials="; ".join(
                        f"{c.external_id} rotated {c.attributes.get('rotated_at', '?')[:10]} "
                        f"expires {(c.attributes.get('expires_at') or 'n/a')[:10]}"
                        for c, _ in credentials
                    ),
                    dependents=", ".join(d.name for d in dependents),
                    findings=", ".join(
                        sorted({f["rule"] for f in findings if f["identity"]["id"] == n.id})
                    ),
                    basis="OBSERVED metadata (no secret values)",
                    evidence_ids="",
                )
            )
        return list(rows[0]) if rows else [], rows, notes
    if report_type == "ai_agent_governance":
        rows = []
        for n in sorted(snap.nodes.values(), key=lambda n: n.name):
            if n.kind != "identity" or n.subtype != "agent":
                continue
            p = agent_profile(snap, conn, n.id)
            p.pop("_access")
            rows.append(
                dict(
                    agent=n.name,
                    owner=p["declared"]["owner"],
                    model=p["declared"]["model"],
                    expiry_state=p["expiry"]["state"],
                    tools=", ".join(p["effective"]["tools"]),
                    data=", ".join(p["effective"]["data"]),
                    excess=", ".join(p["excess_tools"] + p["excess_data"]),
                    prohibited_reachable=", ".join(p["prohibited_access"]),
                    basis="DECLARED vs EFFECTIVE",
                    evidence_ids="",
                )
            )
        return list(rows[0]) if rows else [], rows, notes
    if report_type == "access_review":
        rows = conn.execute(
            "SELECT c.name AS campaign, i.recommendation, i.recommendation_basis AS basis, i.status, i.decision, "
            "u.display_name AS reviewer, i.decision_justification AS justification, i.decided_at, "
            "i.evidence->'grant'->>'type' AS grant_type, i.evidence->'grant'->'attributes'->>'ticket' AS ticket, "
            "array_to_string(i.finding_keys, ' ') AS evidence_ids FROM review_items i JOIN review_campaigns c "
            "ON c.id=i.campaign_id JOIN users u ON u.id=i.reviewer_id WHERE c.environment_id=%s "
            "ORDER BY c.created_at, i.status",
            (environment_id,),
        ).fetchall()
        return (
            [
                "campaign",
                "grant_type",
                "ticket",
                "recommendation",
                "basis",
                "status",
                "decision",
                "reviewer",
                "justification",
                "decided_at",
                "evidence_ids",
            ],
            rows,
            notes,
        )
    if report_type == "jml":
        rows = conn.execute(
            "SELECT e.kind, e.effective_at, e.details::text AS details, w.id AS workflow, "
            "array_length(w.change_request_ids,1) AS proposals, e.observation_id AS evidence_ids "
            "FROM employment_events e LEFT JOIN lifecycle_workflows w ON w.event_id=e.id "
            "WHERE e.environment_id=%s ORDER BY e.effective_at",
            (environment_id,),
        ).fetchall()
        return (
            ["kind", "effective_at", "details", "workflow", "proposals", "evidence_ids"],
            rows,
            notes,
        )
    if report_type == "attack_path":
        paths = attack_paths(snap, conn, None, None, 2, 300)
        if not paths["complete"]:
            notes.append(f"Search bounded: {paths['truncation_reason']}; unlisted paths may exist.")
        notes.append("Potential exposure only; not evidence of exploitation.")
        rows = [
            dict(
                source=p["source"]["name"],
                destination=p["destination"]["name"],
                status=p["status"],
                sensitivity=p["sensitivity"],
                steps=" -> ".join(f"{s['kind']}:{s['to']['name']}" for s in p["steps"]),
                controls="; ".join(p["defensive_controls"]),
                basis=paths["rules_version"],
                evidence_ids=" ".join(p["evidence_ids"]),
            )
            for p in paths["paths"]
        ]
        return (
            [
                "source",
                "destination",
                "status",
                "sensitivity",
                "steps",
                "controls",
                "basis",
                "evidence_ids",
            ],
            rows,
            notes,
        )
    if report_type == "policy_compliance":
        policies = conn.execute(
            "SELECT v.definition->>'name' AS policy, v.version, v.definition->>'action' AS action, v.activated_at "
            "FROM policy_versions v JOIN policies p ON p.id=v.policy_id WHERE p.environment_id=%s AND v.status='ACTIVE'",
            (environment_id,),
        ).fetchall()
        notes.append(
            "Active policies: "
            + (
                "; ".join(f"{p['policy']} v{p['version']} ({p['action']})" for p in policies)
                or "none"
            )
        )
        return (
            FINDING_COLUMNS,
            _finding_rows(_findings(snap, conn, environment_id, {"POLICY_VIOLATION"})),
            notes,
        )
    if report_type == "lab_completion":
        rows = conn.execute(
            "SELECT u.display_name AS learner, a.lab_id, a.lab_version, a.status, a.started_at, a.submitted_at, "
            "(a.result->'score'->>'total')::int AS score, (a.result->'score'->>'passed') AS passed, "
            "jsonb_array_length(a.hints_used) AS hints, a.resets, a.solution_viewed FROM lab_attempts a "
            "JOIN users u ON u.id=a.learner_id ORDER BY a.started_at"
        ).fetchall()
        notes.append("Scores are produced by deterministic validators; models never award scores.")
        return (
            [
                "learner",
                "lab_id",
                "lab_version",
                "status",
                "score",
                "passed",
                "hints",
                "resets",
                "solution_viewed",
                "started_at",
                "submitted_at",
            ],
            rows,
            notes,
        )
    raise ValueError("Unknown report type")
