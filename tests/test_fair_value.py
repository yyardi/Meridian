"""Fair-value model and ladder curve fit."""

from __future__ import annotations

import datetime as dt

import pytest
from scipy.stats import norm

from strategies.wnba_totals.config import WNBATotalsConfig
from strategies.wnba_totals.model.curve_fit import (
    LadderRung,
    check_monotonic,
    clean_rungs,
    fit_from_rungs,
    fit_ladder,
)
from strategies.wnba_totals.model.fair_value import (
    MARGIN_SIGMA_RATIO,
    MARKET_SPREAD,
    MARKET_TOTAL,
    MARKET_WINNER,
    MODEL_VERSION,
    predict_market,
    prob_over,
    project,
)
from strategies.wnba_totals.model.features import MatchupFeatures, TeamFeatures

UTC = dt.timezone.utc
AS_OF = dt.datetime(2026, 7, 1, tzinfo=UTC)


def _team(tid="T", off=85.0, deff=80.0, residual=0.0, ok=True, n=20) -> TeamFeatures:
    return TeamFeatures(
        team_id=tid, as_of=AS_OF, games_played=n,
        offense_ppg=off, defense_ppg_allowed=deff,
        offense_ppg_home=off, offense_ppg_away=off,
        defense_ppg_allowed_home=deff, defense_ppg_allowed_away=deff,
        offense_ppg_recent=off, defense_ppg_allowed_recent=deff,
        record_residual=residual, sufficient_data=ok,
    )


def _matchup(home=None, away=None, playoff=False) -> MatchupFeatures:
    return MatchupFeatures(
        home=home or _team("HOME"), away=away or _team("AWAY"),
        as_of=AS_OF, is_playoff_game=playoff,
    )


# ------------------------------------------------------------------ #
# Projection
# ------------------------------------------------------------------ #

def test_projection_matches_hand_computation():
    """NOTE: no league context on the matchup -> legacy halved fallback."""
    home = _team("HOME", off=90.0, deff=80.0)
    away = _team("AWAY", off=84.0, deff=76.0)
    p = project(_matchup(home, away))

    # home = (90 + 76)/2 = 83 ; away = (84 + 80)/2 = 82
    assert p.projected_home == pytest.approx(83.0)
    assert p.projected_away == pytest.approx(82.0)
    assert p.projected_total == pytest.approx(165.0)
    assert p.baseline_margin == pytest.approx(1.0)


def test_strength_mode_adds_deviations_instead_of_halving():
    """The v3 default. off_A + def_B - league_mean per side.

    The original halved form shrank every matchup deviation by half —
    measured scale slope 1.53 against a correct 1.0.
    """
    m = MatchupFeatures(
        home=_team("HOME", off=90.0, deff=80.0),
        away=_team("AWAY", off=84.0, deff=76.0),
        as_of=AS_OF, league_points_per_team=82.0,
    )
    p = project(m)   # default config: totals_projection="strength"
    assert p.projected_home == pytest.approx(90 + 76 - 82)   # 84
    assert p.projected_away == pytest.approx(84 + 80 - 82)   # 82
    assert p.projected_total == pytest.approx(166.0)
    # Margin doubles relative to the halved form (2.0 vs 1.0).
    assert p.baseline_margin == pytest.approx(2.0)


def test_strength_reduces_to_league_total_for_average_teams():
    """Two exactly-average teams must project exactly the league total."""
    m = MatchupFeatures(
        home=_team("HOME", off=82.0, deff=82.0),
        away=_team("AWAY", off=82.0, deff=82.0),
        as_of=AS_OF, league_points_per_team=82.0,
    )
    assert project(m).projected_total == pytest.approx(164.0)


def test_missing_league_context_falls_back_to_halved():
    """league_points_per_team=0 means unknown -> legacy behaviour, not garbage."""
    m = _matchup(home=_team("HOME", off=90.0, deff=80.0),
                 away=_team("AWAY", off=84.0, deff=76.0))
    p = project(m)
    assert p.projected_home == pytest.approx(83.0)   # (90+76)/2


def test_projection_is_deterministic():
    m = _matchup()
    assert project(m) == project(m)


def test_prob_over_is_half_at_the_projection():
    assert prob_over(165.0, 165.0, 17.3) == pytest.approx(0.5)


def test_prob_over_decreases_as_line_rises():
    ps = [prob_over(165.0, line, 17.3) for line in (155, 160, 165, 170, 175)]
    assert all(a > b for a, b in zip(ps, ps[1:]))


