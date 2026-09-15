"""The registered test: outcome on (venue implied probability, Elo probability).

The registered quantity is the ELO COEFFICIENT and its game-clustered
interval. This module also computes a two-way player-clustered interval and
reports both, because a match is a DYAD and players recur, so a
match-clustered SE treats repeated players as independent and is optimistic
(docs/math/tabletennis-elo-harness.md §4). The registered one is what the
verdict is read from; the other is reported beside it, never quietly
substituted.

Logistic regression by IRLS in numpy rather than a library call, so the
sandwich has the working residuals and the hat weights it needs and the
estimator is visible in the file that claims it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Probabilities are clipped off the boundary before the logit: a venue price
#: of exactly 0 or 1 is not information, it is a settled market leaking in.
EPS = 1e-6


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


@dataclass(frozen=True)
class Fit:
    names: list[str]
    beta: np.ndarray
    se_game: np.ndarray            # one cluster per match (REGISTERED)
    se_player: np.ndarray          # two-way, on the dyad's two players
    n: int
    g_game: int
    g_player: int
    converged: bool
    iters: int

    def ci(self, i: int, which: str = "game", z: float = 1.959964
           ) -> tuple[float, float]:
        se = self.se_game if which == "game" else self.se_player
        return self.beta[i] - z * se[i], self.beta[i] + z * se[i]

    def excludes_zero(self, i: int, which: str = "game") -> bool:
        lo, hi = self.ci(i, which)
        return lo > 0.0 or hi < 0.0

    def deff(self, i: int) -> float:
        """Design effect of the player clustering against the match one.

        A large coefficient with deff ~1 is a DEFECT SIGNATURE: a player-linked
        effect whose clustering does not show up means the clustering is not
        being measured.
        """
        if self.se_game[i] <= 0:
            return float("nan")
        return float((self.se_player[i] / self.se_game[i]) ** 2)

    def g_eff(self, i: int) -> float:
        d = self.deff(i)
        return float("nan") if math.isnan(d) or d <= 0 else self.n / d


def _irls(X: np.ndarray, y: np.ndarray, iters: int = 100, tol: float = 1e-10
          ) -> tuple[np.ndarray, np.ndarray, bool, int]:
    beta = np.zeros(X.shape[1])
    for it in range(1, iters + 1):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1.0 - mu), 1e-12, None)
        XtWX = X.T @ (X * w[:, None])
        step = np.linalg.solve(XtWX, X.T @ (y - mu))
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            return beta, mu, True, it
    return beta, 1.0 / (1.0 + np.exp(-(X @ beta))), False, iters


def _meat(X: np.ndarray, resid: np.ndarray, groups) -> np.ndarray:
    """Sum of outer products of per-cluster score sums."""
    k = X.shape[1]
    m = np.zeros((k, k))
    s = X * resid[:, None]
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    for idx in by.values():
        u = s[idx].sum(axis=0)
        m += np.outer(u, u)
    return m


def fit(price_yes, elo_p, y, players_a, players_b, *,
        names=("const", "logit_price", "logit_elo")) -> Fit:
    """Logistic fit of `y` on the two logits, with both clustered sandwiches.

    Two-way on the dyad follows Cameron-Gelbach-Miller:
        V_a + V_b - V_ab
    where a and b index the two players of each match and ab is their pair.
    Clustering on the PAIR is what the match-level sandwich already is, so the
    subtraction removes the double-counted within-dyad term rather than an
    arbitrary intersection.
    """
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones_like(y), logit(price_yes), logit(elo_p)])
    beta, mu, conv, iters = _irls(X, y)

    bread = np.linalg.inv(X.T @ (X * np.clip(mu * (1 - mu), 1e-12, None)[:, None]))
    resid = y - mu

    pairs = [tuple(sorted((a, b))) for a, b in zip(players_a, players_b)]
    v_match = bread @ _meat(X, resid, list(range(len(y)))) @ bread
    v_a = bread @ _meat(X, resid, list(players_a)) @ bread
    v_b = bread @ _meat(X, resid, list(players_b)) @ bread
    v_ab = bread @ _meat(X, resid, pairs) @ bread
    v_two = v_a + v_b - v_ab

    def _se(v):
        d = np.diag(v).copy()
        d[d < 0] = np.nan            # a non-PSD two-way sandwich says so
        return np.sqrt(d)

    return Fit(list(names), beta, _se(v_match), _se(v_two), len(y),
               len(y), len(set(players_a) | set(players_b)), conv, iters)


def shuffle_within_price_bucket(price_yes, y, rng, *, width: float = 0.05):
    """The NULL: permute outcomes only among matches at (almost) the same price.

    Per `a-null-can-remove-the-wrong-thing`, a null that destroys PRICE
    CALIBRATION manufactures an artifact rather than removing one. Shuffling
    inside a narrow price bucket leaves realized-vs-price almost unchanged
    while severing any link between the outcome and the RATING, which is the
    only thing the primary test claims. The caller must verify the calibration
    curve survives; there is a test that fails if it does not.
    """
    price_yes = np.asarray(price_yes, dtype=float)
    y = np.asarray(y, dtype=float).copy()
    bucket = np.floor(price_yes / width).astype(int)
    for b in np.unique(bucket):
        idx = np.flatnonzero(bucket == b)
        if idx.size > 1:
            y[idx] = y[rng.permutation(idx)]
    return y
