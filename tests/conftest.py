"""Test configuration.

Pins the whole suite to a DEDICATED, per-run test database — never the
analysis mirror, never Supabase.

Why a dedicated database (2026-08-07, the B6 lesson made structural)
--------------------------------------------------------------------
The suite used to run against `localhost:5433/meridian` — the analysis
mirror, which the live recorder writes to and other pytest runs share. That
produced three distinct failure classes, all observed:

1. a fixture teardown once deleted real rows (B6);
2. tests asserting on freshness/staleness went red whenever the real
   recorder wrote (the flaky `test_api_status` pair);
3. two suites running concurrently deadlocked on each other's fixture
   cleanup (`DELETE ... WHERE market_slug LIKE '%test%'`), and four failures
   eventually reproduced even on a quiet mirror — intra-suite state
   pollution.

The fix is structural, not disciplinary: every pytest run creates its own
`meridian_test_<pid>` database in the same local Postgres container, migrates
it to head with Alembic, runs against it, and drops it on the way out.
Nothing else ever connects to it; pytest can no longer reach the mirror at
all, because the URL it is given does not point there — and a test asserts
that it never can (`tests/test_database_isolation.py`).

Two reasons the database stays local, unchanged from before:

1. **Safety.** These tests insert and delete rows.
2. **Speed.** Against a remote database, round-trip latency dominated:
   186 seconds versus 3 locally.

Override deliberately with ``MERIDIAN_TEST_DATABASE_URL`` if you ever need to
run against something else — the create/migrate/drop lifecycle is skipped for
overrides whose database name does not start with ``meridian_test``, and the
production guard still applies.
"""

from __future__ import annotations

import os

#: The local Docker Postgres from docker-compose.yml — server half only. The
#: analysis mirror lives at /meridian on this server; the suite must never
#: open a connection to it.
LOCAL_PG = "postgresql+psycopg://meridian:meridian@localhost:5433"
MIRROR_URL = f"{LOCAL_PG}/meridian"

#: Per-run database name: concurrent suites get disjoint databases, which is
#: the whole point — the collision case was two pytest runs sharing one.
TEST_DB_NAME = f"meridian_test_{os.getpid()}"
TEST_URL = os.environ.get("MERIDIAN_TEST_DATABASE_URL", f"{LOCAL_PG}/{TEST_DB_NAME}")

# Must happen before anything imports core.storage, which reads the env at
# module import time. MERIDIAN_LOCAL_DATABASE_URL is repointed too: the
# status endpoint's live-recorder heartbeat check reads it (defaulting to the
# mirror), and a suite that seeds heartbeats in one database while the code
# under test reads another is the shared-state bug all over again.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["MERIDIAN_LOCAL_DATABASE_URL"] = TEST_URL

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

# The EV guard's background loop pushes to a REAL ntfy topic (it lives in
# .env for the alerter) on EDGE-GONE transitions, and TestClient fires
# startup events — a test seeding a losing position would ping the user's
# phone. Off for the suite; guard tests drive check_once() with a fake pusher.
os.environ["MERIDIAN_EV_GUARD"] = "0"

# The fill watcher starts on FastAPI startup when ordering is enabled, and
# TestClient fires startup events. A test that sets MERIDIAN_ORDER_TOKEN on a
# machine whose shell carries real venue credentials would otherwise start a
# real background poller against the real venue. Off for the whole suite;
# watcher tests drive `poll_once()` directly with injected fake clients.
os.environ["MERIDIAN_FILL_WATCHER"] = "0"

import pytest  # noqa: E402


def _manages_lifecycle() -> bool:
    """True when this run owns its database (create/migrate/drop).

    A deliberate MERIDIAN_TEST_DATABASE_URL override pointing anywhere else is
    the caller's responsibility — we neither create nor drop what we did not
    name ourselves.
    """
    return TEST_URL.rsplit("/", 1)[-1].startswith("meridian_test")


def pytest_report_header(config) -> str:
    from core.storage import get_database_url

    url = get_database_url()
    host = url.split("@")[-1] if "@" in url else url
    return f"meridian: tests pinned to {host} (dedicated per-run database)"


