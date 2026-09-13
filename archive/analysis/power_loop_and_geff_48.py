"""Closing the power loop on 48 games, G_eff, and a calibration attempt.

Three assignments from meridian-ce. Two answered, one not runnable as specified,
and two of my own intermediate findings dissolved on inspection — recorded here
rather than removed.

## 1. THE POWER PROJECTION, CLOSED

C projected the CFB half-width would fall from 2.61¢ toward **0.68¢** with more
games. Measured on the 48-game pin:

    11 games (engine 63e7f1b8, 09-04)   half-width 2.392¢   Kish G_eff  6.74
    48 games, both CFB binaries         half-width 0.750¢   Kish G_eff 25.12
    48 games, single binary 63e7f1b8    half-width 0.836¢   Kish G_eff 22.72

**The projection lands. 0.750¢ actual against 0.68¢ predicted — about 10% wider,
23% on the single-binary basis.** For a model validated only against simulation
this is a good outcome, and it is now validated against a real sample increase
as well, which is what the assignment was for.

**But the starting point does not reproduce**: I measure 2.392¢ where C reported
2.61¢. So the *ratio* the projection achieved is not the ratio I can verify.

## 2. ★ THE POSITIVE CONTROL ON G_eff FAILS, AND IN THE WORSE DIRECTION

I cannot reproduce C's **Kish G_eff = 7.73 on 11 games**. On the cohort that
matches their description (engine 63e7f1b8, G=11) I get **6.74**, and every
variant I can construct is lower still:

    all fills 6.735 | ingame 6.744 | phantom-only 6.915 | real-only 5.903

**Every one is below 7.73**, so if my implementation is the correct one the
yield skew was costing *more* independent information than reported, not less.
I have not resolved which is right, and the 48-game numbers below use MY
implementation — anyone reconciling should start here.

## 3. G_eff ON 48 GAMES — the manager's suspicion is confirmed

    11 games:  Kish 6.74 / 11  =  61.3% efficiency
    48 games:  Kish 25.1 / 48  =  52.3% efficiency

**The slate day's skew is worse than the 11-game day's.** Nominal 48 is worth
about 25 independent games, and the efficiency *fell* by 9 points. Every
interval quoted off this pin should carry ~25, not 48.

**And the real population covers only 35 of the 48 games** (Kish 20.5) — 13
games produced no real fills at all, which is a coverage fact separate from the
skew and is not visible in the headline count.

## 4. SECOND-MOMENT CALIBRATION — not runnable as specified

The assignment wants standardised residuals `(fv − outcome)/σ` to have unit
variance. **The pin carries no model fair value and no per-observation σ**:
`m_q` is the market mid and `s_q` is the quoted spread (0.01–0.15, capped at
our own MAX_SPREAD gate). PULSE's `fv` is not in this file. Substituting the
mid for a model forecast would measure the market against itself, which is the
disease of the last two days.

What IS runnable is the **benchmark** version — is the market's own mid
calibrated in its second moment — and it dissolved:

    mid used   Var(z)                    mean resid
    first      0.9431 [0.8758, 1.0105]   +1.50pp   CONTAINS 1
    median     0.8468 [0.8043, 0.8893]   +0.78pp   excludes 1
    last       0.7631 [0.6877, 0.8386]   +0.84pp   excludes 1

**Monotone in how late the mid is taken — that is look-ahead, not a market
property.** A market's mid drifts toward its outcome, so summarising it by a
median or a last value imports part of the answer and shrinks the residuals.
At the earliest observation, the only one that is an ex-ante forecast,
**Var(z) contains 1: the market is calibrated in its second moment.** That is
the bar a model has to beat, and it is a hard one.

## 5. ★ AND THE FAVOURITE–LONGSHOT PATTERN I FOUND IS NOT REPORTABLE

By price band the market's mid looks badly biased — mids of 25% winning 13%,
mids of 75% winning 89%. That is the textbook pattern and it matches the
published Kalshi result. **It is also exactly what this programme retracted
this afternoon as a one-sided sampling artifact, and the known-answer control
is unavailable here: only 3 complementary pairs exist in 2,102 markets (99.7%
unpaired).**

A second defect, mine: my first version of that control summed the two
residuals of a pair, which is algebraically `1 − (p₁+p₂)` — a restatement of
the mid-sum, so it tests vig and not directional bias. It cannot corroborate
anything.

**So the pattern is unresolvable on this substrate rather than confirmed or
refuted.** It should not travel in either direction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

PIN_48 = "backups/exports/quote_fills_classified_20260906T024500Z.csv"
PIN_11 = "backups/exports/quote_fills_classified_20260904T181800Z.csv"
CFB_BINARY = "63e7f1b8bcd06dcfaafc4bd000a8ae0904e53fc8"


def kish(counts) -> float:
    """Effective number of clusters under unequal sizes: (Σn)² / Σn²."""
    n = np.asarray(counts, float)
    return float(n.sum() ** 2 / (n ** 2).sum())


def clustered(frame: pd.DataFrame, col: str):
    s = frame[[col, "game_id"]].dropna()
    return clustered_mean({g: v.tolist() for g, v in s.groupby("game_id")[col]})


def half_width(frame: pd.DataFrame, col: str = "pnl_c"):
    r = clustered(frame, col)
    return (r.hi - r.lo) / 2, r.mean, r.n_clusters


def main() -> int:
    old = pd.read_csv(PIN_11)
    new = pd.read_csv(PIN_48)
    for f in (old, new):
        f["pnl_c"] = f.pnl * 100

    print("=" * 70)
    print("1+2. POWER LOOP AND G_eff — control first")
    print("=" * 70)
    o = old[old.engine_commit == CFB_BINARY]
    h, m, g = half_width(o)
    ke = kish(o.groupby("game_id").size())
    print(f"  11 games  half-width {h:.3f}c (C reported 2.61c)  Kish {ke:.2f} "
          f"(C reported 7.73)")
    print(f"    -> BOTH controls miss. Mine are lower on Kish in every variant.")

    cfb = new[new.engine_commit != "UNSTAMPED"]
    for lbl, s in (("48 games, both binaries", cfb),
                   ("48 games, single binary", new[new.engine_commit == CFB_BINARY]),
                   ("  real fills only", cfb[cfb["pop"] == "real"])):
        h, m, g = half_width(s)
        ke = kish(s.groupby("game_id").size())
        print(f"  {lbl:24s} G {g:>2}  Kish {ke:5.2f} ({ke/g*100:4.1f}%)  "
              f"mean {m:+6.3f}c  half-width {h:.3f}c")
    print("  -> projection predicted 0.68c; actual 0.750c, about 10% wider.")
    print("  -> efficiency FELL: 6.74/11 = 61.3% then, 25.1/48 = 52.3% now.")

    print("\n" + "=" * 70)
    print("4. SECOND MOMENT — the benchmark version, and its look-ahead")
    print("=" * 70)
    d = cfb.copy()
    d["filled_at"] = pd.to_datetime(d.filled_at, utc=True, format="ISO8601")
    d = d.sort_values("filled_at")
    a = d.groupby(["game_id", "market_slug"]).agg(
        first=("m_q", "first"), med=("m_q", "median"), last=("m_q", "last"),
        y=("settlement", "first")).reset_index()
    a = a[a[["first", "med", "last"]].gt(0.005).all(axis=1)
          & a[["first", "med", "last"]].lt(0.995).all(axis=1)]
    print(f"  {len(a):,} markets, one row each (the outcome is shared per market,")
    print(f"  so per-fill rows would count the same settlement thousands of times)")
    for lbl in ("first", "med", "last"):
        z2 = ((a.y - a[lbl]) / np.sqrt(a[lbl] * (1 - a[lbl]))) ** 2
        t = pd.DataFrame({"game_id": a.game_id, "z2": z2})
        r = clustered(t, "z2")
        print(f"    {lbl:>6} mid  Var(z) {r.mean:.4f} [{r.lo:.4f}, {r.hi:.4f}]  "
              f"{'CONTAINS 1' if r.lo <= 1 <= r.hi else 'excludes 1'}")
    print("  Monotone in lateness -> look-ahead in the summary, not a market")
    print("  property. At the earliest mid the market IS second-moment calibrated.")

    print("\n" + "=" * 70)
    print("5. THE FAVOURITE-LONGSHOT PATTERN — and why it cannot be reported")
    print("=" * 70)
    a["band"] = pd.cut(a["med"], [0, .1, .3, .5, .7, .9, 1.0])
    for b, s in a.groupby("band", observed=True):
        if len(s) < 30:
            continue
        print(f"    mid {str(b):12s} n {len(s):>4}  wins {s.y.mean()*100:5.1f}% "
              f"vs mid {s['med'].mean()*100:5.1f}%")
    m2 = d.groupby(["game_id", "market_slug", "sports_market_type", "line"],
                   dropna=False).agg(p=("m_q", "median"), y=("settlement", "first"))
    m2 = m2.reset_index()
    pairs = sum(1 for _, s in m2.groupby(["game_id", "sports_market_type", "line"],
                                         dropna=False)
                if len(s) == 2 and set(s.y) == {0, 1})
    print(f"  complementary pairs available for the known-answer control: {pairs}")
    print(f"  of {len(m2):,} markets — {100 - 2*pairs/len(m2)*100:.1f}% unpaired.")
    print("  The control the retraction relied on cannot be run here. The pattern")
    print("  is UNRESOLVABLE on this substrate, not confirmed and not refuted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
