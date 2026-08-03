"""Adverse-selection measurement: window construction, P&L, clustered CIs.

The load-bearing tests here are the ones about *clustering*. A row-level
confidence interval on ladder rows sampled every second is wrong by roughly
sqrt(rows per game), and wrong in the direction that manufactures a result. If
`test_clustering_widens_the_interval` ever fails, every verdict this module
produces becomes untrustworthy.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.quote.adverse_selection import (
    GATE_MIN_GAMES,
    GATE_MIN_WINDOWS,
    Quote,
    QuoteWindow,
    build_windows,
    cadence,
    clustered_mean,
    format_report,
    naive_mean,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 2, 1, 0, tzinfo=UTC)


def _q(seconds: float, bid: float, ask: float, *, game: str = "g1", slug: str = "m1") -> Quote:
    return Quote(
        game_id=game,
        market_slug=slug,
        captured_at=T0 + dt.timedelta(seconds=seconds),
        bid=bid,
        ask=ask,
    )


# ------------------------------------------------------------------ #
# Quote filtering
# ------------------------------------------------------------------ #


def test_deep_rungs_are_excluded():
    """22-26c-spread rungs do not trade; their drift must not enter the mean."""
    assert _q(0, 0.49, 0.52).is_quotable
    assert not _q(0, 0.90, 0.95).is_quotable, "mid outside the tradable band"
    assert not _q(0, 0.40, 0.62).is_quotable, "spread wider than MAX_SPREAD"
    assert not _q(0, 0.500, 0.5001).is_quotable, "spread below one tick"


# ------------------------------------------------------------------ #
# Window construction
# ------------------------------------------------------------------ #


def test_window_pairs_with_the_nearest_observation_to_the_horizon():
    series = {"m1": [_q(0, 0.49, 0.52), _q(25, 0.40, 0.43), _q(31, 0.30, 0.33)]}
    windows = build_windows(series, horizon_seconds=30.0)

    assert len(windows) == 1
    w = windows[0]
    # 31s is nearer to the 30s target than 25s is.
    assert w.horizon_seconds == pytest.approx(31.0)
    assert w.mid_at_horizon == pytest.approx(0.315)


def test_window_is_dropped_when_the_gap_is_outside_tolerance():
    """A 10-minute hole must not be reported as a 30-second horizon."""
    series = {"m1": [_q(0, 0.49, 0.52), _q(600, 0.40, 0.43)]}
    assert build_windows(series, horizon_seconds=30.0) == []


def test_window_ignores_observations_before_the_horizon_opens():
    series = {"m1": [_q(0, 0.49, 0.52), _q(5, 0.48, 0.51)]}
    assert build_windows(series, horizon_seconds=30.0) == []


# ------------------------------------------------------------------ #
# The P&L decomposition — the actual question
# ------------------------------------------------------------------ #


def test_filled_bid_pnl_is_half_spread_plus_the_mid_move():
    """net = (m - b) + (m_H - m). The identity the whole experiment rests on."""
    quote = _q(0, 0.48, 0.52)          # mid 0.50, half-spread 0.02
    w = QuoteWindow(quote=quote, horizon_seconds=30.0, mid_at_horizon=0.44)

    assert w.bid_filled, "mid fell to 0.44, through the 0.48 bid"
    assert w.net_bid() == pytest.approx((0.44 - 0.48))
    assert w.net_bid() == pytest.approx(w.half_spread + w.dmid)
    assert w.net_bid() < 0, "run over: the 2c half-spread did not cover a 6c drop"


def test_filled_offer_pnl_is_half_spread_minus_the_mid_move():
    quote = _q(0, 0.48, 0.52)
    w = QuoteWindow(quote=quote, horizon_seconds=30.0, mid_at_horizon=0.56)

    assert w.ask_filled
    assert w.net_ask() == pytest.approx(0.52 - 0.56)
    assert w.net_ask() == pytest.approx(w.half_spread - w.dmid)


def test_a_quiet_market_fills_neither_side():
    """No fill is not a loss. It is simply not an observation."""
    w = QuoteWindow(quote=_q(0, 0.48, 0.52), horizon_seconds=30.0, mid_at_horizon=0.50)
    assert not w.bid_filled and not w.ask_filled
    assert w.fills() == []


def test_a_small_move_leaves_the_spread_intact():
    """The favourable case: filled, and the mid barely moved."""
    quote = _q(0, 0.45, 0.55)  # half-spread 5c
    w = QuoteWindow(quote=quote, horizon_seconds=30.0, mid_at_horizon=0.44)
    assert w.bid_filled
    assert w.net_bid() == pytest.approx(-0.01)


def test_fee_is_subtracted_not_rebated():
    """A gate must not be passable by an accounting assumption."""
    w = QuoteWindow(quote=_q(0, 0.48, 0.52), horizon_seconds=30.0, mid_at_horizon=0.44)
    assert w.net_bid(fee=0.01) < w.net_bid(fee=0.0)


# ------------------------------------------------------------------ #
# Clustering — where a wrong answer would be most expensive
# ------------------------------------------------------------------ #


def test_clustering_widens_the_interval():
    """Correlated rows within a game must not read as independent evidence.

    Ten games, each contributing 50 identical rows. Within a game there is zero
    variance, so the row-level interval collapses to nothing and declares a
    result; the clustered interval sees ten observations and stays honest.
    """
    by_game = {f"g{i}": [0.01 * (i - 4.5)] * 50 for i in range(10)}
    values = [x for v in by_game.values() for x in v]

    clustered = clustered_mean(by_game)
    naive = naive_mean(values)

    assert clustered is not None and naive is not None
    assert clustered.mean == pytest.approx(naive.mean)
    assert clustered.stderr > naive.stderr * 3, (
        "clustering must widen the interval substantially when rows repeat"
    )
    assert clustered.n_clusters == 10
    assert clustered.n == 500


def test_clustered_interval_covers_zero_for_a_symmetric_sample():
    by_game = {f"g{i}": [1.0, -1.0] for i in range(12)}
    cl = clustered_mean(by_game)
    assert cl is not None
    assert cl.mean == pytest.approx(0.0)
    assert not cl.excludes_zero


def test_clustered_mean_refuses_a_single_cluster():
    """One game cannot produce a between-game interval."""
    assert clustered_mean({"g1": [0.1, 0.2, 0.3]}) is None


def test_clustered_mean_ignores_empty_clusters():
    cl = clustered_mean({"g1": [0.1], "g2": [0.2], "g3": []})
    assert cl is not None and cl.n_clusters == 2


# ------------------------------------------------------------------ #
# Cadence reporting
# ------------------------------------------------------------------ #


def test_cadence_reports_the_bimodal_stream_rather_than_hiding_it():
    """Live rows come from two processes at very different rates.

    The pregame recorder sweeps the board every ~15 min and flags whatever is
    live; the live recorder samples at ~1s. Quoting only a median invites
    reading a 15-minute gap as a fast one, so the distribution is reported.
    """
    fast = [_q(i, 0.49, 0.52) for i in range(0, 10)]
    slow = [_q(1000 + 900 * i, 0.49, 0.52) for i in range(6)]
    c = cadence({"m1": fast + slow})

    assert c is not None
    assert c.p10 == pytest.approx(1.0)
    assert c.p90 > 500
    assert 0.0 < c.under_2min < 1.0


def test_cadence_ignores_overnight_holes():
    """A gap between recording sessions is not a poll interval."""
    quotes = [_q(0, 0.49, 0.52), _q(1, 0.49, 0.52), _q(50_000, 0.49, 0.52)]
    c = cadence({"m1": quotes})
    assert c is not None and c.n_gaps == 1


# ------------------------------------------------------------------ #
# Verdicts
# ------------------------------------------------------------------ #


def test_zero_windows_reports_no_data_not_a_null():
    report = format_report([], horizon_seconds=30.0)
    assert "NO DATA" in report
    assert "Not a null result" in report
    assert "FAIL" not in report


def test_below_the_game_gate_reports_no_data_even_with_many_windows():
    """Sample size is games, not rows — the gate that usually binds."""
    windows = [
        QuoteWindow(
            quote=_q(i, 0.48, 0.52, game="g1", slug=f"m{i}"),
            horizon_seconds=30.0,
            mid_at_horizon=0.44,
        )
        for i in range(GATE_MIN_WINDOWS + 100)
    ]
    report = format_report(windows, horizon_seconds=30.0)
    assert "NO DATA" in report
    assert f"{GATE_MIN_GAMES} games" in report
    # "PASS requires ..." appears in the pre-registration block; the verdict
    # line is what must be absent.
    assert "PASS —" not in report


def test_a_losing_sample_across_enough_games_reports_fail():
    windows = [
        QuoteWindow(
            quote=_q(i, 0.48, 0.52, game=f"g{i % GATE_MIN_GAMES}", slug=f"m{i}"),
            horizon_seconds=30.0,
            mid_at_horizon=0.40,     # 8c against a 2c half-spread
        )
        for i in range(GATE_MIN_WINDOWS + 50)
    ]
    report = format_report(windows, horizon_seconds=30.0)
    assert "FAIL" in report
    assert "Adverse selection ate the spread" in report


def test_the_report_always_states_the_fill_rule_caveat():
    """A PASS here is an upper bound, and must never be quoted without that."""
    windows = [
        QuoteWindow(
            quote=_q(i, 0.48, 0.52, game=f"g{i % 12}", slug=f"m{i}"),
            horizon_seconds=30.0,
            mid_at_horizon=0.44,
        )
        for i in range(GATE_MIN_WINDOWS + 50)
    ]
    report = format_report(windows, horizon_seconds=30.0)
    assert "Fill-rule caveat" in report
    assert "PASS is an upper bound" in report
