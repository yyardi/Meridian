"""Win-curve and hypothesis-16 tests.

Nearly all the weight is on **side conventions**. The V14/V15/V16 family of
bugs all had the same shape: every individual number was correct and the frame
they were quoted in was wrong, so nothing looked broken. A flipped side here
turns "the trailing team is underpriced" into its exact negation while every
probability stays inside [0, 1].

The rest pins the things that would let a small sample read as a result.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.win_curve import (
    BOUNDARIES,
    GATE_MIN_GAMES,
    REGULATION_MINUTES,
    BoundaryQuote,
    Cell,
    GameState,
    anchored_probability,
    bucket_of,
    build_cells,
    compare,
    curve_probability,
    empirical_probability,
    fit_sigma,
    pregame_margin_from_price,
    wilson,
)

UTC = dt.timezone.utc


def _quote(first: int, second: int, mid: float, *, boundary: str = "half",
           minutes_left: float = 20.0, slug: str = "wnba-aaa-bbb-2026-08-06"
           ) -> BoundaryQuote:
    return BoundaryQuote(
        event_slug=slug, boundary=boundary, minutes_left=minutes_left,
        first_points=first, second_points=second,
        mid_window=mid, mid_last=mid, spread=0.01, n_ticks=10,
    )


# --------------------------------------------------------------------- #
# Side conventions — the ones that invert the hypothesis
# --------------------------------------------------------------------- #


def test_when_the_first_team_trails_the_market_price_is_the_mid_itself():
    """YES = the first team wins, so a trailing first team IS the mid.

    Verified against 12 of 12 settled games; see the module docstring.
    """
    q = _quote(first=40, second=48, mid=0.20)
    assert q.first_is_trailing is True
    assert q.market_p_trailing() == pytest.approx(0.20)


def test_when_the_second_team_trails_the_market_price_is_one_minus_the_mid():
    q = _quote(first=48, second=40, mid=0.80)
    assert q.first_is_trailing is False
    assert q.market_p_trailing() == pytest.approx(0.20)


def test_the_two_side_branches_agree_on_the_same_underlying_book():
    """A book at 0.20/0.80 describes one game from two ends.

    Whichever team trails, the trailing team's implied probability must be the
    cheap side. If these two ever disagree, one branch is inverted.
    """
    trailing_is_first = _quote(first=40, second=48, mid=0.2)
    trailing_is_second = _quote(first=48, second=40, mid=0.8)
    assert trailing_is_first.market_p_trailing() == pytest.approx(
        trailing_is_second.market_p_trailing())
    assert trailing_is_first.market_p_trailing() < 0.5


def test_trailing_margin_is_negative_whichever_side_trails():
    assert _quote(first=40, second=48, mid=0.2).trailing_margin == -8
    assert _quote(first=48, second=40, mid=0.8).trailing_margin == -8


def test_the_anchored_check_uses_the_trailing_teams_own_pregame_price():
    """Anchoring must follow the same side flip as the market price.

    A heavy pregame underdog trailing slightly should come out near the price,
    not near the league base rate. Anchoring the wrong side would put the
    favourite's prior on the underdog and produce a large fake edge — which is
    precisely the artifact this check exists to expose.
    """
    sigma = 2.6
    # First team is a 0.10 pregame underdog and trails by 1 at the half.
    p_first = anchored_probability(-1, 20.0, sigma, 0.10)
    assert p_first < 0.25, "a 10% underdog down 1 is not a coin flip"
    # Mirror: second team is the 0.10 underdog (first team's price is 0.90).
    p_first_fav = anchored_probability(+1, 20.0, sigma, 0.90)
    assert (1.0 - p_first_fav) < 0.25


# --------------------------------------------------------------------- #
# The curve
# --------------------------------------------------------------------- #


def test_a_tied_game_is_a_coin_flip():
    assert curve_probability(0, 20.0, 2.6) == pytest.approx(0.5)


def test_leading_beats_trailing_by_the_same_margin():
    up = curve_probability(+5, 20.0, 2.6)
    down = curve_probability(-5, 20.0, 2.6)
    assert up > 0.5 > down
    assert up + down == pytest.approx(1.0)


def test_the_same_lead_is_worth_more_with_less_time_left():
    """5 points up at end Q3 is safer than 5 points up at end Q1."""
    early = curve_probability(5, 30.0, 2.6)
    late = curve_probability(5, 10.0, 2.6)
    assert late > early


def test_no_time_left_is_a_step_function_not_a_division_by_zero():
    assert curve_probability(3, 0.0, 2.6) == 1.0
    assert curve_probability(-3, 0.0, 2.6) == 0.0
    assert curve_probability(0, 0.0, 2.6) == 0.5


def test_pregame_price_inverts_to_a_margin_and_back():
    sigma = 2.6
    e = pregame_margin_from_price(0.75, sigma)
    assert e > 0
    # Feeding that margin back at full time must recover the price.
    assert curve_probability(e, REGULATION_MINUTES, sigma) == pytest.approx(0.75)


def test_an_extreme_price_does_not_imply_an_infinite_margin():
    """A 1c quote must not become a 40-point favourite via Phi^-1(0)."""
    assert abs(pregame_margin_from_price(0.0, 2.6)) < 100
    assert abs(pregame_margin_from_price(1.0, 2.6)) < 100


def test_anchoring_decays_the_pregame_edge_as_the_game_runs_out():
    """With no score change, a favourite's edge shrinks as time is used up."""
    sigma = 2.6
    early = anchored_probability(0, 30.0, sigma, 0.80)
    late = anchored_probability(0, 5.0, sigma, 0.80)
    assert 0.5 < late < early < 0.80


