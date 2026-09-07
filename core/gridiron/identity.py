"""c7's zero-parameter identity, sited on a spread ladder.

    z(t, L)  =  (mu_anchor + L) / sigma  +  [ Phi^-1(WP_t) - Phi^-1(WP_0) ]
    P(cover at L)  =  Phi( z )

No fitted parameters. `sigma` comes from `core.gridiron.scale`, read off the
traded ladder and never fitted to an outcome; `mu_anchor` is the pregame line;
the update is ESPN's win probability now against its value at kickoff.

Margin space, and why
---------------------
The alternative is to update additively in LOGIT space and map to points at the
end. Both are defensible and they give materially different answers, so the
choice is recorded here rather than left in the code.

**Margin space, because sigma cancels out of the update term.** Writing it in
three steps -- `mu_espn(t) = sigma * Phi^-1(WP_t)`, `mu_hat = mu_anchor +
[mu_espn(t) - mu_espn(0)]`, `z = (mu_hat + L)/sigma` -- the sigma introduced by
the first step is divided out again by the third, exactly:

    z = (mu_anchor + L)/sigma + [Phi^-1(WP_t) - Phi^-1(WP_0)]

**The update's contribution to `z` is `Phi^-1(WP_t) - Phi^-1(WP_0)` and does not
involve sigma at all.** So a sigma error is confined to the anchor's
contribution. In logit space it is not: the same inputs at sigma = 12/15.65/20
give z = 0.822/0.795/0.775 there, where the update itself is distorted by the
scale. Since B's shape test attributes error between the anchor and sigma, an
update that sigma can distort would mix the two.

The other half is that margin space puts the update in POINTS, the unit the
sigma surface returns and the unit B fixed the link to.

Frame
-----
`L` is the handicap ADDED to the quoted team's margin, matching the venue's
slug encoding: `mid = P(margin + L > 0)`, so `z` RISES with `L` and the crossing
sits at `L = -mu`. ce's `Phi((mu - L)/sigma)` is the same identity with the
opposite sign on `L`; a reader mixing the two gets a silently inverted ladder,
which is the B15 failure mode on a different axis.

Two assumptions, both named
---------------------------
**1. sigma is pregame and does not vary with the clock.** By instruction, since
the within-game series is n = 1 (`corr(reg_left, sigma) = +0.568` on 13 buckets
of one game, 15.23 down to 11.52).

**The error has a sign, and it is not the obvious one.** sigma falls as the
clock runs, so a pregame sigma is TOO LARGE in-game. It divides the ANCHOR term
only -- the update is sigma-free -- so it shrinks `(mu_anchor + L)/sigma`
toward zero and pulls `z` toward the pure-update value `Phi^-1(WP_t) -
Phi^-1(WP_0)`. **The identity therefore systematically UNDER-WEIGHTS THE ANCHOR
and OVER-WEIGHTS ESPN's update, increasingly so late in a game.**

It is NOT "pulled toward 0.5": that was the first guess and it is wrong,
because `(mu_anchor + L)` is negative on rungs above the crossing and positive
below, so shrinking it moves the price in opposite directions on the two wings.
A test asserting the toward-0.5 version failed, which is how this entry got
written. Saturday's sigma(t) relaxes it; `sigma_t` is accepted now, defaulting
to pregame, so adding it later cannot silently change anything already scored.

**2. The kickoff row must be a real kickoff.** This term has burned two people.
`display_clock` holds "15:00" in period 1 on rows already scoring 21-0, and
`reg_left` jumps BACKWARDS four times, once by a full 900s at a period
boundary. **Gate on period == 1 AND 0-0, never on a clock.** `kickoff_wp` does.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .scale import MarginScale

_E = 1e-6


def espn_margin_delta(wp_now, wp_kickoff):
    """The update, in standard deviations of margin. **Free of sigma.**"""
    a = np.clip(np.asarray(wp_now, dtype=float), _E, 1 - _E)
    b = np.clip(np.asarray(wp_kickoff, dtype=float), _E, 1 - _E)
    return norm.ppf(a) - norm.ppf(b)


def kickoff_wp(state: pd.DataFrame) -> pd.Series:
    """ESPN's win probability at a genuine kickoff: period 1, 0-0. No clock.

    A clock-based gate admits rows at 21-0 whose `display_clock` still reads
    15:00, and `reg_left` is not even monotone. Score is the honest gate: a
    game that has not scored has not been played.
    """
    s = state[(state.state == "in") & (state.period == 1)
              & (state.home_score == 0) & (state.away_score == 0)]
    s = s.dropna(subset=["espn_home_win_pct"]).sort_values("first_seen_at")
    return s.groupby("game_id").espn_home_win_pct.first()


def identity_z(line, mu_anchor, wp_now, wp_kickoff, scale: MarginScale,
               *, sigma_t: float | None = None):
    """`z` for a rung at `line`. `mu_anchor` is the quoted team's expected margin.

    `sigma_t` overrides the pregame scale; it defaults to pregame so that a
    time-varying sigma can be introduced later without changing any result
    already computed without one.
    """
    sigma = scale.sigma(mu_anchor) if sigma_t is None else float(sigma_t)
    return (mu_anchor + np.asarray(line, dtype=float)) / sigma \
        + espn_margin_delta(wp_now, wp_kickoff)


def identity_cover_probability(line, mu_anchor, wp_now, wp_kickoff,
                               scale: MarginScale, *, sigma_t: float | None = None):
    return norm.cdf(identity_z(line, mu_anchor, wp_now, wp_kickoff, scale,
                               sigma_t=sigma_t))


def ladder_fit_quality(ladder: pd.DataFrame, mu_anchor, wp_now, wp_kickoff,
                       scale: MarginScale, *, sigma_t: float | None = None) -> dict:
    """**The falsification.** Does the identity's ladder fit the traded one?

    A winner market prices ONE line, so any monotone update produces a valid
    probability and the model cannot be caught being wrong. A ladder prices ~40
    that must move together. This returns the identity's residual against the
    traded rungs alongside the venue's own free fit, which is the ceiling:

    * `r2_identity` -- variance explained by the identity's z, which has NO free
      parameters against this ladder.
    * `r2_venue` -- the ladder's own best-fit line, 2 free parameters. The
      identity cannot beat it and should not fall far short of it.
    * `rmse_z` -- residual in z units, the honest scale for "how wrong".

    A materially worse fit means the update is wrong in a way a single line
    could never have revealed. That is the whole reason for re-siting.
    """
    d = ladder[(ladder["mid"] > 0.05) & (ladder["mid"] < 0.95)]
    if len(d) < 4:
        return {"n_rungs": len(d), "r2_identity": np.nan, "r2_venue": np.nan,
                "rmse_z": np.nan}
    z_obs = norm.ppf(d["mid"].values)
    z_hat = identity_z(d.line.values, mu_anchor, wp_now, wp_kickoff, scale,
                       sigma_t=sigma_t)
    ss = np.sum((z_obs - np.mean(z_obs)) ** 2)
    slope, intercept = np.polyfit(d.line.values, z_obs, 1)
    z_free = intercept + slope * d.line.values
    return {"n_rungs": len(d),
            "r2_identity": float(1 - np.sum((z_obs - z_hat) ** 2) / ss) if ss else np.nan,
            "r2_venue": float(1 - np.sum((z_obs - z_free) ** 2) / ss) if ss else np.nan,
            "rmse_z": float(np.sqrt(np.mean((z_obs - z_hat) ** 2)))}
