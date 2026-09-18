"""The margin-scale surface. Every value read off a ladder, none from an outcome."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from core.gridiron.scale import (MarginScale, cover_probability, ladder_scale)


def _ladder(game, mu, sigma, lines=range(-30, 31, 2), noise=0.0):
    """A ladder generated FROM a known (mu, sigma), so the fit has a right answer."""
    lines = np.array(list(lines), dtype=float)
    p = norm.cdf((mu + lines) / sigma) + noise
    return pd.DataFrame({"game": game, "line": lines, "mid": p})


def test_it_recovers_the_scale_it_was_generated_from():
    out = ladder_scale(_ladder(1, mu=-14.0, sigma=15.0))
    assert out.sigma.iloc[0] == pytest.approx(15.0, abs=0.05)
    assert out.implied_line.iloc[0] == pytest.approx(14.0, abs=0.05)
    assert out.r2.iloc[0] > 0.999


def test_the_crossing_is_recovered_without_the_ladder_bracketing_it():
    """The whole reason to fit rather than interpolate: a one-sided ladder.

    `fit.spread_anchor` needs mids either side of 0.5 and dropped 2 of 14 games
    for not having them. Every rung here is below 0.5.
    """
    lad = _ladder(1, mu=-40.0, sigma=17.0, lines=range(-30, 31, 2))
    assert lad["mid"].max() < 0.5, "fixture must not bracket, or it tests nothing"
    out = ladder_scale(lad)
    assert len(out) == 1
    assert out.implied_line.iloc[0] == pytest.approx(40.0, abs=0.5)


def test_clipped_rungs_are_excluded_because_they_are_not_quotes():
    """The venue pins the tails at 0.015/0.985. Those flat rungs would drag the
    slope toward zero and inflate sigma."""
    lad = _ladder(1, mu=0.0, sigma=14.0, lines=range(-60, 61, 2))
    clipped = lad.assign(mid=lad["mid"].clip(0.015, 0.985))
    assert ladder_scale(clipped).sigma.iloc[0] == pytest.approx(14.0, abs=0.4)


def test_a_thin_ladder_is_dropped_rather_than_fitted():
    assert ladder_scale(_ladder(1, 0.0, 14.0, lines=[-2, 0, 2])).empty


def test_a_ladder_that_falls_with_the_line_is_refused():
    """A negative slope is not a wide distribution, it is a frame error."""
    lad = _ladder(1, mu=0.0, sigma=14.0)
    assert ladder_scale(lad.assign(mid=1 - lad["mid"])).empty


def test_r2_is_reported_not_filtered():
    """A bad ladder must reach the caller visibly, not vanish and not pass."""
    rng = np.random.default_rng(0)
    lad = _ladder(1, mu=-10.0, sigma=15.0)
    lad["mid"] = np.clip(lad["mid"] + rng.normal(0, 0.08, len(lad)), 0.06, 0.94)
    out = ladder_scale(lad)
    assert len(out) == 1 and out.r2.iloc[0] < 0.99


def _scales(sigmas, lines):
    return pd.DataFrame({"game": range(len(sigmas)), "sigma": sigmas,
                         "implied_line": lines, "r2": 0.99, "n_rungs": 20})


def test_the_slope_is_fitted_on_absolute_line_so_underdogs_count():
    """A +13 home underdog and a -13 favourite are both 13 points of lopsidedness."""
    m = MarginScale.fit(_scales([14, 14, 18, 18, 16, 16], [5, -5, 40, -40, 20, -20]))
    assert m.sigma(5) == pytest.approx(m.sigma(-5))
    assert m.slope > 0


def test_it_clamps_instead_of_extrapolating():
    m = MarginScale.fit(_scales([14, 15, 16, 17, 18, 19], [5, 10, 20, 30, 40, 45]))
    assert m.sigma(500) == pytest.approx(m.sigma(45))
    assert m.sigma(0) == pytest.approx(m.sigma(5))


def test_too_few_games_refuses_to_fit_a_slope():
    with pytest.raises(ValueError, match="not enough"):
        MarginScale.fit(_scales([14, 15, 16], [5, 20, 40]))


def test_the_cover_probability_is_a_half_at_its_own_line():
    """The one identity this map must satisfy exactly, at every lopsidedness."""
    m = MarginScale.fit(_scales([14, 15, 16, 17, 18, 19], [5, 10, 20, 30, 40, 45]))
    for mu in (3.0, 10.0, 20.0, 35.0):
        assert cover_probability(-mu, mu, m) == pytest.approx(0.5, abs=1e-9)


def test_a_wider_scale_flattens_the_ladder():
    """Sanity on the direction: more uncertainty pulls every rung toward 0.5."""
    narrow = MarginScale(10.0, 0.0, line_range=(0, 50), n_games=9, corr=0.0)
    wide = MarginScale(20.0, 0.0, line_range=(0, 50), n_games=9, corr=0.0)
    assert cover_probability(0.0, 14.0, narrow) > cover_probability(0.0, 14.0, wide) > 0.5


def test_sigma_is_one_number_per_game_not_one_per_rung():
    """The argument is the GAME's spread. Feeding a rung's line back in would
    give a different width per rung, denying the single-distribution assumption
    the ladder is being used to test."""
    m = MarginScale.fit(_scales([14, 15, 16, 17, 18, 19], [5, 10, 20, 30, 40, 45]))
    game_spread = -20.0
    s = m.sigma(game_spread)
    # every rung on this game's ladder prices from the SAME width
    for rung in (-27.5, -24.0, -20.0, -16.5, -13.0):
        assert cover_probability(rung, -game_spread, m) == pytest.approx(
            norm.cdf((-game_spread + rung) / s))


def test_the_ladder_is_monotone_in_the_line():
    """Whatever sigma is, a bigger cushion must never price lower."""
    m = MarginScale.fit(_scales([14, 15, 16, 17, 18, 19], [5, 10, 20, 30, 40, 45]))
    p = [cover_probability(L, 20.0, m) for L in range(-35, 6, 5)]
    assert all(b > a for a, b in zip(p, p[1:]))


def test_the_flat_surface_is_constant_and_does_not_clamp_away_real_lines():
    """The gated 2026-09-07 cohort supports a level, not a trend."""
    m = MarginScale.flat(15.86)
    assert m.sigma(8.1) == pytest.approx(15.86)
    assert m.sigma(23.9) == pytest.approx(15.86)
    assert m.sigma(49.7) == pytest.approx(15.86)
    assert m.slope == 0.0


def test_flat_beats_the_shipped_relation_on_the_gated_cohort():
    """Pins the comparison that demoted the slope, so a later edit that
    reinstates it has to explain these three games."""
    gated = [(8.1, 15.98), (22.5, 15.61), (23.9, 15.98)]
    shipped = MarginScale(13.19, 0.1182, line_range=(7.9, 49.7), n_games=14, corr=0.948)
    flat = MarginScale.flat(15.86)
    err = lambda m: sum(abs(s - m.sigma(l)) for l, s in gated) / len(gated)
    assert err(flat) < 0.25 < 0.6 < err(shipped)
