"""The ladder-sigma damping shadow arm (docs/math/ladder-sigma-damping.md).

What is defended:

* the damping sigma IS the published finals-residual constant — pinned to
  the elapsed-0 row of the totals table, so a refit of the table cannot
  silently diverge from the registration;
* the damped probability preserves the ladder's own implied mean (p = 0.5
  at the mean) and removes exactly the excess width: tail rungs lose mass
  in BOTH directions relative to the wider ladder;
* the damped value lands BESIDE the undamped — model_probability is never
  touched — and non-totals rows, thin ladders, and failed fits are left
  NULL, silently and correctly.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from scipy import stats as scipy_stats

from core.live_totals_fv import TOTALS_ANCHORS
from core.predictions import DAMPED_LADDER_SIGMA, _apply_ladder_damping
from core.storage import Prediction
from strategies.wnba_totals.model.fair_value import MARKET_TOTAL, MARKET_WINNER

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)

#: The emergent effective sigma the damping removes (measured 2026-08-07).
WIDE_SIGMA = 20.75
MU = 160.0


def _row(line, prob, mtype=MARKET_TOTAL, event="damp-ev-1"):
    return Prediction(
        predicted_at=NOW, model_version="v4-test", strategy="wnba_totals",
        market_slug=f"tsc-{event}-{line}", event_slug=event,
        sports_market_type=mtype,
        line=None if line is None else Decimal(str(line)),
        model_probability=None if prob is None else Decimal(str(round(prob, 4))),
    )


def _ladder(event="damp-ev-1", mu=MU, sigma=WIDE_SIGMA,
            lines=(140.5, 150.5, 160.5, 170.5, 180.5)):
    return [_row(ln, 1 - scipy_stats.norm.cdf((ln - mu) / sigma), event=event)
            for ln in lines]


def test_damping_sigma_is_the_published_constant():
    """19.00 is the elapsed-0 residual sd of the totals table, fitted
    2026-08-07 — the registration's whole argument is that this constant
    predates the bucket test. If the table is ever refit, this test fails
    and the divergence becomes a registration decision, never a drift."""
    assert DAMPED_LADDER_SIGMA == TOTALS_ANCHORS[0][3] == 19.00


def test_damped_preserves_the_mean_and_narrows_the_tails():
    rows = _ladder()
    assert _apply_ladder_damping(rows) == 1
    by_line = {float(r.line): r for r in rows}
    # Mean preserved: at a line ~the implied mean, damped p ~ 0.5.
    assert float(by_line[160.5].damped_probability) == pytest.approx(0.5, abs=0.02)
    # Tails narrowed in BOTH directions: high lines lose over-mass, low
    # lines gain it (equivalently their under-mass shrinks).
    assert float(by_line[180.5].damped_probability) < float(by_line[180.5].model_probability)
    assert float(by_line[140.5].damped_probability) > float(by_line[140.5].model_probability)
    # And the undamped column was never touched.
    p = 1 - scipy_stats.norm.cdf((180.5 - MU) / WIDE_SIGMA)
    assert float(by_line[180.5].model_probability) == pytest.approx(p, abs=1e-3)


def test_non_totals_thin_ladders_and_failed_fits_stay_null():
    winner = _row(None, 0.6, mtype=MARKET_WINNER)
    thin = [_row(150.5, 0.7, event="thin"), _row(160.5, 0.5, event="thin")]
    rows = [winner, *thin]
    assert _apply_ladder_damping(rows) == 0
    assert winner.damped_probability is None
    assert all(r.damped_probability is None for r in thin)


def test_two_events_damp_independently():
    a = _ladder(event="ev-a", mu=150.0)
    b = _ladder(event="ev-b", mu=170.0, lines=(150.5, 160.5, 170.5, 180.5, 190.5))
    rows = [*a, *b]
    assert _apply_ladder_damping(rows) == 2
    mid_a = next(r for r in a if float(r.line) == 150.5)
    mid_b = next(r for r in b if float(r.line) == 170.5)
    assert float(mid_a.damped_probability) == pytest.approx(0.5, abs=0.02)
    assert float(mid_b.damped_probability) == pytest.approx(0.5, abs=0.02)
