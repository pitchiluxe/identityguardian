from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, url):
        self.url = url

    @contextmanager
    def transaction(self, organization_id=None):
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5) as conn:
            if organization_id:
                conn.execute("SELECT set_config('app.org', %s, true)", (str(organization_id),))
            yield conn
