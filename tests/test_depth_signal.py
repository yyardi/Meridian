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
