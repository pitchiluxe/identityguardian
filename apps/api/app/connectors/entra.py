"""Read-only Microsoft Entra ID connector (Phase 23).

Client-credentials token, then GET-only Microsoft Graph v1.0 calls to fixed hosts. Each read()
performs one Graph request and returns canonical objects; the staged cursor carries the Graph
nextLink and the queue of groups/roles/apps still to expand. Real tenant data: no synthetic flag.
"""

import base64
import json
import re

import httpx

from .base import Capabilities, Connector, ConnectorUnavailable, Page, RateLimited

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_APPS = 200
REJECTED = "Microsoft rejected the app credentials or permissions"
UNAVAILABLE = "Microsoft Graph unavailable"
STAGES = ["users", "groups", "group_members", "roles", "role_members", "apps", "app_assignments"]
LISTS = {
    "users": "/users?$select=id,displayName,userPrincipalName,accountEnabled,department,"
    "jobTitle,userType&$top=100",
    "groups": "/groups?$select=id,displayName,securityEnabled&$top=100",
    "roles": "/directoryRoles?$select=id,displayName",
    "apps": "/servicePrincipals?$select=id,displayName,appId&$top=100",
}
EXPAND = {  # stage -> (queue name, URL template)
    "group_members": ("groups", "/groups/{}/members?$select=id&$top=100"),
    "role_members": ("roles", "/directoryRoles/{}/members?$select=id"),
    "app_assignments": ("apps", "/servicePrincipals/{}/appRoleAssignedTo?$top=100"),
}
USER, GROUP = "#microsoft.graph.user", "#microsoft.graph.group"


def _encode(state):
    return base64.urlsafe_b64encode(json.dumps(state, sort_keys=True).encode()).decode()


def _decode(cursor):
    return json.loads(base64.urlsafe_b64decode(cursor.encode()))


