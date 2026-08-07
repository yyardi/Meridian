"""Test configuration.

Pins the whole suite to the LOCAL database, always.

Two reasons, both learned the hard way once ``DATABASE_URL`` was repointed at
Supabase:

1. **Safety.** These tests insert and delete rows. Running them against the
   live database is writing to production. The fixtures only touch
   deliberately fake keys (season 1998/1999, slugs containing "test"), so no
   real data was harmed — but that is a property of the fixtures, not a
   guarantee of the setup, and it should not be relied on.

2. **Speed.** The suite issues thousands of small queries. Against a remote
   database, round-trip latency dominated: 186 seconds versus 3 locally, plus
   pooler connection-limit contention that produced spurious failures.

Override deliberately with ``MERIDIAN_TEST_DATABASE_URL`` if you ever need to
run against something else.
"""

from __future__ import annotations

import os

#: Local Docker Postgres from docker-compose.yml.
LOCAL_TEST_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

# Must happen before anything imports core.storage, which reads the env at
# module import time.
os.environ["DATABASE_URL"] = os.environ.get("MERIDIAN_TEST_DATABASE_URL", LOCAL_TEST_URL)

# The suite must be structurally unable to reach the venue. Several tests
# submit through /api/orders and assert they get the 503 that missing
# credentials produce — which was an assumption about the developer's shell,
# not a property of the suite, and on a shell that exports real credentials
# those tests were sending REAL signed POSTs to api.polymarket.us. Strip the
# credentials before anything imports; tests that need credentials construct
# them explicitly. Set to empty rather than popped: `core.storage.base` runs
# `load_dotenv()` at import, which would re-inject a popped key from `.env`
# but never overrides one that exists — and `from_env` treats empty as unset.
os.environ["POLYMARKET_KEY_ID"] = ""
os.environ["POLYMARKET_SECRET_KEY"] = ""
# Same reasoning for the order token: with it set (it lives in .env for the
# api container), /api/status judges the fill watcher's heartbeat and every
# status test fails healthy on a host not running the watcher. Tests that
# exercise the order path set it explicitly with monkeypatch.
os.environ["MERIDIAN_ORDER_TOKEN"] = ""

# The fill watcher starts on FastAPI startup when ordering is enabled, and
# TestClient fires startup events. A test that sets MERIDIAN_ORDER_TOKEN on a
# machine whose shell carries real venue credentials would otherwise start a
# real background poller against the real venue. Off for the whole suite;
# watcher tests drive `poll_once()` directly with injected fake clients.
os.environ["MERIDIAN_FILL_WATCHER"] = "0"

import pytest  # noqa: E402


def pytest_report_header(config) -> str:
    from core.storage import get_database_url

    url = get_database_url()
    host = url.split("@")[-1] if "@" in url else url
    return f"meridian: tests pinned to {host}"


@pytest.fixture(scope="session", autouse=True)
def guard_against_production():
    """Fail loudly rather than mutate a remote database."""
    from core.storage import get_database_url

    url = get_database_url()
    if "supabase" in url or ("localhost" not in url and "127.0.0.1" not in url):
        pytest.exit(
            "Refusing to run the test suite against a non-local database "
            f"({url.split('@')[-1]}). These tests write and delete rows. "
            "Set MERIDIAN_TEST_DATABASE_URL if this is intentional.",
            returncode=1,
        )
    yield
