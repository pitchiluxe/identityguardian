"""Deterministic question -> structured intent. Only allowlisted intents exist; anything else asks
for clarification. Nothing here generates or executes SQL, shell or code."""

import re
from dataclasses import dataclass, field

INTENTS = {
    "identity_status": "Who an identity is: type, department, status",
    "effective_access": "What an identity can access, with routes",
    "lineage": "Why an identity can access a specific target",
    "who_can_access": "Which identities can access a target",
    "ownerless_machines": "Non-human identities without an accountable owner",
    "dormant_admins": "Privileged identities with no recent sign-in",
    "exposure_paths": "Defensive exposure paths from an identity",
    "prior_role_access": "Access retained from an identity's previous role",
}
REFUSE = re.compile(
    r"\b(delete|drop|remove|revoke|grant|disable|execute|approve|insert|update|"
    r"sql|shell|script|password|secret|token|exploit|hack)\b",
    re.I,
)


@dataclass
class Intent:
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class Clarification:
    reason: str
    supported: dict = field(default_factory=lambda: dict(INTENTS))


def _find(names, text):
    """Longest known name mentioned in the text (names map lowercase -> external id)."""
    hits = [
        (len(n), ext) for n, ext in names.items() if re.search(r"\b" + re.escape(n) + r"\b", text)
    ]
    return [ext for _, ext in sorted(hits, reverse=True)]


def parse(question: str, identities: dict, targets: dict):
    text = " ".join(question.lower().split())
    if len(text) < 4:
        return Clarification("Ask a question about identities or access.")
    if REFUSE.search(text):
        return Clarification(
            "The investigator only answers read-only questions; it cannot change "
            "access, run commands or reveal secrets."
        )
    people = _find(identities, text)
    things = _find(targets, text)
    if re.search(r"\b(owner|ownerless|unowned)\b", text) and re.search(
        r"\b(machine|service|account|workload)", text
    ):
        return Intent("ownerless_machines")
    if re.search(r"\b(dormant|inactive|stale)\b", text):
        return Intent("dormant_admins")
    if re.search(r"\bwho\b.*\b(access|reach|use)\b", text) and things:
        return Intent("who_can_access", dict(target=things[0]))
    if not people:
        return Clarification("Name an identity or target the question is about.")
    if len(people) > 1 and not things:
        return Clarification("The question mentions several identities; ask about one at a time.")
    identity = people[0]
    if re.search(r"\b(attack|exposure|path|escalat|compromise)\w*", text):
        return Intent("exposure_paths", dict(identity=identity))
    if re.search(r"\b(previous|prior|old|former|legacy|creep|retain)\w*", text):
        return Intent("prior_role_access", dict(identity=identity))
    if re.search(r"\bwhy\b|\bhow\b.*\b(get|obtain|have)\b|\blineage\b", text) and things:
        return Intent("lineage", dict(identity=identity, target=things[0]))
    if re.search(r"\b(access|reach|can|permission|entitle)\w*", text):
        if things:
            return Intent("lineage", dict(identity=identity, target=things[0]))
        return Intent("effective_access", dict(identity=identity))
    if re.search(r"\b(who is|status|type|department|terminated|active)\b", text):
        return Intent("identity_status", dict(identity=identity))
    return Clarification(
        "Ask what an identity can access, why, who can access a target, or about "
        "ownerless machines, dormant administrators or exposure paths."
    )