# --------------------------------------------------------------------- #
# Buckets, cells, Wilson
# --------------------------------------------------------------------- #


def test_buckets_cover_the_pre_registered_ranges():
    assert bucket_of(1) == bucket_of(3) == "1-3"
    assert bucket_of(4) == bucket_of(6) == "4-6"
    assert bucket_of(7) == bucket_of(9) == "7-9"
    assert bucket_of(10) == bucket_of(40) == "10+"


def test_a_tie_has_no_bucket_rather_than_falling_into_the_first_one():
    assert bucket_of(0) is None


def test_buckets_are_symmetric_in_sign():
    assert bucket_of(-5) == bucket_of(5)


def test_wilson_stays_inside_zero_and_one_at_the_extremes():
    p, lo, hi = wilson(0, 10)
    assert p == 0.0 and lo >= 0.0
    p, lo, hi = wilson(10, 10)
    assert p == 1.0 and hi <= 1.0


def test_lead_and_trail_cells_are_the_same_games_from_opposite_ends():
    """Both sides of every game are emitted, so the two cells must sum to 1."""
    states = [
        GameState(espn_game_id="g1", team="AAA", opponent="BBB", is_home=True,
                  boundary="half", minutes_left=20.0, margin=+5, won=True),
        GameState(espn_game_id="g1", team="BBB", opponent="AAA", is_home=False,
                  boundary="half", minutes_left=20.0, margin=-5, won=False),
        GameState(espn_game_id="g2", team="CCC", opponent="DDD", is_home=True,
                  boundary="half", minutes_left=20.0, margin=+5, won=False),
        GameState(espn_game_id="g2", team="DDD", opponent="CCC", is_home=False,
                  boundary="half", minutes_left=20.0, margin=-5, won=True),
    ]
    cells = build_cells(states)
    lead = cells[("half", "4-6", False)]
    trail = cells[("half", "4-6", True)]
    assert lead.n == trail.n == 2
    assert lead.rate + trail.rate == pytest.approx(1.0)


# --------------------------------------------------------------------- #
# Sigma fit
# --------------------------------------------------------------------- #


def test_sigma_is_recovered_from_data_generated_by_a_known_sigma():
    """Generate states from sigma=3.0 and check the fit finds it."""
    from scipy import stats as _st

    true_sigma = 3.0
    states: list[GameState] = []
    gid = 0
    for minutes_left in (30.0, 20.0, 10.0):
        for margin in range(-12, 13):
            if margin == 0:
                continue
            p = float(_st.norm.cdf(margin / (true_sigma * (minutes_left ** 0.5))))
            n = 400
            wins = round(p * n)
            for i in range(n):
                gid += 1
                states.append(GameState(
                    espn_game_id=f"g{gid}", team="AAA", opponent="BBB",
                    is_home=True, boundary="x", minutes_left=minutes_left,
                    margin=margin, won=i < wins))
    fit = fit_sigma(states)
    assert fit is not None
    assert fit.sigma == pytest.approx(true_sigma, rel=0.05)