# ------------------------------------------------------------------ #
# Record modifier — the load-bearing rules
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("residual", [-0.20, -0.05, 0.0, 0.05, 0.20])
def test_totals_are_never_moved_by_the_record_modifier(residual):
    """Clutch execution cannot move a game's COMBINED score."""
    cfg = WNBATotalsConfig(record_beta=5.0)  # deliberately large
    base = project(_matchup(), config=cfg).projected_total
    moved = project(
        _matchup(home=_team("HOME", residual=residual)), config=cfg
    ).projected_total
    assert moved == pytest.approx(base), "record modifier leaked into totals"


def test_record_modifier_moves_the_margin():
    cfg = WNBATotalsConfig(record_beta=10.0)
    neutral = project(_matchup(), config=cfg)
    clutch = project(_matchup(home=_team("HOME", residual=0.05)), config=cfg)
    assert clutch.projected_margin > neutral.projected_margin
    assert clutch.record_adjustment == pytest.approx(10.0 * 0.05)


def test_beta_zero_is_an_exact_no_op():
    """Default config must reproduce the PPG-only baseline exactly."""
    cfg = WNBATotalsConfig(record_beta=0.0)
    p = project(_matchup(home=_team("HOME", residual=0.13)), config=cfg)
    assert p.record_adjustment == 0.0
    assert p.projected_margin == p.baseline_margin


def test_default_config_ships_with_beta_zero():
    """The feature must not contribute until the backtest earns it."""
    assert WNBATotalsConfig().record_beta == 0.0


def test_playoff_downweights_the_modifier_and_flags_confidence():
    cfg = WNBATotalsConfig(record_beta=10.0, playoff_record_weight=0.25)
    home = _team("HOME", residual=0.05)
    reg = project(_matchup(home=home, playoff=False), config=cfg)
    post = project(_matchup(home=home, playoff=True), config=cfg)

    assert abs(post.record_adjustment) < abs(reg.record_adjustment)
    assert post.record_adjustment == pytest.approx(reg.record_adjustment * 0.25)
    assert post.reduced_confidence is True
    assert "playoff" in (post.confidence_notes or "")
    assert reg.reduced_confidence is False


# ------------------------------------------------------------------ #
# Refusal and metadata
# ------------------------------------------------------------------ #

def test_refuses_to_predict_on_thin_data():
    """Emitting a confident number from 2 games is worse than emitting none."""
    thin = _matchup(home=_team("HOME", ok=False, n=2))
    out = predict_market(
        features=thin, projection=project(thin),
        market_slug="x", sports_market_type=MARKET_TOTAL, line=165.0,
    )
    assert out is None


def test_prediction_carries_version_and_config_hash():
    m = _matchup()
    out = predict_market(
        features=m, projection=project(m),
        market_slug="tsc-x-165pt5", sports_market_type=MARKET_TOTAL, line=165.5,
        market_bid=0.50, market_ask=0.52,
    )
    assert out is not None
    # v4: the live path now applies the winner's-curse shrinkage the backtest
    # always did. Pinned to a literal deliberately — a silent version drift
    # would let two model generations share a grouping key in the log.
    assert out.model_version == MODEL_VERSION == "v4"
    assert len(out.config_hash) == 64          # sha256 hex
    assert out.model_config_snapshot["record_beta"] == 0.0
    assert out.features["home"]["team_id"] == "HOME"


def test_edge_is_model_minus_market_mid():
    m = _matchup()
    out = predict_market(
        features=m, projection=project(m),
        market_slug="x", sports_market_type=MARKET_TOTAL, line=165.0,
        market_bid=0.40, market_ask=0.44,
    )
    assert out is not None
    assert out.market_mid == pytest.approx(0.42)
    assert out.edge == pytest.approx(out.model_probability - 0.42)


def test_all_three_market_types_produce_a_probability():
    m = _matchup()
    proj = project(m)
    for mtype, line in ((MARKET_TOTAL, 165.0), (MARKET_SPREAD, -1.5), (MARKET_WINNER, None)):
        out = predict_market(
            features=m, projection=proj, market_slug="x",
            sports_market_type=mtype, line=line,
        )
        assert out is not None, mtype
        assert 0.0 < out.model_probability < 1.0


def test_over_and_under_sides_sum_to_one():
    m = _matchup()
    proj = project(m)
    over = predict_market(features=m, projection=proj, market_slug="x",
                          sports_market_type=MARKET_TOTAL, line=170.0, is_over_side=True)
    under = predict_market(features=m, projection=proj, market_slug="x",
                           sports_market_type=MARKET_TOTAL, line=170.0, is_over_side=False)
    assert over.model_probability + under.model_probability == pytest.approx(1.0)


def test_margin_sigma_is_smaller_than_total_sigma():
    """Team scores are positively correlated, so the difference varies less."""
    assert 0 < MARGIN_SIGMA_RATIO < 1


# ------------------------------------------------------------------ #
# Ladder curve fit
# ------------------------------------------------------------------ #

