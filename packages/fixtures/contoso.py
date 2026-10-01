"""Deterministic SYNTHETIC Contoso source records. Not real organizational data.

Objects mirror what a sandbox HR/directory/IAM source would expose. Every timestamp is fixed so
tests and demos are reproducible. `alternate_path=True` adds a second payroll route for Erick.
"""

from datetime import datetime, timedelta, timezone

FIXTURE_VERSION = "contoso-v1"
SYNTHETIC = "SYNTHETIC — Contoso fixture"


def ts(value: str) -> str:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).isoformat()


DEPARTMENTS = [
    "IT",
    "Security",
    "Finance",
    "Human Resources",
    "Sales",
    "Engineering",
    "Operations",
    "Executive",
]

# id, name, subtype, department, title, manager, status, mfa, joined, extra
PEOPLE = [
    (
        "james",
        "James Okafor",
        "employee",
        "Executive",
        "Chief Executive Officer",
        None,
        "active",
        True,
        "2019-01-07",
        {},
    ),
    (
        "maria",
        "Maria Lopez",
        "employee",
        "IT",
        "IT Manager",
        "james",
        "active",
        True,
        "2020-02-03",
        {},
    ),
    (
        "erick",
        "Erick Mensah",
        "employee",
        "IT",
        "IT Support Specialist",
        "maria",
        "active",
        True,
        "2024-09-02",
        {},
    ),
    (
        "priya",
        "Priya Raman",
        "employee",
        "Security",
        "Security Lead",
        "james",
        "active",
        True,
        "2020-05-11",
        {},
    ),
    (
        "fatima",
        "Fatima Haddad",
        "admin",
        "Security",
        "Identity Administrator",
        "priya",
        "active",
        True,
        "2021-03-01",
        {},
    ),
    (
        "ana",
        "Ana Silva",
        "employee",
        "Finance",
        "Finance Manager",
        "james",
        "active",
        True,
        "2019-06-17",
        {},
    ),
    (
        "tom",
        "Tom Becker",
        "employee",
        "Finance",
        "Payroll Analyst",
        "ana",
        "active",
        True,
        "2022-01-10",
        {},
    ),
    (
        "liam",
        "Liam Walsh",
        "employee",
        "Human Resources",
        "HR Business Partner",
        "james",
        "active",
        True,
        "2021-08-23",
        {},
    ),
    (
        "sofia",
        "Sofia Rossi",
        "employee",
        "Sales",
        "Account Executive",
        "olivia",
        "active",
        True,
        "2023-04-03",
        {},
    ),
    (
        "olivia",
        "Olivia Chen",
        "employee",
        "Sales",
        "Sales Director",
        "james",
        "active",
        True,
        "2020-10-05",
        {},
    ),
    (
        "noah",
        "Noah Kim",
        "employee",
        "Engineering",
        "Engineering Manager",
        "james",
        "active",
        True,
        "2020-07-20",
        {},
    ),
    (
        "chen",
        "Chen Wei",
        "admin",
        "Engineering",
        "Platform Administrator",
        "noah",
        "active",
        True,
        "2021-11-15",
        {},
    ),
    (
        "dave",
        "Dave Miller",
        "admin",
        "Operations",
        "Operations Administrator",
        "james",
        "active",
        False,
        "2018-04-02",
        {},
    ),
    (
        "grace",
        "Grace Hall",
        "contractor",
        "Engineering",
        "Contract Developer",
        "noah",
        "active",
        True,
        "2026-04-01",
        {"contract_end": ts("2026-12-31")},
    ),
    (
        "ben",
        "Ben Carter",
        "employee",
        "Sales",
        "Sales Associate",
        "olivia",
        "terminated",
        True,
        "2023-02-06",
        {"terminated_at": ts("2026-08-15")},
    ),
    (
        "kim",
        "Kim Vendor",
        "guest",
        "Operations",
        "External Auditor",
        "dave",
        "active",
        False,
        "2026-07-01",
        {"sponsor": "idn-dave"},
    ),
    (
        "nina",
        "Nina Petrova",
        "employee",
        "Finance",
        "Accounts Payable Specialist",
        "ana",
        "active",
        False,
        "2026-09-28",
        {},
    ),
]

