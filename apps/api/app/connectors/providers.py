"""Mock providers (read-only) and the sandbox adapter, all behind the connector contract."""

from packages.fixtures import mock_providers

from .base import Capabilities, Connector, ConnectorUnavailable, Page, RateLimited

PAGE_SIZE = 25
BASELINE = "2024-01-01T00:00:00+00:00"  # providers expose no membership start: bounded below


def _row(object_id, body, version):
    return dict(
        object_id=object_id, object_type=body["type"], body=body, deleted=False, version=version
    )


def _node(oid, kind, name, subtype, attributes, valid_from=BASELINE, status="active"):
    return dict(
        type="node",
        id=oid,
        kind=kind,
        subtype=subtype,
        name=name,
        revisions=[dict(valid_from=valid_from, status=status, attributes=attributes)],
    )


def _rel(oid, rel, src, dst, attributes, valid_from=BASELINE):
    return dict(
        type="relationship",
        id=oid,
        rel=rel,
        src=src,
        dst=dst,
        valid_from=valid_from,
        valid_to=None,
        attributes=dict(origin="group_membership", **attributes),
    )


class PagedMock(Connector):
    """Pages over canonical objects; injected faults model provider outages and throttling."""

    def __init__(self, config: dict):
        self.config = config or {}
        self.throttled = 0
        omit = set(self.config.get("omit") or [])  # simulates objects deleted at the provider
        self._objects = [o for o in self.canonical() if o["object_id"] not in omit]

    def capabilities(self):
        return Capabilities(
            read=["identity", "account", "group", "membership"],
            write=[],
            permission_semantics="group membership only",
            native_ttl=False,
            idempotent_writes=False,
            reversible="read-only mock",
            authoritative_scope=self.scope,
            page_size=PAGE_SIZE,
        )

    def read(self, cursor):
        offset = int(cursor or 0)
        page_number = offset // PAGE_SIZE + 1
        if self.config.get("fail_on_page") == page_number:
            raise ConnectorUnavailable(
                f"{self.source} unavailable on page {page_number} (injected fault)"
            )
        if self.config.get("rate_limit_on_page") == page_number and self.throttled < int(
            self.config.get("rate_limit_times", 1)
        ):
            self.throttled += 1
            raise RateLimited(f"{self.source} returned 429 on page {page_number} (injected)")
        chunk = self._objects[offset : offset + PAGE_SIZE]
        nxt = offset + PAGE_SIZE
        return Page(
            objects=chunk,
            next_cursor=str(nxt) if nxt < len(self._objects) else None,
            provenance=dict(provider=self.source, page=page_number, synthetic=True),
        )


class MockEntra(PagedMock):
    source, scope = "mock_entra", "Mock Entra tenant contoso-mock: users, groups, memberships"

    def canonical(self):
        data = mock_providers.entra()
        objects, v = [], 0
        for u in data["users"]:
            v += 1
            uid = "entra:" + u["id"]
            objects.append(
                _row(
                    uid,
                    _node(
                        uid,
                        "identity",
                        u["displayName"],
                        "employee",
                        dict(
                            upn=u["userPrincipalName"],
                            department=u["department"],
                            title=u["jobTitle"],
                            synthetic=True,
                        ),
                        status="active" if u["accountEnabled"] else "disabled",
                    ),
                    v,
                )
            )
            aid = "entra-acct:" + u["id"]
            objects.append(
                _row(
                    aid,
                    _node(
                        aid,
                        "account",
                        u["userPrincipalName"],
                        "entra",
                        dict(
                            enabled=u["accountEnabled"],
                            last_sign_in=u["signInActivity"]["lastSignInDateTime"],
                        ),
                    ),
                    v,
                )
            )
            objects.append(
                _row(
                    f"entra-has:{u['id']}",
                    _rel(f"entra-has:{u['id']}", "HAS_ACCOUNT", uid, aid, {}),
                    v,
                )
            )
        for g in data["groups"]:
            v += 1
            gid = "entra:" + g["id"]
            objects.append(
                _row(
                    gid,
                    _node(gid, "group", g["displayName"], "security", dict(source_group=True)),
                    v,
                )
            )
        for m in data["members"]:
            v += 1
            mid = f"entra-mem:{m['groupId']}:{m['memberId']}"
            objects.append(
                _row(
                    mid,
                    _rel(
                        mid,
                        "USER_MEMBER_OF_GROUP",
                        "entra:" + m["memberId"],
                        "entra:" + m["groupId"],
                        {},
                    ),
                    v,
                )
            )
        return objects


class MockOkta(PagedMock):
    source, scope = "mock_okta", "Mock Okta org contoso-mock: users, groups, memberships"

    def canonical(self):
        data = mock_providers.okta()
        objects, v = [], 0
        for u in data["users"]:
            v += 1
            uid = "okta:" + u["id"]
            objects.append(
                _row(
                    uid,
                    _node(
                        uid,
                        "identity",
                        u["profile"]["displayName"],
                        "employee",
                        dict(
                            login=u["profile"]["login"],
                            department=u["profile"]["department"],
                            synthetic=True,
                        ),
                        status="active" if u["status"] == "ACTIVE" else "deprovisioned",
                    ),
                    v,
                )
            )
        for g in data["groups"]:
            v += 1
            gid = "okta:" + g["id"]
            objects.append(
                _row(gid, _node(gid, "group", g["profile"]["name"], "okta_group", {}), v)
            )
        for m in data["members"]:
            v += 1
            mid = f"okta-mem:{m['groupId']}:{m['userId']}"
            objects.append(
                _row(
                    mid,
                    _rel(
                        mid,
                        "USER_MEMBER_OF_GROUP",
                        "okta:" + m["userId"],
                        "okta:" + m["groupId"],
                        {},
                    ),
                    v,
                )
            )
        return objects


PROVIDERS = {"mock_entra": MockEntra, "mock_okta": MockOkta}


def build(connector_row, settings=None) -> Connector:
    kind = connector_row["kind"]
    if kind == "entra":
        from ..config import master_keys
        from ..secrets_envelope import open_envelope
        from . import entra

        current, previous = (
            (settings.secret_master_key, settings.secret_master_key_previous)
            if settings
            else master_keys()
        )
        try:
            secret = open_envelope(
                connector_row["secret_envelope"],
                current,
                f"connector:{connector_row['id']}",
                previous,
            )
        except Exception:  # noqa: BLE001 - any failure to open is reported without detail
            raise ConnectorUnavailable(
                "Connector secret cannot be opened with the configured keys"
            ) from None
        return entra.EntraConnector(connector_row.get("config") or {}, secret)
    if kind not in PROVIDERS:
        raise ValueError(f"No paged provider for {kind}")
    return PROVIDERS[kind](connector_row.get("config") or {})