def test_sigma_fit_returns_none_rather_than_guessing_on_thin_data():
    assert fit_sigma([]) is None


# --------------------------------------------------------------------- #
# The comparison and its scope
# --------------------------------------------------------------------- #


def _cells_with(boundary: str, bucket: str, trailing_rate: float) -> dict:
    n = 200
    return {
        (boundary, bucket, True): Cell(boundary=boundary, bucket=bucket,
                                       trailing=True, n=n,
                                       wins=round(trailing_rate * n)),
    }


def test_only_trailing_by_one_to_nine_enters_the_sample():
    """The hypothesis is about tight games; 10+ is out by pre-registration."""
    cells = {
        **_cells_with("half", "1-3", 0.42),
        **_cells_with("half", "10+", 0.10),
    }
    tight = compare([_quote(40, 42, 0.30)], cells=cells)
    blowout = compare([_quote(40, 55, 0.10)], cells=cells)
    assert len(tight) == 1
    assert blowout == []


def test_a_tied_boundary_produces_no_observation():
    cells = _cells_with("half", "1-3", 0.42)
    assert compare([_quote(40, 40, 0.50)], cells=cells) == []


def test_edge_is_historical_minus_market_for_the_trailing_team():
    cells = _cells_with("half", "1-3", 0.42)
    # First team trails by 2, market prices it at 0.30.
    out = compare([_quote(40, 42, 0.30)], cells=cells)
    assert out[0].historical_p == pytest.approx(0.42)
    assert out[0].market_p == pytest.approx(0.30)
    assert out[0].edge == pytest.approx(0.12)


def test_edge_sign_survives_the_side_flip():
    """Same book, same margin, opposite side named first -> same edge."""
    cells = _cells_with("half", "1-3", 0.42)
    a = compare([_quote(40, 42, 0.30)], cells=cells)[0]
    b = compare([_quote(42, 40, 0.70)], cells=cells)[0]
    assert a.edge == pytest.approx(b.edge)


def test_compare_refuses_both_or_neither_estimator():
    cells = _cells_with("half", "1-3", 0.42)
    with pytest.raises(ValueError):
        compare([_quote(40, 42, 0.3)], cells=cells, sigma=2.6)
    with pytest.raises(ValueError):
        compare([_quote(40, 42, 0.3)])


def test_a_state_with_no_historical_cell_is_dropped_not_defaulted():
    """An unpopulated cell must not silently become 0.5."""
    assert empirical_probability({}, "half", -2) is None
    assert compare([_quote(40, 42, 0.30)], cells={}) == []


# --------------------------------------------------------------------- #
# The report refuses a verdict it has not earned
# --------------------------------------------------------------------- #


def test_boundaries_are_the_three_instants_with_a_known_clock():
    """No game clock exists in the data, so only period ends are usable."""
    assert [m for _, _, m in BOUNDARIES] == [30.0, 20.0, 10.0]
    assert sum(1 for _ in BOUNDARIES) == 3


def test_few_games_reports_no_data_rather_than_a_verdict():
    from core.pulse.win_curve import Study, format_report

    cells = _cells_with("half", "1-3", 0.42)
    quotes = [_quote(40, 42, 0.10, slug=f"wnba-g{i}-2026-08-06") for i in range(3)]
    comparisons = compare(quotes, cells=cells)
    study = Study(states=[], cells=cells, sigma=None, quotes=quotes, skips={},
                  comparisons=comparisons, comparisons_last_tick=comparisons,
                  comparisons_fitted=[], comparisons_anchored=[], deviations=[])
    report = format_report(study)
    verdict = report.split("VERDICT")[-1]
    assert "NO DATA" in verdict
    assert "PASS" not in verdict
    assert f"{GATE_MIN_GAMES - 3} more games" in verdict
