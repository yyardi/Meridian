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

Three buckets, not two, so a non-monotone shape could show itself. **It did, and
an earlier version of this file called it monotone anyway.** Late (+0.01320) sits
ABOVE middle (+0.00840): the dip is in the MIDDLE, so "the effect decays with
game time" is not what these three numbers say.

**The decay is nonetheless real, tested directly rather than read off the
buckets.** Paired within game, same 31 games, early-minus-late:

    +0.04254 [+0.00569, +0.07939]   EXCLUDES 0

and the late interval's upper bound (+0.03925) excludes the early point estimate
(+0.05380), which is what distinguishes a real decay from an underpowered
bucket. So it is decay, not power — but the shape between the endpoints is not
monotone and should not be described as a trend.

## ★ BRIER IS THE WRONG UNIT FOR THE QUESTION PULSE ASKS

Money is linear in the probability gap; Brier squares it, and both models
converge late simply because the outcome becomes obvious. Measured per game:

    bucket   ESPN     ident    RELATIVE gain   |ident - ESPN|
    early    0.09303  0.04189      55.0%       19.14pp [15.97, 22.32]
    middle   0.03574  0.02734      23.5%        8.79pp [ 4.60, 12.98]
    late     0.02867  0.01548      46.0%        3.50pp [ 0.12,  6.88]

**The relative gain does not decay at all — it is U-shaped, 55% / 23.5% / 46%.**
The absolute Brier decay is a ceiling effect: late, ESPN is already at 0.02867
and there is little left to win. What actually decays is the tradeable quantity,
the disagreement between the two estimates: **19.14pp early to 3.50pp late, with
the late interval nearly touching zero.**

So the correct statement for PULSE is neither "the edge decays" nor "the edge
survives": late in a game the identity and ESPN agree to within 3.5pp, and 3.5pp
of disagreement with ESPN is not 3.5pp of disagreement with the market price.
Whether anything is tradeable there needs the price tape, which this file does
not touch.

## ★ IT IS DECAY, NOT POWER, AND THE POWER CALCULATION SAYS SO THE HARD WAY

Between-game sd in the late bucket is 0.07630 on G=31. At alpha 0.05 two-sided
and 80% power:

    early effect size       delta +0.05380   G =  16   ALREADY POWERED
    half the early effect   delta +0.02690   G =  63   short by 32
    the late point estimate delta +0.01126   G = 360   short by 329

**The late bucket needs 16 games to detect an early-sized effect and it has 31.**
It is not underpowered for that effect — it is powered, and it sees nothing. So
no number of Saturdays rescues an early-sized late edge; that possibility is
excluded rather than unresolved. An effect HALF the early size is still open and
needs G=63, which Saturday's ~12 games does not reach (31 -> ~43).

Three routes now agree: the paired within-game test, the late interval excluding
the early point estimate, and this power calculation.

## ★ THE BUCKET BOUNDARIES WERE NOT PRE-DECLARED

>35m / middle / <15m were chosen after seeing the data. The monotonicity claim is
therefore suggestive only, and the individual bucket intervals are not clean.
**This file deliberately does not re-cut them**: searching cut points on 31 games
is how a real decay becomes a discovered edge. The power result above does not
depend on the boundaries being optimal, only on their being fixed.

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

import sys

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


def decay(D: pd.DataFrame) -> None:
    """Is the late tie a POWER problem or a REAL decay? Three buckets cannot say."""
    D = D.copy()
    D["bk"] = pd.cut(D.reg_left, [-1, 900, 2100, 3601], labels=["late", "middle", "early"])
    per = {bk: D[D.bk == bk].groupby("gid").apply(
        lambda z: (z.b_espn_home_win_pct - z.b_ident_0).mean(), include_groups=False)
        for bk in ("early", "middle", "late")}
    print("=== POWER OR DECAY? an uninformative interval is not a contrary one ===")
    for bk in ("early", "middle", "late"):
        r = cm_series(per[bk])
        print(f"  {bk:7s} G {len(per[bk]):>2}  {r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]")
    early, late_r = per["early"].mean(), cm_series(per["late"])
    print(f"  late CI upper {late_r.hi:+.5f} vs early effect {early:+.5f} -> "
          f"{'EXCLUDES it: real decay' if late_r.hi < early else 'contains it: underpowered'}")
    common = sorted(set(per["early"].index) & set(per["late"].index))
    r = cm_series(pd.Series({g: per["early"][g] - per["late"][g] for g in common}))
    print(f"  PAIRED early-minus-late, same {len(common)} games: "
          f"{r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]"
          f"  {'DECAY IS REAL' if r.lo > 0 else 'cannot resolve'}\n")
    print("  BUT Brier squares the edge and money is linear in it. Per game:")
    for bk in ("early", "middle", "late"):
        x = D[D.bk == bk]
        e, i = x.b_espn_home_win_pct.mean(), x.b_ident_0.mean()
        rg = cm_series(x.groupby("gid").apply(
            lambda z: (z.ident_0 - z.espn_home_win_pct).abs().mean(), include_groups=False))
        print(f"  {bk:7s} ESPN {e:.5f} ident {i:.5f}  relative gain {(e-i)/e*100:5.1f}%"
              f"   |ident-ESPN| {rg.mean*100:5.2f}pp [{rg.lo*100:5.2f}, {rg.hi*100:5.2f}]")
    print("  relative gain is U-SHAPED (55/23.5/46), not decaying. What decays is the")
    print("  tradeable disagreement: 19.14pp -> 3.50pp, late interval nearly touching 0.\n")
    power(per["late"], per["early"].mean())


