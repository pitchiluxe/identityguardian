"""Deterministic SYNTHETIC provider payloads shaped like Microsoft Entra ID and Okta APIs.

These are mock providers for the connector framework. They do not call any real service.
"""

import uuid

from .contoso import PEOPLE

NAMESPACE = uuid.UUID("7c1d4c1e-3b6a-4f3e-9b1c-5d2f0a9e1c42")
EXTRA_USERS = 60  # enough to require several pages


def _guid(*parts):
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def entra():
    users = [
        dict(
            id=_guid("entra", pid),
            userPrincipalName=f"{pid}@contoso.example",
            displayName=name,
            department=dept,
            jobTitle=title,
            accountEnabled=status != "terminated",
            signInActivity=dict(lastSignInDateTime="2026-09-29T08:00:00Z"),
        )
        for pid, name, _subtype, dept, title, _mgr, status, *_ in PEOPLE
    ]
    users += [
        dict(
            id=_guid("entra", f"extra{i}"),
            userPrincipalName=f"user{i:02d}@contoso.example",
            displayName=f"Mock User {i:02d}",
            department="Operations",
            jobTitle="Analyst",
            accountEnabled=True,
            signInActivity=dict(lastSignInDateTime=None),
        )
        for i in range(EXTRA_USERS)
    ]
    groups = [
        dict(id=_guid("entra-group", g), displayName=g, securityEnabled=True)
        for g in ["SG-Finance", "SG-IT", "SG-Sales", "SG-Admins"]
    ]
    by_name = {g["displayName"]: g["id"] for g in groups}
    dept_group = {"Finance": "SG-Finance", "IT": "SG-IT", "Sales": "SG-Sales"}
    members = []
    for user in users:
        group = dept_group.get(user["department"])
        if group:
            members.append(dict(groupId=by_name[group], memberId=user["id"]))
    members.append(dict(groupId=by_name["SG-Admins"], memberId=_guid("entra", "fatima")))
    return dict(users=users, groups=groups, members=members)


def okta():
    users = [
        dict(
            id="00u" + _guid("okta", pid).replace("-", "")[:17],
            status="ACTIVE" if status != "terminated" else "DEPROVISIONED",
            profile=dict(
                login=f"{pid}@contoso.example", displayName=name, department=dept, title=title
            ),
        )
        for pid, name, _subtype, dept, title, _mgr, status, *_ in PEOPLE
    ]
    groups = [
        dict(id="00g" + _guid("okta-group", g).replace("-", "")[:17], profile=dict(name=g))
        for g in ["Everyone", "Okta-Admins"]
    ]
    members = [dict(groupId=groups[0]["id"], userId=u["id"]) for u in users]
    members.append(dict(groupId=groups[1]["id"], userId=users[3]["id"]))
    return dict(users=users, groups=groups, members=members)
