"""c7's zero-parameter identity, tested. It clears ESPN — with two caveats.

    logit(p_hat) = logit(anchor_prior) + [ logit(ESPN_live) - logit(ESPN_at_kickoff) ]

`anchor_prior = sigmoid(-live_spread / 7.0)`. Zero fitted parameters: the 7.0 is
the standard points-per-logit football conversion, not a fit. So there is nothing
here that can memorise 28 games, which was the objection to the anchor route.

## THE RESULT, G = 28

    p_base   7 game-state features        0.08076
    anchor   0 params, spread only        0.05721
    anchor   1 param, out-of-fold         0.06447
    ESPN     public number                0.06737
    c7 identity, 0 params                 0.03233   <- clears ESPN

    identity vs ESPN   +0.03504 [+0.00092, +0.06916]  excludes 0, wins 23/28

## ★ CAVEAT 1 — THE DELTA'S OWN CONTRIBUTION DOES NOT CLEAR ZERO

    identity vs ANCHOR ALONE  +0.02489 [-0.00311, +0.05288]  SPANS 0, wins 19/28

The identity beats ESPN. **Most of that is the anchor beating ESPN, not ESPN's
live delta adding information.** The anchor alone is already 0.05721 against
ESPN's 0.06737. Stack the delta on top and it improves, but not resolvably at
G=28. So the correct reading is ce's second branch, not the first: "ESPN's delta
adds something the anchor does not already imply, but 28 games cannot show it."

## ★ CAVEAT 2 — THE GAIN IS EARLY, AND THE MONEY IS LATE

    late <15m   n 1,039  G 28   ESPN 0.04665  ident 0.04370  +0.00295 [-0.05164,+0.05754]  spans 0
    middle      n 1,352  G 25   ESPN 0.05321  ident 0.03498  +0.01823 [-0.01722,+0.05368]  spans 0
    early >35m  n 1,226  G 20   ESPN 0.10053  ident 0.01977  +0.08076 [+0.04865,+0.11288]  EXCLUDES 0

Three buckets, not two, deliberately — a two-way split of a non-monotone series
reports a trend it does not have. Here the series IS monotone and the whole
effect sits in the first 25 minutes, where ESPN is worst (0.10053) and a pregame
spread is nearly sufficient. **By the last 15 minutes the identity and ESPN are
indistinguishable.** PULSE trades late. This result does not reach that regime.

## ★ RETRACTION, AT THE TABLE: ESPN *DOES* CARRY A PREGAME PRIOR

I previously reported that ESPN's CFB win probability has no pregame prior —
"sd 0.0176, 0/23 games with a strong prior" — and that framing is what motivated
the anchor route. **It does not reproduce on this substrate.** Measured at the
earliest observation with reg_left >= 3540s, one per game:

    G 33   mean 0.6968   sd 0.1443   |wp - 0.5| > 0.15 on 13/33 games
    range 0.530 ... 0.972

So the mechanism is NOT "the anchor supplies a prior ESPN lacks". It is **"the
market's prior is better than ESPN's prior"** — a different and more interesting
claim, and one the identity is a fair test of, since the identity's arithmetic is
precisely "keep ESPN's within-game update, replace its pregame level". The
earlier sd 0.0176 figure is withdrawn; I cannot reproduce what population it came
from.

## Two substrate checks this rests on, re-run rather than recalled

* **live_spread is pregame, not live.** Constant within game on 46/50; the 4
  exceptions move by one point (-28.5 -> -29.5). File order agrees with
  game-time order on 48/50 — but this file pins the anchor to the earliest row
  in GAME time regardless, because a file-order `.first()` is not a guarantee.
* **ESPN_at_kickoff is often not at kickoff.** Only 33/49 games have their
  earliest ESPN observation at reg_left >= 3540s; for the other 16 it is a
  mid-game snapshot and the identity's subtrahend is then meaningless. Restricted
  to the 18 clean games in the fit set the identity wins 18/18, +0.05478
  [+0.02675, +0.08281] — but that subset also over-weights early rows, which is
  exactly where the anchor wins, so it is not the stronger result it appears.

## Alignment

Rows are joined on GAME time (reg_left), not publication time, per ce — the
question is whether the information exists, not whether we can consume the feed.
`direction="forward"` on ascending reg_left matches a state at or BEFORE the row
in game time; reg_left decreases as the game runs, so "backward" would import the
future. Tolerance 60s.

G is 28 games with one outcome draw each. Nothing here should travel further.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from core.quote.adverse_selection import clustered_mean

STATE = "backups/exports/espn_cfb_game_state_20260906T174104Z.csv.gz"
FIT = "/tmp/wp_fit.csv"  # the 28-game CFB fit set from cfb_wp_baseline
POINTS_PER_LOGIT = 7.0  # standard football conversion, NOT a fitted parameter
KICKOFF_MIN_REG_LEFT = 3540.0
COLS = ["p_base", "anchor_fixed", "anchor_fit", "espn_home_win_pct", "ident_0"]

logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
sigmoid = lambda z: 1 / (1 + np.exp(-z))


def reg_left(display_clock, period) -> float:
    """Seconds left in regulation. NaN when either field is unparseable."""
    try:
        mm, ss = str(display_clock).split(":")
        left = int(mm) * 60 + float(ss)
        return max(left + max(4 - int(period), 0) * 900, 0)
    except Exception:
        return np.nan


def build() -> pd.DataFrame:
    d = pd.read_csv(FIT).rename(columns={"model_wp": "p_base"})
    d["gid"] = d.gid.astype(str)
    # both sides of the asof key must be float: an all-integer clock column reads
    # back as int64 and merge_asof refuses the mixed-dtype join.
    d["reg_left"] = d.reg_left.astype(float)
    S = pd.read_csv(STATE)
    S["gid"] = S.game_id.astype(str)
    S["reg_left"] = pd.Series(
        [reg_left(c, p) for c, p in zip(S.display_clock, S.period)], dtype=float)
    E = S.dropna(subset=["reg_left", "espn_home_win_pct"])
    # Earliest in GAME time (reg_left descending), never file order.
    spread = (S.dropna(subset=["live_spread", "reg_left"])
              .sort_values("reg_left", ascending=False).groupby("gid").live_spread.first())
    kick = (E.sort_values("reg_left", ascending=False).groupby("gid")
            .agg(rl=("reg_left", "first"), wp=("espn_home_win_pct", "first")))
    out = []
    for gid, x in d.groupby("gid"):
        s = E[E.gid == gid][["reg_left", "espn_home_win_pct"]].sort_values("reg_left")
        if s.empty:
            continue
        # forward on ascending reg_left == at or BEFORE this row in game time
        out.append(pd.merge_asof(x.sort_values("reg_left"), s, on="reg_left",
                                 direction="forward", tolerance=60.0))
    J = pd.concat(out, ignore_index=True)
    J["spread"] = J.gid.map(spread)
    J["espn_k"] = J.gid.map(kick.wp)
    J["kick_ok"] = J.gid.map(kick.rl) >= KICKOFF_MIN_REG_LEFT
    J = J.dropna(subset=["espn_home_win_pct", "spread", "espn_k", "p_base"]).copy()

    J["anchor_fixed"] = sigmoid(-J.spread / POINTS_PER_LOGIT)
    g = J.gid.to_numpy()
    oof = np.full(len(J), np.nan)
    for tr, te in GroupKFold(5).split(J[["spread"]], J.y, g):
        # fit at GAME level: one row per game, so a long game cannot outvote a short one
        tg = J.iloc[tr].groupby("gid").agg(s=("spread", "first"), yy=("y", "first"))
        m = LogisticRegression().fit(tg[["s"]].to_numpy(), tg.yy.to_numpy())
        oof[te] = m.predict_proba(J.iloc[te][["spread"]].to_numpy())[:, 1]
    J["anchor_fit"] = oof
    J["ident_0"] = sigmoid(logit(J.anchor_fixed) + logit(J.espn_home_win_pct) - logit(J.espn_k))
    for c in COLS:
        J["b_" + c] = (J[c] - J.y) ** 2
    return J


def cm(f: pd.DataFrame, col: str):
    return clustered_mean({k: v.tolist() for k, v in f.groupby("gid")[col]})


def contest(f: pd.DataFrame, a: str, b: str, label: str) -> None:
    f = f.copy()
    f["dd"] = f["b_" + a] - f["b_" + b]
    r = cm(f, "dd")
    per_game = f.groupby("gid").apply(
        lambda x: x["b_" + a].mean() - x["b_" + b].mean(), include_groups=False)
    G = f.gid.nunique()
    verdict = "EXCLUDES 0" if r.lo > 0 else ("loses" if r.hi < 0 else "spans 0  ")
    print(f"  {label:26s} {r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}] {verdict}"
          f"  wins {(per_game > 0).sum()}/{G}  G={G}")


def block(f: pd.DataFrame, label: str) -> None:
    G = f.gid.nunique()
    print(f"=== {label}   n {len(f):,}   G {G}   BRIER, lower is better ===")
    for c in COLS:
        print(f"  {c:22s} {cm(f, 'b_' + c).mean:.5f}   G={G}")
    contest(f, "espn_home_win_pct", "ident_0", "identity vs ESPN")
    contest(f, "anchor_fixed", "ident_0", "identity vs anchor alone")
    print("  by game clock — three buckets, so a non-monotone shape can show itself:")
    f = f.copy()
    f["bucket"] = pd.cut(f.reg_left, [-1, 900, 2100, 3601],
                         labels=["late <15m", "middle", "early >35m"])
    for bucket, x in f.groupby("bucket", observed=True):
        if x.gid.nunique() < 3:
            continue
        x = x.copy()
        x["dd"] = x.b_espn_home_win_pct - x.b_ident_0
        r = cm(x, "dd")
        print(f"    {bucket:11s} n {len(x):>5,} G {x.gid.nunique():>2}  "
              f"ESPN {cm(x, 'b_espn_home_win_pct').mean:.5f}  "
              f"ident {cm(x, 'b_ident_0').mean:.5f}  "
              f"{r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]"
              f"{'  EXCLUDES 0' if r.lo > 0 else '  spans 0'}")
    print()


def main() -> int:
    J = build()
    block(J, "ALL matched games")
    block(J[J.kick_ok], "kickoff-anchored games only (espn_k is genuinely at kickoff)")
    print("Caveats 1 and 2 in the module docstring are part of this result, not")
    print("footnotes to it: the delta's own contribution spans zero, and the whole")
    print("gain sits in the first 25 minutes. PULSE trades the last 15.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
