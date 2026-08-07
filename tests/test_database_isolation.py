"""The suite's database can never be the mirror or production — asserted.

This is the structural half of the B6 lesson: `tests/conftest.py` gives every
pytest run its own `meridian_test_<pid>` database, and these tests pin the
properties that make the isolation real rather than customary. If any of
them fails, the suite has regained the ability to write into a database that
something else reads, and every green run after that is untrustworthy.
"""

from __future__ import annotations

import os

# Constants restated rather than imported: `tests/` is not a package, and
# importing conftest as a module re-executes it (which is how this file once
# created the test database twice). The mirror URL is stable; the test URL is
# whatever conftest exported to the environment.
MIRROR_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


def test_suite_url_is_never_the_mirror():
    """The analysis mirror is untouchable by pytest by construction."""
    from core.storage import get_database_url

    url = get_database_url()
    assert url.rstrip("/") != MIRROR_URL
    assert not url.rstrip("/").endswith("/meridian"), (
        "the suite's URL points at a database named 'meridian' — that is the "
        "mirror, and pytest must never hold a URL that can reach it"
    )


def test_suite_url_is_never_the_dotenv_database():
    """.env's DATABASE_URL is production (Supabase) or the operator's choice;
    the suite's URL must differ from it regardless of what it is."""
    from dotenv import dotenv_values

    from core.storage import get_database_url

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_url = (dotenv_values(os.path.join(root, ".env")).get("DATABASE_URL") or "").strip()
    if not dotenv_url:
        return                       # nothing configured, nothing to collide with
    assert get_database_url().rstrip("/") != dotenv_url.rstrip("/")


def test_suite_database_is_local_and_test_named():
    from core.storage import get_database_url

    url = get_database_url()
    assert "localhost" in url or "127.0.0.1" in url
    assert "supabase" not in url
    # The per-run name, unless deliberately overridden — and an override still
    # may not be the mirror (asserted above, which runs unconditionally).
    if "MERIDIAN_TEST_DATABASE_URL" not in os.environ:
        assert url.rsplit("/", 1)[-1].startswith("meridian_test_")


def test_the_local_heartbeat_read_is_repointed_too():
    """/api/status's live-recorder check reads MERIDIAN_LOCAL_DATABASE_URL
    (defaulting to the mirror). If conftest forgot to repoint it, heartbeat
    tests would seed one database while the code under test reads another —
    the shared-state bug in a different coat."""
    from core.storage import get_database_url

    assert os.environ.get("MERIDIAN_LOCAL_DATABASE_URL") == get_database_url()

    import core.api as api

    assert api._LOCAL_HEARTBEAT_URL == get_database_url()


def test_the_mirror_fixture_cannot_write(mirror):
    """The mirror fixture is Postgres-enforced read-only: the handful of
    integration tests that look at real history may not become writers by
    accident, whatever their code does."""
    import pytest as _pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError, InternalError, OperationalError, ProgrammingError

    with mirror() as s:
        with _pytest.raises((DBAPIError, InternalError, OperationalError, ProgrammingError)):
            s.execute(text(
                "insert into service_heartbeats (service, interval_seconds) "
                "values ('isolation-proof', 1)"))
            s.commit()


def test_schema_is_at_alembic_head():
    """The suite runs on exactly what the migrations produce. Model/migration
    drift fails here, before it fails confusingly in some other test."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from core.storage import get_engine

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = ScriptDirectory.from_config(Config(os.path.join(root, "alembic.ini")))
    heads = set(script.get_heads())
    with get_engine().connect() as c:
        current = {r[0] for r in c.execute(text("select version_num from alembic_version"))}
    assert current == heads, f"test database at {current}, migrations head {heads}"
