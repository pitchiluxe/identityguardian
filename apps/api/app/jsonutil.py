import json
from datetime import date, datetime
from uuid import UUID

from psycopg.types.json import Jsonb


def _default(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unserializable {type(value).__name__}")


def dumps(value) -> str:
    return json.dumps(value, default=_default, sort_keys=True)


def jsonb(value) -> Jsonb:
    """Jsonb that stores datetimes as ISO-8601 strings and UUIDs as text."""
    return Jsonb(value, dumps=dumps)
