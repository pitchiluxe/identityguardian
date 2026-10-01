"""Sixteen versioned SYNTHETIC IAM labs (LABS.md). Grading is deterministic.

Rubric: correctness 50%, least privilege 25%, evidence/workflow 25%. Any safety failure blocks
passing regardless of points. Hints progress concept -> diagnostic question -> relevant setting.
"""

from dataclasses import dataclass, field

from ..domain.access import effective_access
from .actions import _put

CATALOG_VERSION = "labs-2026.09-1"
PASS_MARK = 70
PRIVILEGED_GROUPS = {
    "grp-erp-operators",
    "grp-payroll-approvers",
    "grp-directory-admins",
    "grp-security-admins",
    "grp-backup-operators",
    "grp-eng-platform",
}


@dataclass
class Grade:
    checks: list = field(default_factory=list)
    safety: list = field(default_factory=list)
    misconceptions: list = field(default_factory=list)

    def check(self, cid, category, passed, text, weight=1):
        self.checks.append(
            dict(id=cid, category=category, passed=bool(passed), text=text, weight=weight)
        )

    def unsafe(self, rule, message):
        self.safety.append(dict(rule=rule, message=message))


@dataclass
class Lab:
    id: str
    title: str
    objective: str
    tasks: list
    hints: list
    solution: list
    validate: object
    setup: object = None
    actions: tuple = ()


# ---------- state helpers ----------
def node(snap, external_id):
    return snap.by_external(external_id)


def member(snap, who, target, rel="USER_MEMBER_OF_GROUP"):
    n, t = node(snap, who), node(snap, target)
    return (
        next((e for e in snap.out[n.id] if e.type == rel and e.dst == t.id), None)
        if n and t
        else None
    )


def groups_of(snap, who):
    n = node(snap, who)
    return {
        snap.nodes[e.dst].external_id for e in snap.out[n.id] if e.type == "USER_MEMBER_OF_GROUP"
    }


def attrs(snap, external_id):
    n = node(snap, external_id)
    return n.attributes if n else {}


def answers(actions):
    found = {}
    for a in actions:
        if a["type"] == "answer":
            found[a["question"]] = str(a["value"]).strip().lower()
    return found


def touched(actions, *types):
    return [a for a in actions if a["type"] in types]


def baseline_changes(actions, allowed):
    return [
        a
        for a in touched(
            actions, "add_membership", "remove_membership", "assign_role", "remove_role"
        )
        if (a.get("identity"), a.get("group") or a.get("role")) not in allowed
    ]


def set_attr(conn, env, object_id, **changes):
    row = conn.execute(
        "SELECT body FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
        (env["id"], object_id),
    ).fetchone()
    body = row["body"]
    body["revisions"][-1]["attributes"].update(changes)
    _put(conn, env["organization_id"], env["id"], body)


def drop(conn, env, object_id):
    row = conn.execute(
        "SELECT body FROM sandbox_objects WHERE environment_id=%s AND object_id=%s",
        (env["id"], object_id),
    ).fetchone()
    _put(conn, env["organization_id"], env["id"], row["body"], deleted=True)


# ---------- validators ----------
def v_onboarding(snap, actions, conn):
    g = Grade()
    a = attrs(snap, "idn-nina")
    g.check("dept", "correctness", a.get("department") == "Finance", "Department is Finance")
    g.check("manager", "correctness", a.get("manager") == "idn-ana", "Manager is Ana Silva", 1)
    g.check(
        "baseline",
        "correctness",
        "grp-finance-analysts" in groups_of(snap, "idn-nina"),
        "Finance-Analysts baseline membership granted",
        2,
    )
    extra = groups_of(snap, "idn-nina") - {"grp-finance-analysts", "grp-all-staff"}
    g.check(
        "least",
        "least_privilege",
        not extra,
        f"No access beyond the baseline ({', '.join(extra) or 'none'})",
        2,
    )
    g.check(
        "justified",
        "evidence",
        all(x.get("justification") for x in touched(actions, "add_membership")),
        "Each grant recorded a justification",
    )
    if extra & PRIVILEGED_GROUPS:
        g.unsafe("privileged_joiner", "A joiner received privileged access on day one")
    return g


