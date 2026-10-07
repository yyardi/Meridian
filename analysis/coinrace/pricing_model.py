"""Coin Race pricing model and scoring primitives (pure functions; no I/O).

The race
--------
Five coins, a 900-s window. Coin i's settled return is B_i / A_i - 1, with A_i the time-weighted
average (TWA) of its index price over the 60 s before the window opens and B_i the TWA over
the 60 s before it closes. Ranking by B/A is ranking by log(B/A).

At t seconds into the window (t <= 840) A_i is known and the spot S_i(t) is observed. With
log prices a Brownian motion with per-second covariance Sigma and no drift,

    log B_i - log S_i(t) = (1/60) * integral_{840}^{900} (W_i(s) - W_i(t)) ds

is Gaussian with covariance Sigma * v(t), v(t) = (840 - t) + 60/3 = 860 - t seconds. (The
average over the last minute has the variance of a third of that minute, the textbook
integrated-Brownian-motion result.) So the vector of final log returns is

    X ~ N( x(t), Sigma * v(t) ),   x_i(t) = log S_i(t) - log A_i

and P(coin i wins) = P(X_i = max_j X_j), a four-dimensional Gaussian orthant probability.

Computing it
------------
`win_probs` uses Rao-Blackwellised Monte Carlo: draw X, and for each coin i replace the
indicator 1{X_i > max_{j != i} X_j} by its conditional expectation given X_{-i},

    Phi( (E[X_i | X_-i] - max_{j != i} X_j) / sd(X_i | X_-i) ),

which is exact in the coin-i direction, smooth, never exactly 0 or 1, and has far lower
variance than counting winners. The five estimates are renormalised to sum to 1 (the raw sum
differs from 1 by Monte Carlo error only).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import ndtr, ndtri
from scipy.stats import qmc
from scipy.stats import t as student_t

COINS = ("BTC", "ETH", "SOL", "XRP", "HYPE")
MINUTES = (1, 5, 10, 13)
WINDOW_S = 900
AVG_S = 60


def remaining_variance_seconds(t_s: float, window_s: int = WINDOW_S, avg_s: int = AVG_S) -> float:
    """Variance (in seconds of Brownian time) of log(end TWA) - log S(t), for t seconds in.

    Before the averaging minute: (window - avg - t) + avg/3. Inside it, the observed part of
    the average is known and the remaining (window - t) seconds enter with weight
    (window - t)/avg: variance ((window - t)/avg)^2 * (window - t)/3.
    """
    if t_s < 0 or t_s > window_s:
        raise ValueError(t_s)
    if t_s <= window_s - avg_s:
        return (window_s - avg_s - t_s) + avg_s / 3.0
    u = window_s - t_s
    return (u / avg_s) ** 2 * u / 3.0


def taker_fee(price, rate: float = 0.07):
    """Kalshi quadratic taker fee for ONE contract at `price` dollars, rounded UP to the cent."""
    p = np.asarray(price, dtype=float)
    raw = rate * p * (1.0 - p) * 100.0
    return np.ceil(np.round(raw, 9)) / 100.0


def standard_normals(n: int, d: int = 5, seed: int = 20261007) -> np.ndarray:
    """Scrambled-Sobol standard normal draws, shape (n, d); n a power of two.

    Quasi-random draws cut the Monte Carlo error of `win_probs` about tenfold against
    pseudo-random ones at the same n (max abs error ~0.0004 vs ~0.004 at n = 4096 on a
    deliberately ill-conditioned 5-coin case; tests/test_coinrace_pricing.py pins the bound).
    """
    u = qmc.Sobol(d, scramble=True, seed=seed).random(n)
    return ndtri(np.clip(u, 1e-12, 1 - 1e-12))


def t_scales(n: int, nu: float, seed: int = 20261008) -> np.ndarray | None:
    """Variance scales s = (nu - 2) / chi2_nu (mean 1) for a Student-t scale mixture; None = Gaussian."""
    if not np.isfinite(nu):
        return None
    from scipy.stats import chi2
    u = qmc.Sobol(1, scramble=True, seed=seed).random(n)[:, 0]
    return (nu - 2.0) / chi2.ppf(np.clip(u, 1e-12, 1 - 1e-12), nu)


def win_probs(x: np.ndarray, cov: np.ndarray, z: np.ndarray, batch: int = 256,
              scales: np.ndarray | None = None) -> np.ndarray:
    """P(each coin finishes with the highest log return).

    x:   (W, K) current log returns since the start average (or anything additive to them)
    cov: (W, K, K) covariance of the remaining log-return increment, or (K, K) shared
    z:   (n, K) standard normal draws (common random numbers across windows)
    scales: optional (n,) per-draw variance multipliers (a scale mixture, e.g. `t_scales`);
         given the scale the increment is Gaussian, so the Rao-Blackwell step still applies
         with the conditional sd multiplied by sqrt(scale).
    Returns (W, K), rows summing to 1.
    """
    rs = np.ones(len(z)) if scales is None else np.sqrt(np.asarray(scales, dtype=float))
    x = np.atleast_2d(np.asarray(x, dtype=float))
    W, K = x.shape
    cov = np.asarray(cov, dtype=float)
    if cov.ndim == 2:
        cov = np.broadcast_to(cov, (W, K, K))
    out = np.empty((W, K))
    for s in range(0, W, batch):
        xs, cs = x[s:s + batch], cov[s:s + batch]
        L = np.linalg.cholesky(cs)                                   # (b,K,K)
        X = xs[:, None, :] + rs[None, :, None] * np.einsum("nk,bjk->bnj", z, L)  # (b,n,K)
        P = np.linalg.inv(cs)                                         # precision
        pd_ = np.diagonal(P, axis1=1, axis2=2)                        # (b,K)
        cond_sd = 1.0 / np.sqrt(pd_)
        dev = X - xs[:, None, :]                                      # (b,n,K)
        # E[X_i | X_-i] = x_i - (1/P_ii) sum_{j != i} P_ij dev_j
        Pdev = np.einsum("bik,bnk->bni", P, dev)                     # sum_j P_ij dev_j (incl j=i)
        cond_mean = xs[:, None, :] - (Pdev - pd_[:, None, :] * dev) / pd_[:, None, :]
        res = np.empty((X.shape[0], K))
        for i in range(K):
            others = np.delete(X, i, axis=2).max(axis=2)              # (b,n)
            res[:, i] = ndtr((cond_mean[:, :, i] - others)
                             / (cond_sd[:, None, i] * rs[None, :])).mean(axis=1)
        out[s:s + batch] = res
    out = np.clip(out, 1e-9, None)
    return out / out.sum(axis=1, keepdims=True)


def log_loss(p: np.ndarray, y: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """Multiclass log loss per row: -sum_i y_i log p_i (y sums to 1; a two-way tie is 0.5/0.5)."""
    p = np.clip(np.asarray(p, dtype=float), floor, 1.0)
    return -(np.asarray(y, dtype=float) * np.log(p)).sum(axis=1)


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Multiclass Brier per row: sum_i (p_i - y_i)^2."""
    return ((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2).sum(axis=1)


def clustered_mean_ci(values, clusters, level: float = 0.95) -> dict:
    """Mean of `values` with a cluster-robust (CR1) standard error and a t_{G-1} interval.

    Var(mean) = G/(G-1) * sum_g (sum_{i in g} (v_i - mean))^2 / N^2.
    """
    v = np.asarray(values, dtype=float)
    c = np.asarray(clusters)
    ok = np.isfinite(v)
    v, c = v[ok], c[ok]
    n = len(v)
    if n == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "se": float("nan"),
                "n": 0, "G": 0}
    m = v.mean()
    _, inv = np.unique(c, return_inverse=True)
    G = inv.max() + 1
    sums = np.bincount(inv, weights=v - m, minlength=G)
    if G < 2:
        se = float("nan")
    else:
        se = math.sqrt(G / (G - 1) * float((sums ** 2).sum())) / n
    q = student_t.ppf(0.5 + level / 2, max(G - 1, 1))
    return {"mean": float(m), "lo": float(m - q * se), "hi": float(m + q * se), "se": se,
            "n": int(n), "G": int(G)}


def twa_proxy(o, h, l, c):
    """Time-weighted-average proxy for one minute from its OHLC: (O + H + L + C) / 4.
    Fixed before looking at outcomes; the alternatives are reported, not selected."""
    return (np.asarray(o) + np.asarray(h) + np.asarray(l) + np.asarray(c)) / 4.0


def shrink_cov(S: np.ndarray, target_corr: np.ndarray | None = None, w: float = 0.0) -> np.ndarray:
    """Optional shrinkage of a covariance's correlation toward a target (w = weight on target)."""
    if w <= 0 or target_corr is None:
        return S
    sd = np.sqrt(np.diag(S))
    R = S / np.outer(sd, sd)
    R2 = (1 - w) * R + w * target_corr
    return R2 * np.outer(sd, sd)
