"""Generate local-only secrets and synthetic login realm; never print secrets."""

import base64
import json
import secrets
from pathlib import Path
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    if (root / ".env").exists():
        raise SystemExit(".env already exists; preserving configuration.")
    local = root / ".local"
    local.mkdir(exist_ok=True)
    database_password = secrets.token_urlsafe(32)
    runtime_password = secrets.token_urlsafe(32)
    worker_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)
    people = []
    for name, roles in [
        ("alex", ["org_admin", "operator"]),
        ("jordan", ["approver"]),
        ("sam", ["viewer"]),
        ("riley", ["reviewer"]),
        ("casey", ["investigator"]),
        ("morgan", ["auditor"]),
        ("quinn", ["operator"]),
        ("lee", ["learner"]),
        ("jamie", ["approver"]),
    ]:
        people.append(
            dict(id=str(uuid4()), username=name, password=secrets.token_urlsafe(20), roles=roles)
        )
    realm = dict(
        realm="identityguardian",
        enabled=True,
        # Invitees register their own credentials; platform access still requires an invite.
        registrationAllowed=True,
        passwordPolicy="length(12) and notUsername",
        sslRequired="none",
        clients=[
            dict(
                clientId="identityguardian",
                publicClient=True,
                standardFlowEnabled=True,
                directAccessGrantsEnabled=False,
                redirectUris=["http://localhost:8000/api/v1/auth/callback"],
                webOrigins=["http://localhost:8000"],
                attributes={"pkce.code.challenge.method": "S256"},
            )
        ],
        users=[
            dict(
                id=p["id"],
                username=p["username"],
                enabled=True,
                emailVerified=True,
                firstName=p["username"].title(),
                lastName="Contoso",
                email=p["username"] + "@contoso.example",
                credentials=[dict(type="password", value=p["password"], temporary=False)],
                requiredActions=[],
            )
            for p in people
        ],
    )
    (local / "realm.json").write_text(json.dumps(realm, indent=2))
    (local / "bootstrap.json").write_text(json.dumps(people, indent=2))
    (root / ".env").write_text(
        f"POSTGRES_PASSWORD={database_password}\nRUNTIME_PASSWORD={runtime_password}\n"
        f"WORKER_PASSWORD={worker_password}\n"
        f"WORKER_DATABASE_URL=postgresql://guardian_worker:{worker_password}@127.0.0.1:55432/identityguardian\n"
        f"KEYCLOAK_ADMIN_PASSWORD={admin_password}\n"
        f"MIGRATION_DATABASE_URL=postgresql://guardian_migrator:{database_password}@127.0.0.1:55432/identityguardian\n"
        f"DATABASE_URL=postgresql://guardian_app:{runtime_password}@127.0.0.1:55432/identityguardian\n"
        "APP_ORIGIN=http://localhost:8000\nOIDC_ISSUER_URL=http://localhost:58080/realms/identityguardian\n"
        "OIDC_CLIENT_ID=identityguardian\nDEVELOPMENT=true\nSECURE_COOKIES=false\n"
        f"SECRET_MASTER_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}\n"
        f"AUDIT_SIGNING_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}\n"
    )
    print(
        "Created ignored .env and .local files. Local login credentials are in .local/bootstrap.json."
    )


if __name__ == "__main__":
    main()
