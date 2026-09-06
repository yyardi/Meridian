"""Market-as-feature design matrix for CFB.

The architecture the public work actually validates
---------------------------------------------------
nflfastR and CFBD both take the market as an INPUT, not an opponent: the price
is a FEATURE and the model's job is to move it using state the market has not
repriced yet. Neither forecasts independently and diffs against the price.
PULSE does the opposite, and `lambda*` measured whether that independence buys
anything (it does not, at G=34).

So `mid` is a column here, alongside game state — not a baseline to beat.
See docs/math/public-wp-models.md for the survey this comes from.

Three joins, three namespaces
-----------------------------
ESPN game state and the venue price tape do not share an id. The bridge is
`cfb_game_map`, and the cohort is the INTERSECTION:

    state.game_id  ->  map.espn_game_id  ->  map.venue_game_id  ->  prices.game_id
       50 games            19 joinable            37                   99 games

**19 games join end to end, 11 at match_confidence >= 0.9.** "50 CFB games" and
"cfb_game_map 55/55" are both true and neither implies a 50-game cohort.

What this pipeline found on the 2026-09-05/06 cohort: NOTHING TO FIT
--------------------------------------------------------------------
The venue price recorder died 2026-09-05 22:08Z — the minute the CFB slate went
live — and was not restored until 2026-09-06 20:43Z. The export holds 1,016,039
quoted live rows, but they are overwhelmingly PREGAME; during the game windows
quoting collapses to hundreds per hour.

Joined against game state at an honest tolerance:

    tolerance    rows   games   median mid staleness
        30s        29      18            12s
       120s       120      18            60s
       300s       295      18           152s
       900s       875      18           443s

**29 usable rows.** Widening the tolerance buys rows only by pairing state with
a mid up to seven minutes stale, which is not a market feature, it is a memory
of one. So this cohort cannot fit the model, and no amount of care with the join
changes that — the prices were never recorded.

The pipeline is the deliverable and it is verified. It produces rows the moment
the tape and the state feed overlap, which they do from the 20:43Z restoration
onward. The measurement comes from Saturday, not from here.

The market feature does NOT come from `live_spread`
---------------------------------------------------
`espn_cfb_game_state.live_spread` is constant within 46 of 50 games — a pregame
line carried forward under a live-sounding name. It is not a price series. The
market feature is the mid of `best_bid`/`best_ask` from the venue tape.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Regulation is 4 x 15 minutes. Verified against the data rather than assumed:
#: clock_s spans 0-900 in every period 1-4, and every OT row carries '0:00'.
QUARTER_SECONDS = 900.0
REGULATION_SECONDS = 4 * QUARTER_SECONDS


def clock_seconds(display_clock) -> float:
    """`'5:04'` -> 304.0. Returns NaN for anything else, never a guess."""
    if not isinstance(display_clock, str) or ":" not in display_clock:
        return float("nan")
    mins, _, secs = display_clock.partition(":")
    try:
        return int(mins) * 60 + float(secs)
    except ValueError:
        return float("nan")


def regulation_left(period, clock_s) -> float:
    """Seconds left in regulation. **OT is pinned to 0, never extrapolated.**

    College overtime is untimed — possession-based, no clock — and every OT row
    in this feed carries `'0:00'`. Treating period 5 as `(4-5)*900` would
    manufacture negative time, which is the sign trap in this transform.
    """
    if not np.isfinite(period):
        return float("nan")
    if period >= 5:
        return 0.0
    return (4 - period) * QUARTER_SECONDS + clock_s


def build(state: pd.DataFrame, prices: pd.DataFrame, game_map: pd.DataFrame,
          *, min_confidence: float = 0.0, tolerance_s: float = 30.0) -> pd.DataFrame:
    """One row per (game, observation) with the market mid joined as a feature.

    `min_confidence` filters `cfb_game_map`; state it whenever a result is
    quoted, since 19 games join at 0.0 and only 11 at 0.9.

    The price is joined BACKWARD in time with a tolerance: each state row takes
    the most recent mid at or before it, never a later one. A forward join would
    let a price that moved *after* the state was observed inform the row, which
    is the leak that manufactures skill.
    """
    m = game_map[game_map.match_confidence >= min_confidence]
    m = m[["espn_game_id", "venue_game_id"]].drop_duplicates("espn_game_id")

    s = state[state.state == "in"].copy()
    s["clock_s"] = s.display_clock.map(clock_seconds)
    s["reg_left"] = [regulation_left(p, c) for p, c in zip(s.period, s.clock_s)]
    s["score_diff"] = s.home_score - s.away_score
    s["timeout_diff"] = s.away_timeouts_used - s.home_timeouts_used
    s = s.merge(m, left_on="game_id", right_on="espn_game_id", how="inner")

    p = prices.dropna(subset=["best_bid", "best_ask", "game_id"]).copy()
    p = p[p.is_live.astype(str).str.lower().isin(("t", "true", "1"))]
    # mid for the model; raw bid/ask kept because money scoring needs the price
    # actually payable on each side — a mid cannot say which you would have hit.
    p["mid"] = (p.best_bid + p.best_ask) / 2.0
    p["venue_game_id"] = p.game_id.astype(int)

    out = []
    for vid, sg in s.groupby("venue_game_id"):
        pg = p[p.venue_game_id == vid]
        if pg.empty:
            continue
        sg = sg.sort_values("first_seen_at")
        pg = pg.sort_values("captured_at")
        joined = pd.merge_asof(
            sg, pg[["captured_at", "mid", "best_bid", "best_ask",
                    "is_live", "market_slug"]],
            left_on="first_seen_at", right_on="captured_at",
            direction="backward",                      # never a later price
            tolerance=pd.Timedelta(seconds=tolerance_s),
        )
        out.append(joined)
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True).dropna(subset=["mid", "reg_left"])
