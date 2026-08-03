"""Live odds recorder: change detection, live-provider quarantine, cadence.

The load-bearing test is `test_in_progress_odds_are_quarantined_as_live`. ESPN
does not publish a live line today (measured: the scoreboard's odds block is
empty in-game and `pickcenter` is a frozen pregame number), but if one ever
appears it must be excluded from every backtest and CLV calculation the moment
it lands — not the moment someone notices. The naming convention is what
enforces that, and `_is_live_provider` is what reads it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from core.backtest.engine import _is_live_provider
from core.feeds.live_odds_recorder import (
    LiveOddsRecorder,
    game_state,
    odds_fingerprint,
    provider_name,
)
from core.storage import SportsbookOdds, get_engine, get_sessionmaker

UTC = dt.timezone.utc


def _odds(spread=-1.5, ou=186.5, provider="DraftKings"):
    return {
        "provider": {"name": provider},
        "spread": spread,
        "overUnder": ou,
        "details": f"POR {spread}",
        "homeTeamOdds": {"moneyLine": -120},
        "awayTeamOdds": {"moneyLine": 100},
    }


def _board(state="pre", odds=None, game_id="401857108", start=None):
    return {
        "events": [
            {
                "id": game_id,
                "date": start or "2026-08-02T23:00:00Z",
                "competitions": [
                    {
                        "id": game_id,
                        "status": {"type": {"state": state}},
                        "odds": [] if odds is None else odds,
                    }
                ],
            }
        ]
    }


class FakeESPN:
    def __init__(self, boards):
        #: list of payloads returned in order; the last repeats.
        self.boards = boards
        self.calls = 0

    def get_scoreboard(self, date_yyyymmdd: str):
        payload = self.boards[min(self.calls, len(self.boards) - 1)]
        self.calls += 1
        return payload


@pytest.fixture
def clean_db():
    Session = get_sessionmaker(get_engine())

    def _wipe(s):
        s.execute(delete(SportsbookOdds).where(SportsbookOdds.espn_game_id == "999999"))
        s.commit()

    with Session() as s:
        _wipe(s)
    yield Session
    with Session() as s:
        _wipe(s)


# ------------------------------------------------------------------ #
# Live quarantine — the correctness rule
# ------------------------------------------------------------------ #


def test_in_progress_odds_are_quarantined_as_live():
    """An in-game line must be excluded from backtests by its own name."""
    assert provider_name("DraftKings", "in") == "DraftKings (live)"
    assert _is_live_provider(provider_name("DraftKings", "in"))


def test_pregame_odds_keep_their_plain_name():
    """Pregame lines are the CLV benchmark and must stay usable."""
    for state in ("pre", "post", None):
        name = provider_name("DraftKings", state)
        assert name == "DraftKings"
        assert not _is_live_provider(name)


def test_live_suffix_is_not_applied_twice():
    assert provider_name("DraftKings (live)", "in") == "DraftKings (live)"


def test_game_state_reads_the_scoreboard_status():
    board = _board(state="in")
    assert game_state(board["events"][0]["competitions"][0]) == "in"
    assert game_state({}) is None


# ------------------------------------------------------------------ #
# Change detection
# ------------------------------------------------------------------ #


def test_only_changes_are_written(clean_db):
    """Identical lines must not accumulate thousands of duplicate rows."""
    Session = clean_db
    client = FakeESPN([_board(odds=[_odds()], game_id="999999")])
    rec = LiveOddsRecorder(client=client, sessionmaker=Session)

    at = dt.datetime.now(UTC)
    first = rec.poll_once(captured_at=at)
    second = rec.poll_once(captured_at=at + dt.timedelta(seconds=15))

    assert first.rows_written == 1
    assert second.rows_written == 0, "an unchanged line is not a new observation"
    assert second.unchanged == 1


def test_a_moved_line_is_written(clean_db):
    """The whole point: catching the book repricing."""
    Session = clean_db
    client = FakeESPN([
        _board(odds=[_odds(ou=186.5)], game_id="999999"),
        _board(odds=[_odds(ou=188.5)], game_id="999999"),
    ])
    rec = LiveOddsRecorder(client=client, sessionmaker=Session)

    at = dt.datetime.now(UTC)
    rec.poll_once(captured_at=at)
    moved = rec.poll_once(captured_at=at + dt.timedelta(seconds=15))

    assert moved.rows_written == 1

    with Session() as s:
        totals = sorted(
            float(r) for r in s.scalars(
                select(SportsbookOdds.over_under).where(
                    SportsbookOdds.espn_game_id == "999999"
                )
            ).all()
        )
    assert totals == [186.5, 188.5]


def test_heartbeat_rewrites_a_still_line(clean_db):
    """'No rows for six hours' must not be ambiguous between a still market
    and a dead recorder — the same reason InjuryPoll exists."""
    Session = clean_db
    client = FakeESPN([_board(odds=[_odds()], game_id="999999")])
    rec = LiveOddsRecorder(client=client, sessionmaker=Session, heartbeat_seconds=0.0)

    at = dt.datetime.now(UTC)
    rec.poll_once(captured_at=at)
    beat = rec.poll_once(captured_at=at + dt.timedelta(seconds=15))
    assert beat.rows_written == 1, "heartbeat must re-record an unchanged line"


def test_fingerprint_covers_every_price_field():
    base = {"spread": -1.5, "over_under": 186.5, "over_odds": -110,
            "under_odds": -110, "home_moneyline": -120, "away_moneyline": 100}
    for field in base:
        moved = dict(base)
        moved[field] = 999
        assert odds_fingerprint(moved) != odds_fingerprint(base), field


# ------------------------------------------------------------------ #
# Reality: ESPN publishes nothing in-game
# ------------------------------------------------------------------ #


def test_an_in_progress_game_with_no_odds_writes_nothing(clean_db):
    """Measured behaviour: the scoreboard's odds block is empty mid-game.

    The recorder must treat that as "nothing to record", not as an error and
    not by falling back to a frozen pickcenter number.
    """
    Session = clean_db
    client = FakeESPN([_board(state="in", odds=None, game_id="999999")])
    stats = LiveOddsRecorder(client=client, sessionmaker=Session).poll_once()

    assert stats.in_progress == 1
    assert stats.with_odds == 0
    assert stats.rows_written == 0
    assert stats.errors == 0


def test_odds_appearing_mid_game_would_be_captured_and_quarantined(clean_db):
    """If ESPN ever starts publishing a live line, we get it — safely."""
    Session = clean_db
    client = FakeESPN([_board(state="in", odds=[_odds()], game_id="999999")])
    stats = LiveOddsRecorder(client=client, sessionmaker=Session).poll_once()

    assert stats.rows_written == 1
    with Session() as s:
        name = s.scalar(
            select(SportsbookOdds.provider_name).where(
                SportsbookOdds.espn_game_id == "999999"
            )
        )
    assert name == "DraftKings (live)"
    assert _is_live_provider(name)


def test_is_closing_line_is_never_set(clean_db):
    """The scoreboard nests current prices under keys named 'close'. Trusting
    that name would corrupt the CLV benchmark, which is the headline metric."""
    Session = clean_db
    client = FakeESPN([_board(odds=[_odds()], game_id="999999")])
    LiveOddsRecorder(client=client, sessionmaker=Session).poll_once()

    with Session() as s:
        row = s.scalar(
            select(SportsbookOdds).where(SportsbookOdds.espn_game_id == "999999")
        )
    assert row.is_closing_line is False
    assert row.close_total is None


# ------------------------------------------------------------------ #
# Cadence and robustness
# ------------------------------------------------------------------ #


def test_cadence_is_fast_for_a_live_slate_and_slow_when_idle():
    rec = LiveOddsRecorder(client=FakeESPN([{}]), sessionmaker=object)

    assert rec.next_interval(_board(state="in")) == rec.interval_seconds

    soon = (dt.datetime.now(UTC) + dt.timedelta(hours=1)).isoformat()
    assert rec.next_interval(_board(state="pre", start=soon)) == rec.interval_seconds

    far = (dt.datetime.now(UTC) + dt.timedelta(days=4)).isoformat()
    assert rec.next_interval(_board(state="pre", start=far)) > rec.interval_seconds


def test_scoreboard_failure_does_not_raise(clean_db):
    class Dead:
        def get_scoreboard(self, date_yyyymmdd):
            raise RuntimeError("espn down")

    stats = LiveOddsRecorder(client=Dead(), sessionmaker=clean_db).poll_once()
    assert stats.errors == 1
    assert stats.rows_written == 0  # and no exception escaped


def test_malformed_event_does_not_lose_the_rest_of_the_slate(clean_db):
    Session = clean_db
    board = {
        "events": [
            "not-a-dict",
            {"id": "999999", "date": "2026-08-02T23:00:00Z",
             "competitions": [{"id": "999999",
                               "status": {"type": {"state": "pre"}},
                               "odds": [_odds()]}]},
        ]
    }
    stats = LiveOddsRecorder(
        client=FakeESPN([board]), sessionmaker=Session
    ).poll_once()
    assert stats.rows_written == 1