def _create_and_migrate() -> None:
    """Create this run's database and migrate it to head.

    Runs at conftest IMPORT time, not in a fixture: several test modules open
    a connection during collection (e.g. test_retention probes partitioning
    support to decide skips), which happens before any session fixture fires.

    Stale `meridian_test_*` databases from crashed runs are swept first — but
    only the ones with no active connections, so a concurrently running
    suite's database survives (plain DROP refuses busy databases; FORCE is
    reserved for our own teardown).
    """
    from sqlalchemy import create_engine, text

    admin = create_engine(MIRROR_URL, isolation_level="AUTOCOMMIT",
                          pool_size=1, max_overflow=0)

    def _owner_is_alive(name: str) -> bool:
        """The database name carries its creator's pid — the honest liveness
        test. "Has no connections" is NOT one: a concurrent suite's database
        has no connections during its collection phase, and the first version
        of this sweep dropped a live suite's database out from under it."""
        try:
            pid = int(name.rsplit("_", 1)[-1])
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError):
            return False
        except PermissionError:
            return True                   # exists, owned by someone else

    with admin.connect() as c:
        stale = [
            name for (name,) in c.execute(text(
                "select datname from pg_database "
                "where datname like 'meridian_test_%'"))
        ]
        for name in stale:
            if _owner_is_alive(name):
                continue
            try:
                c.execute(text(f'drop database "{name}"'))
            except Exception:
                pass
        c.execute(text(f'create database "{TEST_DB_NAME}"'))
    admin.dispose()

    # Alembic against the new database: env.py reads DATABASE_URL, which this
    # module already pointed at it. The suite runs on the same schema the
    # migrations produce — drift between models and migrations fails here,
    # before any test does.
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(root, "alembic.ini")), "head")


# Idempotence guard, via the environment rather than a module global:
# `tests/` is not a package, so this file can be executed TWICE in one
# process (once as pytest's special conftest module, once more if anything
# does `import conftest`/`from tests import conftest`). A module global would
# be per-module-object and reset on the second execution; the process
# environment is shared across both.
if _manages_lifecycle() and os.environ.get("_MERIDIAN_TEST_DB_CREATED") != TEST_URL:
    _create_and_migrate()
    os.environ["_MERIDIAN_TEST_DB_CREATED"] = TEST_URL


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Session handle for teardown; creation already ran at import."""
    yield
    if not _manages_lifecycle():
        return
    # Drop our own database WITH FORCE: our own pooled connections are the
    # only ones there, and they do not deserve a graceful goodbye.
    from sqlalchemy import create_engine, text
    try:
        from core.storage.base import get_engine
        get_engine().dispose()
    except Exception:
        pass
    admin = create_engine(MIRROR_URL, isolation_level="AUTOCOMMIT",
                          pool_size=1, max_overflow=0)
    with admin.connect() as c:
        try:
            c.execute(text(f'drop database "{TEST_DB_NAME}" with (force)'))
        except Exception:
            pass
    admin.dispose()


@pytest.fixture(scope="session")
def mirror():
    """READ-ONLY sessionmaker for the analysis mirror's real historical data.

    A handful of tests are integration checks against reality — season game
    counts, known-game joins, the 2026 scoring-regime shift — and reality
    lives in the mirror, not in a fresh test database. They may LOOK at it.
    They may not touch it, and that is enforced by Postgres, not by care:
    every connection opens with `default_transaction_read_only=on`, so any
    write raises `ReadOnlySqlTransaction` no matter what the test does.
    `tests/test_database_isolation.py` proves the enforcement.

    Skips (does not fail) when the mirror is unreachable or empty — an
    integration test without its subject has not run, which is different from
    failing.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        MIRROR_URL, pool_size=1, max_overflow=1,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as c:
            n = c.execute(text("select count(*) from team_game_logs")).scalar()
    except Exception as exc:
        pytest.skip(f"analysis mirror unreachable: {str(exc)[:120]}")
    if not n:
        pytest.skip("analysis mirror has no historical data to check against")
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def guard_against_production(test_database):
    """Fail loudly rather than mutate a remote database — or the mirror.

    Depends on `test_database` so the ordering is explicit: the database
    exists before anything checks it or touches it.
    """
    from core.storage import get_database_url

    url = get_database_url()
    if "supabase" in url or ("localhost" not in url and "127.0.0.1" not in url):
        pytest.exit(
            "Refusing to run the test suite against a non-local database "
            f"({url.split('@')[-1]}). These tests write and delete rows. "
            "Set MERIDIAN_TEST_DATABASE_URL if this is intentional.",
            returncode=1,
        )
    if url.rstrip("/") == MIRROR_URL:
        pytest.exit(
            "Refusing to run the test suite against the analysis mirror "
            "(localhost:5433/meridian). The suite gets its own per-run "
            "database; something bypassed conftest's URL pinning.",
            returncode=1,
        )
    yield
