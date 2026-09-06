"""The margin-scale surface: how wide is the margin distribution the ladder prices?

A spread ladder is an empirical margin CDF. ~40 rungs, each a `(line, P(cover))`
pair, and under any location-scale family

    link(mid) = (mu + L) / sigma          -> LINEAR in L, slope 1/sigma

so the ladder both names the distribution and measures its scale. That is what
makes this a MEASUREMENT rather than a model: **every value here is read off
the traded ladder and none is fitted to an outcome.** No game result enters this
module. It needs no `cfb_game_map`, no settled games and no kickoff.

Why it exists
-------------
c7's identity updates a win probability. A spread market prices
`P(margin > -L)`, so moving the identity onto a ladder needs the scale of the
margin distribution -- and `sigma` is exactly where a zero-parameter identity
would quietly become a fitted model if it were assumed instead of measured.
See docs/math/spread-transfer.md.

Which link
----------
Measured on 14 pregame ladders, interior rungs only: probit (normal margin)
median R2 **0.99210**, logit (logistic margin) **0.99162**, probit winning 8 of
14. **They are not distinguishable.** The identity's logit-additivity is itself
a distributional assumption and over the tradeable range the ladder says it
costs nothing. Probit is used here because it won by a hair; nothing depends on
that choice within `0.05 < mid < 0.95`.

What is measured, and what is NOT
---------------------------------
**sigma varies with the line, and that IS measured.** Fitted by this module on
the 09-05 pregame ladders:

    sigma = 13.19 + 0.1182*|line|      n = 14 games, corr = +0.948

A single sigma = 15.65 misprices a 40-point game by ~2.3 points of scale.
Bigger favourites carry more margin variance, and a constant sigma is therefore
a mixture -- biased hardest where the anchor is most informative.

**The relation survives every filter choice**, which is the sensitivity check
that matters, since the cohort is 14 games:

    r2 floor   games   sigma(line)                    corr
      none       14    13.19 + 0.1182*|line|        +0.948
      0.95       13    13.30 + 0.1116*|line|        +0.942
      0.97       12    13.62 + 0.0939*|line|        +0.915
      0.99        8    13.06 + 0.1232*|line|        +0.974

Intercept 13.1-13.6, slope 0.094-0.123 across all of them.

**A side effect worth knowing: fitting the ladder retires the bracket filter.**
`fit.spread_anchor` interpolates to the P(YES)=0.5 crossing and therefore needs
the ladder to bracket it, which dropped 2 games in 14. A probit fit recovers
the crossing analytically from all rungs, so it needs no bracketing. It costs
a little accuracy against DraftKings and buys coverage:

    interpolated, bracket filter    12 games   mean |diff| 0.41   worst 1.67
    probit fit, no filter           14 games   mean |diff| 0.68   worst 2.59
    probit fit, r2 >= 0.95          13 games   mean |diff| 0.53   worst 1.88

Almost all the degradation is one game with the worst-fitting ladder
(r2 0.9362, off by 2.6 points). That is why `r2` is returned per game.

**sigma also varies with time remaining, and that is NOT measured.** It has been
observed on ONE game (13 five-minute buckets, `corr(reg_left, sigma) = +0.568`,
15.23 at 2933s down to 11.52 at 1884s), with two buckets fitting poorly
(R2 0.89, 0.93). Direction is plausible and the magnitude is not established.
**This module deliberately does not expose a time argument.** A two-argument
surface with n=12 on one axis and n=1 on the other would read as equally
supported in both directions, and a later reader could not tell which half was
one game. Saturday's slate supplies the second axis.

An earlier version of the time series ran to sigma=10.64. That was wrong: the
buckets past 21:37Z reused the last game-state row after the ESPN recorder
stopped, so the decay was being read against a clock that had stopped
advancing. The clock is also non-monotone before that -- `reg_left` jumps
BACKWARDS four times, once by a full 900s at a period boundary. Any use of game
clock as an axis has to enforce monotonicity first.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

INTERIOR = (0.05, 0.95)     # the venue clips at 0.015/0.985; clipped rungs are not quotes
MIN_RUNGS = 6


def ladder_scale(ladders: pd.DataFrame, *, interior: tuple[float, float] = INTERIOR,
                 min_rungs: int = MIN_RUNGS) -> pd.DataFrame:
    """Fit `sigma` per game from `(game, line, mid)` rows. One row out per game.

    `mid` is P(the FIRST-named team covers `line`); the frame does not matter to
    `sigma`, which is a width. `implied_line` is returned in that same frame and
    does need orienting before use — see `fit.AWAY_TEAM_IS_FIRST`.

    Returns `game`, `sigma`, `r2`, `n_rungs`, `implied_line`. **`r2` is returned,
    not filtered on**, so a badly-fitting ladder is visible to the caller rather
    than silently dropped or silently kept.
    """
    lo, hi = interior
    out = []
    for g, d in ladders.groupby("game"):
        d = d[(d["mid"] > lo) & (d["mid"] < hi)]
        if len(d) < min_rungs or d.line.nunique() < 2:
            continue
        z = norm.ppf(d["mid"].values)
        slope, intercept = np.polyfit(d.line.values, z, 1)
        if slope <= 0:                      # a ladder must rise with the line
            continue
        pred = intercept + slope * d.line.values
        ss = np.sum((z - np.mean(z)) ** 2)
        out.append({"game": g, "sigma": 1.0 / slope,
                    "r2": float(1 - np.sum((z - pred) ** 2) / ss) if ss else np.nan,
                    "n_rungs": len(d), "implied_line": -intercept / slope})
    return pd.DataFrame(out, columns=["game", "sigma", "r2", "n_rungs", "implied_line"])


class MarginScale:
    """`sigma` as a function of the line, fitted across games. No outcomes used.

    Refuses to extrapolate: outside the `|line|` range it was fitted on, it
    CLAMPS to the nearest fitted end rather than continuing the trend. The
    relation is linear over 3-41 points because that is where the games were;
    nothing measured says it stays linear at 60.
    """

    def __init__(self, intercept: float, slope: float, *, line_range: tuple[float, float],
                 n_games: int, corr: float):
        self.intercept, self.slope = intercept, slope
        self.line_range, self.n_games, self.corr = line_range, n_games, corr

    @classmethod
    def fit(cls, scales: pd.DataFrame, *, line_col: str = "implied_line",
            min_games: int = 6) -> "MarginScale":
        d = scales.dropna(subset=["sigma", line_col])
        if len(d) < min_games:
            raise ValueError(
                f"{len(d)} games is not enough to fit a slope (need {min_games}). "
                "A relation fitted on fewer is a line through noise."
            )
        x = d[line_col].abs().values
        slope, intercept = np.polyfit(x, d.sigma.values, 1)
        return cls(float(intercept), float(slope), line_range=(float(x.min()), float(x.max())),
                   n_games=len(d), corr=float(np.corrcoef(x, d.sigma.values)[0, 1]))

    def sigma(self, line: float | np.ndarray) -> float | np.ndarray:
        a = np.clip(np.abs(np.asarray(line, dtype=float)), *self.line_range)
        out = self.intercept + self.slope * a
        return float(out) if np.ndim(line) == 0 else out

    def __repr__(self) -> str:
        return (f"MarginScale(sigma = {self.intercept:.2f} + {self.slope:.4f}*|line|, "
                f"n={self.n_games}, corr={self.corr:+.3f}, "
                f"clamped to |line| in {self.line_range[0]:.1f}..{self.line_range[1]:.1f})")


def cover_probability(line: float | np.ndarray, expected_margin: float,
                      scale: MarginScale) -> float | np.ndarray:
    """P(margin > -line) for the team the line is quoted on.

    This is the map the identity needs: a location from the anchor, a width from
    the ladder. `expected_margin` is that team's expected margin, so a 20-point
    favourite is +20.
    """
    return norm.cdf((expected_margin + np.asarray(line, dtype=float))
                    / scale.sigma(expected_margin))
