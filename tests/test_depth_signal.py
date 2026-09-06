"""Whale/depth signal: appearance detection, sampling gaps, sign, gates.

The two tests that matter most:

* `test_a_resting_wall_counts_once` — a whale that sits there for ten minutes
  is one event. At 1s sampling, counting it per snapshot would emit hundreds of
  copies of a single observation and blow through any n-based gate on noise.
* `test_unsampled_gaps_do_not_manufacture_an_appearance` — the live recorder
  samples depth sparsely by design. If "not looked at" reads as "the whale
  left", every resumption of sampling invents a fresh appearance.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.quote.depth_signal import (
    DEFAULT_WHALE_NOTIONAL,
    GATE_MIN_EVENTS,
    GATE_MIN_GAMES,
    BookState,
    WhaleEvent,
    detect_appearances,
    format_report,
    notional_percentiles,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 2, 1, 0, tzinfo=UTC)

BIG = 20_000.0     # unmistakable against a $177 median top-of-book
SMALL = 200.0


def _s(seconds: float, mid: float, bid_notional: float, ask_notional: float, *,
       sampled: bool = True, game: str = "g1", slug: str = "m1",
       spread: float = 0.02) -> BookState:
    return BookState(
        game_id=game,
        market_slug=slug,
        captured_at=T0 + dt.timedelta(seconds=seconds),
        mid=mid,
        spread=spread,
        top_bid_notional=bid_notional,
        top_ask_notional=ask_notional,
        sampled=sampled,
    )


# ------------------------------------------------------------------ #
# Whale identification
# ------------------------------------------------------------------ #


def test_whale_side_uses_notional_not_contracts():
    """10,000 contracts at 2c and 200 at 99c are different objects."""
    assert _s(0, 0.5, BIG, SMALL).whale_side(DEFAULT_WHALE_NOTIONAL) == 1
    assert _s(0, 0.5, SMALL, BIG).whale_side(DEFAULT_WHALE_NOTIONAL) == -1
    assert _s(0, 0.5, SMALL, SMALL).whale_side(DEFAULT_WHALE_NOTIONAL) == 0


def test_whales_on_both_sides_resolve_to_the_larger():
    assert _s(0, 0.5, BIG, BIG * 2).whale_side(DEFAULT_WHALE_NOTIONAL) == -1
    assert _s(0, 0.5, BIG * 2, BIG).whale_side(DEFAULT_WHALE_NOTIONAL) == 1


# ------------------------------------------------------------------ #
# Appearance detection
# ------------------------------------------------------------------ #


def test_appearance_requires_a_transition():
    states = [
        _s(0, 0.50, SMALL, SMALL),
        _s(60, 0.50, BIG, SMALL),      # <- appears here
        _s(120, 0.55, BIG, SMALL),
    ]
    events = detect_appearances({"m1": states}, horizons=(60.0,))
    assert len(events) == 1
    assert events[0].side == 1
    assert events[0].at == T0 + dt.timedelta(seconds=60)


def test_a_resting_wall_counts_once():
    """A whale sitting for ten minutes is one event, not one per snapshot."""
    states = [_s(0, 0.50, SMALL, SMALL)]
    states += [_s(i, 0.50, BIG, SMALL) for i in range(1, 600)]
    events = detect_appearances({"m1": states}, horizons=(60.0,))
    assert len(events) == 1


def test_a_whale_switching_sides_is_a_new_appearance():
    states = [
        _s(0, 0.50, SMALL, SMALL),
        _s(60, 0.50, BIG, SMALL),
        _s(120, 0.50, SMALL, BIG),     # flipped to the offer
    ]
    events = detect_appearances({"m1": states}, horizons=(60.0,))
    assert [e.side for e in events] == [1, -1]


def test_the_first_observation_is_not_an_appearance():
    """We did not see it arrive; it may have been resting for an hour."""
    states = [_s(0, 0.50, BIG, SMALL), _s(60, 0.50, BIG, SMALL)]
    assert detect_appearances({"m1": states}, horizons=(60.0,)) == []


def test_unsampled_gaps_do_not_manufacture_an_appearance():
    """Depth is sampled sparsely by design; a gap is not the whale leaving."""
    states = [
        _s(0, 0.50, SMALL, SMALL),
        _s(60, 0.50, BIG, SMALL),                    # real appearance
        _s(120, 0.50, 0.0, 0.0, sampled=False),      # deep-tier: not looked at
        _s(180, 0.50, 0.0, 0.0, sampled=False),
        _s(240, 0.50, BIG, SMALL),                   # same whale, still there
    ]
    events = detect_appearances({"m1": states}, horizons=(60.0,))
    assert len(events) == 1, "resumed sampling must not invent a second whale"


def test_untradable_rungs_are_excluded():
    states = [
        _s(0, 0.97, SMALL, SMALL, spread=0.02),
        _s(60, 0.97, BIG, SMALL, spread=0.02),
    ]
    assert detect_appearances({"m1": states}, horizons=(60.0,)) == []


# ------------------------------------------------------------------ #
# The sign convention
# ------------------------------------------------------------------ #


def test_signal_is_positive_when_price_moves_toward_the_size():
    bid_whale = WhaleEvent(
        game_id="g1", market_slug="m1", at=T0, side=1,
        notional=BIG, mid=0.50, after={60.0: 0.54},
    )
    assert bid_whale.signal(60.0) == pytest.approx(0.04)

    ask_whale = WhaleEvent(
        game_id="g1", market_slug="m1", at=T0, side=-1,
        notional=BIG, mid=0.50, after={60.0: 0.46},
    )
    assert ask_whale.signal(60.0) == pytest.approx(0.04)


def test_signal_is_negative_when_the_whale_is_run_over():
    event = WhaleEvent(
        game_id="g1", market_slug="m1", at=T0, side=1,
        notional=BIG, mid=0.50, after={60.0: 0.44},
    )
    assert event.signal(60.0) == pytest.approx(-0.06)


def test_unobserved_horizon_is_none_not_zero():
    event = WhaleEvent(
        game_id="g1", market_slug="m1", at=T0, side=1,
        notional=BIG, mid=0.50, after={},
    )
    assert event.signal(60.0) is None


# ------------------------------------------------------------------ #
# Context
# ------------------------------------------------------------------ #


def test_percentiles_skip_unsampled_states():
    """An unsampled book is not a $0 book."""
    states = [
        _s(0, 0.5, 100.0, 50.0),
        _s(1, 0.5, 300.0, 50.0),
        _s(2, 0.5, 0.0, 0.0, sampled=False),
    ]
    pcts = notional_percentiles({"m1": states})
    assert pcts["n"] == 2
    assert pcts["max"] == pytest.approx(300.0)


# ------------------------------------------------------------------ #
# Verdicts
# ------------------------------------------------------------------ #


def _events(n: int, games: int, move: float) -> list[WhaleEvent]:
    return [
        WhaleEvent(
            game_id=f"g{i % games}", market_slug=f"m{i}", at=T0, side=1,
            notional=BIG, mid=0.50,
            after={h: 0.50 + move for h in (30.0, 60.0, 300.0)},
        )
        for i in range(n)
    ]


def test_zero_appearances_reports_no_data_not_a_null():
    report = format_report(
        [], threshold=DEFAULT_WHALE_NOTIONAL, states_examined=1000,
        sampled_states=1000, percentiles={},
    )
    assert "NO DATA" in report
    assert "Not a null result" in report


def test_no_whale_ever_seen_is_called_out_specifically():
    """Never having seen one is different from having seen and tested them."""
    report = format_report(
        [], threshold=DEFAULT_WHALE_NOTIONAL, states_examined=1000,
        sampled_states=1000,
        percentiles={"n": 1000.0, "p50": 177.0, "p90": 400.0, "p99": 900.0,
                     "max": 1200.0},
    )
    assert "No whale has been seen yet" in report


def test_a_real_signal_across_enough_games_reports_pass():
    report = format_report(
        _events(GATE_MIN_EVENTS + 20, GATE_MIN_GAMES + 2, move=0.03),
        threshold=DEFAULT_WHALE_NOTIONAL, states_examined=9000,
        sampled_states=9000, percentiles={},
    )
    assert "PASS —" in report


def test_a_real_but_tiny_signal_is_flagged_as_useless():
    """Real is not the same as useful. A 0.2c signal cannot skew a quote."""
    report = format_report(
        _events(GATE_MIN_EVENTS + 20, GATE_MIN_GAMES + 2, move=0.002),
        threshold=DEFAULT_WHALE_NOTIONAL, states_examined=9000,
        sampled_states=9000, percentiles={},
    )
    assert "PASS —" in report
    assert "Real is not the same as useful" in report


def test_price_moving_away_from_the_size_reports_fail():
    report = format_report(
        _events(GATE_MIN_EVENTS + 20, GATE_MIN_GAMES + 2, move=-0.03),
        threshold=DEFAULT_WHALE_NOTIONAL, states_examined=9000,
        sampled_states=9000, percentiles={},
    )
    assert "FAIL" in report
    assert "does not predict" in report


def test_enough_appearances_but_too_few_games_is_no_data():
    report = format_report(
        _events(GATE_MIN_EVENTS + 100, 3, move=0.03),
        threshold=DEFAULT_WHALE_NOTIONAL, states_examined=9000,
        sampled_states=9000, percentiles={},
    )
    assert "NO DATA" in report
    assert "PASS —" not in report


# --------------------------------------------------------------------------- #
# live_only means mid-stream, not "the venue said live once"
# --------------------------------------------------------------------------- #
#
# 2026-09-06. `live_only: bool = True` was the DEFAULT while the only
# freshness relation lived in the OPTIONAL since/as_of arguments — so the
# population was decided by `is_live` alone, which cannot decide it: when a
# game ends its markets drop off the venue's board and nothing overwrites the
# last row, which says is_live=True forever.
#
# The property below is why this never needs re-opening: the guard cannot bite
# any arm sampled faster than 600s. Measured on prod over the full 29.8M-row
# live population it dropped 0.037% of rows and 13 of 146 games — every one of
# those games recorded at 817-3,000s per market. It is inert on 1s data by
# construction, and that is asserted here rather than asserted in prose.


def _states(gaps_seconds, *, slug="tsc-wnba-guard-1"):
    from core.quote.depth_signal import BookState

    t = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    out, at = [], t
    for g in [0, *gaps_seconds]:
        at = at + dt.timedelta(seconds=g)
        out.append(BookState(game_id="g1", market_slug=slug, captured_at=at,
                             mid=0.5, spread=0.02, top_bid_notional=10.0,
                             top_ask_notional=10.0, sampled=True))
    return out


def test_the_guard_is_inert_on_fast_cadence_data():
    """The load-bearing property. At 1s spacing every row but the final one
    has a successor inside 600s, so a fast-cadence arm is untouched."""
    from core.quote.depth_signal import _mid_stream

    states = _states([1] * 200)
    kept = _mid_stream(states)
    assert len(kept) == len(states) - 1, (
        "only the stream's final row may be dropped at 1s cadence")


def test_a_sweep_cadence_market_is_dropped_entirely():
    """817-3,000s per market is what the 13 removed games actually looked
    like. Every gap exceeds the guard, so nothing survives."""
    from core.quote.depth_signal import _mid_stream

    assert _mid_stream(_states([900] * 20)) == []


def test_the_tail_of_a_stream_goes_and_the_body_stays():
    """A market that recorded fast and then stopped keeps its body and loses
    the rows across the gap — the ones that only look adjacent."""
    from core.quote.depth_signal import _mid_stream

    # offsets 0, 1, 2, 3, 5003, 5004, 5005 — one 5,000s hole in the middle
    states = _states([1, 1, 1, 5000, 1, 1])
    kept = _mid_stream(states)
    # index 3 goes: its successor is across the hole. index 6 goes: no
    # successor at all. Everything else has a neighbour within 600s.
    assert [s.captured_at for s in kept] == [
        states[i].captured_at for i in (0, 1, 2, 4, 5)]


def test_the_threshold_is_the_one_the_engine_already_uses():
    """Not a new constant. A second number here would drift from the engine's
    and nobody would notice which one a population was built with."""
    from core.quote.depth_signal import MID_STREAM_SECONDS
    from core.quote.engine import MAX_OBSERVATION_AGE_SECONDS

    assert MID_STREAM_SECONDS == MAX_OBSERVATION_AGE_SECONDS


def test_live_only_actually_applies_the_guard_to_the_loaded_population():
    """The wiring, not the arithmetic.

    The three tests above call `_mid_stream` directly, so they pass whether or
    not `load_book_states` ever calls it — deleting the call from the loader
    left them all green, which is the absent-variable failure this codebase
    has been bitten by before. This one goes through the loader, so it fails
    if the guard is computed and then not used.

    It is also the first test either quote loader has ever had, which is the
    honest reason a default of `live_only=True` with no freshness relation
    survived this long.
    """
    from sqlalchemy import text

    from core.quote.depth_signal import load_book_states
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    base = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    fast, sweep = "tsc-wnba-guardwire-fast", "tsc-wnba-guardwire-sweep"

    def _wipe(s):
        s.execute(text("DELETE FROM market_snapshots WHERE market_slug IN "
                       "(:a, :b)"), {"a": fast, "b": sweep})
        s.commit()

    with Session() as s:
        _wipe(s)
        rows = ([(fast, base + dt.timedelta(seconds=i)) for i in range(6)]
                + [(sweep, base + dt.timedelta(seconds=900 * i)) for i in range(6)])
        for slug, at in rows:
            s.execute(text("""
                INSERT INTO market_snapshots
                    (market_slug, game_id, captured_at, best_bid, best_ask, is_live)
                VALUES (:m, 'guardwire-game', :t, 0.49, 0.51, true)
            """), {"m": slug, "t": at})
        s.commit()
        try:
            series = load_book_states(s, as_of=None, since=base
                                      - dt.timedelta(days=1), live_only=True)
            assert fast in series, (
                "a market recording at 1s must survive — the guard is meant to "
                "be inert on fast cadence")
            assert len(series[fast]) == 5, "all but the stream's final row"
            assert sweep not in series, (
                "a market recording every 900s has no two rows within 600s; "
                "if it is still here the guard is not wired into the loader")
        finally:
            _wipe(s)