def power(late: pd.Series, early_effect: float) -> None:
    """How many GAMES would the late bucket need? Reported as a G, not a p-value.

    THE ANSWER IS NOT "MORE GAMES". The late bucket needs G=16 to detect an
    early-sized effect at 80% power and it already has 31, so it is powered for
    that effect and does not see one. That is the decay result, arrived at by a
    second route that agrees with the paired test.
    """
    sd, G = late.std(ddof=1), len(late)
    z = (1.959964 + 0.8416212) ** 2  # alpha 0.05 two-sided, power 0.80
    print("=== GAMES REQUIRED IN THE LATE BUCKET (alpha .05 two-sided, power .80) ===")
    print(f"  between-game sd {sd:.5f}   have G={G}")
    for label, delta in (("early effect size", early_effect),
                         ("half the early effect", early_effect / 2),
                         ("the late point estimate", abs(late.mean()))):
        need = z * sd ** 2 / delta ** 2
        verdict = "ALREADY POWERED — and it sees nothing" if need <= G else f"short by {need-G:,.0f}"
        print(f"    {label:24s} delta {delta:+.5f}   G = {need:>7,.0f}   {verdict}")
    print("  So an early-sized effect in the last 15 minutes is EXCLUDED, not unresolved.")
    print("  An effect half that size needs G=63; Saturday's ~12 games take 31 to ~43.\n")


def cm_series(s: pd.Series):
    return clustered_mean({k: [v] for k, v in s.items()})


EXPORT_COLS = ["gid", "first_seen_at", "reg_left", "period", "display_clock",
               "home", "away", "home_score", "away_score", "clock_is_stale",
               "anchor", "espn_k", "espn_home_win_pct", "ident_0", "y"]


def export(D: pd.DataFrame, path: str) -> None:
    """Hand-off for the venue comparison. THE FRAME IS P(HOME), NOT P(YES).

    Every probability column is P(home team wins). Mapping to a venue YES leg is
    the consumer's job and it is not the identity function on every market.

    `clock_is_stale` is the trap that cost me the whole evening: ESPN's
    display_clock holds 15:00 in period 1 on rows already scoring 21-0. Any
    tolerance-matching on game time MUST drop or special-case those rows.
    """
    E = D.copy()
    E["clock_is_stale"] = (E.reg_left >= 3540) & ((E.home_score != 0) | (E.away_score != 0))
    E[EXPORT_COLS].sort_values(["gid", "first_seen_at"]).to_csv(path, index=False)
    n_stale = int(E.clock_is_stale.sum())
    print(f"  wrote {path}: {len(E):,} rows, G {E.gid.nunique()}, "
          f"{n_stale} rows flagged clock_is_stale ({n_stale/len(E)*100:.1f}%)")
    print("  FRAME: every probability column is P(HOME WINS), not P(YES).")


def main() -> int:
    S = load_state()
    print(f"  settled STRICT (post row)                      {len(settled(S, False))}")
    print(f"  settled LOOSE  (post OR P>=4 & 0:00 & untied)  {len(settled(S, True))}\n")
    loose = build(S, loose=True)
    block(loose, "LOOSE")
    decay(loose)
    # The caveat goes ABOVE the number it qualifies, not below it.
    print("STRICT is a SURVIVORSHIP FILTER: 'has a post row' keeps games whose recorder")
    print("survived to the whistle, which over-weights the early rows where the identity")
    print("wins. It is tighter on a SMALLER cohort, which is backwards for sampling")
    print("noise. LOOSE above is the honest denominator; do not quote the next block.")
    block(build(S, loose=False), "STRICT")
    print("It TIES ESPN (spans zero, 29/31) and BEATS ITS OWN ANCHOR (excludes zero).")
    print("Decay to the late game is real, but the shape is not monotone and the")
    print("relative gain does not decay at all. G=31, one outcome draw each.")
    if len(sys.argv) > 2 and sys.argv[1] == "--export":
        print()
        export(loose, sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
