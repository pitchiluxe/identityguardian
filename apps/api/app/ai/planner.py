"""Authorized planner: intent -> allowlisted deterministic query -> evidence bundle.

Authorization happens before retrieval. Facts are produced by the deterministic engines; each
carries an ID (F1, F2, ...) that model claims must cite, plus the underlying evidence IDs.
"""

from ..domain.access import effective_access, principals_for
from ..domain.exposure import attack_paths
from ..domain.findings import all_findings

CAPABILITY = {
    "identity_status": "identity:read",
    "effective_access": "access:read",
    "lineage": "access:read",
    "who_can_access": "access:read",
    "ownerless_machines": "findings:read",
    "dormant_admins": "findings:read",
    "exposure_paths": "findings:read",
    "prior_role_access": "findings:read",
}
MAX_FACTS = 25


class Bundle:
    def __init__(self, intent, snapshot):
        self.intent, self.snapshot = intent, snapshot
        self.facts, self.complete, self.notes = [], True, []

    def add(self, text, evidence_ids=(), data=None):
        if len(self.facts) >= MAX_FACTS:
            self.complete = False
            return
        self.facts.append(
            dict(
                id=f"F{len(self.facts) + 1}",
                text=text,
                evidence_ids=sorted(set(evidence_ids)),
                data=data or {},
            )
        )

    def as_dict(self):
        return dict(
            intent=self.intent.name,
            params=self.intent.params,
            facts=self.facts,
            complete=self.complete,
            notes=self.notes,
            snapshot=self.snapshot.describe(),
        )


def route(path):
    return " → ".join(h["to"]["name"] for h in path["hops"])


def plan(intent, snap, conn, environment_id):
    bundle = Bundle(intent, snap)
    params = intent.params
    node = snap.by_external(params["identity"]) if "identity" in params else None
    target = snap.by_external(params["target"]) if "target" in params else None
    if ("identity" in params and not node) or ("target" in params and not target):
        bundle.notes.append("A named identity or target is not effective in this environment now.")
        return bundle
    if intent.name == "identity_status":
        a = node.attributes
        bundle.add(
            f"{node.name} is a {node.subtype} identity with status {node.status}, department "
            f"{a.get('department', 'unknown')}, title {a.get('title', 'unknown')}."
        )
    elif intent.name in {"effective_access", "lineage"}:
        result = effective_access(snap, node.id, conn)
        bundle.complete = result["complete"]
        for entry in result["entries"]:
            res = entry["resource"] or entry["permission"]
            if (
                target
                and res["id"] != target.id
                and (entry["permission"] or {}).get("id") != target.id
            ):
                continue
            perm = entry["permission"]["name"] if entry["permission"] else entry["action"]
            for path in entry["paths"][:3]:
                first = path["hops"][0]["edge"]["attributes"]
                bundle.add(
                    f"{node.name} has {path['status']} access to {res['name']} ({perm}) via {route(path)}; "
                    f"first grant origin {first.get('origin')}, ticket {first.get('ticket') or 'none'}, "
                    f"approver {first.get('approver') or 'unknown'}.",
                    path["evidence_ids"],
                )
            usage = entry["usage"]
            if usage and usage["coverage"]:
                bundle.add(
                    f"Observed uses of {res['name']} by {node.name}: {usage['observed_events']} "
                    "within telemetry coverage (absence of use is not proof of non-use)."
                )
        if target and not bundle.facts:
            bundle.add(
                f"No grant route from {node.name} to {target.name} was found within the bounds"
                f"{'' if result['complete'] else ' (search was truncated; this is not proof of absence)'}."
            )
    elif intent.name == "who_can_access":
        result = principals_for(snap, target.id)
        bundle.complete = result["complete"]
        for p in result["principals"]:
            bundle.add(
                f"{p['identity']['name']} has {p['decision']} access to {target.name} via "
                f"{len(p['paths'])} route(s), e.g. {route(p['paths'][0])}.",
                [e for path in p["paths"] for e in path["evidence_ids"]],
            )
    elif intent.name == "exposure_paths":
        result = attack_paths(snap, conn, node.id, None, 2, 10)
        bundle.complete = result["complete"]
        for p in result["paths"]:
            steps = " → ".join(f"{s['kind']}:{s['to']['name']}" for s in p["steps"])
            bundle.add(
                f"Potential {p['status']} exposure from {node.name} to {p['destination']['name']} "
                f"({p['sensitivity']}) via {steps}. Not evidence of exploitation.",
                p["evidence_ids"],
            )
    else:
        rule = {
            "ownerless_machines": "OWNERLESS_MACHINE",
            "dormant_admins": "DORMANT_PRIVILEGED",
            "prior_role_access": "PRIOR_ROLE_RETAINED",
        }[intent.name]
        for f in all_findings(snap, conn, environment_id):
            if f["rule"] != rule or (node and f["identity"]["id"] != node.id):
                continue
            bundle.add(f"[{f['severity']}] {f['title']}. {f['summary']}", f["evidence_ids"])
        if not bundle.facts:
            bundle.add(f"No {rule.replace('_', ' ').lower()} findings at this time (rule-based).")
    if not bundle.complete:
        bundle.notes.append("A traversal or fact bound was reached; results are partial.")
    return bundle
