"""The board must not disappear when writers run at different cadences.

The bug this pins
-----------------
`/api/board` and `/api/events` selected `captured_at == max(captured_at)`. That
was correct while a single recorder wrote the whole board every cycle: the
newest instant *was* a complete picture.

It stopped being true the moment two writers existed on different cadences. The
live recorder samples only in-progress games every 200ms; the pregame recorder
sweeps the whole board every 15 minutes. So the global maximum timestamp belongs
to one live game and contains nothing else, and an equality test that looks
entirely reasonable silently drops every pregame market. Observed live: a
12-game board rendered as one game with 9 markets.

The failure mode is what makes it worth a test — nothing errors, nothing logs,
the page just quietly shows less than it should.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from core.api import app
from core.storage import MarketSnapshot, get_engine, get_sessionmaker

UTC = dt.timezone.utc

LIVE = "tsc-apitest-live-100pt5"
PREGAME = "tsc-apitest-pregame-200pt5"
OLD = "tsc-apitest-finished-150pt5"


@pytest.fixture
def seeded():
    """One market written now, another 15 minutes ago — the exact shape."""
    Session = get_sessionmaker(get_engine())
    now = dt.datetime.now(UTC)

    def _wipe(s):
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%apitest%"))
        )
        s.commit()

    rows = [
        # Live game: written 0.2s ago by the fast recorder.
        dict(
            captured_at=now - dt.timedelta(seconds=0.2),
            market_slug=LIVE, event_slug="wnba-apitest-live",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("100.5"), best_bid=Decimal("0.50"), best_ask=Decimal("0.52"),
            game_start_time=now - dt.timedelta(hours=1), is_live=True,
        ),
        # Pregame game: written 15 minutes ago by the slow recorder. This is
        # the row the old query dropped.
        dict(
            captured_at=now - dt.timedelta(minutes=15),
            market_slug=PREGAME, event_slug="wnba-apitest-pregame",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("200.5"), best_bid=Decimal("0.48"), best_ask=Decimal("0.51"),
            game_start_time=now + dt.timedelta(hours=3), is_live=False,
        ),
        # An older snapshot of the SAME pregame market — must not win.
        dict(
            captured_at=now - dt.timedelta(hours=2),
            market_slug=PREGAME, event_slug="wnba-apitest-pregame",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("200.5"), best_bid=Decimal("0.10"), best_ask=Decimal("0.90"),
            game_start_time=now + dt.timedelta(hours=3), is_live=False,
        ),
        # A game that finished days ago — off the board entirely.
        dict(
            captured_at=now - dt.timedelta(days=2),
            market_slug=OLD, event_slug="wnba-apitest-finished",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("150.5"), best_bid=Decimal("0.60"), best_ask=Decimal("0.62"),
            game_start_time=now - dt.timedelta(days=2), is_live=False,
        ),
    ]

    with Session() as s:
        _wipe(s)
        for row in rows:
            s.add(MarketSnapshot(**row))
        s.commit()
    yield TestClient(app)
    with Session() as s:
        _wipe(s)


def _markets(client):
    return {
        m["market_slug"]: m
        for m in client.get("/api/board").json()["markets"]
        if "apitest" in m["market_slug"]
    }


# ------------------------------------------------------------------ #
# The regression
# ------------------------------------------------------------------ #


def test_board_returns_markets_written_at_different_times(seeded):
    """One market at T and another at T-15min: the board must return BOTH."""
    found = _markets(seeded)
    assert LIVE in found, "the live market should be present"
    assert PREGAME in found, (
        "the pregame market was written 15 minutes ago and was dropped by the "
        "global-max-timestamp query — this is the bug"
    )


def test_board_picks_the_newest_row_per_market(seeded):
    """Per-market latest, not merely 'some row within a window'."""
    found = _markets(seeded)
    assert found[PREGAME]["bid"] == pytest.approx(0.48), (
        "should be the 15-minute-old row, not the 2-hour-old one"
    )
    assert found[PREGAME]["ask"] == pytest.approx(0.51)


def test_finished_games_fall_off_the_board(seeded):
    """The bound is on game time, so a two-day-old game is gone.

    Deliberately not a bound on `captured_at`: that would make a market vanish
    because its writer is slow rather than because its game is over, which is
    the original bug wearing a different hat.
    """
    assert OLD not in _markets(seeded)


def test_events_lists_every_game_not_just_the_live_one(seeded):
    """The sidebar had the identical defect — a full slate rendered as one game."""
    slugs = {
        e["event_slug"]
        for e in seeded.get("/api/events").json()["events"]
        if "apitest" in e["event_slug"]
    }
    assert "wnba-apitest-live" in slugs
    assert "wnba-apitest-pregame" in slugs
    assert "wnba-apitest-finished" not in slugs


# ------------------------------------------------------------------ #
# Staleness must be visible
# ------------------------------------------------------------------ #


def test_each_row_reports_its_own_age(seeded):
    """A 15-minute-old quote must not be presented as 200ms-fresh."""
    found = _markets(seeded)
    assert found[LIVE]["age_seconds"] < 30
    assert found[PREGAME]["age_seconds"] > 600
    assert found[PREGAME]["age_seconds"] > found[LIVE]["age_seconds"] * 10


def test_events_report_the_staleness_of_their_oldest_market(seeded):
    events = {
        e["event_slug"]: e
        for e in seeded.get("/api/events").json()["events"]
        if "apitest" in e["event_slug"]
    }
    assert events["wnba-apitest-pregame"]["age_seconds"] > 600
    assert events["wnba-apitest-live"]["age_seconds"] < 30


# ------------------------------------------------------------------ #
# "No edge" must say why
# ------------------------------------------------------------------ #


def test_in_play_market_is_labelled_not_left_blank(seeded):
    """The model is pregame-only and correctly refuses to price a live game.

    That is right, but on screen it is indistinguishable from a malfunction, so
    the state is named rather than left as an empty cell.
    """
    found = _markets(seeded)
    assert found[LIVE]["pricing_state"] == "in_play"
    assert found[LIVE]["is_live"] is True


def test_pregame_market_without_a_prediction_is_unpriced_not_in_play(seeded):
    """Two different reasons for a blank edge must not look the same."""
    found = _markets(seeded)
    assert found[PREGAME]["pricing_state"] == "unpriced"


def test_board_is_empty_rather_than_erroring_with_no_data():
    """No snapshots at all must not 500."""
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(
            delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%apitest%"))
        )
        s.commit()
    body = TestClient(app).get("/api/board").json()
    assert "markets" in body


# ------------------------------------------------------------------ #
# Finished games — `is_live` freezes True forever once a game ends
# ------------------------------------------------------------------ #


def test_a_finished_game_is_not_in_play_however_the_flag_reads():
    """Markets leave the venue's board when a game ends, so nothing ever
    overwrites the last row — and it says is_live=True indefinitely.

    Observed: a game 4.7h past tip-off with a 2.7h-old snapshot still rendering
    as LIVE, and the flag frozen per-market so 9 of 18 said live and 9 did not.
    """
    from core.board import FINISHED, IN_PLAY, market_state

    now = dt.datetime.now(UTC)

    def snap(started_hours_ago, age_minutes, is_live, slug="x"):
        return MarketSnapshot(
            market_slug=slug, captured_at=now - dt.timedelta(minutes=age_minutes),
            game_start_time=now - dt.timedelta(hours=started_hours_ago),
            is_live=is_live,
        )

    # The exact observed case: long past tip-off, stale, still flagged live.
    assert market_state(snap(4.7, 162, True), as_of=now) == FINISHED
    # Genuinely in progress: started recently, stream still writing.
    assert market_state(snap(1.0, 0.1, True), as_of=now) == IN_PLAY
    # Started but the stream went quiet — the game ended.
    assert market_state(snap(1.0, 30, True), as_of=now) == FINISHED

    # ★ "PAST ANY PLAUSIBLE GAME LENGTH" IS NOT LEAGUE-FREE, AND THIS TEST USED
    # TO ASSERT IT WAS. Five hours past tip-off with a six-second-old stream was
    # asserted FINISHED on a slug with no league in it, which took the WNBA
    # value (3.5h, and the constant's own comment said so) and applied it to
    # football. ESPN's state field puts a real CFB game at 5.11h, so that case
    # is a long game in progress, not a frozen flag. Both directions are now
    # pinned to a league.
    # Real slug shapes, taken from prod. My first attempt invented
    # "nfl-cfb-osu-mich-..." and `league_of_slug` read it as NFL off the leading
    # token, so the cfb case silently asserted the NFL cap.
    wnba = "aec-wnba-conn-dal-2026-08-02"
    cfb = "asc-cfb-cencon-toledo-2026-09-12-4q-pos-4pt5"
    assert market_state(snap(5.0, 0.1, True, wnba), as_of=now) == FINISHED
    assert market_state(snap(5.0, 0.1, True, cfb), as_of=now) == IN_PLAY
    # and the backstop still exists for football, past anything ESPN has seen
    assert market_state(snap(7.0, 0.1, True, cfb), as_of=now) == FINISHED


def test_a_game_not_yet_started_is_pregame_even_if_flagged_live():
    from core.board import PREGAME, market_state

    now = dt.datetime.now(UTC)
    future = MarketSnapshot(
        market_slug="x", captured_at=now, is_live=True,
        game_start_time=now + dt.timedelta(hours=2),
    )
    assert market_state(future, as_of=now) == PREGAME


def test_finished_games_are_dropped_from_the_board(seeded):
    """Their last quote never updates again, so leaving them in means showing
    hours-old prices — and an edge computed against them — beside live ones."""
    slugs = _markets(seeded)
    # The fixture's "live" market started an hour ago with a 0.2s-old snapshot.
    assert LIVE in slugs
    body = seeded.get("/api/board?include_finished=true").json()
    assert len(body["markets"]) >= len(slugs), "escape hatch still returns them"


def test_shadow_orders_are_hidden_for_market_types_the_executor_refuses(seeded):
    """Rows written before the moneyline was refused are artifacts of a
    superseded policy; showing them implies an order that would never be sent."""
    from core.api import _EXECUTOR_POLICY

    assert not _EXECUTOR_POLICY.is_tradable("basketball_team_full_game_winner")
    for m in seeded.get("/api/board").json()["markets"]:
        if m["type"] == "winner":
            assert m["shadow"] is None


# --------------------------------------------------------------------------- #
# The wall clock is per league because one number was measured on one league.
# --------------------------------------------------------------------------- #
#: league -> longest game ESPN's `state` field actually observed, hours.
#: `espn_cfb_game_state`, `in` -> `post`, the 2026-09-12/13 slate.
#: CFB: 72 games, mean 3.37, p95 4.19, p99 4.64, max 5.11.
#: NFL: 9 games, mean 3.09, max 3.64.
_OBSERVED_MAX_HOURS = {"cfb": 5.11, "nfl": 3.64}


def test_every_cap_clears_the_longest_game_its_league_has_played():
    """★ THE REGRESSION THIS EXISTS TO CATCH. The cap was a single 3.5, and its
    own comment named the population: "a WNBA game is 40 minutes of clock and
    roughly two hours of wall time". Applied to college football, 3.5h is barely
    the MEAN, and 18 of 72 measured games exceeded it -- costing 491 live-minutes
    in one weekend, a mean of 27 per affected game, and it is the last 27
    minutes.

    Pinned to the measurement rather than to the values, so tightening a cap
    below a game its league has actually played fails here."""
    from core.board import _WALL_HOURS

    for league, observed in _OBSERVED_MAX_HOURS.items():
        cap = _WALL_HOURS[league]
        assert cap > observed, (
            f"{league} cap {cap}h is below the longest game ESPN observed "
            f"({observed}h) -- games would read FINISHED while still in play")


def test_the_caps_are_not_all_the_same_number():
    """A per-league map whose values are identical is the single constant again
    wearing a dict. WNBA (~2h wall) and CFB (max 5.11h) must differ."""
    from core.board import _WALL_HOURS

    assert _WALL_HOURS["cfb"] > _WALL_HOURS["wnba"]
    assert len(set(_WALL_HOURS.values())) > 1


def test_an_unknown_league_gets_the_generous_default_not_the_wnba_value():
    """An unrecognised slug must not inherit the tightest cap. The backstop that
    matters is stream staleness; being generous here costs little, being tight
    costs the end of games."""
    from core.board import DEFAULT_WALL_HOURS, _WALL_HOURS, wall_hours_for

    assert wall_hours_for("no-league-in-this-slug") == DEFAULT_WALL_HOURS
    assert wall_hours_for(None) == DEFAULT_WALL_HOURS
    assert DEFAULT_WALL_HOURS >= max(_OBSERVED_MAX_HOURS.values())
    assert DEFAULT_WALL_HOURS > _WALL_HOURS["wnba"]


def test_stream_staleness_still_ends_a_game_inside_every_cap():
    """The caps got looser, so this is the check that they did not become the
    only thing standing between a stale quote and the board. A quiet stream must
    finish a game well before any cap, in the league with the loosest one."""
    from core.board import FINISHED, _WALL_HOURS, market_state

    now = dt.datetime.now(UTC)
    loosest = max(_WALL_HOURS, key=lambda k: _WALL_HOURS[k])
    slug = {"cricket": "aec-county-x-y-2026-09-13",
            "cfb": "asc-cfb-cencon-toledo-2026-09-12-2h-27pt5",
            "mlb": "aec-mlb-nyy-bos-2026-09-13"}.get(loosest, "x")
    quiet = MarketSnapshot(
        market_slug=slug, captured_at=now - dt.timedelta(minutes=20),
        game_start_time=now - dt.timedelta(hours=1), is_live=True,
    )
    assert market_state(quiet, as_of=now) == FINISHED