def v_password_reset(snap, actions, conn):
    g = Grade()
    resets = touched(actions, "reset_password")
    target = [r for r in resets if r["identity"] == "idn-sofia"]
    g.check("target", "correctness", bool(target), "Sofia's password was reset", 2)
    g.check(
        "verified",
        "correctness",
        bool(target) and target[-1]["verification"] != "none",
        "Identity verified before reset (manager callback or ID document)",
        2,
    )
    g.check(
        "scope",
        "least_privilege",
        all(r["identity"] == "idn-sofia" for r in resets),
        "Only the requester was reset",
        2,
    )
    g.check(
        "ticket",
        "evidence",
        bool(target) and bool(target[-1].get("justification")),
        "Reset references the request",
    )
    if any(r["identity"] in {"idn-fatima", "idn-chen", "idn-dave", "idn-james"} for r in resets):
        g.unsafe("privileged_reset", "Help-desk reset of a privileged account")
    if target and target[-1]["verification"] == "none":
        g.misconceptions.append(
            "Resetting without verifying the caller enables social engineering."
        )
    return g


def v_lockout(snap, actions, conn):
    g = Grade()
    ans = answers(actions)
    g.check(
        "cause",
        "correctness",
        ans.get("cause") == "password_spray",
        "Diagnosed the lockout cause",
        2,
    )
    acct = attrs(snap, "acct-tom")
    g.check("unlocked", "correctness", acct.get("locked") is False, "Account unlocked", 1)
    order = [a["type"] for a in actions if a["type"] in {"reset_password", "unlock_account"}]
    reset_first = "reset_password" in order and (
        "unlock_account" not in order
        or order.index("reset_password") < order.index("unlock_account")
    )
    g.check(
        "policy",
        "least_privilege",
        reset_first,
        "Password reset before unlocking after an attack",
        2,
    )
    g.check(
        "mfa",
        "evidence",
        attrs(snap, "idn-tom").get("mfa_registered") is True,
        "MFA remains registered",
    )
    if acct.get("locked") is False and not reset_first:
        g.unsafe(
            "unlock_without_reset", "Unlocked an attacked account without resetting its password"
        )
    return g


def v_group(snap, actions, conn):
    g = Grade()
    g.check(
        "added",
        "correctness",
        member(snap, "idn-sofia", "grp-finance-analysts") is not None,
        "Sofia added to Finance-Analysts",
        3,
    )
    unintended = baseline_changes(actions, {("idn-sofia", "grp-finance-analysts")})
    g.check("only", "least_privilege", not unintended, "No other membership changed", 2)
    g.check(
        "why",
        "evidence",
        any(a.get("justification") for a in touched(actions, "add_membership")),
        "Justification recorded",
    )
    if any(a["type"].startswith("remove") for a in unintended) or any(
        (a.get("group") or "") in PRIVILEGED_GROUPS for a in unintended
    ):
        g.unsafe("collateral_change", "Changed memberships beyond the request")
    return g


def v_rbac(snap, actions, conn):
    g = Grade()
    access = effective_access(snap, node(snap, "idn-nina").id, conn)
    ledger = any(
        (e["permission"] or {}).get("external_id") == "perm-ledger-read" for e in access["entries"]
    )
    roles = touched(actions, "create_role")
    perms = set(roles[-1]["permissions"]) if roles else set()
    g.check("works", "correctness", ledger, "Nina can read the general ledger", 2)
    g.check(
        "via_role",
        "correctness",
        bool(touched(actions, "assign_role")),
        "Access granted through a role",
        1,
    )
    g.check(
        "exact",
        "least_privilege",
        perms == {"perm-ledger-read"},
        "Role holds exactly the required permission",
        2,
    )
    g.check(
        "named",
        "evidence",
        bool(roles) and len(roles[-1]["name"]) >= 3,
        "Role has a descriptive name",
    )
    if perms & {"perm-payroll-config", "perm-tenant-admin", "perm-repo-admin"}:
        g.unsafe("over_privileged_role", "Role includes administrative permissions")
    return g


def v_mfa(snap, actions, conn):
    g = Grade()
    a = attrs(snap, "idn-dave")
    methods = set(a.get("mfa_methods") or [])
    g.check(
        "registered", "correctness", a.get("mfa_registered") is True, "Dave has MFA registered", 2
    )
    g.check(
        "strong",
        "least_privilege",
        bool(methods & {"totp", "webauthn"}),
        "Phishing-resistant or app-based method",
        2,
    )
    g.check("nosms", "evidence", "sms" not in methods, "SMS avoided for an administrator")
    if "sms" in methods:
        g.misconceptions.append(
            "SMS codes are vulnerable to SIM swap; prefer TOTP or WebAuthn for admins."
        )
    return g


