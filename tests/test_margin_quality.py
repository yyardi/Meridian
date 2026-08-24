"""The margin-quality diagnostic: sign convention, pairing, and the
between-bucket test that the per-bucket table cannot substitute for."""

from __future__ import annotations

import pytest

from core.backtest.margin_quality import Bucket, GameMargin, bucket_difference


def _g(gid: str, model: float, market: float, actual: float) -> GameMargin:
    return GameMargin(
        espn_game_id=gid, season=2025, month=6,
        market_margin=market, model_margin=model, actual_margin=actual,
    )


def _gd(gid: str, delta: float) -> GameMargin:
    """A game whose paired delta is exactly `delta`.

    Both errors are absolute values, so one side is exact and the other off by
    |delta|: positive delta means WE are the inaccurate one, negative means the
    market is.
    """
    if delta >= 0:
        return _g(gid, model=delta, market=0.0, actual=0.0)
    return _g(gid, model=0.0, market=-delta, actual=0.0)


def test_delta_is_ours_minus_theirs_and_positive_means_we_are_worse():
    """Sign convention is load-bearing — the whole diagnostic reads backwards
    if it flips, and a flipped sign yields a confident answer of the wrong
    shape rather than an obvious blank (V19)."""
    worse = _g("1", model=10.0, market=4.0, actual=5.0)   # ours off 5, theirs 1
    assert worse.model_err == pytest.approx(5.0)
    assert worse.market_err == pytest.approx(1.0)
    assert worse.delta == pytest.approx(4.0), "positive = we are worse"

    better = _g("2", model=6.0, market=1.0, actual=5.0)   # ours off 1, theirs 4
    assert better.delta == pytest.approx(-3.0), "negative = we are better"


def test_pairing_removes_shared_game_difficulty():
    """Both errors on one game share that game's difficulty. Differencing per
    game before aggregating is what removes it; averaging the two MAEs
    separately and subtracting would leave the shared term in the spread of
    the bootstrap, understating certainty about the gap."""
    # A blowout nobody called, and a close game everyone called. Both have a
    # constant +2 gap in OUR favour being worse, despite wildly different MAEs.
    games = [_g("1", model=30.0, market=28.0, actual=0.0),
             _g("2", model=3.0, market=1.0, actual=0.0)]
    b = Bucket(label="t", games=games)
    assert b.model_mae == pytest.approx(16.5)
    assert b.market_mae == pytest.approx(14.5)
    assert b.mean_delta == pytest.approx(2.0)
    lo, hi = b.delta_interval(resamples=500)
    # Every game has the identical delta, so the paired interval is a point.
    assert lo == pytest.approx(2.0) and hi == pytest.approx(2.0)


def test_between_bucket_difference_is_not_the_per_bucket_intervals():
    """The trap this function exists to avoid.

    Bucket A's own interval crosses zero and bucket B's does not — which reads
    as 'the gap is concentrated in B'. It is not: resampling the DIFFERENCE
    shows the two are indistinguishable. Small buckets have wide intervals, so
    'not significant' frequently means 'not enough games'.
    """
    noisy = [1.4, -1.3, 1.9, -1.5, 1.6, -1.2]        # small, straddles zero
    a = Bucket(label="A", games=[_gd(f"a{i}", d) for i, d in enumerate(noisy)])
    b = Bucket(label="B", games=[_gd(f"b{i}", 0.5) for i in range(40)])

    a_ci = a.delta_interval(resamples=2000)
    b_ci = b.delta_interval(resamples=2000)
    assert a_ci[0] < 0 < a_ci[1], "A straddles zero"
    assert not (b_ci[0] < 0 < b_ci[1]), "B does not straddle zero"

    d = bucket_difference(a, b, resamples=2000)
    assert d["distinguishable_from_zero"] is False, (
        "one bucket clearing zero and another not does NOT make them different; "
        "that inference is the error this test pins"
    )


def test_bucket_difference_reports_none_when_a_bucket_is_too_small():
    a = Bucket(label="A", games=[_g("a", 0.0, -1.0, 0.0)])
    b = Bucket(label="B", games=[_g(f"b{i}", 0.0, -1.0, 0.0) for i in range(10)])
    assert bucket_difference(a, b)["difference"] is None