MACHINES = [
    ("svc-backup", "svc-backup", "service_account", "maria", "Nightly backups"),
    ("svc-erp-sync", "svc-erp-sync", "service_account", None, "ERP to payroll synchronisation"),
    ("svc-ci", "github-actions-deploy", "workload", "chen", "CI/CD deployment"),
    ("k8s-payments", "payments-api (Kubernetes)", "kubernetes", "noah", "Payments workload"),
]

AGENTS = [
    (
        "agent-support",
        "Customer Support Assistant",
        "sofia",
        "Sales",
        {
            "model": "local-llm-support-v2",
            "purpose": "Draft customer replies",
            "max_privilege": "read customer records; send email drafts",
            "credential_scope": "crm.read email.send",
            "expires_at": ts("2026-12-31"),
            "prohibited_data": ["payroll", "credentials"],
        },
    ),
    (
        "agent-reviewer",
        "Code Review Agent",
        "noah",
        "Engineering",
        {
            "model": "local-llm-code-v1",
            "purpose": "Comment on pull requests",
            "max_privilege": "read repositories; comment",
            "credential_scope": "repo.read pr.comment",
            "expires_at": ts("2027-03-31"),
            "prohibited_data": ["customer-data"],
        },
    ),
]

APPLICATIONS = [
    ("app-erp", "ERP", "high"),
    ("app-crm", "CRM", "medium"),
    ("app-email", "Email", "medium"),
    ("app-github", "GitHub", "high"),
    ("app-backup", "Backup Vault", "high"),
    ("app-directory", "Directory Admin Portal", "critical"),
]
RESOURCES = [
    ("res-payroll", "Payroll · SIMULATED", "critical", "database"),
    ("res-ledger", "General Ledger", "high", "database"),
    ("res-customer-data", "Customer Data Store", "high", "database"),
    ("res-repos", "Source Repositories", "high", "cloud"),
    ("res-backups", "Backup Archives", "high", "server"),
]
TOOLS = [
    ("tool-email-send", "email.send"),
    ("tool-crm-read", "crm.read"),
    ("tool-repo-read", "repo.read"),
    ("tool-pr-comment", "pr.comment"),
]

GROUPS = [
    "Finance-Legacy",
    "ERP-Operators",
    "HelpDesk-L2",
    "Finance-Analysts",
    "IT-Support",
    "Security-Admins",
    "Engineering",
    "Sales-Team",
    "All-Staff",
    "Eng-Platform",
    "Eng-SRE",
    "Payroll-Approvers",
    "Directory-Admins",
    "Backup-Operators",
    "External-Auditors",
]

ROLES = [
    ("role-erp-admin", "ERP Application Administrator"),
    ("role-erp-reader", "ERP Reader"),
    ("role-payroll-config", "Payroll Configurator"),
    ("role-helpdesk-reset", "HelpDesk Password Reset Operator"),
    ("role-global-admin", "Global Administrator"),
    ("role-crm-user", "CRM User"),
    ("role-backup-operator", "Backup Operator"),
    ("role-github-owner", "GitHub Organization Owner"),
    ("role-breakglass", "Production Break-glass"),
    ("role-ledger-reader", "Ledger Reader"),
]
PERMISSIONS = [
    ("perm-payroll-config", "Manage payroll configuration", "manage_config", "res-payroll"),
    ("perm-ledger-read", "Read general ledger", "read", "res-ledger"),
    ("perm-erp-use", "Use ERP", "use", "app-erp"),
    ("perm-reset-sales", "Reset passwords · Sales users", "reset_password", None),
    ("perm-tenant-admin", "Administer identity tenant", "administer", "app-directory"),
    ("perm-crm-read", "Read CRM records", "read", "app-crm"),
    ("perm-customer-read", "Read customer data", "read", "res-customer-data"),
    ("perm-backup-run", "Run and restore backups", "operate", "res-backups"),
    ("perm-repo-admin", "Administer repositories", "administer", "res-repos"),
    ("perm-email-send", "Send email", "send", "app-email"),
]


def _node(
    oid,
    kind,
    name,
    subtype="",
    attributes=None,
    revisions=None,
    status="active",
    valid_from="2018-01-01",
):
    revs = revisions or [
        dict(valid_from=ts(valid_from), status=status, attributes=attributes or {})
    ]
    return dict(type="node", id=oid, kind=kind, subtype=subtype, name=name, revisions=revs)


