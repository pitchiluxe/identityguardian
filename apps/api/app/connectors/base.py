"""Connector contract (INTEGRATIONS.md).

discover capabilities -> read entities/relationships page by page with a cursor -> return
provenance and coverage -> (optionally) validate/apply an exact approved operation -> read back.
Pages are canonical objects (`node`/`relationship`) ready for ingestion; providers translate their
own shapes. A connector never decides to delete: absence is reconciled only by the ingestion
pipeline after a complete authoritative read.
"""

import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlparse


class ConnectorUnavailable(Exception):
    """Transient: the read may be retried later from the same cursor."""


class RateLimited(ConnectorUnavailable):
    pass


class UnsupportedOperation(Exception):
    pass


@dataclass
class Page:
    objects: list  # canonical objects: dict(object_id, object_type, body, deleted, version)
    next_cursor: str | None  # None when the read is complete
    provenance: dict = field(default_factory=dict)


@dataclass
class Capabilities:
    read: list
    write: list
    permission_semantics: str
    native_ttl: bool
    idempotent_writes: bool
    reversible: str
    authoritative_scope: str
    page_size: int

    def as_dict(self):
        return dict(self.__dict__)


class Connector:
    source: str

    def capabilities(self) -> Capabilities:  # pragma: no cover - interface
        raise NotImplementedError

    def read(self, cursor: str | None) -> Page:  # pragma: no cover - interface
        raise NotImplementedError

    def apply(self, operation: dict):
        raise UnsupportedOperation(
            f"{self.source} is read-only; writes need a separately approved adapter"
        )

    def read_back(self, operation: dict):
        raise UnsupportedOperation(f"{self.source} does not support read-back of writes")


def validate_endpoint(url: str, allowlist: list[str]):
    """Outbound endpoints are server configuration: https only, allowlisted host, never private."""
    parsed = urlparse(url)
    if parsed.scheme == "mock":
        return
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Connector endpoints must use https")
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
        ):
            raise ValueError(
                "Connector endpoints cannot target private, loopback or link-local addresses"
            )
    except ValueError as exc:
        if "Connector endpoints" in str(exc):
            raise
    if host not in allowlist:
        raise ValueError(f"Host {host} is not in the connector allowlist")
