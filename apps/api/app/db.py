import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _reset(conn):
    # Tenant context is transaction-local already; RESET ALL is a second guard so nothing set on a
    # session can follow a pooled connection to the next request.
    conn.execute("RESET ALL")
    conn.commit()  # leave the connection idle so the pool keeps it


class Database:
    """Pooled connections. Each `transaction()` is one database transaction whose tenant scope
    (`app.org`) is set with `set_config(..., true)` and therefore ends with the transaction."""

    def __init__(self, url, max_size=8):
        self.url, self.max_size = url, max_size
        self._pool = None
        self._lock = threading.Lock()

    @property
    def pool(self):
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    self._pool = ConnectionPool(
                        self.url,
                        min_size=0,
                        max_size=self.max_size,
                        max_idle=60,
                        timeout=15,
                        kwargs=dict(row_factory=dict_row, connect_timeout=10),
                        reset=_reset,
                        open=True,
                        name="identityguardian",
                    )
        return self._pool

    @contextmanager
    def transaction(self, organization_id=None):
        # The pool commits on success and rolls back on error, like a direct connection context.
        with self.pool.connection() as conn:
            if organization_id:
                conn.execute("SELECT set_config('app.org', %s, true)", (str(organization_id),))
            yield conn

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool = None