class EntraConnector(Connector):
    source = "entra"

    def __init__(self, config: dict, client_secret: str, http: httpx.Client | None = None):
        config = config or {}
        self.tenant, self.client_id = config.get("tenant_id", ""), config.get("client_id", "")
        if not (GUID.match(self.tenant or "") and GUID.match(self.client_id or "")):
            raise ValueError("Tenant ID and Client ID must be GUIDs")
        if not client_secret:
            raise ValueError("A client secret is required")
        self._secret = client_secret
        self._http = http or httpx.Client(timeout=30, follow_redirects=False)
        self._token = None

    def capabilities(self):
        return Capabilities(
            read=["identity", "account", "group", "membership", "role", "application"],
            write=[],
            permission_semantics="Entra group membership, directory roles, app assignments",
            native_ttl=False,
            idempotent_writes=False,
            reversible="read-only",
            authoritative_scope=f"Entra tenant {self.tenant}: users, groups, roles, app assignments",
            page_size=100,
        )

    # -- HTTP ---------------------------------------------------------------------------------
    def _fetch_token(self):
        try:
            response = self._http.post(
                f"{LOGIN}/{self.tenant}/oauth2/v2.0/token",
                data=dict(
                    grant_type="client_credentials",
                    client_id=self.client_id,
                    client_secret=self._secret,
                    scope="https://graph.microsoft.com/.default",
                ),
            )
        except httpx.HTTPError:
            raise ConnectorUnavailable(UNAVAILABLE) from None
        if response.status_code in (400, 401, 403):
            raise ConnectorUnavailable(REJECTED)
        if response.status_code == 429:
            raise RateLimited("Microsoft throttled the token request")
        if response.status_code >= 300:
            raise ConnectorUnavailable(UNAVAILABLE)
        self._token = response.json().get("access_token")
        if not self._token:
            raise ConnectorUnavailable(UNAVAILABLE)

    def _get(self, url):
        if not url.startswith(GRAPH + "/"):  # nextLinks must stay on Microsoft Graph
            raise ConnectorUnavailable(UNAVAILABLE)
        for attempt in (0, 1):
            if self._token is None:
                self._fetch_token()
            try:
                response = self._http.get(url, headers={"Authorization": f"Bearer {self._token}"})
            except httpx.HTTPError:
                raise ConnectorUnavailable(UNAVAILABLE) from None
            if response.status_code == 401 and attempt == 0:
                self._token = None  # expired token: refresh once
                continue
            if response.status_code in (401, 403):
                raise ConnectorUnavailable(REJECTED)
            if response.status_code == 429:
                raise RateLimited("Microsoft Graph throttled the request")
            if response.status_code >= 300:
                raise ConnectorUnavailable(UNAVAILABLE)
            return response.json()
        raise ConnectorUnavailable(REJECTED)

    # -- staged read --------------------------------------------------------------------------
    def read(self, cursor):
        from .providers import _node, _rel, _row  # shared canonical shapes

        state = (
            _decode(cursor)
            if cursor
            else dict(
                stage="users", url=None, current=None, groups=[], roles=[], apps=[], skipped=0
            )
        )
        objects, version = [], 0

        def emit(oid, body):
            nonlocal version
            version += 1
            objects.append(_row(oid, body, version))

        while state["stage"] != "done":
            stage = state["stage"]
            if stage in LISTS:
                data = self._get(state["url"] or GRAPH + LISTS[stage])
                for item in data.get("value", []):
                    self._map_list(stage, item, state, emit, _node, _rel)
                self._advance(state, data.get("@odata.nextLink"))
                break
            queue_name, template = EXPAND[stage]
            if state["current"] is None:
                if not state[queue_name]:
                    self._advance(state, None)
                    continue
                state["current"] = state[queue_name].pop(0)
            data = self._get(state["url"] or GRAPH + template.format(state["current"]))
            for item in data.get("value", []):
                self._map_member(stage, state["current"], item, state, emit, _rel)
            nxt = data.get("@odata.nextLink")
            state["url"] = nxt
            if not nxt:
                state["current"] = None
            break
        provenance = dict(
            provider="entra",
            tenant=self.tenant,
            stage=state["stage"],
            skipped_group_app_assignments=state["skipped"],
        )
        done = state["stage"] == "done"
        return Page(
            objects=objects, next_cursor=None if done else _encode(state), provenance=provenance
        )

    @staticmethod
    def _advance(state, next_link):
        if next_link:
            state["url"] = next_link
            return
        state["url"] = None
        index = STAGES.index(state["stage"]) + 1
        state["stage"] = STAGES[index] if index < len(STAGES) else "done"

    @staticmethod
    def _map_list(stage, item, state, emit, _node, _rel):
        oid = "entra:" + item["id"]
        if stage == "users":
            enabled = bool(item.get("accountEnabled"))
            subtype = "guest" if item.get("userType") == "Guest" else "employee"
            attrs = dict(
                upn=item.get("userPrincipalName"),
                department=item.get("department"),
                title=item.get("jobTitle"),
                user_type=item.get("userType"),
            )
            emit(
                oid,
                _node(
                    oid,
                    "identity",
                    item.get("displayName") or item["id"],
                    subtype,
                    attrs,
                    status="active" if enabled else "disabled",
                ),
            )
            account = "entra-acct:" + item["id"]
            emit(
                account,
                _node(
                    account,
                    "account",
                    item.get("userPrincipalName") or item["id"],
                    "entra",
                    dict(enabled=enabled),
                ),
            )
            link = f"entra-has:{item['id']}"
            emit(link, _rel(link, "HAS_ACCOUNT", oid, account, {}))
        elif stage == "groups":
            emit(
                oid,
                _node(
                    oid,
                    "group",
                    item.get("displayName") or item["id"],
                    "security",
                    dict(security_enabled=bool(item.get("securityEnabled"))),
                ),
            )
            state["groups"].append(item["id"])
        elif stage == "roles":
            emit(
                oid, _node(oid, "role", item.get("displayName") or item["id"], "directory_role", {})
            )
            state["roles"].append(item["id"])
        elif stage == "apps" and len(state["apps"]) < MAX_APPS:
            emit(
                oid,
                _node(
                    oid,
                    "application",
                    item.get("displayName") or item["id"],
                    "enterprise_app",
                    dict(app_id=item.get("appId")),
                ),
            )
            state["apps"].append(item["id"])

    @staticmethod
    def _map_member(stage, parent, item, state, emit, _rel):
        if stage == "app_assignments":
            if item.get("principalType") != "User":
                state["skipped"] += 1  # group -> app has no relationship type in the graph rules
                return
            rid = f"entra-app:{parent}:{item['principalId']}"
            body = _rel(
                rid,
                "SERVICE_ACCOUNT_ACCESS_APPLICATION",
                "entra:" + item["principalId"],
                "entra:" + parent,
                {},
            )
            body["attributes"]["origin"] = "app_assignment"
            emit(rid, body)
            return
        kind = item.get("@odata.type")
        if stage == "group_members":
            if kind == USER:
                rel = "USER_MEMBER_OF_GROUP"
            elif kind == GROUP and item["id"] != parent:
                rel = "GROUP_INHERITS_GROUP"  # member group inherits the containing group's access
            else:
                return  # devices, service principals, contacts, self-membership
        elif kind == USER:
            rel = "USER_HAS_ROLE"
        elif kind == GROUP:
            rel = "GROUP_HAS_ROLE"
        else:
            return
        rid = f"entra-{stage}:{parent}:{item['id']}"
        body = _rel(rid, rel, "entra:" + item["id"], "entra:" + parent, {})
        if stage == "role_members":
            body["attributes"]["origin"] = "directory_role"
        emit(rid, body)
