"""The transforms that decide whether a row is right, and the leak that would fake skill."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.gridiron.features import (build, clock_seconds, regulation_left,
                                    scrimmage_plays)


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
        # a REAL moneyline slug: `build` pins the market, and a placeholder
        # slug would make the emptiness assertions below pass for the wrong
        # reason — filtered out rather than correctly rejected.
        "game_id": [16450.0], "is_live": ["t"],
        "market_slug": ["aec-cfb-wsu-uw-2026-09-05-uw"],
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


# --------------------------------------------------------------------- #
# `down == 0` is not a down. It is also not NULL, which is the whole problem:
# the rows survive every dropna and enter the matrix as a valid-looking state.
#
# The real rows (63 of them, in 22 games) are Timeouts, Penalties, 2pt
# conversions and an End Period — NOT an end-of-game all-zero sentinel. They
# carry a possession team, a non-zero yards_to_goal and usually a non-zero
# distance, so the neighbouring rule "all three zero and no pos_team" matches
# none of them and would pass while filtering nothing.
# --------------------------------------------------------------------- #


def _play(**kw):
    row = dict(down=1, distance=10, yards_to_goal=75, pos_team="8",
               play_type="Rush", game_id=1)
    row.update(kw)
    return row


def test_down_zero_rows_are_dropped():
    df = pd.DataFrame([_play(down=d) for d in (1, 2, 3, 4, 0)])
    out = scrimmage_plays(df)
    assert len(out) == 4
    assert set(out.down) == {1, 2, 3, 4}


def test_the_all_zero_description_would_not_have_caught_these():
    """Each row is a REAL shape from the export: down 0, everything else valid."""
    real = pd.DataFrame([
        _play(down=0, distance=3, yards_to_goal=3, play_type="Timeout"),
        _play(down=0, distance=65, yards_to_goal=65, play_type="Penalty"),
        _play(down=0, distance=0, yards_to_goal=8, play_type="Two Point Pass"),
        _play(down=0, distance=35, yards_to_goal=35, play_type="End Period"),
    ])
    # the rule that does NOT work, stated so its failure is visible
    narrow = real[~((real.down == 0) & (real.distance == 0)
                    & (real.yards_to_goal == 0) & (real.pos_team.isna()))]
    assert len(narrow) == 4, "the all-zero rule filters nothing on real rows"
    assert scrimmage_plays(real).empty


def test_a_null_down_is_not_silently_kept_as_a_zero():
    df = pd.DataFrame([_play(down=1), _play(down=None), _play(down=0)])
    out = scrimmage_plays(df)
    assert len(out) == 2                       # NaN passes here...
    assert out.down.isna().sum() == 1          # ...and dies at the dropna
    assert (out.down == 0).sum() == 0


def test_plays_without_a_down_column_pass_through():
    df = pd.DataFrame({"game_id": [1, 2], "period": [1, 2]})
    assert len(scrimmage_plays(df)) == 2


# --------------------------------------------------------------------- #
# A CFB game quotes ~106 markets at once. merge_asof does not care which one
# it hands you — it hands you the most RECENT. Unfiltered, `mid` is a mixture
# of moneyline, spread and total, full-game and per-quarter, every value a
# plausible probability and none of them null.
# --------------------------------------------------------------------- #


def _tape():
    t0 = pd.Timestamp("2026-09-06 20:40:00+00:00")
    state = pd.DataFrame([{
        "game_id": 1, "state": "in", "period": 2, "display_clock": "5:00",
        "home_score": 10, "away_score": 0, "home_timeouts_used": 1,
        "away_timeouts_used": 0, "first_seen_at": t0 + pd.Timedelta(seconds=10),
    }])
    # the moneyline quoted FIRST, a 3rd-quarter spread quoted LAST
    prices = pd.DataFrame([
        {"market_slug": "aec-cfb-a-b-2026-09-06-a", "captured_at": t0,
         "best_bid": 0.90, "best_ask": 0.92, "is_live": "t", "game_id": 7},
        {"market_slug": "asc-cfb-a-b-2026-09-06-3q-pos-7pt5",
         "captured_at": t0 + pd.Timedelta(seconds=5),
         "best_bid": 0.40, "best_ask": 0.42, "is_live": "t", "game_id": 7},
    ])
    gmap = pd.DataFrame([{"espn_game_id": 1, "venue_game_id": 7,
                          "match_confidence": 1.0}])
    return state, prices, gmap


def test_the_mid_comes_from_the_pinned_market_not_the_latest_tick():
    state, prices, gmap = _tape()
    out = build(state, prices, gmap)
    assert len(out) == 1
    assert out.market_slug.iloc[0].startswith("aec")
    assert out.mid.iloc[0] == pytest.approx(0.91)   # NOT 0.41, the newer tick


def test_unpinned_build_takes_the_wrong_market_which_is_why_it_is_pinned():
    state, prices, gmap = _tape()
    out = build(state, prices, gmap, market_prefix="")
    assert out.mid.iloc[0] == pytest.approx(0.41)   # the 3q spread wins on time


def test_a_game_with_no_quote_in_the_pinned_market_drops_rather_than_substitutes():
    state, prices, gmap = _tape()
    out = build(state, prices[prices.market_slug.str.startswith("asc")], gmap)
    assert out.empty
