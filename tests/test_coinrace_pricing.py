"""Coin Race pricing screen: the model's arithmetic, the scoring, and the walk-forward boundary.

No database and no network: every test builds its own arrays.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest
from scipy.special import ndtr

ROOT = pathlib.Path(__file__).resolve().parents[1]
CR = ROOT / "analysis" / "coinrace"
sys.path.insert(0, str(CR))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, CR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pm = _load("pricing_model")
pdat = _load("pricing_data")
ps = _load("pricing_screen")


# ------------------------------------------------------------------ contract arithmetic
def test_ticker_time_is_window_end_in_eastern():
    # 26OCT062330 = Oct 6 11:30 PM EDT = 03:30Z Oct 7, the market's close_time (checked on
    # the API: open 03:15Z, close 03:30Z).
    assert pdat.ticker_close_utc("KXCRYPTOLEAD15M-26OCT062330") == dt.datetime(
        2026, 10, 7, 3, 30, tzinfo=dt.timezone.utc)
    # Standard time after the November change: 5 h offset, not 4.
    assert pdat.ticker_close_utc("KXCRYPTOLEAD15M-26NOV101200") == dt.datetime(
        2026, 11, 10, 17, 0, tzinfo=dt.timezone.utc)


def test_taker_fee_rounds_up_to_the_cent():
    # 0.07 * 0.5 * 0.5 = 0.0175 -> 0.02; 0.07 * 0.01 * 0.99 = 0.000693 -> 0.01
    assert pm.taker_fee(0.5) == pytest.approx(0.02)
    assert pm.taker_fee(0.01) == pytest.approx(0.01)
    assert pm.taker_fee(0.99) == pytest.approx(0.01)
    # an exact cent is not pushed up by float noise: 0.07 * 0.2 * 0.8 = 0.0112 -> 0.02
    assert pm.taker_fee(0.2) == pytest.approx(0.02)


def test_remaining_variance_includes_the_averaging_minute():
    # t = 0: 840 s of walk plus a 60-s average (variance of 20 s) = 860
    assert pm.remaining_variance_seconds(0) == pytest.approx(860.0)
    assert pm.remaining_variance_seconds(780) == pytest.approx(80.0)     # minute 13
    assert pm.remaining_variance_seconds(840) == pytest.approx(20.0)
    # inside the last minute the variance keeps falling to zero continuously
    assert pm.remaining_variance_seconds(870) == pytest.approx((0.5 ** 2) * 30 / 3)
    assert pm.remaining_variance_seconds(900) == 0.0


def test_remaining_variance_matches_a_simulated_average():
    rng = np.random.default_rng(0)
    n, t = 20000, 780
    steps = rng.standard_normal((n, 900 - t))          # unit-variance per-second increments
    path = np.cumsum(steps, axis=1)                    # W(s) - W(t) for s = t+1..900
    avg = path[:, -60:].mean(axis=1)
    assert avg.var() == pytest.approx(pm.remaining_variance_seconds(t), rel=0.05)


# --------------------------------------------------------------------------- the model
def test_symmetric_race_is_one_fifth_each():
    p = pm.win_probs(np.zeros((1, 5)), np.eye(5), pm.standard_normals(4096))
    assert np.allclose(p, 0.2, atol=0.003)


def test_two_coins_match_the_closed_form():
    C = np.array([[1.0, 0.6], [0.6, 2.0]])
    x = np.array([[0.3, -0.2]])
    p = pm.win_probs(x, C, pm.standard_normals(4096, d=2))
    assert p[0, 0] == pytest.approx(ndtr(0.5 / np.sqrt(1 + 2 - 1.2)), abs=1e-3)


def test_five_coins_match_brute_force_counting():
    rng = np.random.default_rng(1)
    A = rng.standard_normal((5, 5))
    C = A @ A.T + 0.5 * np.eye(5)
    x = rng.standard_normal(5) * 0.8
    p = pm.win_probs(x[None], C, pm.standard_normals(8192))[0]
    X = x + rng.standard_normal((2_000_000, 5)) @ np.linalg.cholesky(C).T
    brute = np.bincount(X.argmax(axis=1), minlength=5) / len(X)
    assert np.abs(p - brute).max() < 0.002


def test_a_leader_late_wins_more_than_early():
    C = np.eye(5) * 1e-8                               # per-second variance
    x = np.array([[5e-4, 0, 0, 0, 0]])                 # coin 0 up 5 bp
    early = pm.win_probs(x, C * pm.remaining_variance_seconds(60), pm.standard_normals(4096))
    late = pm.win_probs(x, C * pm.remaining_variance_seconds(780), pm.standard_normals(4096))
    assert late[0, 0] > early[0, 0] > 0.2


# --------------------------------------------------------------------------- scoring
def test_log_loss_and_brier_handle_a_tie():
    p = np.array([[0.5, 0.5, 0.0, 0.0, 0.0]])
    y = np.array([[0.5, 0.5, 0.0, 0.0, 0.0]])
    assert pm.log_loss(p, y)[0] == pytest.approx(np.log(2))
    assert pm.brier(p, y)[0] == pytest.approx(0.0)


def test_clustered_ci_widens_with_within_cluster_correlation():
    rng = np.random.default_rng(2)
    g = np.repeat(np.arange(40), 50)
    iid = rng.standard_normal(2000)
    shared = rng.standard_normal(40)[g] + 0.1 * rng.standard_normal(2000)
    a, b = pm.clustered_mean_ci(iid, g), pm.clustered_mean_ci(shared, g)
    assert (b["hi"] - b["lo"]) > 3 * (a["hi"] - a["lo"])
    assert a["G"] == 40 and a["n"] == 2000


# ------------------------------------------------------------------ walk-forward boundary
def _synthetic_candles(days=10, seed=3):
    rng = np.random.default_rng(seed)
    t0 = int(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc).timestamp())
    n = days * 1440
    rows = []
    for k, coin in enumerate(pm.COINS):
        lp = np.cumsum(rng.standard_normal(n) * 1e-3 * (1 + k / 5))
        c = 100 * np.exp(lp)
        for i in range(n):
            rows.append((t0 + 60 * i, c[i], c[i], c[i], c[i], 1.0, coin))
    return t0, pd.DataFrame(rows, columns=["ts", "low", "high", "open", "close", "volume", "coin"])


def test_day_params_never_read_the_scored_day():
    t0, df = _synthetic_candles()
    D0 = t0 + 8 * 86400
    base = ps.day_params(ps.Candles(df), D0, 5)
    # Poison everything from D0 on: the parameters for day D must not move.
    df2 = df.copy()
    late = df2["ts"] >= D0
    df2.loc[late, ["low", "high", "open", "close"]] *= np.exp(
        np.random.default_rng(9).standard_normal(late.sum()) * 0.05)[:, None]
    poisoned = ps.day_params(ps.Candles(df2), D0, 5)
    assert np.allclose(base["S"], poisoned["S"])
    assert np.allclose(base["prof"], poisoned["prof"])


def test_window_state_uses_the_candle_that_closes_at_the_minute():
    t0, df = _synthetic_candles(days=2)
    cd = ps.Candles(df)
    open_ts = t0 + 86400                                  # a window opening at day 2 00:00Z
    ev = pd.DataFrame({"open_ts": [open_ts]})
    st = ps.window_states(ev, cd)
    k = pm.COINS.index("BTC")
    close_at = df[(df.coin == "BTC")].set_index("ts")["close"]
    # minute 5 = the candle starting at open+4 min (it closes at open+5 min)
    assert np.exp(st["x5"][0, k] + st["logA"][0, k]) == pytest.approx(close_at[open_ts + 240])
    # the start average is the minute BEFORE the window
    assert np.exp(st["logA"][0, k]) == pytest.approx(close_at[open_ts - 60])


def test_student_t_mixture_matches_brute_force():
    # The scale must be drawn jointly with the normals: a separately scrambled 1-D Sobol
    # sequence paired with the 5-D one tied the scale to the first coin's draw (BTC off by
    # 0.010 in the 2026-10-07 hand check).
    rng = np.random.default_rng(4)
    A = rng.standard_normal((5, 5))
    C = (A @ A.T + 0.5 * np.eye(5)) * 1e-6
    x = rng.standard_normal(5) * 1e-3
    nu = 4.0
    n = 4096
    p = pm.win_probs(x[None], C, pm.standard_normals(n), scales=pm.t_scales(n, nu))[0]
    nb = 2_000_000
    z = rng.standard_normal((nb, 5)) @ np.linalg.cholesky(C).T
    z *= np.sqrt((nu - 2.0) / rng.chisquare(nu, nb))[:, None]
    brute = np.bincount((x + z).argmax(axis=1), minlength=5) / nb
    assert np.abs(p - brute).max() < 0.003
