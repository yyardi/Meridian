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
⛔ **THE LINE DEPENDENCE FAILED A POWERED OUT-OF-SAMPLE TEST, 2026-09-07. USE
THE LEVEL, NOT THE SLOPE.** Three games gated on `true_kickoff` (period 1, 0-0)
with closing ladders inside the <=900s window, on a board that was quoting:

    game    rungs   sigma      R2    |line|    slope 0.1182 predicts
    16453      34   15.98  0.9778       8.1                    14.15
    16488      23   15.61  0.9871      22.5                    15.85
    16486      25   15.98  0.9959      23.9                    16.01

    fitted slope on these three   -0.0105     (shipped: +0.1182)
    predicted rise 8.1 -> 23.9     1.87 pts   observed  0.00 pts
    TOTAL spread of all 3 sigma    0.37 pts
    predicted effect               5.0x the ENTIRE observed range

    (An earlier version of this block quoted "signal-to-scatter 9.7x, the test
    HAD power". **That overstated it and B caught it**: n = 3 with two fitted
    parameters leaves ONE degree of freedom, so a residual sd is barely a
    quantity and a ratio built on it is not a power statement. The lines above
    use no fitted dispersion -- the predicted effect is five times the entire
    observed spread, which needs no distributional assumption to read.)

Mean absolute error: **flat sigma = 15.86 gives 0.16 pts; the shipped relation
gives 0.70.** The level reproduces on a fresh cohort; the slope does not, and
this cohort predicts an effect five times larger than the entire observed spread.

**Not refitted on n = 3.** The coefficients below are unchanged so the
supersession trail stays legible, and `sigma()` clamps, so a wrong slope costs
~2 points of scale at the extremes rather than diverging. **Prefer
`MarginScale.flat()`.** The line dependence below is the historical fit and
should be read as unsupported.

**How it survived four months of looking right:** it was fitted on frozen
mid-game ladders where lopsided games had more one-sided rungs, and a tail-only
probit fit inflates sigma. My symmetric-window control argued against exactly
that mechanism — and ran on the same 14 contaminated ladders, so it never had
the power to clear itself.

**sigma varies with the line, and that WAS the measurement.** Fitted by this
module on the 09-05 pregame ladders:

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

**And it is not an artifact of one-sided ladders**, which is the confound worth
naming: a lopsided game's ladder carries rungs only BELOW its crossing, and a
tail-only fit would inflate sigma if the true tail were fatter than normal --
manufacturing exactly this positive slope. Refitting with every game trimmed to
a SYMMETRIC window around its own crossing:

    window     games   slope    intercept   corr
    none         14    0.1182     13.19     0.948
    +/-30 pts     9    0.1171     13.27     0.862
    +/-20 pts     9    0.1256     13.09     0.897
    +/-12 pts     9    0.1180     13.22     0.868

The slope is unchanged. **But symmetry costs the lopsided games**: the line
range collapses from 7.9-49.7 to 7.8-27.7. So the relation is independently
confirmed between roughly 8 and 28 points of spread, and beyond 28 it rests on
ladders that are one-sided by construction -- the venue lists a fixed span of
lines, so a game whose crossing sits at 49.7 has no rungs above it.

**Power lives in the wings, and the wings are where the board is thinnest.**
Under probit, sigma has EXACTLY ZERO effect at the money and peaks about one
sigma out (~15.7 points). Interior rungs by distance from their own crossing:

    |L - L0| >=  5    243 of 313   (77.6%)
    |L - L0| >= 10    184          (58.8%)
    |L - L0| >= 15    126          (40.3%)
    |L - L0| >= 25     24           (7.7%)

Requiring >=3 rungs at |L - L0| >= 10 on BOTH sides admits **4 of 14 games**,
and all four are near-even (crossing 7.9-13.7). Requiring it on at least one
side admits all 14. A two-sided rule and a wide line range are in direct
tension on this board.

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

# PROVENANCE: the 09-05 ladders these constants were fitted on were selected by
# a "kickoff" that was the ESPN recorder starting (22:08Z, identical for all 14
# games, every one already in progress). They survive only because the board was
# FROZEN -- 0.0% of 575 markets moved -- so the quotes were still pregame. Use
# `fit.true_kickoff` for any new cohort; see docs/math/spread-transfer.md.
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
    def flat(cls, sigma: float, *, n_games: int = 3) -> "MarginScale":
        """A constant scale, which is what the gated 2026-09-07 cohort supports.

        Three properly-gated closing ladders spanning |line| 8.1 to 23.9 gave a
        fitted slope of -0.0105 against the shipped +0.1182, with a
        signal-to-scatter ratio of 9.7 -- so the flat reading is not merely
        consistent, it is preferred by mean absolute error 0.16 against 0.70.
        """
        return cls(float(sigma), 0.0, line_range=(0.0, 60.0),
                   n_games=n_games, corr=0.0)

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

    def sigma(self, game_spread: float | np.ndarray) -> float | np.ndarray:
        """Width of THIS GAME's margin distribution, in points.

        **The argument is the GAME's spread, never a rung's line.** For one
        game there is exactly one sigma — it is the width of one margin
        distribution, and every rung on that ladder is priced from it. Feeding
        a rung's line back in would give a different sigma per rung, which
        denies the single-distribution assumption the ladder is being used to
        test. The line-dependence measured here is ACROSS games, not across
        rungs within one.

        A scalar per game is therefore sufficient, once it is computed from
        that game's own spread.
        """
        a = np.clip(np.abs(np.asarray(game_spread, dtype=float)), *self.line_range)
        out = self.intercept + self.slope * a
        return float(out) if np.ndim(game_spread) == 0 else out

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
