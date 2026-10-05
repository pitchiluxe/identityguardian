"""Idempotently add SYNTHETIC local users to the loopback Keycloak realm and platform memberships.

Local development only: talks to http://localhost:58080 with the generated local admin password
from .env, writes generated passwords only to ignored .local/bootstrap.json and never prints them.
Optional TOTP enrolment (`--mfa user`) stores the generated seed in the same ignored file so local
browser tests can complete MFA.
"""

import argparse
import base64
import json
import os
import secrets
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ORG = UUID("10000000-0000-4000-8000-000000000001")
KEYCLOAK = "http://localhost:58080"
REALM = "identityguardian"
EXTRA = [
    ("riley", ["reviewer"]),
    ("casey", ["investigator"]),
    ("morgan", ["auditor"]),
    ("quinn", ["operator"]),
    ("lee", ["learner"]),
    ("jamie", ["approver"]),
]


def admin_token(client):
    response = client.post(
        f"{KEYCLOAK}/realms/master/protocol/openid-connect/token",
        data=dict(
            grant_type="password",
            client_id="admin-cli",
            username="local-admin",
            password=os.environ["KEYCLOAK_ADMIN_PASSWORD"],
        ),
    )
    response.raise_for_status()
    return response.json()["access_token"]


def otp_credential(seed):
    return dict(
        type="otp",
        userLabel="local-synthetic-totp",
        secretData=json.dumps({"value": seed}),
        credentialData=json.dumps(
            {"subType": "totp", "digits": 6, "counter": 0, "period": 30, "algorithm": "HmacSHA1"}
        ),
    )


def configure_amr(client, headers):
    """Emit an `amr` claim (pwd / otp) so the platform can verify MFA assurance."""
    admin = f"{KEYCLOAK}/admin/realms/{REALM}"
    clients = client.get(
        f"{admin}/clients", params={"clientId": "identityguardian"}, headers=headers
    ).json()
    cid = clients[0]["id"]
    mappers = client.get(f"{admin}/clients/{cid}/protocol-mappers/models", headers=headers).json()
    if not any(m["protocolMapper"] == "oidc-amr-mapper" for m in mappers):
        client.post(
            f"{admin}/clients/{cid}/protocol-mappers/models",
            headers=headers,
            json=dict(
                name="amr",
                protocol="openid-connect",
                protocolMapper="oidc-amr-mapper",
                config={"id.token.claim": "true", "access.token.claim": "true"},
            ),
        ).raise_for_status()
    references = {"auth-username-password-form": "pwd", "auth-otp-form": "otp"}
    executions = client.get(
        f"{admin}/authentication/flows/browser/executions", headers=headers
    ).json()
    for execution in executions:
        value = references.get(execution.get("providerId"))
        if not value:
            continue
        # maxAge matches the platform's 5-minute MFA recency requirement.
        config = {"default.reference.value": value, "default.reference.maxAge": "300"}
        if execution.get("authenticationConfig"):
            existing = client.get(
                f"{admin}/authentication/config/{execution['authenticationConfig']}",
                headers=headers,
            ).json()
            existing["config"] = config
            client.put(
                f"{admin}/authentication/config/{existing['id']}", headers=headers, json=existing
            ).raise_for_status()
        else:
            client.post(
                f"{admin}/authentication/executions/{execution['id']}/config",
                headers=headers,
                json=dict(alias=f"amr-{value}", config=config),
            ).raise_for_status()


def configure_registration(client, headers):
    """Self-registration for invitees: own password (policy) and mandatory TOTP enrolment.
    Access is still granted only by an invite in the platform."""
    admin = f"{KEYCLOAK}/admin/realms/{REALM}"
    realm = client.get(admin, headers=headers).json()
    realm.update(registrationAllowed=True, passwordPolicy="length(12) and notUsername")
    client.put(admin, headers=headers, json=realm).raise_for_status()
    url = f"{admin}/authentication/required-actions/CONFIGURE_TOTP"
    action = client.get(url, headers=headers).json()
    action.update(enabled=True, defaultAction=True)
    client.put(url, headers=headers, json=action).raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mfa", action="append", default=[], help="enrol TOTP for this username")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    path = ROOT / ".local" / "bootstrap.json"
    people = json.loads(path.read_text())
    known = {p["username"] for p in people}
    with httpx.Client(timeout=15) as client:
        headers = {"Authorization": "Bearer " + admin_token(client)}
        configure_amr(client, headers)
        configure_registration(client, headers)
        added = []
        for name, roles in EXTRA:
            if name in known:
                continue
            person = dict(
                id=str(uuid4()), username=name, password=secrets.token_urlsafe(20), roles=roles
            )
            body = dict(
                id=person["id"],
                username=name,
                enabled=True,
                emailVerified=True,
                firstName=name.title(),
                lastName="Contoso",
                email=f"{name}@contoso.example",
                credentials=[dict(type="password", value=person["password"], temporary=False)],
            )
            client.post(
                f"{KEYCLOAK}/admin/realms/{REALM}/users", json=body, headers=headers
            ).raise_for_status()
            people.append(person)
            added.append(person)
        # Keycloak assigns its own user IDs; the OIDC subject is that ID.
        renamed = {}
        for person in people:
            found = client.get(
                f"{KEYCLOAK}/admin/realms/{REALM}/users",
                params=dict(username=person["username"], exact="true"),
                headers=headers,
            ).json()
            if found and found[0]["id"] != person["id"]:
                renamed[person["id"]] = found[0]["id"]
                person["id"] = found[0]["id"]
        for person in people:
            if person["username"] in args.mfa and not person.get("totp_seed"):
                seed = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
                user_id = person["id"]
                imported = client.post(
                    f"{KEYCLOAK}/admin/realms/{REALM}/partialImport",
                    json=dict(
                        ifResourceExists="OVERWRITE",
                        users=[
                            dict(
                                id=user_id,
                                username=person["username"],
                                enabled=True,
                                emailVerified=True,
                                firstName=person["username"].title(),
                                lastName="Contoso",
                                email=f"{person['username']}@contoso.example",
                                credentials=[
                                    dict(
                                        type="password", value=person["password"], temporary=False
                                    ),
                                    otp_credential(seed),
                                ],
                            )
                        ],
                    ),
                    headers=headers,
                )
                imported.raise_for_status()
                person["totp_seed"] = seed
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        for old, new in renamed.items():
            conn.execute(
                "DELETE FROM memberships WHERE user_id=%s AND NOT EXISTS "
                "(SELECT 1 FROM audit_events WHERE actor_id=%s)",
                (old, old),
            )
            try:
                with conn.transaction():
                    conn.execute(
                        "DELETE FROM users u WHERE id=%s AND NOT EXISTS "
                        "(SELECT 1 FROM memberships m WHERE m.user_id=u.id)",
                        (old,),
                    )
            except psycopg.errors.ForeignKeyViolation:
                pass  # referenced by records; keep the inactive user row for integrity
        for person in people:
            if person["id"] not in renamed.values() and person not in added:
                continue
            conn.execute(
                "INSERT INTO users VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    person["id"],
                    os.environ["OIDC_ISSUER_URL"],
                    person["id"],
                    person["username"].title() + " Contoso",
                ),
            )
            conn.execute(
                "INSERT INTO memberships(organization_id,user_id,roles) VALUES (%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (ORG, person["id"], person["roles"]),
            )
    path.write_text(json.dumps(people, indent=2))
    print(
        f"Added {len(added)} synthetic users; MFA enrolment requested for {len(args.mfa)}. "
        "Credentials remain in ignored .local/bootstrap.json."
    )


if __name__ == "__main__":
    main()