def _synthetic_ladder(mu: float, sigma: float, lines: list[float]) -> list[tuple[float, float]]:
    return [(l, float(1 - norm.cdf(l, loc=mu, scale=sigma))) for l in lines]


def test_recovers_known_parameters_from_a_synthetic_ladder():
    lines = [173.5, 176.5, 179.5, 182.5, 185.5, 188.5, 191.5, 194.5]
    fit = fit_ladder(_synthetic_ladder(184.0, 17.3, lines))
    assert fit.ok, fit.reason
    assert fit.implied_mean == pytest.approx(184.0, abs=0.5)
    assert fit.implied_stdev == pytest.approx(17.3, abs=0.5)
    assert fit.r_squared > 0.99


def test_rejects_too_few_rungs():
    fit = fit_ladder([(180.0, 0.6), (183.0, 0.5)])
    assert fit.ok is False and "rungs" in fit.reason


def test_detects_non_monotonic_ladder():
    """P(Over) cannot rise as the line rises — that means stale quotes."""
    bad = [(173.5, 0.60), (176.5, 0.85), (179.5, 0.50), (182.5, 0.45)]
    assert check_monotonic(bad)
    fit = fit_ladder(bad)
    assert fit.ok is False and "monotonic" in fit.reason


def test_wide_spread_rungs_are_dropped():
    """A rung quoting 0.03/0.39 carries no information."""
    rungs = [
        LadderRung(173.5, 0.77, 0.82),
        LadderRung(176.5, 0.71, 0.77),
        LadderRung(179.5, 0.03, 0.39),   # junk
        LadderRung(182.5, 0.59, 0.62),
        LadderRung(185.5, 0.51, 0.53),
    ]
    points, dropped = clean_rungs(rungs)
    assert len(points) == 4
    assert any("179.5" in d for d in dropped)


def test_fit_from_rungs_uses_mid_prices():
    rungs = [
        LadderRung(173.5, 0.77, 0.83),
        LadderRung(176.5, 0.70, 0.76),
        LadderRung(179.5, 0.63, 0.69),
        LadderRung(182.5, 0.56, 0.62),
        LadderRung(185.5, 0.48, 0.54),
    ]
    fit = fit_from_rungs(rungs)
    assert fit.ok, fit.reason
    # Mid crosses 0.5 near 185 -> implied mean should be in that region.
    assert 178.0 < fit.implied_mean < 192.0
    assert fit.rungs_used == 5


def test_regime_shift_is_real_and_estimator_tracks_it():
    """The WNBA scoring environment is NOT stationary.

    Measured from our own data: 2020-2025 sit at mean 161-166 / sigma 16.5-17.7,
    but 2026 is mean 174.4 / sigma 21.7. A multi-season estimate would project
    2026 totals ~10 points low on every market — and would look fine in a
    multi-year backtest because the error averages out across regimes.
    """
    import datetime as dt

    from core.storage import get_engine, get_sessionmaker
    from strategies.wnba_totals.model.fair_value import estimate_totals_distribution

    S = get_sessionmaker(get_engine())
    with S() as s:
        d2026 = estimate_totals_distribution(
            as_of=dt.datetime(2026, 7, 31, tzinfo=UTC), session=s
        )
        d2025 = estimate_totals_distribution(
            as_of=dt.datetime(2025, 7, 31, tzinfo=UTC), session=s
        )

    # Each estimate should reflect ITS OWN season, not a blended average.
    assert d2026.mean > d2025.mean + 4, (d2026.mean, d2025.mean)
    assert d2026.sigma > d2025.sigma
    assert d2025.mean == pytest.approx(164.0, abs=3.0)


def test_early_season_shrinks_toward_history():
    """With 18 games played, the estimate must not chase noise."""
    import datetime as dt

    from core.storage import get_engine, get_sessionmaker
    from strategies.wnba_totals.model.fair_value import estimate_totals_distribution

    S = get_sessionmaker(get_engine())
    with S() as s:
        early = estimate_totals_distribution(
            as_of=dt.datetime(2026, 5, 15, tzinfo=UTC), session=s
        )
        late = estimate_totals_distribution(
            as_of=dt.datetime(2026, 7, 31, tzinfo=UTC), session=s
        )
    assert early.n_current_season < late.n_current_season
    assert early.shrunk_toward_history is True
    # Early estimate sits between history (~163) and the eventual 2026 level.
    assert early.mean < late.mean


def test_sigma_estimation_dedupes_games():
    """team_game_logs holds two rows per game; counting both inflates n."""
    import datetime as dt

    from core.storage import get_engine, get_sessionmaker
    from strategies.wnba_totals.model.fair_value import estimate_totals_distribution

    S = get_sessionmaker(get_engine())
    with S() as s:
        d = estimate_totals_distribution(
            as_of=dt.datetime(2025, 12, 31, tzinfo=UTC), session=s, history_seasons=0
        )
    # 2025 had 287 regular-season games, not 574.
    assert 250 < d.n_current_season < 320, d.n_current_season