def v_conditional(snap, actions, conn):
    g = Grade()
    rel = "gr-grp-sales-team-role-crm-user"
    edge = next(
        (
            e
            for e in snap.edges
            if e.relationship_id
            and snap.nodes[e.src].external_id == "grp-sales-team"
            and e.type == "GROUP_HAS_ROLE"
        ),
        None,
    )
    conds = {c.get("type") for c in (edge.attributes.get("conditions") or [])} if edge else set()
    g.check(
        "present", "correctness", edge is not None, "Sales-Team keeps CRM User (positive case)", 2
    )
    g.check("mfa", "correctness", "mfa_required" in conds, "MFA required for the CRM grant", 2)
    sofia = effective_access(snap, node(snap, "idn-sofia").id, conn)
    crm = [e for e in sofia["entries"] if (e["resource"] or {}).get("external_id") == "app-crm"]
    g.check(
        "negative",
        "least_privilege",
        bool(crm)
        and all(p["status"] != "ALLOW" or p["conditions"] for e in crm for p in e["paths"]),
        "Unconditioned access path removed (protected negative case)",
        2,
    )
    g.check(
        "targeted",
        "evidence",
        all(a["relationship"] == rel for a in touched(actions, "add_condition")),
        "Condition applied only to the intended grant",
    )
    if edge is None:
        g.unsafe("access_removed", "Removed the grant instead of conditioning it")
    return g


def v_sso(snap, actions, conn):
    g = Grade()
    sso = attrs(snap, "app-crm").get("sso") or {}
    g.check(
        "issuer",
        "correctness",
        sso.get("issuer") == "https://idp.contoso.example/realms/contoso",
        "Issuer matches the IdP",
        2,
    )
    g.check(
        "audience", "correctness", sso.get("audience") == "crm", "Audience is the CRM client ID", 2
    )
    mappings = sso.get("mappings") or {}
    g.check(
        "mappings",
        "least_privilege",
        mappings == {"email": "email", "department": "department"},
        "Only required attributes are mapped",
        2,
    )
    g.check(
        "documented", "evidence", bool(touched(actions, "configure_sso")), "Configuration recorded"
    )
    if sso.get("audience") in {"*", ""}:
        g.unsafe(
            "wildcard_audience", "A wildcard audience accepts tokens issued for any application"
        )
    return g


def v_review(snap, actions, conn):
    g = Grade()
    ans = answers(actions)
    g.check(
        "decision",
        "correctness",
        ans.get("decision") == "remove",
        "REMOVE decided for Finance-Legacy",
        2,
    )
    g.check(
        "evidence",
        "evidence",
        "tkt-1042" in ans.get("justification", "") or "move" in ans.get("justification", ""),
        "Justification cites the ticket or the role move",
        2,
    )
    g.check(
        "kept",
        "least_privilege",
        member(snap, "idn-erick", "grp-helpdesk-l2") is not None,
        "Justified HelpDesk-L2 access kept",
        2,
    )
    g.check(
        "proposal",
        "correctness",
        ans.get("proposal") == "mem-erick-grp-finance-legacy",
        "Removal proposal targets only the reviewed grant",
        1,
    )
    if member(snap, "idn-erick", "grp-helpdesk-l2") is None:
        g.unsafe("removed_justified", "Removed justified current-role access")
    return g


def v_privileged(snap, actions, conn):
    g = Grade()
    grant = member(snap, "idn-chen", "grp-directory-admins")
    adds = [a for a in touched(actions, "add_membership") if a["group"] == "grp-directory-admins"]
    g.check("granted", "correctness", grant is not None, "Chen received Directory-Admins", 2)
    g.check(
        "bounded",
        "least_privilege",
        bool(adds) and bool(adds[-1].get("expires_at")),
        "Access is time-bound (≤ 8 h)",
        2,
    )
    g.check(
        "justified",
        "evidence",
        bool(adds) and len(adds[-1].get("justification") or "") >= 8,
        "Justification recorded",
    )
    g.check(
        "independent",
        "evidence",
        bool(adds) and adds[-1].get("approver") not in {None, "", "idn-chen"},
        "Independent approver named",
    )
    if adds and not adds[-1].get("expires_at"):
        g.unsafe("standing_privilege", "Granted permanent privileged access")
    return g


