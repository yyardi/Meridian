"""Cross-venue gap analysis tests.

Almost all the weight is on **matching and frames**. The statistics are two
medians; if they are wrong it is because the wrong two contracts were compared
or one of them was quoted from the wrong end. That failure is invisible — every
number stays in [0, 1] — and it is the V14/V15 family this project keeps
paying for.

The second theme is the gate: it must refuse to emit price statistics below
its pre-registered minimum, and it must not be satisfied by a proxy that never
checks Polymarket's side.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.kalshi.analysis import (
    MIN_MATCHED_GAMES,
    PAIR_TOLERANCE_SECONDS,
    Pair,
    game_medians,
    gap_by_horizon,
    kalshi_team_from_ticker,
    median_abs_gap,
    pm_spread_team_and_invert,
    sign_persistence,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 6, 22, 0, tzinfo=UTC)


def _pair(game="G1", gap=0.0, mt="spread", line=1.5, hours=0.5, lag=0.0) -> Pair:
    return Pair(
        game_key=game, market_type=mt, line=line, team="IND",
        captured_pm=T0, captured_kalshi=T0 + dt.timedelta(seconds=lag),
        pm_mid=0.50 + gap, kalshi_mid=0.50, hours_to_tipoff=hours,
    )


# --------------------------------------------------------------------- #
# Frames — the part that would fail silently
# --------------------------------------------------------------------- #


def test_a_negative_polymarket_spread_pairs_with_the_same_team_directly():
    """`-neg-9.5` from IND is "IND wins by more than 9.5" — Kalshi's wording."""
    team, strike, invert = pm_spread_team_and_invert(
        "asc-wnba-lv-ind-2026-08-06-neg-9pt5", -9.5, "LV", "IND")
    assert (team, strike, invert) == ("LV", 9.5, False)


def test_a_positive_polymarket_spread_pairs_with_the_OPPONENT_and_inverts():
    """`-pos-9.5` from LV is "LV +9.5" = NOT(IND wins by over 9.5).

    Pairing this with LV's own Kalshi contract would compare a team covering
    with the same team winning outright — different events, both in [0, 1].
    """
    team, strike, invert = pm_spread_team_and_invert(
        "asc-wnba-lv-ind-2026-08-06-pos-9pt5", 9.5, "LV", "IND")
    assert (team, strike, invert) == ("IND", 9.5, True)


def test_an_unrecognised_spread_slug_is_refused_rather_than_guessed():
    assert pm_spread_team_and_invert("asc-wnba-lv-ind-2026-08-06", 9.5, "LV", "IND") is None


def test_the_two_spread_directions_are_complements_of_each_other():
    """Both slug directions at one strike must name opposite teams.

    This is the property that makes the DAL/WSH consistency check work: at
    +/-1.5, P(DAL by >1.5) + P(WSH by >1.5) came to 0.96, the missing 4% being
    one-point games.
    """
    neg = pm_spread_team_and_invert("x-neg-1pt5", -1.5, "DAL", "WSH")
    pos = pm_spread_team_and_invert("x-pos-1pt5", 1.5, "DAL", "WSH")
    assert neg[0] != pos[0]
    assert neg[2] is False and pos[2] is True
    assert neg[1] == pos[1] == 1.5


def test_kalshi_team_comes_from_the_ticker_suffix():
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG05DALWSH-DAL") == "DAL"
    assert kalshi_team_from_ticker("KXWNBASPREAD-26AUG06LVIND-IND10") == "IND"


def test_the_two_kalshi_codes_that_differ_from_espn_are_translated():
    """CONN -> CON and PDX -> POR, or every game with them mismatches."""
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG07PHXCONN-CONN") == "CON"
    assert kalshi_team_from_ticker("KXWNBASPREAD-26AUG06TORPDX-PDX2") == "POR"


def test_an_unknown_team_code_yields_none_rather_than_a_wrong_match():
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG05XXXYYY-ZZZ") is None


def test_the_gap_is_polymarket_minus_kalshi_in_one_frame():
    assert _pair(gap=+0.03).gap == pytest.approx(0.03)
    assert _pair(gap=-0.03).gap == pytest.approx(-0.03)


# --------------------------------------------------------------------- #
# Pairing tolerance is pinned by the spec, not chosen
# --------------------------------------------------------------------- #


def test_the_pairing_tolerance_is_the_pre_registered_sixty_seconds():
    assert PAIR_TOLERANCE_SECONDS == 60.0


def test_lag_is_absolute_so_either_venue_may_lead():
    assert _pair(lag=+30).lag_seconds == pytest.approx(30.0)
    assert _pair(lag=-30).lag_seconds == pytest.approx(30.0)