def _rel(oid, rel, src, dst, valid_from, valid_to=None, **attributes):
    attributes.setdefault("origin", "direct_assignment")
    return dict(
        type="relationship",
        id=oid,
        rel=rel,
        src=src,
        dst=dst,
        valid_from=ts(valid_from),
        valid_to=ts(valid_to) if valid_to else None,
        attributes=attributes,
    )


def build(alternate_path: bool = False) -> list[dict]:
    objects: list[dict] = []
    add = objects.append
    for d in DEPARTMENTS:
        add(_node("dept-" + d.lower().replace(" ", "-"), "department", d))
    dept = {d: "dept-" + d.lower().replace(" ", "-") for d in DEPARTMENTS}

    for pid, name, subtype, department, title, manager, status, mfa, joined, extra in PEOPLE:
        base = dict(
            department=department,
            title=title,
            email=f"{pid}@contoso.example",
            manager=f"idn-{manager}" if manager else None,
            mfa_registered=mfa,
            employment_status="active",
            synthetic=True,
            **extra,
        )
        if pid == "erick":
            revisions = [
                dict(
                    valid_from=ts(joined),
                    status="active",
                    attributes={
                        **base,
                        "department": "Finance",
                        "title": "Finance Analyst",
                        "manager": "idn-ana",
                    },
                ),
                dict(valid_from=ts("2026-06-01"), status="active", attributes=base),
            ]
        elif pid == "ben":
            revisions = [
                dict(valid_from=ts(joined), status="active", attributes=base),
                dict(
                    valid_from=ts("2026-08-15"),
                    status="terminated",
                    attributes={**base, "employment_status": "terminated"},
                ),
            ]
        else:
            revisions = [dict(valid_from=ts(joined), status=status, attributes=base)]
        add(_node(f"idn-{pid}", "identity", name, subtype, revisions=revisions))
        last_sign_in = {
            "dave": "2026-02-11",
            "ben": "2026-08-14",
            "kim": "2026-07-03",
            "nina": "2026-09-29",
        }.get(pid, "2026-09-29")
        add(
            _node(
                f"acct-{pid}",
                "account",
                f"{pid}@contoso.example",
                "directory",
                dict(
                    enabled=True,  # Ben's account was never disabled.
                    last_sign_in=ts(last_sign_in),
                    mfa_registered=mfa,
                ),
                valid_from=joined,
            )
        )
        add(_rel(f"has-acct-{pid}", "HAS_ACCOUNT", f"idn-{pid}", f"acct-{pid}", joined))
        current_dept = department
        if pid == "erick":
            add(
                _rel(
                    "dept-erick-fin",
                    "IDENTITY_IN_DEPARTMENT",
                    "idn-erick",
                    dept["Finance"],
                    joined,
                    "2026-06-01",
                )
            )
            add(
                _rel(
                    "dept-erick-it", "IDENTITY_IN_DEPARTMENT", "idn-erick", dept["IT"], "2026-06-01"
                )
            )
            add(_rel("rpt-erick-ana", "REPORTS_TO", "idn-erick", "idn-ana", joined, "2026-06-01"))
            add(_rel("rpt-erick-maria", "REPORTS_TO", "idn-erick", "idn-maria", "2026-06-01"))
        else:
            add(
                _rel(
                    f"dept-{pid}",
                    "IDENTITY_IN_DEPARTMENT",
                    f"idn-{pid}",
                    dept[current_dept],
                    joined,
                )
            )
            if manager:
                add(_rel(f"rpt-{pid}", "REPORTS_TO", f"idn-{pid}", f"idn-{manager}", joined))
        add(
            _rel(
                f"all-staff-{pid}",
                "USER_MEMBER_OF_GROUP",
                f"idn-{pid}",
                "grp-all-staff",
                joined,
                origin="automated_provisioning",
            )
        )

    for mid, name, subtype, owner, purpose in MACHINES:
        attrs = dict(purpose=purpose, owner=f"idn-{owner}" if owner else None, synthetic=True)
        add(
            _node(
                f"idn-{mid}",
                "identity",
                name,
                "machine",
                dict(attrs, machine_kind=subtype),
                valid_from="2022-01-01",
            )
        )
        if owner:
            add(
                _rel(
                    f"own-{mid}",
                    "USER_OWNS_SERVICE_ACCOUNT",
                    f"idn-{owner}",
                    f"idn-{mid}",
                    "2022-01-01",
                )
            )

    for aid, name, owner, department, attrs in AGENTS:
        add(
            _node(
                f"idn-{aid}",
                "identity",
                name,
                "agent",
                dict(attrs, owner=f"idn-{owner}", department=department, synthetic=True),
                valid_from="2026-03-01",
            )
        )
        add(
            _rel(
                f"own-{aid}",
                "USER_OWNS_SERVICE_ACCOUNT",
                f"idn-{owner}",
                f"idn-{aid}",
                "2026-03-01",
            )
        )

    for oid, name, sensitivity in APPLICATIONS:
        add(
            _node(
                oid, "application", name, "saas", dict(sensitivity=sensitivity, owner="idn-maria")
            )
        )
        add(_rel(f"trust-{oid}", "APPLICATION_TRUSTS_IDP", oid, "idp-contoso", "2019-01-01"))
    add(_node("idp-contoso", "provider", "Contoso Identity Provider", "oidc"))
    for oid, name, sensitivity, subtype in RESOURCES:
        owner = (
            None
            if oid == "res-backups"
            else "idn-ana"
            if oid in {"res-payroll", "res-ledger"}
            else "idn-olivia"
            if oid == "res-customer-data"
            else "idn-noah"
        )
        add(
            _node(
                oid,
                "resource",
                name,
                subtype,
                dict(sensitivity=sensitivity, owner=owner, simulated=True),
            )
        )
    for oid, name in TOOLS:
        add(_node(oid, "tool", name, "agent_tool"))
    for g in GROUPS:
        add(_node("grp-" + g.lower(), "group", g, "security"))
    for oid, name in ROLES:
        add(_node(oid, "role", name, "application_role"))
    for oid, name, action, resource in PERMISSIONS:
        add(_node(oid, "permission", name, action, dict(action=action)))
        if resource:
            add(
                _rel(
                    f"pa-{oid}",
                    "PERMISSION_ACCESS_RESOURCE",
                    oid,
                    resource,
                    "2019-01-01",
                    action=action,
                )
            )

    # Operational dependencies.
    add(_rel("dep-payroll-erp", "RESOURCE_DEPENDS_ON", "res-payroll", "app-erp", "2019-01-01"))
    add(_rel("dep-ledger-erp", "RESOURCE_DEPENDS_ON", "res-ledger", "app-erp", "2019-01-01"))
    add(
        _rel(
            "dep-erp-sync",
            "RESOURCE_DEPENDS_ON",
            "app-erp",
            "idn-svc-erp-sync",
            "2022-01-01",
            note="Monthly payroll run uses svc-erp-sync",
        )
    )

    # Group nesting, including a preserved cycle.
    add(
        _rel(
            "nest-finlegacy-erpops",
            "GROUP_INHERITS_GROUP",
            "grp-finance-legacy",
            "grp-erp-operators",
            "2021-01-01",
        )
    )
    add(
        _rel(
            "nest-platform-sre",
            "GROUP_INHERITS_GROUP",
            "grp-eng-platform",
            "grp-eng-sre",
            "2023-01-01",
        )
    )
    add(
        _rel(
            "nest-sre-platform",
            "GROUP_INHERITS_GROUP",
            "grp-eng-sre",
            "grp-eng-platform",
            "2023-01-01",
        )
    )
    add(
        _rel(
            "nest-security-directory",
            "GROUP_INHERITS_GROUP",
            "grp-security-admins",
            "grp-directory-admins",
            "2021-01-01",
        )
    )

    # Group -> role -> permission chains.
    for gid, rid, since in [
        ("grp-erp-operators", "role-erp-admin", "2021-01-01"),
        ("grp-finance-analysts", "role-erp-reader", "2021-01-01"),
        ("grp-finance-analysts", "role-ledger-reader", "2021-01-01"),
        ("grp-helpdesk-l2", "role-helpdesk-reset", "2022-01-01"),
        ("grp-directory-admins", "role-global-admin", "2021-01-01"),
        ("grp-sales-team", "role-crm-user", "2021-01-01"),
        ("grp-backup-operators", "role-backup-operator", "2021-01-01"),
        ("grp-eng-platform", "role-github-owner", "2023-01-01"),
        ("grp-payroll-approvers", "role-payroll-config", "2022-01-01"),
        ("grp-external-auditors", "role-ledger-reader", "2026-07-01"),
    ]:
        add(_rel(f"gr-{gid}-{rid}", "GROUP_HAS_ROLE", gid, rid, since))
    for rid, pid in [
        ("role-erp-admin", "perm-payroll-config"),
        ("role-erp-admin", "perm-erp-use"),
        ("role-erp-admin", "perm-ledger-read"),
        ("role-erp-reader", "perm-erp-use"),
        ("role-ledger-reader", "perm-ledger-read"),
        ("role-payroll-config", "perm-payroll-config"),
        ("role-helpdesk-reset", "perm-reset-sales"),
        ("role-global-admin", "perm-tenant-admin"),
        ("role-crm-user", "perm-crm-read"),
        ("role-crm-user", "perm-customer-read"),
        ("role-backup-operator", "perm-backup-run"),
        ("role-github-owner", "perm-repo-admin"),
        ("role-breakglass", "perm-tenant-admin"),
    ]:
        add(_rel(f"rp-{rid}-{pid}", "ROLE_HAS_PERMISSION", rid, pid, "2019-01-01"))

    # Exposure: HelpDesk reset scope covers Sales users only. Reset does not bypass target MFA.
    for target in ["sofia", "olivia", "ben"]:
        add(
            _rel(
                f"reset-{target}",
                "CAN_RESET_CREDENTIAL",
                "perm-reset-sales",
                f"idn-{target}",
                "2022-01-01",
                conditions=[{"type": "target_mfa_registered"}],
                scope="Sales OU",
            )
        )
    add(
        _rel(
            "assume-chen-breakglass",
            "CAN_ASSUME_ROLE",
            "idn-chen",
            "role-breakglass",
            "2022-06-01",
            conditions=[{"type": "mfa_required"}, {"type": "approval_ticket"}],
        )
    )

    # Memberships. Erick's Finance-Legacy grant is the retained previous-role entitlement.
    mem = [
        (
            "erick",
            "grp-finance-legacy",
            "2025-03-10",
            None,
            dict(
                origin="legacy_entitlement",
                ticket="TKT-1042",
                approver="idn-ana",
                justification="Quarter-end close support for Finance",
            ),
        ),
        (
            "erick",
            "grp-finance-analysts",
            "2024-09-02",
            "2026-06-01",
            dict(
                origin="role",
                ticket="TKT-0811",
                approver="idn-ana",
                justification="Finance Analyst baseline",
            ),
        ),
        (
            "erick",
            "grp-helpdesk-l2",
            "2026-06-01",
            None,
            dict(
                origin="manager_approval",
                ticket="TKT-2210",
                approver="idn-maria",
                justification="IT Support Specialist duties",
            ),
        ),
        (
            "erick",
            "grp-it-support",
            "2026-06-01",
            None,
            dict(origin="role", ticket="TKT-2210", approver="idn-maria"),
        ),
        (
            "tom",
            "grp-erp-operators",
            "2022-01-10",
            None,
            dict(
                origin="role",
                ticket="TKT-0150",
                approver="idn-ana",
                justification="Payroll operations",
            ),
        ),
        ("tom", "grp-finance-analysts", "2022-01-10", None, dict(origin="role")),
        ("ana", "grp-finance-analysts", "2019-06-17", None, dict(origin="role")),
        (
            "ana",
            "grp-payroll-approvers",
            "2022-01-01",
            None,
            dict(origin="role", approver="idn-james"),
        ),
        ("nina", "grp-finance-analysts", "2026-09-28", None, dict(origin="automated_provisioning")),
        ("maria", "grp-it-support", "2020-02-03", None, dict(origin="role")),
        ("maria", "grp-backup-operators", "2020-02-03", None, dict(origin="role")),
        (
            "fatima",
            "grp-security-admins",
            "2021-03-01",
            None,
            dict(origin="role", approver="idn-priya"),
        ),
        ("priya", "grp-security-admins", "2020-05-11", None, dict(origin="role")),
        ("sofia", "grp-sales-team", "2023-04-03", None, dict(origin="role")),
        ("olivia", "grp-sales-team", "2020-10-05", None, dict(origin="role")),
        ("ben", "grp-sales-team", "2023-02-06", None, dict(origin="role")),
        ("noah", "grp-engineering", "2020-07-20", None, dict(origin="role")),
        ("chen", "grp-eng-platform", "2021-11-15", None, dict(origin="role", approver="idn-noah")),
        ("chen", "grp-engineering", "2021-11-15", None, dict(origin="role")),
        ("grace", "grp-engineering", "2026-04-01", None, dict(origin="role", approver="idn-noah")),
        ("dave", "grp-directory-admins", "2018-04-02", None, dict(origin="unknown")),
        ("dave", "grp-backup-operators", "2018-04-02", None, dict(origin="unknown")),
        (
            "kim",
            "grp-external-auditors",
            "2026-07-01",
            None,
            dict(origin="delegation", approver="idn-dave", expires_at=ts("2026-10-31")),
        ),
        (
            "svc-erp-sync",
            "grp-erp-operators",
            "2022-01-01",
            None,
            dict(origin="automated_provisioning"),
        ),
        (
            "svc-backup",
            "grp-backup-operators",
            "2022-01-01",
            None,
            dict(origin="automated_provisioning"),
        ),
    ]
    if alternate_path:
        mem.append(
            (
                "erick",
                "grp-payroll-approvers",
                "2026-06-15",
                None,
                dict(
                    origin="manager_approval",
                    ticket="TKT-2301",
                    approver="idn-ana",
                    justification="Temporary payroll cover (alternate-path variant)",
                ),
            )
        )
    for who, gid, since, until, attrs in mem:
        add(
            _rel(
                f"mem-{who}-{gid}", "USER_MEMBER_OF_GROUP", f"idn-{who}", gid, since, until, **attrs
            )
        )

    # Direct role: contractor with permanent Global Administrator (policy example) and an explicit deny.
    add(
        _rel(
            "ur-grace-global",
            "USER_HAS_ROLE",
            "idn-grace",
            "role-global-admin",
            "2026-04-15",
            origin="direct_assignment",
            ticket="TKT-1999",
            approver="idn-chen",
            justification="Tenant migration",
        )
    )
    add(
        _rel(
            "deny-grace-payroll",
            "DENY_ASSIGNMENT",
            "idn-grace",
            "perm-payroll-config",
            "2026-04-15",
            origin="direct_assignment",
            justification="Contractors excluded from payroll",
        )
    )
    add(
        _rel(
            "ur-sofia-crm-cond",
            "USER_HAS_ROLE",
            "idn-sofia",
            "role-crm-user",
            "2023-04-03",
            origin="abac",
            conditions=[{"type": "device_compliant"}],
        )
    )

    # Machine and agent grants.
    add(
        _rel(
            "sa-erp-sync",
            "SERVICE_ACCOUNT_ACCESS_APPLICATION",
            "idn-svc-erp-sync",
            "app-erp",
            "2022-01-01",
        )
    )
    add(
        _rel(
            "sa-backup",
            "SERVICE_ACCOUNT_ACCESS_APPLICATION",
            "idn-svc-backup",
            "app-backup",
            "2022-01-01",
        )
    )
    add(
        _rel(
            "sa-ci", "SERVICE_ACCOUNT_ACCESS_APPLICATION", "idn-svc-ci", "app-github", "2023-01-01"
        )
    )
    add(
        _rel(
            "sa-k8s",
            "SERVICE_ACCOUNT_ACCESS_APPLICATION",
            "idn-k8s-payments",
            "app-erp",
            "2024-01-01",
        )
    )
    for aid, tool in [
        ("agent-support", "tool-email-send"),
        ("agent-support", "tool-crm-read"),
        ("agent-reviewer", "tool-repo-read"),
        ("agent-reviewer", "tool-pr-comment"),
    ]:
        add(
            _rel(
                f"tool-{aid}-{tool}",
                "AI_AGENT_USES_TOOL",
                f"idn-{aid}",
                tool,
                "2026-03-01",
                origin="direct_assignment",
                approver="idn-priya",
            )
        )
    add(
        _rel(
            "data-agent-support",
            "AI_AGENT_ACCESS_DATA",
            "idn-agent-support",
            "res-customer-data",
            "2026-03-01",
            origin="direct_assignment",
            approver="idn-priya",
            action="read",
        )
    )
    add(
        _rel(
            "data-agent-reviewer",
            "AI_AGENT_ACCESS_DATA",
            "idn-agent-reviewer",
            "res-repos",
            "2026-03-01",
            origin="direct_assignment",
            approver="idn-noah",
            action="read",
        )
    )

    # Credentials (metadata only; no secret material exists in the fixture).
    for cid, holder, subtype, created, rotated, expires in [
        (
            "cred-backup-secret",
            "svc-backup",
            "client_secret",
            "2025-08-01",
            "2025-08-01",
            "2027-08-01",
        ),
        ("cert-erp-sync", "svc-erp-sync", "certificate", "2024-10-20", "2024-10-20", "2026-10-20"),
        ("cred-ci-oidc", "svc-ci", "federated_credential", "2025-01-15", "2025-01-15", None),
        (
            "cred-agent-support",
            "agent-support",
            "api_key",
            "2026-03-01",
            "2026-03-01",
            "2026-12-31",
        ),
    ]:
        add(
            _node(
                cid,
                "credential",
                cid,
                subtype,
                dict(
                    created_at=ts(created),
                    rotated_at=ts(rotated),
                    expires_at=ts(expires) if expires else None,
                    secret_material="none (metadata only)",
                ),
                valid_from=created,
            )
        )
        add(_rel(f"hc-{cid}", "HAS_CREDENTIAL", f"idn-{holder}", cid, created))

    for did, owner in [
        ("dev-erick-laptop", "erick"),
        ("dev-sofia-laptop", "sofia"),
        ("dev-dave-desktop", "dave"),
    ]:
        add(_node(did, "device", did, "laptop", dict(compliant=did != "dev-dave-desktop")))
        add(_rel(f"du-{did}", "DEVICE_USED_BY_USER", did, f"idn-{owner}", "2025-01-01"))

    # Employment events.
    for eid, who, kind, when, details in [
        (
            "hr-erick-move",
            "erick",
            "move",
            "2026-06-01",
            dict(
                from_department="Finance",
                to_department="IT",
                from_title="Finance Analyst",
                to_title="IT Support Specialist",
            ),
        ),
        ("hr-ben-leave", "ben", "leave", "2026-08-15", dict(reason="resignation")),
        (
            "hr-grace-join",
            "grace",
            "join",
            "2026-04-01",
            dict(department="Engineering", worker_type="contractor"),
        ),
        (
            "hr-nina-join",
            "nina",
            "join",
            "2026-09-28",
            dict(department="Finance", title="Accounts Payable Specialist"),
        ),
        (
            "hr-kim-join",
            "kim",
            "join",
            "2026-07-01",
            dict(department="Operations", worker_type="guest"),
        ),
    ]:
        add(
            dict(
                type="employment_event",
                id=eid,
                identity=f"idn-{who}",
                kind=kind,
                effective_at=ts(when),
                details=details,
            )
        )

    # Telemetry coverage and usage. Coverage gaps are deliberate.
    for cid, target, start, end, completeness in [
        ("cov-erp-q2", "app-erp", "2026-03-01", "2026-06-01", "partial"),
        ("cov-erp-q3", "app-erp", "2026-06-01", "2026-09-30", "complete"),
        ("cov-payroll", "res-payroll", "2026-06-01", "2026-09-30", "complete"),
        ("cov-crm", "app-crm", "2026-01-01", "2026-09-30", "complete"),
        ("cov-directory", "app-directory", "2026-01-01", "2026-09-30", "complete"),
        ("cov-backup", "app-backup", "2026-05-01", "2026-09-30", "complete"),
    ]:
        add(
            dict(
                type="coverage",
                id=cid,
                target=target,
                covered_from=ts(start),
                covered_to=ts(end),
                completeness=completeness,
            )
        )
    start = datetime(2026, 3, 2, 9, tzinfo=timezone.utc)
    usage = []
    for week in range(30):
        day = start + timedelta(days=7 * week)
        usage.append(("tom", "app-erp", day))
        usage.append(("tom", "res-payroll", day + timedelta(hours=2)))
        usage.append(("svc-erp-sync", "app-erp", day + timedelta(hours=20)))
        usage.append(("sofia", "app-crm", day + timedelta(hours=1)))
        if day < datetime(2026, 6, 1, tzinfo=timezone.utc):
            usage.append(("erick", "app-erp", day + timedelta(hours=3)))
        if week % 4 == 0:
            usage.append(("fatima", "app-directory", day + timedelta(hours=4)))
            usage.append(("maria", "app-backup", day + timedelta(hours=5)))
    for i, (who, target, when) in enumerate(usage):
        add(
            dict(
                type="usage",
                id=f"use-{i:04d}",
                identity=f"idn-{who}",
                target=target,
                occurred_at=when.isoformat(),
            )
        )
    return objects