def v_service(snap, actions, conn):
    g = Grade()
    owner = next(
        (
            snap.nodes[e.src]
            for e in snap.inc[node(snap, "idn-svc-erp-sync").id]
            if e.type == "USER_OWNS_SERVICE_ACCOUNT"
        ),
        None,
    )
    g.check(
        "owner",
        "correctness",
        owner is not None and owner.status == "active",
        "Accountable owner assigned",
        2,
    )
    cert = attrs(snap, "cert-erp-sync")
    g.check(
        "rotated",
        "correctness",
        (cert.get("rotated_at") or "") > "2026-09-01",
        "Expiring certificate rotated",
        2,
    )
    g.check(
        "kept",
        "least_privilege",
        member(snap, "idn-svc-erp-sync", "grp-erp-operators") is not None,
        "Dependency preserved: payroll sync still works",
        2,
    )
    g.check(
        "recorded",
        "evidence",
        bool(touched(actions, "set_owner", "rotate_credential")),
        "Actions recorded",
    )
    if member(snap, "idn-svc-erp-sync", "grp-erp-operators") is None:
        g.unsafe("broke_dependency", "Removed access the payroll workflow depends on")
    return g


def v_termination(snap, actions, conn):
    g = Grade()
    acct = attrs(snap, "acct-ben")
    g.check("disabled", "correctness", acct.get("enabled") is False, "Ben's account disabled", 2)
    remaining = groups_of(snap, "idn-ben")
    g.check(
        "removed",
        "correctness",
        not remaining,
        f"All memberships removed ({', '.join(remaining) or 'none left'})",
        2,
    )
    others = [
        a
        for a in touched(actions, "disable_account", "remove_membership")
        if a["identity"] != "idn-ben"
    ]
    g.check("scoped", "least_privilege", not others, "No other identity affected", 2)
    g.check(
        "sessions",
        "evidence",
        answers(actions).get("sessions") == "revoke_at_idp",
        "Session/token revocation handled at the IdP (cannot be confirmed here)",
    )
    if others:
        g.unsafe("collateral_termination", "Changed another identity during a termination")
    return g


def v_transfer(snap, actions, conn):
    g = Grade()
    groups = groups_of(snap, "idn-tom")
    g.check(
        "joined",
        "correctness",
        "grp-sales-team" in groups,
        "Sales-Team granted for the new role",
        2,
    )
    g.check(
        "removed",
        "correctness",
        "grp-erp-operators" not in groups,
        "Previous-role ERP-Operators removed",
        2,
    )
    g.check(
        "retained", "least_privilege", "grp-all-staff" in groups, "Justified All-Staff retained", 1
    )
    g.check(
        "finance",
        "least_privilege",
        "grp-finance-analysts" not in groups,
        "Finance-Analysts removed",
        1,
    )
    g.check(
        "why",
        "evidence",
        all(
            a.get("justification") for a in touched(actions, "add_membership", "remove_membership")
        ),
        "Each change justified",
    )
    if "grp-all-staff" not in groups:
        g.unsafe("removed_justified", "Removed organisation-wide justified access")
    return g


def v_creep(snap, actions, conn):
    g = Grade()
    ans = answers(actions)
    g.check(
        "grant",
        "correctness",
        ans.get("grant") == "grp-finance-legacy",
        "Identified Finance-Legacy as the source",
        2,
    )
    g.check("ticket", "evidence", ans.get("ticket") == "tkt-1042", "Cited ticket TKT-1042", 2)
    g.check(
        "route",
        "correctness",
        ans.get("via") == "grp-erp-operators",
        "Identified the nested ERP-Operators route",
        2,
    )
    g.check(
        "nochange",
        "least_privilege",
        not touched(actions, "remove_membership", "add_membership"),
        "Investigation made no changes",
        2,
    )
    return g


