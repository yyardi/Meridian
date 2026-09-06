"""c7's zero-parameter identity. It TIES ESPN. The delta does add over the anchor.

    logit(p_hat) = logit(anchor_prior) + [ logit(ESPN_live) - logit(ESPN_at_kickoff) ]

`anchor_prior = sigmoid(-live_spread / 7.0)`. Zero fitted parameters — the 7.0 is
the standard points-per-logit football conversion, not a fit — so nothing here can
memorise the 22 distinct anchor values that destroyed the state+anchor GBM.

## THE RESULT — LOOSE settled predicate, export 20260906T174104Z, G = 31

    n 14,458 in-progress rows        BRIER, lower is better    G   predicate
    base rate (90.3% home)   0.09856                           31  LOOSE
    anchor only, 0 params    0.04991                           31  LOOSE
    ESPN public number       0.05404                           31  LOOSE
    c7 identity, 0 params    0.02948                           31  LOOSE

    identity vs ESPN           +0.02456 [-0.00890, +0.05801]  SPANS 0   wins 29/31
    identity vs anchor alone   +0.02043 [+0.00100, +0.03986]  EXCLUDES 0 wins 30/31
    identity vs base rate      +0.06908 [-0.01354, +0.15169]  SPANS 0   wins 28/31

**It ties ESPN.** ce's second branch, not the first. But the narrowing is the
OPPOSITE of "ESPN's delta adds nothing the anchor already implies": the delta is
the one comparison that clears zero. The identity beats its own anchor, and ties
the public model.

**The two instruments disagree and both are reported.** The game-clustered
sandwich spans zero while the identity wins 29 of 31 games — a sign test on 29/31
is p < 1e-5. The sandwich weights magnitude and the sign test does not, so the
gap means the few losses are large ones. Neither is the answer alone; the honest
reading is "wins nearly always, by an amount 31 games cannot pin down".

## ★ THE GAIN IS EARLY. THE MONEY IS LATE.

    late <15m   n 3,590 G 31  ESPN 0.02867  ident 0.01548  +0.01320 [-0.01712,+0.04351] spans 0
    middle      n 5,800 G 31  ESPN 0.03574  ident 0.02734  +0.00840 [-0.02839,+0.04520] spans 0
    early >35m  n 5,063 G 31  ESPN 0.09303  ident 0.04189  +0.05115 [+0.00975,+0.09254] EXCL 0

Three buckets, not two, so a non-monotone shape could show itself. It does not:
the effect is monotone and sits entirely in the first 25 minutes, where ESPN is
worst. **PULSE trades the last 15 minutes, where this is a tie.**

## ★ CORRECTION TO THE PREVIOUS COMMIT OF THIS FILE (20c544b)

That commit retracted the "ESPN carries no pregame prior" finding and reported
sd 0.1443 with 13/33 strong priors. **That retraction was wrong and is itself
withdrawn. The original finding stands.**

The defect was the row selector, and ce's condition 1 is what caught it. I took
the largest-`reg_left` row carrying a non-null WP; ESPN's `display_clock` holds
"15:00" in period 1 on rows whose scoreboard already reads 21-0, so that selector
grabbed mid-game rows. **94 of 281 rows (33.5%) at reg_left >= 3540 are not 0-0,
across 17 games**, and the two selectors disagree on 19 of 32 games:

    selector = max reg_left with a WP      G 32  mean 0.6793  sd 0.1404  12/32 strong
    selector = P1 AND 0-0 (ce's, correct)  G 32  mean 0.5928  sd 0.0218   0/32 strong

So ESPN's CFB win probability really does open every game near a coin flip, and
the anchor really is supplying a prior ESPN does not have. Both my earlier
retraction and the "caveat 1" in commit 20c544b were artifacts of this selector:
with a contaminated `espn_k` the update term measured the change since an already
decided game, which is d5's 0.169 failure in a different disguise.

## Predicate, stated because it is worth 72% of the cohort

    settled STRICT = has a 'post' row                              28 games -> cohort 18
    settled LOOSE  = post OR (period>=4 AND clock 0:00 AND untied) 44 games -> cohort 31

LOOSE is what `cfb-state-substrate.md` specifies and what d5's module uses, so
this composes with their pipeline. Both are computed below; G and predicate are
printed on every row. Export vintage is named because d5 gets 16 where ce gets 18
purely on vintage.

**★ THE PREDICATE FLIPS THE HEADLINE, WHICH IS ITSELF THE RESULT.**

    STRICT G=18   identity vs ESPN  +0.04739 [+0.02030, +0.07448]  EXCLUDES 0, 18/18
    LOOSE  G=31   identity vs ESPN  +0.02456 [-0.00890, +0.05801]  spans 0,   29/31

The SMALLER cohort gives the STRONGER result, which is backwards for sampling
noise and means STRICT is a selected subpopulation: "has a post row" selects
games where the recorder survived to the whistle, and those carry more of the
early rows where the identity wins. LOOSE is the honest denominator and LOOSE
says tie. Anyone quoting +0.04739 is quoting a survivorship filter.

## Why there is no asof join here any more

Every state row already carries its own `espn_home_win_pct`, so the identity is
evaluated per state row and needs no time alignment at all. This removes the
clock from the critical path — which matters, because the clock is the field that
was lying. `reg_left` survives only as the bucket axis, and it is sound for that:
monotone on 99.2% of within-game steps, median within-game corr -0.981 against
row order, 0/50 games badly scrambled.

Rows with the outcome already determined (a 'post' row, or period>=4 at 0:00) are
excluded from scoring.

## Not on the same footing as the earlier table

The `p_base` 7-feature GBM row (0.08061) came from the 28-game fit set joined on
game time, and cannot be recomputed here: `down`/`distance` are not in the state
table. It is NOT comparable to these rows and is deliberately absent.

G is 31 games with one outcome draw each, 90.3% of them home wins. A
zero-parameter tie at G=31 is worth having and is not worth broadcasting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

STATE = "backups/exports/espn_cfb_game_state_20260906T174104Z.csv.gz"
VINTAGE = "20260906T174104Z"
POINTS_PER_LOGIT = 7.0  # standard football conversion, NOT a fitted parameter
COLS = ["base_rate", "anchor", "espn_home_win_pct", "ident_0"]

logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
sigmoid = lambda z: 1 / (1 + np.exp(-z))


def reg_left(display_clock, period) -> float:
    """Seconds left in regulation. Bucket axis only — never a join key here."""
    try:
        mm, ss = str(display_clock).split(":")
        return max(int(mm) * 60 + float(ss) + max(4 - int(period), 0) * 900, 0)
    except Exception:
        return np.nan


def load_state() -> pd.DataFrame:
    S = pd.read_csv(STATE)
    S["gid"] = S.game_id.astype(str)
    S["t"] = pd.to_datetime(S.first_seen_at, utc=True, format="ISO8601", errors="coerce")
    S["reg_left"] = pd.Series(
        [reg_left(c, p) for c, p in zip(S.display_clock, S.period)], dtype=float)
    S["zero_clock"] = S.display_clock.astype(str).str.strip().isin(
        ["0:00", "00:00", "0.0", "0:00.0"])
    S["is_post"] = S.state.astype(str).str.lower().eq("post")
    return S


def settled(S: pd.DataFrame, loose: bool) -> set[str]:
    strict = set(S[S.is_post].gid.unique())
    if not loose:
        return strict
    return strict | set(
        S[(S.period >= 4) & S.zero_clock & (S.home_score != S.away_score)].gid.unique())


def build(S: pd.DataFrame, loose: bool) -> pd.DataFrame:
    # KICKOFF = period 1 AND 0-0. NOT "earliest row with a WP": display_clock holds
    # 15:00 on rows already scoring 21-0, and that selector was wrong on 19/32 games.
    kick = (S[(S.period == 1) & (S.home_score == 0) & (S.away_score == 0)]
            .dropna(subset=["espn_home_win_pct"])
            .sort_values("reg_left", ascending=False)
            .groupby("gid").espn_home_win_pct.first())
    # ONE anchor, not two: corr(live_spread, venue ladder) = +0.9992, so using both
    # is the collinearity trap. Earliest in GAME time, never file order.
    spread = (S.dropna(subset=["live_spread", "reg_left"])
              .sort_values("reg_left", ascending=False).groupby("gid").live_spread.first())
    final = S.sort_values("t").groupby("gid").agg(hs=("home_score", "last"),
                                                  as_=("away_score", "last"))
    cohort = sorted(settled(S, loose) & set(kick.index) & set(spread.dropna().index))

    D = S[S.gid.isin(cohort)].dropna(subset=["espn_home_win_pct"]).copy()
    D = D[~D.is_post & ~((D.period >= 4) & D.zero_clock)]  # outcome already determined
    D["y"] = (D.gid.map(final.hs) > D.gid.map(final.as_)).astype(int)
    D["anchor"] = sigmoid(-D.gid.map(spread) / POINTS_PER_LOGIT)
    D["espn_k"] = D.gid.map(kick)
    D["ident_0"] = sigmoid(logit(D.anchor) + logit(D.espn_home_win_pct) - logit(D.espn_k))
    # Control that can fail: 90.3% home wins, so a constant at the base rate is the
    # thing the anchor must beat before "the market prior is informative" means anything.
    D["base_rate"] = D.groupby("gid").y.first().mean()
    for c in COLS:
        D["b_" + c] = (D[c] - D.y) ** 2
    return D


def cm(f: pd.DataFrame, col: str):
    return clustered_mean({k: v.tolist() for k, v in f.groupby("gid")[col]})


def contest(f: pd.DataFrame, a: str, b: str, label: str, tag: str) -> None:
    f = f.copy()
    f["dd"] = f["b_" + a] - f["b_" + b]
    r = cm(f, "dd")
    per_game = f.groupby("gid").apply(
        lambda x: x["b_" + a].mean() - x["b_" + b].mean(), include_groups=False)
    G = f.gid.nunique()
    verdict = "EXCLUDES 0" if r.lo > 0 else ("loses     " if r.hi < 0 else "spans 0   ")
    print(f"  {label:26s} {r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}] {verdict}"
          f" wins {(per_game > 0).sum()}/{G}  G={G} {tag}")


def block(D: pd.DataFrame, tag: str) -> None:
    G = D.gid.nunique()
    yg = D.groupby("gid").y.first()
    print(f"=== {tag} predicate | export {VINTAGE} | n {len(D):,} rows | G {G} ===")
    print(f"    home wins {int(yg.sum())}/{len(yg)} = {yg.mean()*100:.1f}%   BRIER, lower better")
    for c in COLS:
        print(f"  {c:22s} {cm(D, 'b_' + c).mean:.5f}   G={G} {tag}")
    contest(D, "espn_home_win_pct", "ident_0", "identity vs ESPN", tag)
    contest(D, "anchor", "ident_0", "identity vs anchor alone", tag)
    contest(D, "base_rate", "ident_0", "identity vs base rate", tag)
    print("  by game clock — three buckets, so a non-monotone shape could show itself:")
    D = D.copy()
    D["bucket"] = pd.cut(D.reg_left, [-1, 900, 2100, 3601],
                         labels=["late <15m", "middle", "early >35m"])
    for bucket, x in D.groupby("bucket", observed=True):
        if x.gid.nunique() < 3:
            continue
        x = x.copy()
        x["dd"] = x.b_espn_home_win_pct - x.b_ident_0
        r = cm(x, "dd")
        print(f"    {bucket:11s} n {len(x):>6,} G {x.gid.nunique():>2}  "
              f"ESPN {cm(x, 'b_espn_home_win_pct').mean:.5f}  "
              f"ident {cm(x, 'b_ident_0').mean:.5f}  "
              f"{r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]"
              f"{'  EXCLUDES 0' if r.lo > 0 else '  spans 0'}  G={x.gid.nunique()}")
    print()


def main() -> int:
    S = load_state()
    print(f"  settled STRICT (post row)                      {len(settled(S, False))}")
    print(f"  settled LOOSE  (post OR P>=4 & 0:00 & untied)  {len(settled(S, True))}\n")
    block(build(S, loose=True), "LOOSE")
    block(build(S, loose=False), "STRICT")
    print("It TIES ESPN and BEATS ITS OWN ANCHOR. The gain is in the first 25")
    print("minutes; the last 15, where PULSE trades, is a tie. G=31, one draw each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