def test_missing_quotes_are_dropped_not_guessed():
    rungs = [LadderRung(173.5, None, None), LadderRung(176.5, 0.71, 0.77)]
    points, dropped = clean_rungs(rungs)
    assert len(points) == 1 and any("missing" in d for d in dropped)


# ------------------------------------------------------------------ #
# Winner's-curse shrinkage (the live path's correction)
# ------------------------------------------------------------------ #


def _proj(total: float, margin: float = 2.0, sigma: float = 19.0):
    from strategies.wnba_totals.model.fair_value import Projection

    half = (total - margin) / 2.0
    return Projection(
        projected_home=half + margin, projected_away=half,
        projected_total=total, projected_margin=margin, baseline_margin=margin,
        record_adjustment=0.0, sigma=sigma, is_playoff_game=False,
        reduced_confidence=False, confidence_notes=None,
    )


def test_shrinkage_pulls_the_projection_toward_the_market():
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    out = shrink_to_market(_proj(182.0), market_total=175.0, slope=0.25)
    # 175 + 0.25 * 7 = 176.75
    assert out.projected_total == pytest.approx(176.75)


def test_shrinkage_preserves_the_margin():
    """The anchor is a total; there is no market total to shrink a margin by,
    so spread and moneyline pricing must be left alone."""
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0, margin=6.0)
    after = shrink_to_market(before, market_total=175.0, slope=0.25)
    assert after.projected_margin == pytest.approx(before.projected_margin)
    assert after.projected_home - after.projected_away == pytest.approx(6.0)


def test_shrunk_sides_still_sum_to_the_total():
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    out = shrink_to_market(_proj(182.0, margin=4.0), market_total=170.0, slope=0.3)
    assert out.projected_home + out.projected_away == pytest.approx(out.projected_total)


def test_slope_of_one_is_a_no_op():
    """Slope 1.0 means 'no measured shrinkage yet' — must not alter anything."""
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0)
    assert shrink_to_market(before, market_total=175.0, slope=1.0) is before


def test_no_market_anchor_is_a_no_op():
    """Without a book line there is nothing to shrink toward."""
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0)
    assert shrink_to_market(before, market_total=None, slope=0.25) is before


def test_shrinkage_shrinks_the_displayed_edge_severalfold():
    """The bug this fixes: the dashboard showed the raw gap.

    A 7-point disagreement reads as a ~14% edge unshrunk and ~2-3% shrunk at
    the measured slope. Anyone sizing on the unshrunk number is sizing on a
    number roughly four times too large.
    """
    from strategies.wnba_totals.model.fair_value import prob_over, shrink_to_market

    book, sigma, slope = 175.0, 19.0, 0.231
    raw = _proj(182.0, sigma=sigma)
    shrunk = shrink_to_market(raw, market_total=book, slope=slope)

    raw_edge = prob_over(raw.projected_total, book, sigma) - 0.5
    shrunk_edge = prob_over(shrunk.projected_total, book, sigma) - 0.5

    assert raw_edge > 0.13
    assert shrunk_edge < 0.05
    assert raw_edge / shrunk_edge > 3.0


def test_margin_is_shrunk_against_its_own_anchor():
    """Totals and margin disagree independently and must shrink separately.

    A game can be one where we disagree wildly about pace and not at all about
    who wins. Averaging those two disagreements would corrupt both.
    """
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0, margin=10.0)
    after = shrink_to_market(
        before, market_total=175.0, market_margin=2.0, slope=0.2
    )
    assert after.projected_total == pytest.approx(175.0 + 0.2 * 7.0)   # 176.4
    assert after.projected_margin == pytest.approx(2.0 + 0.2 * 8.0)    # 3.6


def test_sides_are_rebuilt_consistently_from_total_and_margin():
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    out = shrink_to_market(
        _proj(182.0, margin=10.0), market_total=175.0,
        market_margin=2.0, slope=0.2,
    )
    assert out.projected_home + out.projected_away == pytest.approx(out.projected_total)
    assert out.projected_home - out.projected_away == pytest.approx(out.projected_margin)


def test_a_missing_anchor_leaves_that_dimension_alone():
    """No book spread => margin untouched, total still shrunk."""
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0, margin=10.0)
    after = shrink_to_market(
        before, market_total=175.0, market_margin=None, slope=0.2
    )
    assert after.projected_margin == pytest.approx(10.0)
    assert after.projected_total < before.projected_total


def test_no_anchors_at_all_is_a_no_op():
    from strategies.wnba_totals.model.fair_value import shrink_to_market

    before = _proj(182.0)
    assert shrink_to_market(
        before, market_total=None, market_margin=None, slope=0.2
    ) is before
