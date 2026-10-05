# Reuse the API fixtures (tenants, sessions, twin environment).
from tests.api.conftest import client, shared_db, tenant, twin  # noqa: F401
