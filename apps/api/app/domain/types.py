"""Typed relationship vocabulary from GRAPH.md. Endpoint kinds are validated on ingestion."""

IDENTITY = {"identity"}
TARGETS = {"resource", "application"}

# type -> (classification, allowed source kinds, allowed destination kinds)
RELATIONSHIPS = {
    "USER_MEMBER_OF_GROUP": ("grant", IDENTITY, {"group"}),
    "GROUP_INHERITS_GROUP": ("grant", {"group"}, {"group"}),
    "GROUP_HAS_ROLE": ("grant", {"group"}, {"role"}),
    "USER_HAS_ROLE": ("grant", IDENTITY, {"role"}),
    "ROLE_HAS_PERMISSION": ("grant", {"role"}, {"permission"}),
    "PERMISSION_ACCESS_RESOURCE": ("grant", {"permission"}, TARGETS),
    "SERVICE_ACCOUNT_ACCESS_APPLICATION": ("grant", IDENTITY, TARGETS),
    "AI_AGENT_USES_TOOL": ("grant", IDENTITY, {"tool"}),
    "AI_AGENT_ACCESS_DATA": ("grant", IDENTITY, TARGETS),
    "DENY_ASSIGNMENT": ("deny", IDENTITY | {"group"}, {"permission"}),
    "USER_OWNS_SERVICE_ACCOUNT": ("context", IDENTITY, IDENTITY),
    "DEVICE_USED_BY_USER": ("context", {"device"}, IDENTITY),
    "APPLICATION_TRUSTS_IDP": ("context", {"application"}, {"provider"}),
    "IDENTITY_IN_DEPARTMENT": ("context", IDENTITY, {"department"}),
    "REPORTS_TO": ("context", IDENTITY, IDENTITY),
    "HAS_ACCOUNT": ("context", IDENTITY, {"account"}),
    "HAS_CREDENTIAL": ("context", IDENTITY, {"credential"}),
    "CAN_RESET_CREDENTIAL": ("exposure", {"permission"} | IDENTITY, IDENTITY | {"account"}),
    "CAN_ASSUME_ROLE": ("exposure", IDENTITY, {"role"}),
    "RESOURCE_DEPENDS_ON": ("dependency", TARGETS, TARGETS | IDENTITY),
}

# Grant edges an identity's access flows along, in traversal order.
GRANT_FLOW = {
    "USER_MEMBER_OF_GROUP",
    "GROUP_INHERITS_GROUP",
    "GROUP_HAS_ROLE",
    "USER_HAS_ROLE",
    "ROLE_HAS_PERMISSION",
    "PERMISSION_ACCESS_RESOURCE",
    "SERVICE_ACCOUNT_ACCESS_APPLICATION",
    "AI_AGENT_USES_TOOL",
    "AI_AGENT_ACCESS_DATA",
}

# Origin vocabulary from REQUIREMENTS.md. Anything else is stored as "unknown".
ORIGINS = {
    "direct_assignment",
    "group_membership",
    "nested_membership",
    "role",
    "rbac",
    "abac",
    "temporary_privilege",
    "application_role",
    "legacy_entitlement",
    "delegation",
    "manager_approval",
    "automated_provisioning",
    "unknown",
}

# Conditions the engine understands. Anything else evaluates to UNKNOWN, never ALLOW.
SUPPORTED_CONDITIONS = {
    "mfa_required",
    "device_compliant",
    "target_mfa_registered",
    "approval_ticket",
    "network_location",
    "time_window",
}


def validate(rel_type: str, src_kind: str, dst_kind: str) -> str:
    if rel_type not in RELATIONSHIPS:
        raise ValueError(f"Unknown relationship type {rel_type}")
    classification, sources, destinations = RELATIONSHIPS[rel_type]
    if src_kind not in sources or dst_kind not in destinations:
        raise ValueError(f"{rel_type} cannot connect {src_kind} to {dst_kind}")
    return classification
