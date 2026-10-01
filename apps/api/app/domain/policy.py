"""Policy-as-code (ROADMAP "Policy proposal contract").

A policy is data, never code: typed conditions over an allowlist of fields and operators. It is
validated, tested against its own positive/negative/exception cases, simulated against the twin,
independently approved by digest and only then activated. FLAG never revokes; REJECT_PROPOSED
blocks new grant proposals that would violate it.
"""

from datetime import datetime, timezone

from ..jsonutil import dumps
from ..security import digest
from .graph import Snapshot, edge_json, node_json

SCHEMA_VERSION = "1"
FIELDS = {
    "identity.subtype",
    "identity.department",
    "identity.status",
    "identity.mfa_registered",
    "identity.external_id",
    "target.kind",
    "target.name",
    "target.external_id",
    "target.sensitivity",
    "target.data_classification",
    "grant.type",
    "grant.origin",
    "grant.expires_at",
    "grant.ticket",
    "grant.approver",
}
OPERATORS = {"eq", "neq", "in", "not_in", "exists", "missing", "contains", "before", "after"}
ACTIONS = {"flag", "reject_proposed"}
GRANT_TYPES = {
    "USER_MEMBER_OF_GROUP",
    "USER_HAS_ROLE",
    "SERVICE_ACCOUNT_ACCESS_APPLICATION",
    "AI_AGENT_USES_TOOL",
    "AI_AGENT_ACCESS_DATA",
}
MAX_DEPTH, MAX_CONDITIONS = 3, 20


class PolicyError(ValueError):
    pass


def _check_condition(node, depth=1, count=None):
    count = count if count is not None else [0]
    if depth > MAX_DEPTH:
        raise PolicyError("Conditions are nested too deeply")
    if not isinstance(node, dict):
        raise PolicyError("Each condition is {all:[...]}, {any:[...]} or {field, op, value}")
    if set(node) & {"all", "any"}:
        key = "all" if "all" in node else "any"
        if set(node) != {key} or not isinstance(node[key], list) or not node[key]:
            raise PolicyError(f"'{key}' must be a non-empty list")
        for child in node[key]:
            _check_condition(child, depth + 1, count)
        return
    if not {"field", "op"} <= set(node):
        raise PolicyError("Each condition is {all:[...]}, {any:[...]} or {field, op, value}")
    count[0] += 1
    if count[0] > MAX_CONDITIONS:
        raise PolicyError("Too many conditions")
    if set(node) - {"field", "op", "value"}:
        raise PolicyError("Unknown condition keys")
    if node["field"] not in FIELDS:
        raise PolicyError(f"Unknown field {node['field']}")
    if node["op"] not in OPERATORS:
        raise PolicyError(f"Unknown operator {node['op']}")
    if node["op"] in {"exists", "missing"}:
        if "value" in node:
            raise PolicyError(f"'{node['op']}' takes no value")
    elif "value" not in node:
        raise PolicyError(f"'{node['op']}' requires a value")
    elif node["op"] in {"in", "not_in"} and not isinstance(node["value"], list):
        raise PolicyError(f"'{node['op']}' requires a list")
    elif node["op"] in {"before", "after"}:
        try:
            parsed = datetime.fromisoformat(str(node["value"]))
        except ValueError:
            raise PolicyError("Date comparison requires an ISO-8601 timestamp") from None
        if parsed.tzinfo is None:
            raise PolicyError("Date comparison requires a timezone")


