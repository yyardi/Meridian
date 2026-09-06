"""The transforms that decide whether a row is right, and the leak that would fake skill."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.gridiron.features import build, clock_seconds, regulation_left


@pytest.mark.parametrize("s, want", [("5:04", 304), ("14:56", 896), ("0:00", 0)])
def test_clock_parses(s, want):
    assert clock_seconds(s) == want


@pytest.mark.parametrize("bad", [None, "", "junk", float("nan"), 12])
def test_unparseable_clock_is_nan_not_a_guess(bad):
    assert np.isnan(clock_seconds(bad))


@pytest.mark.parametrize("period, clock, want", [
    (1, 896, 3596), (2, 304, 2104), (4, 900, 900), (4, 0, 0),
])
def test_regulation_left(period, clock, want):
    assert regulation_left(period, clock) == want


@pytest.mark.parametrize("period", [5, 6, 7])
def test_overtime_is_pinned_to_zero_never_negative(period):
    """College OT is untimed. (4-5)*900 would manufacture -900s of 'remaining'."""
    assert regulation_left(period, 0.0) == 0.0


def _frames(price_time, state_time):
    state = pd.DataFrame({
        "game_id": [401], "state": ["in"], "period": [2.0],
        "display_clock": ["5:04"], "home_score": [14], "away_score": [7],
        "home_timeouts_used": [1], "away_timeouts_used": [2],
        "first_seen_at": [pd.Timestamp(state_time, tz="UTC")],
    })
    prices = pd.DataFrame({
        "game_id": [16450.0], "market_slug": ["m"], "is_live": ["t"],
        "best_bid": [0.40], "best_ask": [0.44],
        "captured_at": [pd.Timestamp(price_time, tz="UTC")],
    })
    gmap = pd.DataFrame({"espn_game_id": [401], "venue_game_id": [16450],
                         "match_confidence": [0.95]})
    return state, prices, gmap


def test_a_price_from_the_future_is_never_joined():
    """The leak that manufactures skill: a mid that moved AFTER the state was
    observed already contains part of the answer."""
    X = build(*_frames("2026-09-05T22:10:00", "2026-09-05T22:09:00"))
    assert X.empty, "a later price was joined to an earlier state row"


def test_a_recent_earlier_price_is_joined_with_its_raw_legs():
    X = build(*_frames("2026-09-05T22:09:50", "2026-09-05T22:10:00"))
    assert len(X) == 1
    row = X.iloc[0]
    assert row["mid"] == pytest.approx(0.42)
    # money scoring needs the payable price per side, which a mid cannot give
    assert row.best_bid == pytest.approx(0.40) and row.best_ask == pytest.approx(0.44)
    assert row.score_diff == 7 and row.reg_left == 2104


def test_a_stale_price_is_dropped_rather_than_carried():
    X = build(*_frames("2026-09-05T21:00:00", "2026-09-05T22:10:00"), tolerance_s=30)
    assert X.empty, "an hour-old mid is a memory of a market, not a feature"


def test_confidence_floor_excludes_the_game():
    X = build(*_frames("2026-09-05T22:09:50", "2026-09-05T22:10:00"), min_confidence=0.99)
    assert X.empty


# --------------------------------------------------------------------- #
# The spread anchor must be FULL-GAME only.
#
# Only 4,553 of 8,088 `asc-` markets are full-game; 1h/2h/1q/2q/3q/4q share the
# prefix. Mixing a first-quarter line into a game-level feature produces no
# error and no null — a wrong number in a right-shaped column. The moneyline
# anchor is 132/132 full-game, so it was safe BY CONSTRUCTION rather than by
# care, and construction-safety is invisible when it holds and when it breaks.
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("slug, is_full", [
    ("asc-cfb-abchr-txtech-2026-09-05-pos-22pt5", True),
    ("asc-cfb-abchr-txtech-2026-09-05-neg-7", True),
    ("asc-cfb-abchr-txtech-2026-09-05-1h-pos-22pt5", False),
    ("asc-cfb-abchr-txtech-2026-09-05-2h-pos-22pt5", False),
    ("asc-cfb-abchr-txtech-2026-09-05-1q-pos-22pt5", False),
    ("asc-cfb-abchr-txtech-2026-09-05-4q-neg-3pt5", False),
])
def test_quarter_and_half_spreads_are_excluded(slug, is_full):
    from core.gridiron.fit import FULL_GAME_SPREAD
    assert bool(FULL_GAME_SPREAD.match(slug)) is is_full, slug


def test_the_line_sign_and_fraction_are_recovered():
    from core.gridiron.fit import FULL_GAME_SPREAD
    m = FULL_GAME_SPREAD.match("asc-cfb-a-b-2026-09-05-neg-13pt5")
    assert m.group(3) == "neg" and m.group(4) == "13" and m.group(5) == "5"
    m = FULL_GAME_SPREAD.match("asc-cfb-a-b-2026-09-05-pos-7")
    assert m.group(3) == "pos" and m.group(4) == "7" and m.group(5) is None
