"""The nflfastR-shaped fit: market as a FEATURE, plays as state, held out by game.

Run it:  python -m core.gridiron.fit

What this is and is not
-----------------------
It is a model that exists and runs forward on a slate. **It is not a result and
no score is printed**, because the cohort cannot support one: 10 games with a
0.900 home-win rate, against a minimum detectable effect an order of magnitude
above anything this programme produces. The measurement comes from slates not
yet played.

Why the market anchor is a frozen pregame number
------------------------------------------------
nflfastR's market feature is `spread_line` — *"the closing spread line for the
game"*, a per-game CONSTANT — decayed by time into `spread_time`; `vegas_wp` is
*"win probability taking into account PRE-GAME spread"*. It is not a live price.

This matters because the 2026-09-05 venue tape was frozen before kickoff and
dead after it, and a live-mid design yields 29 usable rows. The reference
architecture never wanted a live mid. Using the last pregame moneyline mid
(<= 15 min before kickoff) as a per-game anchor yields 1,792 plays over 10 games
from the same data.

**A frozen quote is not necessarily a TAKEABLE quote.** The pregame tape shows
`pct_moved = 0.0` at full write cadence, and nothing in it distinguishes a live
price nobody moved from a stale artifact of the venue freeze. So this fit
answers *"is there forecast skill against the closing line"* and leaves
*"could we have transacted at it"* open. The second is where the money is.

Two anchors, and market COUNT was the wrong denominator
-------------------------------------------------------
The CFB board carries **70 moneyline markets against 8,088 spread markets**,
which reads as "the spread is the robust anchor". Measured in GAMES it is the
other way round:

    full-game SPREAD anchor      12 games
    MONEYLINE anchor             19 games

A moneyline is **one market per game**; a spread is **~41 lines per game**. So
8,088 spread markets are a deeper book over FEWER games, and the count ratio
says nothing about coverage. Games is the denominator that matters.

The spread anchor also needs the quoted mids to BRACKET 0.5 to interpolate an
implied line, which drops games whose lines sit all one side.

**And only 4,553 of the 8,088 spread markets are full-game** — the rest are
1h/2h/1q/2q/3q/4q. An unfiltered spread anchor silently mixes first-quarter
lines into a game-level feature. Moneyline is all full-game (132/132), so that
anchor was safe by construction.

**So: prefer the SPREAD anchor for fidelity — it is nflfastR's actual feature,
a point spread — and fall back to the MONEYLINE for coverage.** Neither
dominates; the fidelity argument and the coverage argument point opposite ways
and the code carries both rather than choosing once.

Joins
-----
* plays join on **`wall_clock`, never `first_seen_at`** — the recorder started
  22:08Z and backfilled to 20:18Z, so `first_seen_at` is when we SAW a play, not
  when it happened. Using it truncates two hours and misdates the rest.
* the anchor is oriented to HOME via the slug's first team against the map's
  home name (V14's YES-frame), not assumed.
* outcome cohort is `post` rows plus untied `P4 0:00`, per docs/math/cfb-state-substrate.md.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .features import scrimmage_plays

EXPORTS = "backups/exports/"
ANCHOR_MAX_STALE_S = 900.0          # 15 min before kickoff; p50 is ~1 min
DECAY = 3.0                         # nflfastR decays the line by elapsed share
FEATURES = ["anchor_time", "anchor_logit", "reg_left", "score_diff",
            "down", "distance", "yards_to_goal", "drive_is_home_offense"]
_E = 1e-6

# The venue names an event AWAY-FIRST and its contract pays on that first team.
#
#   `cfb-washst-wash-2026-09-06`  is Washington State AT Washington.
#
# Measured two ways, because this frame has silently inverted results before:
#   * over the 73-row computed map, the slug's first team resolved to the AWAY
#     side 53 times, to the HOME side **0 times**, ambiguous on 20 (short codes
#     that appear in both names). No counterexample.
#   * on 2026-09-06 the one moneyline `aec-cfb-washst-wash-2026-09-06` quoted
#     mid **0.053** with Washington the heavy home favourite. 0.053 is
#     Washington STATE's number.
#
# So the home probability is `1 - mid`, unconditionally, and the home spread is
# the negation of the ladder crossing.
#
# This replaces a comparison — `event_slug.split("-")[1] == market_slug
# .split("-")[2]` — that read like an orientation test and was measured
# **True on 1,451,379 of 1,451,379 rows across 5,754 slugs**. It had no else
# branch in practice: the moneyline anchor was the AWAY team's win probability
# labelled `home` in every game, and the spread anchor was right by accident
# because its always-taken branch happened to be the correct one.
AWAY_TEAM_IS_FIRST = True


def _logit(x):
    x = np.clip(x, _E, 1 - _E)
    return np.log(x / (1 - x))


def assert_away_first(game_map: pd.DataFrame) -> None:
    """Raise if any event_slug names the HOME team first.

    The orientation is a constant, so nothing in the arithmetic can notice it
    changing. This is the thing that would notice. Rows whose short code is
    ambiguous between the two names are skipped rather than guessed — 20 of 73
    on the computed map — so this catches a flip, not a near-miss.
    """
    need = {"event_slug", "home_espn_name", "away_espn_name"}
    if not need.issubset(game_map.columns):
        return
    def _pfx(code, name):
        c = re.sub(r"[^a-z]", "", str(code).lower())
        n = re.sub(r"[^a-z]", "", str(name).lower())
        return next((k for k in range(len(c), 1, -1) if c[:k] in n), 0)
    bad = []
    for _, r in game_map.iterrows():
        parts = str(r.event_slug).split("-")
        if len(parts) < 3:
            continue
        h, a = _pfx(parts[1], r.home_espn_name), _pfx(parts[1], r.away_espn_name)
        if h > a:
            bad.append(r.event_slug)
    if bad:
        raise ValueError(
            f"event_slug names the HOME team first in {len(bad)} row(s) "
            f"({bad[:3]}). AWAY_TEAM_IS_FIRST is false here and every anchor "
            "in this module is inverted for those games."
        )


def _truthy(s):
    return s.astype(str).str.lower().isin(("t", "true", "1"))


def true_kickoff(state: pd.DataFrame) -> pd.Series:
    """First state row that is genuinely a kickoff: period 1, score 0-0.

    **Replaces `state[state.state=="in"].groupby(...).first_seen_at.min()`,
    which is not a kickoff — it is the first moment the RECORDER SAW the game.**

    On 2026-09-05 those are catastrophically different and the difference was
    invisible: all 14 games in the anchor cohort returned a "kickoff" of
    22:08-22:09Z, **the same minute**, because that is when the ESPN recorder
    started. ESPN's own rows say every one of those games was already in
    progress -- period 2 at 14-0, period 4 at 49-3, period 4 at 45-3. **Zero of
    14 was a genuine kickoff.**

    The anchor window (<= 900s before "kickoff") therefore selected ladders from
    21:54-22:08Z, which is mid-game for all 14, and labelled them pregame.

    **The measurements came out right anyway, and that is the dangerous part.**
    Those ladders were completely frozen: across 575 full-game spread markets
    and a median of 27 snapshots each, **0.0% showed more than one distinct
    mid**. A frozen board still carries its last pregame quotes, so a pregame
    sigma was recovered from a selector that had asked for the wrong rows. On a
    board that is actually quoting -- Saturday -- the same selector returns
    in-game ladders under a pregame label, with no error and no null.

    Returns nothing for a game never observed at 0-0. That is honest: a game we
    first saw at 49-3 has no recoverable kickoff, and a fallback would be the
    original bug wearing a helper's name.
    """
    s = state[(state.state == "in") & (state.period == 1)
              & (state.home_score == 0) & (state.away_score == 0)]
    return s.groupby("game_id").first_seen_at.min().rename("kickoff")


def settlement_hazard(state: pd.DataFrame) -> pd.DataFrame:
    """Games where the FIRST `post` row disagrees with the last recorded row.

    Run this on every new export before trusting `outcome_cohort`. It exists
    because of B's argument, which is better than the test I first wrote: a
    synthetic fixture pins the BEHAVIOUR and passes forever, including after the
    substrate stops exercising the hazard. **A check that can no longer fail has
    gone blind, and nothing in a green suite says so.** This one reports whether
    the phenomenon is still present in the data, and names the games.

    On `espn_cfb_game_state_20260906T174104Z`: **2 of 28** games with a `post`
    row, and on 401858428 the WINNER changes (first post 7-12, last row 13-12).
    An empty result on a later export means either ESPN stopped un-posting or
    the export stopped capturing it — both worth knowing, neither safe to assume.
    """
    s = state.sort_values(["game_id", "first_seen_at"])
    rows = []
    for g, d in s.groupby("game_id"):
        p = d[d.state == "post"]
        if p.empty:
            continue
        first_m = p.home_score.iloc[0] - p.away_score.iloc[0]
        last_m = d.home_score.iloc[-1] - d.away_score.iloc[-1]
        if first_m != last_m:
            rows.append({"game_id": g, "first_post_margin": first_m,
                         "last_row_margin": last_m,
                         "winner_changes": bool((first_m > 0) != (last_m > 0))})
    return pd.DataFrame(rows, columns=["game_id", "first_post_margin",
                                       "last_row_margin", "winner_changes"])


def outcome_cohort(state: pd.DataFrame) -> pd.DataFrame:
    """Settled games: a `post` row, or a decided regulation end we watched to.

    **The clock branch is the fourth instance of the same defect and it is load
    bearing** -- it supplies **14 of 42** games on the 09-05 tape, where the
    recorder stopped before ESPN flipped the game to `post`. Those are real
    finals (66-21, 50-0, 34-18) and dropping them would cost a third of the
    cohort, so the branch stays and is guarded instead.

    **What makes it unsafe: `period == 4, display_clock == "0:00"` does not mean
    the game is over.** On this tape 7 games carry such a row followed by more
    live action, so the predicate alone can fire mid-game.

    **CORRECTION, and the real hazard is elsewhere and worse.** I first reported
    this as a sign flip across a `P4 0:00` row on game 401858428, margin -5 to
    +1. **That attribution was wrong** -- the clock rows on that game are a
    clean 7-12 throughout. The flip is across the `post` row:

        02:54:26Z  post   7-12     <- ESPN calls it final
        02:54:52Z  in    13-12     <- reverts to live, home has scored
        02:55:43Z  post  13-12     <- finals again, OTHER TEAM WON

    **`state == "post"` is not final. ESPN un-posts.** Two of 28 games change
    margin at or after their first `post` row, and on this one it changes the
    WINNER. Anyone taking *the first* `post` row as the outcome names the wrong
    team on 1 game in 28.

    What saves us is again the row selector rather than the predicate: `tail(1)`
    takes the LAST row, which is the corrected `post`. Both hazards therefore
    have the same shape -- a predicate that is unsafe alone, rescued by an
    undocumented `tail(1)`. The guard below makes the clock branch explicit; the
    `post`-revert hazard is handled only by `tail(1)`, which is now stated here
    so nobody reimplements this with `first()`.
    """
    s = state.sort_values(["game_id", "first_seen_at"])
    last = s.groupby("game_id").tail(1).assign(
        margin=lambda d: d.home_score - d.away_score)
    live = s[s.state == "in"]
    max_period = live.groupby("game_id").period.max()
    last_live = live.groupby("game_id").first_seen_at.max()
    ok_clock = (
        (last.period == 4) & (last.display_clock == "0:00") & (last.margin != 0)
        & (last.game_id.map(max_period) <= 4)                 # no overtime
        & (last.first_seen_at >= last.game_id.map(last_live))  # nothing live after
    )
    coh = last[(last.state == "post") | ok_clock][["game_id", "margin"]]
    return coh


def design(plays, prices, game_map, state) -> pd.DataFrame:
    """One row per play, with the pregame market anchor joined per game."""
    coh = outcome_cohort(state)
    coh = coh.assign(y=(coh.margin > 0).astype(int))

    m = game_map[["espn_game_id", "venue_game_id", "event_slug"]].drop_duplicates("espn_game_id")
    kick = true_kickoff(state)

    q = prices.dropna(subset=["best_bid", "best_ask", "game_id"]).copy()
    q = q[q.market_slug.str.startswith("aec")]          # moneyline = win probability
    q["vid"] = q.game_id.astype(int)
    q["mid"] = (q.best_bid + q.best_ask) / 2.0

    d = (scrimmage_plays(plays).merge(coh, on="game_id")
              .merge(m, left_on="game_id", right_on="espn_game_id")
              .merge(kick, on="game_id"))
    a = q.merge(d[["venue_game_id", "kickoff"]].drop_duplicates(),
                left_on="vid", right_on="venue_game_id")
    a = a[(a.captured_at < a.kickoff)
          & ((a.kickoff - a.captured_at).dt.total_seconds() <= ANCHOR_MAX_STALE_S)]
    a = a.sort_values("captured_at").groupby("vid").tail(1)[["vid", "mid", "market_slug"]]
    d = d.merge(a, left_on="venue_game_id", right_on="vid")

    # the quote is the FIRST-named team's, and that team is the away side
    assert_away_first(game_map)
    d["anchor"] = 1 - d["mid"]

    d["reg_left"] = np.where(_truthy(d.is_overtime), 0.0,
                             (4 - d.period) * 900 + d.clock_minutes * 60 + d.clock_seconds)
    d["score_diff"] = d.home_score - d.away_score
    d["drive_is_home_offense"] = _truthy(d.drive_is_home_offense).astype(int)
    d["anchor_logit"] = _logit(d.anchor)
    d["anchor_time"] = d.anchor_logit * np.exp(-DECAY * (1 - d.reg_left / 3600.0))
    return d.dropna(subset=["anchor", "reg_left", "down", "distance", "yards_to_goal"])


def fit_by_game(d: pd.DataFrame):
    """Leave-one-game-out. Returns (oos predictions, folds trained, n games).

    A fold is skipped when the remaining games carry only one outcome — at a
    0.900 home rate that happens, and skipping is honest where imputing is not.
    """
    X = d[FEATURES].astype(float).values
    y, g = d.y.values, d.game_id.values
    oos = np.full(len(d), np.nan)
    trained = 0
    for gg in np.unique(g):
        tr, te = g != gg, g == gg
        if len(np.unique(y[tr])) < 2:
            continue
        oos[te] = LogisticRegression(max_iter=2000, C=0.5).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        trained += 1
    return oos, trained, len(np.unique(g))


FULL_GAME_SPREAD = re.compile(
    r"^asc-[a-z]+-([a-z0-9]+)-([a-z0-9]+)-\d{4}-\d{2}-\d{2}-(neg|pos)-(\d+)(?:pt(\d))?$"
)


def spread_anchor(prices: pd.DataFrame, game_map: pd.DataFrame,
                  kickoff: pd.Series) -> pd.DataFrame:
    """Market-implied full-game spread per game, home-oriented, in points.

    nflfastR's `spread_line` is a POINT SPREAD, so this is the faithful anchor.
    Derived by interpolating the quoted ladder to the line where P(YES) = 0.5
    rather than taking any single listed line — the crossing is the market's
    own estimate and a listed line is only the nearest rung to it.

    The regex pins **full-game** markets: only 4,553 of 8,088 `asc-` markets are
    full-game; 1h/2h/1q/2q/3q/4q share the prefix and would otherwise be mixed
    into a game-level feature with no error and no null — a wrong number in a
    right-shaped column. Pinned by `test_quarter_and_half_spreads_are_excluded`
    rather than by this paragraph, because construction-safety is invisible both
    when it holds and when it breaks.

    **The bracket filter is not free and is not silent here.** Measured on the
    2026-09-05 board: 14 games reach this stage, **12 keep an anchor and 2 are
    dropped because their ladder does not bracket 0.5** — 14% of the stage, on a
    cohort where 12 is the whole result. Games with fewer than 2 quoted lines
    would also drop; none did.
    """
    assert_away_first(game_map)
    q = prices.dropna(subset=["best_bid", "best_ask", "game_id"]).copy()
    q["vid"] = q.game_id.astype(int)
    q["mid"] = (q.best_bid + q.best_ask) / 2.0
    parts = q.market_slug.str.extract(FULL_GAME_SPREAD)
    q = q[parts[0].notna()].copy()
    q["first_team"] = parts[0]
    q["line"] = (np.where(parts[2] == "neg", -1.0, 1.0)
                 * (parts[3].astype(float) + parts[4].fillna(0).astype(float) / 10))

    m = (game_map[["espn_game_id", "venue_game_id", "event_slug"]]
         .drop_duplicates("espn_game_id")
         .merge(kickoff, left_on="espn_game_id", right_index=True))
    q = q.merge(m, left_on="vid", right_on="venue_game_id")
    q = q[(q.captured_at < q.kickoff)
          & ((q.kickoff - q.captured_at).dt.total_seconds() <= ANCHOR_MAX_STALE_S)]
    last = q.sort_values("captured_at").groupby(["vid", "market_slug"]).tail(1)

    rows = []
    for vid, g in last.groupby("vid"):
        g = g.sort_values("line")
        if len(g) < 2 or not (g["mid"].min() < 0.5 < g["mid"].max()):
            continue                      # ladder does not bracket the crossing
        # the ladder is quoted on the FIRST-named team, who is the away side,
        # so the crossing is the AWAY line and the home line is its negation
        crossing = float(np.interp(0.5, g["mid"].values, g.line.values))
        rows.append({"espn_game_id": g.espn_game_id.iloc[0],
                     "home_spread": -crossing,
                     "n_lines": len(g)})
    return pd.DataFrame(rows)


def espn_spread_anchor(state: pd.DataFrame) -> pd.DataFrame:
    """Home-oriented full-game spread in POINTS, from ESPN's `live_spread`.

    This is the anchor to prefer on a real slate, and the reason is coverage
    rather than quality — the two anchors are the same number:

        corr with the venue ladder   +0.999   (12 overlapping games)
        mean |difference|             0.41 pts
        worst single game             1.67 pts

    It costs none of what the venue path costs. `live_spread` lives in the same
    ESPN-keyed table as the game state, so it needs **no `cfb_game_map`, no
    full-game slug filter and no bracket filter**: 50 of 50 games against the
    venue ladder's 12. It is also a real book — `line_provider` is DraftKings
    on 100% of 18,627 rows, not a number ESPN invented.

    **Fidelity caveat.** nflfastR's `spread_line` is the CLOSING line. This is
    not established to be one: only 2 rows in the 09-05/06 export carry
    `state == 'pre'`. What is measured is that it BEHAVES like a close — it
    moves in 4 of 50 games and every move is <= 1 point inside the first
    quarter, so it is a pregame line with an early settle rather than a live
    one.

    **Provenance caveat.** A venue price is one someone could transact at; a
    DraftKings line carried by ESPN is not a quote on our book. Harmless for a
    forecast feature, not harmless for anything that becomes a P&L claim.

    Returns one row per game: `espn_game_id`, `home_spread`, `n_values`.
    """
    ls = state.dropna(subset=["live_spread"])
    if ls.empty:
        return pd.DataFrame(columns=["espn_game_id", "home_spread", "n_values"])
    g = ls.sort_values("first_seen_at").groupby("game_id")
    out = g.live_spread.first().rename("home_spread").to_frame()
    out["n_values"] = g.live_spread.nunique()
    return out.reset_index().rename(columns={"game_id": "espn_game_id"})


def check_espn_spread_orientation(espn: pd.DataFrame, venue: pd.DataFrame,
                                  *, min_games: int = 5) -> float | None:
    """Police `live_spread`'s sign with the venue ladder. Raises on a flip.

    `espn_spread_anchor` is the one anchor here that genuinely DEPENDS on a
    convention it cannot derive: `live_spread` is a bare number with no team
    attached, so nothing in it says which side the sign favours. That is the
    case where a guard earns its place — unlike the slug-orientation sites,
    which compare two independent sources and would stay correct through a
    flip.

    Measured home-relative (negative = home favoured) at corr +0.999 against
    the venue ladder. This re-runs that check on whatever cohort is to hand and
    is the reason to keep the venue anchor alive at 12 games: **its job is to
    police this one.**

    Returns the correlation, or None if fewer than `min_games` overlap — in
    which case nothing was checked, and the caller is told so rather than
    reassured.
    """
    j = espn.merge(venue, on="espn_game_id", suffixes=("_espn", "_venue"))
    if len(j) < min_games:
        return None
    r = float(np.corrcoef(j.home_spread_espn, j.home_spread_venue)[0, 1])
    if r < 0:
        raise ValueError(
            f"live_spread disagrees in SIGN with the venue ladder (corr {r:+.3f} "
            f"on {len(j)} games). One of the two is inverted; the measured value "
            "is +0.999. Do not fit until this is resolved."
        )
    return r
