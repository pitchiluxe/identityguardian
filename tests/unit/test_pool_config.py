"""The API keeps warm connections: on Windows a new PostgreSQL backend can take >10 s under load,
so a pool that drains to zero turns the first request after idle time into a 503."""

from apps.api.app.config import Settings
from apps.api.app.db import Database
from apps.api.app.main import create_app


def test_api_pool_keeps_warm_connections():
    app = create_app(Settings(database_url="postgresql://unused@127.0.0.1:1/x"))
    assert app.state.db.min_size == 2  # pool is created lazily; no connection is made here


def test_other_pools_stay_lazy_and_bounded():
    assert Database("postgresql://unused@127.0.0.1:1/x").min_size == 0
    assert Database("postgresql://unused@127.0.0.1:1/x", max_size=1, min_size=2).min_size == 1
