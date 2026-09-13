"""The LIVE model, scored for the first time — and the sigma build is unnecessary.

meridian-ce corrected me: `predictions` is the pregame model, `pulse_decisions`
is the live one, and my "there are NO in-game predictions" was true of the
former and false of the system. This file works the right substrate.

## ★ CORRECTION TO MY OWN CLAIM, RECORDED RATHER THAN EDITED AWAY

I wrote "There are no in-game predictions. NONE." on the basis of
`predictions`: p5 = 7.7 hours to resolution, 0.00% of rows under 2.5h. That
statement is **correct about the pregame model and wrong about PULSE**, because
a second model exists with 19,333 in-play rows across 34 games. My Brier result
stands relabelled as a statement about the pregame model; my inference that the
sigma question was closed does not.

## ★ THE SIGMA BUILD IS NOT A THING TO BUILD — IT ALREADY EXISTS

`total_sigma` on the live model is a per-decision column, not a config
constant, and it is already doing exactly what a per-observation sigma should:

    corr(total_sigma, minutes_left)  = +0.967
    corr(total_sigma, total_so_far)  = -0.944

    minutes_left    n        median sigma
    (30, 40]        2,519         17.39
    (20, 30]        2,972         14.66
    (10, 20]        2,963         12.11
    (5, 10]         1,068          7.28
    (0, 5]            599          2.35

**Median 17.39 with over 30 minutes left against 2.35 with under five.** And
17.39 is essentially the pregame model's constant 17.3 — whose value I
separately showed is the maximum-likelihood full-game sigma (in-sample optimum
17.11). **The two models are coherent, not contradictory:** the pregame model
carries the full-game sigma because it forecasts one horizon; the live model
shrinks it as the clock runs. Nothing here needs building. The open question is
whether the varying sigma is *calibrated*, not whether it varies.

## ★ FIRST SCORING OF THE LIVE MODEL — AND ITS SCOPE

**`settlement` is present on 1,944 of 19,333 rows (10.1%), and every one of
them is an `enter`.** Holds (13,680) and exits (2,679) carry none. So this is
not "does the live model beat the market" — it is **"does it beat the market on
the trades it chose and was filled on"**, which is selected by the entry rule
and again by the fill. After two days establishing that the fill rule selects
adversely, that scope has to lead.

    Brier(model) 0.20173   Brier(market) 0.19692
    difference  -0.00481 [-0.02283, +0.01321]   G=34   TIE

    measured    n 1,581  G 33   -0.00096 [-0.01705, +0.01513]   tie
    ESTIMATED   n   363  G 21   -0.02158 [-0.08696, +0.04379]   tie

Split rather than pooled, because `minutes_left_is_estimate` marks inferred
values. Both tie; the measured arm is far closer to parity.

By `minutes_left` there is a gradient — late-game worst (−0.02130), early-game
best (+0.00376) — **and every bucket ties**, so it is a direction and not a
result.

## The trap, now in its third substrate

`minutes_left_is_estimate` is a **'t'/'f' string**. That is `is_live` on the
QUOTE tape and `is_actionable` on `predictions`. Three columns, three
substrates, same failure: comparing to `True` selects nothing and returns a
clean empty result rather than an error.

## And a multiple-comparison note on the calibration

Five fair-value buckets were tested; one, (0.2, 0.4], excluded zero at
−11.34pp. **One in five at the 5% level is what chance produces.** By sigma
tercile every bucket's interval spans zero. No calibration failure is
established here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

EXPORT = "backups/exports/pulse_decisions_full_20260901T195202Z.csv"


def load() -> pd.DataFrame:
    d = pd.read_csv(EXPORT)
    # 't'/'f' STRING — third substrate carrying this trap.
    d["est"] = d.minutes_left_is_estimate.astype(str).str.lower().isin(("t", "true", "1"))
    d["mid"] = (d.market_bid + d.market_ask) / 2.0
    return d


def cm(frame: pd.DataFrame, col: str):
    s = frame[[col, "game_id"]].dropna()
    return clustered_mean({k: v.tolist() for k, v in s.groupby("game_id")[col]})


def verdict(r) -> str:
    return "MODEL" if r.lo > 0 else ("MARKET" if r.hi < 0 else "tie")


def main() -> int:
    d = load()
    print(f"live decisions: {len(d):,} rows | {d.game_id.nunique()} games | "
          f"phase={d.phase.unique().tolist()}")

    print("\n" + "=" * 70)
    print("1. total_sigma ALREADY VARIES AND TRACKS THE CLOCK")
    print("=" * 70)
    s = d[d.total_sigma.notna()]
    print(f"  n {len(s):,}  distinct values {s.total_sigma.nunique():,}")
    print(f"  corr with minutes_left {s.total_sigma.corr(s.minutes_left):+.3f}  "
          f"| with total_so_far {s.total_sigma.corr(s.total_so_far):+.3f}")
    for b, x in s.groupby(pd.cut(s.minutes_left, [-.01, 5, 10, 20, 30, 40]),
                          observed=True):
        print(f"    minutes_left {str(b):>13}  n {len(x):>6,}  "
              f"median sigma {x.total_sigma.median():6.2f}")
    print("  -> a per-observation sigma is not a thing to build. It exists.")

    print("\n" + "=" * 70)
    print("2. FIRST SCORING OF THE LIVE MODEL — scope first")
    print("=" * 70)
    S = d[d.settlement.notna() & d.fair_value.notna()].copy()
    print(f"  settlement present on {len(S):,}/{len(d):,} ({len(S)/len(d)*100:.1f}%), "
          f"and the action mix is {S.action.value_counts().to_dict()}")
    print("  Every scoreable row is an ENTER. Holds and exits carry no outcome, so")
    print("  this is the model judged on trades it chose AND was filled on.")
    for c in ("b_model", "b_mkt"):
        pass
    S["b_model"] = (S.fair_value - S.settlement) ** 2
    S["b_mkt"] = (S["mid"] - S.settlement) ** 2
    S["b_diff"] = S.b_mkt - S.b_model
    r = cm(S, "b_diff")
    print(f"\n  Brier(model) {cm(S,'b_model').mean:.5f}   "
          f"Brier(market) {cm(S,'b_mkt').mean:.5f}")
    print(f"  difference   {r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]  "
          f"G={r.n_clusters}  -> {verdict(r)}")
    for lbl, x in (("measured", S[~S.est]), ("ESTIMATED", S[S.est])):
        if len(x) < 50:
            continue
        rr = cm(x, "b_diff")
        print(f"    {lbl:10s} n {len(x):>5,} G {x.game_id.nunique():>2}  "
              f"{rr.mean:+.5f} [{rr.lo:+.5f}, {rr.hi:+.5f}]  {verdict(rr)}")
    print("\n  by minutes_left:")
    for b, x in S.groupby(pd.qcut(S.minutes_left, 4, labels=False, duplicates="drop")):
        rr = cm(x, "b_diff")
        print(f"    {x.minutes_left.min():5.1f}-{x.minutes_left.max():5.1f} min  "
              f"n {len(x):>5,}  {rr.mean:+.5f} [{rr.lo:+.5f}, {rr.hi:+.5f}] {verdict(rr)}")
    print("  Every bucket ties. The late-game/early-game ordering is a direction,")
    print("  not a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