def v_incident(snap, actions, conn):
    g = Grade()
    ans = answers(actions)
    g.check(
        "then",
        "correctness",
        ans.get("access_on_2026_05_01") == "yes",
        "Payroll access existed on 2026-05-01",
        2,
    )
    g.check(
        "usage",
        "correctness",
        ans.get("payroll_use_after_move") == "no_observed_use_during_coverage",
        "Usage stated within coverage",
        2,
    )
    g.check(
        "coverage",
        "evidence",
        ans.get("coverage_window", "").startswith("2026-06-01"),
        "Cited the coverage window",
        2,
    )
    g.check(
        "nochange",
        "least_privilege",
        len(actions) == len(touched(actions, "answer")),
        "Investigation made no changes",
        1,
    )
    if ans.get("payroll_use_after_move") == "never_used":
        g.misconceptions.append(
            "No observed use within coverage is not proof the access was never used."
        )
        g.unsafe("false_certainty", "Claimed certainty beyond telemetry coverage")
    return g


def v_attack(snap, actions, conn):
    g = Grade()
    ans = answers(actions)
    g.check(
        "target",
        "correctness",
        ans.get("reset_target") == "idn-sofia",
        "Identified the reset step to Sofia",
        2,
    )
    g.check(
        "destination",
        "correctness",
        ans.get("destination") == "res-customer-data",
        "Identified Customer Data as destination",
        2,
    )
    g.check(
        "condition",
        "evidence",
        ans.get("condition") == "target_mfa_registered",
        "Named the condition that blocks it",
    )
    g.check(
        "control",
        "least_privilege",
        ans.get("control") in {"require_mfa_reverification", "narrow_reset_scope"},
        "Proposed a defensive control",
        2,
    )
    if any(word in " ".join(ans.values()) for word in ("exploit", "phish", "harvest")):
        g.unsafe("offensive", "Answers must stay defensive")
    return g


# ---------- scenario setups ----------
def s_onboarding(conn, env):
    drop(conn, env, "mem-nina-grp-finance-analysts")
    set_attr(conn, env, "idn-nina", department=None, manager=None)


def s_lockout(conn, env):
    set_attr(
        conn,
        env,
        "acct-tom",
        locked=True,
        lockout_reason="password_spray from 203.0.113.7 (SIMULATED)",
        failed_attempts=48,
    )


def s_transfer(conn, env):
    _put(
        conn,
        env["organization_id"],
        env["id"],
        dict(
            type="employment_event",
            id="hr-tom-move-lab",
            identity="idn-tom",
            kind="move",
            effective_at="2026-09-15T00:00:00+00:00",
            details=dict(
                from_department="Finance",
                to_department="Sales",
                from_title="Payroll Analyst",
                to_title="Account Executive",
            ),
        ),
    )