def validate_definition(definition: dict) -> dict:
    required = {"schema_version", "name", "purpose", "conditions", "action", "tests"}
    allowed = required | {"scope", "exceptions"}
    if not isinstance(definition, dict):
        raise PolicyError("Policy must be an object")
    if missing := required - set(definition):
        raise PolicyError(f"Missing: {', '.join(sorted(missing))}")
    if extra := set(definition) - allowed:
        raise PolicyError(f"Unknown keys: {', '.join(sorted(extra))}")
    if definition["schema_version"] != SCHEMA_VERSION:
        raise PolicyError("Unsupported schema version")
    if definition["action"] not in ACTIONS:
        raise PolicyError("Unsupported action")
    for key in ("name", "purpose"):
        if not isinstance(definition[key], str) or not 3 <= len(definition[key]) <= 300:
            raise PolicyError(f"'{key}' must be 3-300 characters")
    _check_condition(definition["conditions"])
    scope = definition.get("scope", {})
    if not isinstance(scope, dict) or set(scope) - {"identity_subtypes", "departments"}:
        raise PolicyError("Scope supports identity_subtypes and departments")
    for exception in definition.get("exceptions", []):
        if set(exception) != {"identity", "expires_at", "justification"}:
            raise PolicyError("Exceptions need identity, expires_at and justification")
        if datetime.fromisoformat(exception["expires_at"]).tzinfo is None:
            raise PolicyError("Exception expiry requires a timezone")
    tests = definition["tests"]
    if not isinstance(tests, list) or len(tests) < 2:
        raise PolicyError("Provide at least one positive and one negative test")
    expectations = set()
    for case in tests:
        if set(case) - {"name", "input", "expect"} or case.get("expect") not in {
            "violation",
            "no_violation",
        }:
            raise PolicyError("Tests are {name, input, expect: violation|no_violation}")
        if set(case["input"]) - FIELDS:
            raise PolicyError(f"Test '{case.get('name')}' uses unknown fields")
        expectations.add(case["expect"])
    if expectations != {"violation", "no_violation"}:
        raise PolicyError("Tests must include both a violation and a no_violation case")
    return definition


def _value(context, field):
    return context.get(field)


def evaluate(node, context) -> bool:
    if "all" in node:
        return all(evaluate(child, context) for child in node["all"])
    if "any" in node:
        return any(evaluate(child, context) for child in node["any"])
    actual, op, expected = _value(context, node["field"]), node["op"], node.get("value")
    if op == "exists":
        return actual not in (None, "")
    if op == "missing":
        return actual in (None, "")
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "contains":
        return isinstance(actual, str) and str(expected).lower() in actual.lower()
    if actual in (None, ""):
        return False
    left, right = datetime.fromisoformat(str(actual)), datetime.fromisoformat(str(expected))
    return left < right if op == "before" else left > right


def in_scope(definition, context):
    scope = definition.get("scope", {})
    if (
        scope.get("identity_subtypes")
        and context.get("identity.subtype") not in scope["identity_subtypes"]
    ):
        return False
    return not (
        scope.get("departments") and context.get("identity.department") not in scope["departments"]
    )


def excepted(definition, context, at):
    for exception in definition.get("exceptions", []):
        if (
            exception["identity"] == context.get("identity.external_id")
            and datetime.fromisoformat(exception["expires_at"]) > at
        ):
            return exception
    return None


def violates(definition, context, at=None):
    at = at or datetime.now(timezone.utc)
    if not in_scope(definition, context) or not evaluate(definition["conditions"], context):
        return False, None
    exception = excepted(definition, context, at)
    return exception is None, exception


def run_tests(definition):
    results = []
    for case in definition["tests"]:
        hit, _ = violates(definition, case["input"])
        outcome = "violation" if hit else "no_violation"
        results.append(
            dict(
                name=case["name"],
                expected=case["expect"],
                actual=outcome,
                passed=outcome == case["expect"],
            )
        )
    return results


