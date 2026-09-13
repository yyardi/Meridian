"""Assert a row EXISTS afterwards — the instrument none of us had.

On 2026-09-06 the CFB recorder wrote nothing for 53 minutes while every check
we owned stayed green. Four instruments, four different reasons for missing it:

  D's parse tests    exercise `parse_plays` / `parse_game_state` as pure
                     functions on a fixture. They never touch the write path,
                     so they pass through a total write failure.
  a1's --probe       parses and prints. Never writes.
  my cycle contract  judges the numbers a recorder REPORTS. It cannot tell you
                     the report was true.
  heartbeats         the cycle completed every 20s and returned cleanly.

The gap is not the alarm. An alarm detects the NEXT occurrence; a write-path
test prevents it. **No test asserted that a row existed after a write**, and
that is the cheapest of the four and the only one that would have failed.

WHAT THIS FILE IS
-----------------
`assert_wrote` is the assertion: count, act, count again, and require the
delta. `SwallowingWriter` is the adversary — it identifies work, raises inside
the insert, catches its own exception one frame up, logs a warning and returns
cleanly, which is exactly what ran tonight.

The proof that matters is `test_a_parse_only_suite_passes_against_the_adversary`:
a naive suite goes GREEN against the swallowing writer, and the round-trip
assertion goes RED. If that ever stops being true, this file has lost the
thing it was built to demonstrate.

HOW IT IS MEANT TO BE RUN. There is no CI here, so a test nobody runs is a
comment. This runs in the ordinary suite against the per-run ephemeral
postgres the conftest already provides — no prod, no fixtures of its own, no
network. `python -m pytest tests/test_write_round_trip.py`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.storage import get_engine, get_sessionmaker

SLUG = "tsc-roundtrip-probe"


@pytest.fixture
def session():
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                  {"m": SLUG})
        s.commit()
        yield s
        s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                  {"m": SLUG})
        s.commit()


def _count(session) -> int:
    return session.execute(
        text("SELECT count(*) FROM market_snapshots WHERE market_slug = :m"),
        {"m": SLUG}).scalar_one()


def assert_wrote(session, action, *, at_least: int = 1) -> int:
    """Run `action`, then require the table to have grown.

    THE POINT: the return value of `action` is never consulted. A writer that
    returns 5 having written nothing passes every check built on its own
    report and fails this one."""
    before = _count(session)
    action()
    after = _count(session)
    grew = after - before
    assert grew >= at_least, (
        f"expected at least {at_least} new row(s), got {grew} "
        f"({before} -> {after}). The writer may have reported success while "
        "writing nothing — see the 2026-09-06 CFB outage.")
    return grew


# ------------------------------------------------------------------ #
# Writers: one honest, one that is exactly tonight's failure
# ------------------------------------------------------------------ #


def _row(session, i: int) -> None:
    session.execute(text("""
        INSERT INTO market_snapshots
            (market_slug, game_id, captured_at, best_bid, best_ask, is_live)
        VALUES (:m, 'rt-game', now() - make_interval(secs => :i), 0.49, 0.51, true)
    """), {"m": SLUG, "i": i})


class HonestWriter:
    """Identifies work, writes it, commits, reports what it built."""

    def __init__(self, session, n=2): self._s, self._n = session, n

    def cycle(self) -> dict:
        for i in range(self._n):
            _row(self._s, i)
        self._s.commit()
        return {"work": self._n, "attempted": self._n, "errors": 0}


class SwallowingWriter:
    """★ TONIGHT'S FAILURE. Identifies work, the INSERT raises before it
    reaches the database, the caller catches it, logs a warning, returns
    cleanly. Container Up, heartbeat green, nothing written."""

    def __init__(self, session, n=2): self._s, self._n = session, n
    warnings: list[str]

    def cycle(self) -> dict:
        self.warnings = []
        written = 0
        for i in range(self._n):
            try:
                # 'Unconsumed column names: league' was raised here, by
                # SQLAlchemy, before the statement reached postgres.
                raise TypeError("Unconsumed column names: league")
            except Exception as exc:          # noqa: BLE001 — the defect itself
                self.warnings.append(str(exc))
                continue
        self._s.rollback()
        return {"work": self._n, "attempted": written, "errors": len(self.warnings)}


# ------------------------------------------------------------------ #
# The assertion works in both directions
# ------------------------------------------------------------------ #


def test_an_honest_writer_leaves_rows_behind(session):
    grew = assert_wrote(session, HonestWriter(session, n=2).cycle, at_least=2)
    assert grew == 2


def test_the_swallowing_writer_is_caught(session):
    """The whole point. It returns cleanly, logs only warnings, and writes
    nothing — and only a count-afterwards sees it."""
    w = SwallowingWriter(session, n=2)
    with pytest.raises(AssertionError, match="reported success while"):
        assert_wrote(session, w.cycle)
    assert w.warnings == ["Unconsumed column names: league"] * 2


def test_a_parse_only_suite_passes_against_the_adversary(session):
    """★ THE INDICTMENT, and it is the reason this file exists.

    A suite that exercises parsing and inspects the writer's own return value
    — which is what we all shipped — is GREEN against a writer that wrote
    nothing. Both assertions below pass. Neither means anything."""
    w = SwallowingWriter(session, n=2)
    report = w.cycle()

    # "the parser produced rows" — true, and irrelevant
    assert report["work"] == 2
    # "the cycle completed and reported its counters" — true, and irrelevant
    assert report["attempted"] == 0 and report["errors"] == 2

    # and the table is empty
    assert _count(session) == 0, (
        "a parse-only suite is green here; only a row count is not")


def test_a_writer_that_lies_about_its_count_is_caught(session):
    """The stronger case: a writer that reports rows it did not write. Every
    instrument built on the writer's own report believes it."""

    class Liar(SwallowingWriter):
        def cycle(self):
            super().cycle()
            return {"work": 2, "attempted": 2, "errors": 0}   # a clean lie

    liar = Liar(session, n=2)
    assert liar.cycle() == {"work": 2, "attempted": 2, "errors": 0}
    with pytest.raises(AssertionError):
        assert_wrote(session, liar.cycle)