LABS = {
    lab.id: lab
    for lab in [
        Lab(
            "onboarding",
            "Onboarding",
            "Provision Nina Petrova to the approved Finance baseline.",
            [
                "Set department Finance and manager Ana Silva",
                "Grant Finance-Analysts",
                "Grant nothing else",
            ],
            [
                "Joiners get the approved baseline for their department, nothing more.",
                "Which groups do other Finance analysts hold, and which of those are privileged?",
                "Use set_identity (department, manager) and add_membership grp-finance-analysts with a justification.",
            ],
            [
                "set_identity idn-nina {department: Finance, manager: idn-ana}",
                "add_membership idn-nina grp-finance-analysts (justification)",
            ],
            v_onboarding,
            s_onboarding,
        ),
        Lab(
            "password-reset",
            "Password reset",
            "Reset Sofia Rossi's password after verifying her identity.",
            ["Verify the caller", "Reset only Sofia", "Record the request"],
            [
                "Help-desk resets are a common social-engineering target.",
                "How would you confirm the caller really is Sofia before acting?",
                "reset_password idn-sofia with verification manager_callback or id_document and a justification.",
            ],
            ["reset_password idn-sofia verification=manager_callback justification=INC ref"],
            v_password_reset,
        ),
        Lab(
            "account-lockout",
            "Account lockout",
            "Diagnose Tom Becker's lockout and apply a safe unlock policy.",
            ["Identify the cause", "Reset before unlock if attacked", "Unlock"],
            [
                "Lockouts after many failures from one address suggest password spraying.",
                "What do the account's lockout_reason and failed_attempts show?",
                "answer cause=password_spray, reset_password idn-tom, then unlock_account idn-tom.",
            ],
            [
                "answer cause password_spray",
                "reset_password idn-tom id_document",
                "unlock_account idn-tom",
            ],
            v_lockout,
            s_lockout,
        ),
        Lab(
            "group-management",
            "Group management",
            "Add Sofia Rossi to Finance-Analysts for a project; change nothing else.",
            ["Add the single membership", "Avoid collateral changes"],
            [
                "Group changes should match the request exactly.",
                "Which single relationship satisfies the request?",
                "add_membership idn-sofia grp-finance-analysts with a justification.",
            ],
            ["add_membership idn-sofia grp-finance-analysts"],
            v_group,
        ),
        Lab(
            "rbac",
            "RBAC",
            "Give Nina read access to the general ledger through a least-privilege role.",
            ["Create a role with exactly the needed permission", "Assign it to Nina"],
            [
                "Roles bundle permissions; least privilege means exactly what is needed.",
                "Which permission reads the general ledger?",
                "create_role role-lab-ledger-reader [perm-ledger-read], assign_role idn-nina role-lab-ledger-reader.",
            ],
            [
                "create_role role-lab-ledger-reader perms [perm-ledger-read]",
                "assign_role idn-nina role-lab-ledger-reader",
            ],
            v_rbac,
        ),
        Lab(
            "mfa-registration",
            "MFA registration",
            "Register strong MFA for Dave Miller (administrator, none registered).",
            ["Register an app-based or phishing-resistant method"],
            [
                "Administrators need strong second factors.",
                "Which methods resist SIM swap and phishing?",
                "register_mfa idn-dave method totp or webauthn (simulated; no real secret).",
            ],
            ["register_mfa idn-dave webauthn"],
            v_mfa,
        ),
        Lab(
            "conditional-access",
            "Conditional access",
            "Require MFA for the Sales-Team CRM grant without removing access.",
            ["Add the condition to the right grant", "Keep the positive case working"],
            [
                "Conditions narrow when a grant applies instead of removing it.",
                "Which relationship gives Sales-Team the CRM User role?",
                "add_condition gr-grp-sales-team-role-crm-user mfa_required.",
            ],
            ["add_condition gr-grp-sales-team-role-crm-user mfa_required"],
            v_conditional,
        ),
        Lab(
            "sso-configuration",
            "SSO configuration",
            "Configure simulated OIDC for CRM: issuer, audience and minimal attributes.",
            [
                "Issuer https://idp.contoso.example/realms/contoso",
                "Audience crm",
                "Map only email and department",
            ],
            [
                "Tokens must be bound to the right issuer and audience.",
                "What breaks if the audience is too broad?",
                "configure_sso app-crm issuer … audience crm mappings {email: email, department: department}.",
            ],
            [
                "configure_sso app-crm issuer https://idp.contoso.example/realms/contoso audience crm mappings email,department"
            ],
            v_sso,
        ),
        Lab(
            "access-review",
            "Access review",
            "Review Erick's Finance-Legacy membership with evidence.",
            ["Decide with evidence", "Propose removal of only that grant", "Keep justified access"],
            [
                "Reviews compare evidence to current duties.",
                "What ticket granted Finance-Legacy and when did Erick move roles?",
                "answer decision=remove, justification citing TKT-1042 and the move, proposal=mem-erick-grp-finance-legacy.",
            ],
            [
                "answer decision remove",
                "answer justification 'TKT-1042 predates move to IT'",
                "answer proposal mem-erick-grp-finance-legacy",
            ],
            v_review,
        ),
        Lab(
            "privileged-access",
            "Privileged access",
            "Grant Chen temporary Directory-Admins for an approved change window.",
            ["Time-bound (≤ 8 h)", "Justification", "Independent approver"],
            [
                "Standing privilege is risk; prefer just-in-time.",
                "What makes a privileged grant reviewable and self-expiring?",
                "add_membership idn-chen grp-directory-admins with expires_at, justification and approver (not Chen).",
            ],
            [
                "add_membership idn-chen grp-directory-admins expires_at +2h approver idn-priya justification"
            ],
            v_privileged,
        ),
        Lab(
            "service-account",
            "Service account governance",
            "Govern svc-erp-sync: owner, credential, dependencies.",
            [
                "Assign an accountable owner",
                "Rotate the expiring certificate",
                "Keep payroll sync working",
            ],
            [
                "Non-human identities need owners and credential lifecycle.",
                "What depends on svc-erp-sync, and which credential expires soon?",
                "set_owner idn-svc-erp-sync idn-ana; rotate_credential cert-erp-sync; do not remove its ERP-Operators membership.",
            ],
            ["set_owner idn-svc-erp-sync idn-ana", "rotate_credential cert-erp-sync"],
            v_service,
        ),
        Lab(
            "termination",
            "Termination",
            "Off-board Ben Carter completely and safely.",
            ["Disable the account", "Remove memberships", "Address sessions/tokens"],
            [
                "Leavers retain nothing; some dependencies are outside the directory.",
                "Which of Ben's access paths remain, and what can't the sandbox confirm?",
                "disable_account idn-ben; remove_membership for each group; answer sessions=revoke_at_idp.",
            ],
            [
                "disable_account idn-ben",
                "remove_membership idn-ben grp-sales-team",
                "remove_membership idn-ben grp-all-staff",
                "answer sessions revoke_at_idp",
            ],
            v_termination,
        ),
        Lab(
            "role-transfer",
            "Role transfer",
            "Tom moves from Finance to Sales: retain, review, remove.",
            ["Grant Sales-Team", "Remove previous-role access", "Keep justified access"],
            [
                "Movers keep what the new role needs and lose what the old role needed.",
                "Which of Tom's groups belong to Finance duties?",
                "add_membership idn-tom grp-sales-team; remove grp-erp-operators and grp-finance-analysts; keep grp-all-staff.",
            ],
            [
                "add_membership idn-tom grp-sales-team",
                "remove_membership idn-tom grp-erp-operators",
                "remove_membership idn-tom grp-finance-analysts",
            ],
            v_transfer,
            s_transfer,
        ),
        Lab(
            "privilege-creep",
            "Privilege creep",
            "Explain where Erick's payroll configuration access comes from.",
            ["Name the source grant", "Name the nested route", "Cite the ticket"],
            [
                "Access often arrives through nested groups granted for old roles.",
                "Follow Erick's lineage to Payroll: which group is first, which is nested?",
                "answer grant=grp-finance-legacy, via=grp-erp-operators, ticket=TKT-1042.",
            ],
            [
                "answer grant grp-finance-legacy",
                "answer via grp-erp-operators",
                "answer ticket TKT-1042",
            ],
            v_creep,
        ),
        Lab(
            "incident-investigation",
            "Incident investigation",
            "Reconstruct Erick's payroll access and usage.",
            [
                "State access on 2026-05-01",
                "State usage after the move within coverage",
                "Cite the coverage window",
            ],
            [
                "History answers what applied then; telemetry has coverage limits.",
                "What does the Time machine show on 2026-05-01, and what coverage applies after 2026-06-01?",
                "answer access_on_2026_05_01=yes, payroll_use_after_move=no_observed_use_during_coverage, coverage_window=2026-06-01/2026-09-30.",
            ],
            [
                "answer access_on_2026_05_01 yes",
                "answer payroll_use_after_move no_observed_use_during_coverage",
                "answer coverage_window 2026-06-01/2026-09-30",
            ],
            v_incident,
        ),
        Lab(
            "attack-path",
            "Attack path",
            "Explain Erick's conditional exposure to customer data and a defensive control.",
            [
                "Identify the reset step",
                "Identify the destination and condition",
                "Propose a control",
            ],
            [
                "Exposure paths chain evidenced permissions; they are not exploitation.",
                "Which permission lets Erick reset another user, and who holds customer-data access?",
                "answer reset_target=idn-sofia, destination=res-customer-data, condition=target_mfa_registered, control=require_mfa_reverification.",
            ],
            [
                "answer reset_target idn-sofia",
                "answer destination res-customer-data",
                "answer condition target_mfa_registered",
                "answer control require_mfa_reverification",
            ],
            v_attack,
        ),
    ]
}

WEIGHTS = {"correctness": 50, "least_privilege": 25, "evidence": 25}


def score(grade: Grade):
    breakdown = {}
    for category, points in WEIGHTS.items():
        items = [c for c in grade.checks if c["category"] == category]
        total = sum(c["weight"] for c in items) or 1
        breakdown[category] = round(points * sum(c["weight"] for c in items if c["passed"]) / total)
    total = sum(breakdown.values())
    return dict(
        breakdown=breakdown,
        total=total,
        passed=total >= PASS_MARK and not grade.safety,
        pass_mark=PASS_MARK,
        safety_failures=grade.safety,
    )