def grant_context(snap: Snapshot, edge, identity_node=None, target_node=None, attributes=None):
    identity = identity_node or snap.nodes[edge.src]
    target = target_node or snap.nodes[edge.dst]
    attrs = attributes if attributes is not None else edge.attributes
    return {
        "identity.subtype": identity.subtype,
        "identity.department": identity.attributes.get("department"),
        "identity.status": identity.status,
        "identity.mfa_registered": identity.attributes.get("mfa_registered"),
        "identity.external_id": identity.external_id,
        "target.kind": target.kind,
        "target.name": target.name,
        "target.external_id": target.external_id,
        "target.sensitivity": target.attributes.get("sensitivity"),
        "target.data_classification": target.attributes.get("data_classification"),
        "grant.type": edge.type if edge else "USER_MEMBER_OF_GROUP",
        "grant.origin": attrs.get("origin"),
        "grant.expires_at": attrs.get("expires_at"),
        "grant.ticket": attrs.get("ticket"),
        "grant.approver": attrs.get("approver"),
    }


def scan(definition, snap: Snapshot):
    """Existing grants in the twin that violate the policy (scope simulation)."""
    violations, exceptions = [], []
    for edge in snap.edges:
        if edge.type not in GRANT_TYPES or snap.nodes[edge.src].kind != "identity":
            continue
        context = grant_context(snap, edge)
        hit, exception = violates(definition, context, snap.effective_at)
        if hit:
            violations.append(
                dict(
                    identity=node_json(snap.nodes[edge.src]),
                    target=node_json(snap.nodes[edge.dst]),
                    grant=edge_json(edge),
                )
            )
        elif exception:
            exceptions.append(
                dict(
                    identity=context["identity.external_id"],
                    target=context["target.external_id"],
                    exception=exception,
                )
            )
    return dict(
        violations=violations,
        excepted=exceptions,
        statement=(
            "FLAG reports existing grants; it never revokes them."
            if definition["action"] == "flag"
            else "REJECT_PROPOSED blocks new proposals; existing grants are reported only."
        ),
    )


def definition_digest(definition):
    return digest(dumps(definition))


def active_policies(conn, environment_id):
    return conn.execute(
        "SELECT v.*, p.name AS policy_name FROM policy_versions v JOIN policies p ON p.id=v.policy_id "
        "WHERE p.environment_id=%s AND v.status='ACTIVE' ORDER BY v.id",
        (environment_id,),
    ).fetchall()


def active_policy_version(conn, environment_id):
    rows = active_policies(conn, environment_id)
    if not rows:
        return "policy:none"
    return "policy:" + digest(",".join(str(r["id"]) for r in rows))[:16]


def proposed_violations(conn, environment_id, snap, src, dst, rel_type, attributes):
    """Active REJECT_PROPOSED policies a hypothetical new grant would violate."""

    class _Edge:
        type = rel_type

    hits = []
    for row in active_policies(conn, environment_id):
        definition = row["definition"]
        if definition["action"] != "reject_proposed":
            continue
        context = grant_context(snap, _Edge, src, dst, attributes)
        hit, _ = violates(definition, context, snap.effective_at)
        if hit:
            hits.append(
                dict(
                    policy=row["policy_name"],
                    version=row["version"],
                    policy_version_id=str(row["id"]),
                )
            )
    return hits


def policy_findings(conn, environment_id, snap):
    from .findings import key

    out = []
    for row in active_policies(conn, environment_id):
        definition = row["definition"]
        if definition["action"] != "flag":
            continue
        for v in scan(definition, snap)["violations"]:
            out.append(
                dict(
                    key=key("POLICY_VIOLATION", row["id"], v["grant"]["relationship_id"]),
                    rule="POLICY_VIOLATION",
                    severity="high",
                    identity=v["identity"],
                    title=f"{v['identity']['name']} violates policy '{definition['name']}'",
                    summary=f"{v['grant']['type']} → {v['target']['name']} matches policy v{row['version']}: "
                    f"{definition['purpose']} Flagged for review; the policy never revokes access.",
                    grant=v["grant"],
                    reaches=[],
                    usage=[],
                    policy=dict(name=definition["name"], version=row["version"]),
                    recommendation="REVIEW under the policy",
                    evidence_ids=[v["grant"]["evidence_id"]],
                )
            )
    return out