# --------------------------------------------------------------------- #
# Statistics: games are the sample, not rows
# --------------------------------------------------------------------- #


def test_a_game_contributes_one_median_however_many_rows_it_has():
    """One game's 10,000 per-minute rows are one observation, not 10,000."""
    pairs = ([_pair(game="A", gap=0.10)] * 10_000) + [_pair(game="B", gap=0.0)]
    assert game_medians(pairs) == {"A": pytest.approx(0.10), "B": pytest.approx(0.0)}
    # Median of the two game medians, not of 10,001 rows.
    assert median_abs_gap(pairs) == pytest.approx(0.05)


def test_sign_persistence_ignores_games_whose_median_gap_is_zero():
    """The spec asks about pairs "where the gap is nonzero"."""
    pairs = [_pair(game="A", gap=0.0), _pair(game="B", gap=0.0),
             _pair(game="C", gap=0.02)]
    fraction, signed, total = sign_persistence(pairs)
    assert (signed, total) == (1, 3)
    assert fraction == pytest.approx(1.0)


def test_sign_persistence_is_undefined_when_no_game_has_a_sign():
    """Measured 2026-08-07: 0 of 7 games had a nonzero median gap.

    None is the honest answer — there is no sign to persist, which is a
    different statement from "the sign flips".
    """
    fraction, signed, total = sign_persistence([_pair(game=g, gap=0.0)
                                                for g in ("A", "B", "C")])
    assert fraction is None and signed == 0 and total == 3


def test_sign_persistence_is_the_majority_share_not_the_positive_share():
    """A gap that is consistently NEGATIVE persists just as strongly."""
    pairs = [_pair(game=g, gap=-0.02) for g in "ABCD"] + [_pair(game="E", gap=0.02)]
    fraction, signed, _ = sign_persistence(pairs)
    assert signed == 5
    assert fraction == pytest.approx(0.8)


def test_gap_by_horizon_buckets_on_hours_to_tipoff():
    pairs = [_pair(game="A", gap=0.01, hours=0.5),
             _pair(game="A", gap=0.05, hours=8.0)]
    buckets = gap_by_horizon(pairs)
    assert buckets["0-1h"][1] == pytest.approx(0.01)
    assert buckets["6-12h"][1] == pytest.approx(0.05)


def test_a_pair_with_no_tipoff_time_is_left_out_of_the_horizon_table():
    assert gap_by_horizon([_pair(hours=None)]) == {}


# --------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------- #


def test_the_gate_minimum_is_ten_games_and_is_not_lowered():
    assert MIN_MATCHED_GAMES == 10


def test_the_report_emits_no_price_statistics_below_the_gate():
    """The pre-registration's own contract: no partial medians.

    Exercised against a stub session so the test states the contract rather
    than depending on whatever the database holds today.
    """
    import core.kalshi.analysis as A

    class _Stub:
        pass

    original = (A.count_matched_games, A.count_comparable_games,
                A.build_pairs, A.matchability)
    A.count_matched_games = lambda s: 10          # the proxy says go
    A.count_comparable_games = lambda s: 7        # the real gate says wait
    A.build_pairs = lambda s: [_pair(game=f"G{i}", gap=0.05) for i in range(7)]
    A.matchability = lambda s: {}
    try:
        out = A.report(_Stub())
    finally:
        (A.count_matched_games, A.count_comparable_games,
         A.build_pairs, A.matchability) = original

    assert out["gate_met"] is False
    assert out["statistics"] is None
    assert "Gate NOT met" in out["note"]
    # The proxy's disagreement with the gate must be visible, not hidden.
    assert out["discovered_games"] == 10 and out["comparable_games"] == 7


def test_the_report_emits_the_two_statistics_once_the_gate_is_met():
    import core.kalshi.analysis as A

    class _Stub:
        pass

    original = (A.count_matched_games, A.count_comparable_games,
                A.build_pairs, A.matchability)
    A.count_matched_games = lambda s: 12
    A.count_comparable_games = lambda s: 12
    A.build_pairs = lambda s: [_pair(game=f"G{i}", gap=0.05) for i in range(12)]
    A.matchability = lambda s: {}
    try:
        out = A.report(_Stub())
    finally:
        (A.count_matched_games, A.count_comparable_games,
         A.build_pairs, A.matchability) = original

    assert out["gate_met"] is True
    stats = out["statistics"]
    assert stats["median_abs_gap"] == pytest.approx(0.05)
    assert stats["sign_persistence"] == pytest.approx(1.0)
    assert stats["mean_abs_gap_clustered"]["games"] == 12
