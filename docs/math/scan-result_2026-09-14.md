# The first scan — result, 2026-09-14

> **Replicated in-game: see `docs/math/scan-result-live_2026-09-14.md`.** The same conclusion
> holds on 296,964 sampled live ticks — a population 790× larger, with continuously moving
> prices rather than one close per market. These are one finding and neither file should be
> read without the other.

`cfb/run_scan.py`, prod read-only, venue-settled through `core/settlements.py`. Registered in
`docs/math/scan-preregistration.md` (+ Amendment 1). A **screen**: it nominates, it never
decides. Nothing was traded.

## The answer: nothing is nominated, and the tradeable board is quieter than noise

| max half-spread | cells | p<.05 obs/null | p<.01 obs/null | min p | E[min p] | lose/win |
|---|---:|---:|---:|---:|---:|---:|
| ≤ 1¢ | 131 | 11 / 6.6 | **0 / 1.3** | 1.18e-02 | 7.58e-03 | 10/1 |
| ≤ 2¢ | 221 | 16 / 11.1 | **0 / 2.2** | 1.18e-02 | 4.50e-03 | 15/1 |
| ≤ 3¢ | 244 | 20 / 12.2 | 2 / 2.4 | 7.30e-04 | 4.08e-03 | 19/1 |
| ≤ 5¢ | 270 | 26 / 13.5 | 5 / 2.7 | 1.64e-04 | 3.69e-03 | 24/2 |
| all | 327 | 43 / 16.4 | 16 / 3.3 | 1.21e-04 | 3.05e-03 | 40/3 |

**On the tradeable subset — half-spread ≤2¢, 221 cells — there are zero cells at p<0.01
against 2.2 expected, and the smallest p over all 221 is 1.18e-02 where a pure null expects a
minimum of 4.5e-03.** The best cell is **2.6× less extreme than chance would produce** and
**52× away** from the Bonferroni bar of 2.26e-04. **Zero cells nominated at any tradeable cap.**

This is not "we found nothing". It is a measurement that the tight-spread board is *flatter
than chance*, which is a statement about the venue rather than an absence of one.

## Why the unconditional excess is cost, not edge

Unconditionally the scan looks striking: 43 cells at p<0.05 against 16.4 expected, 16 at p<0.01
against 3.3. Two facts kill it.

**1. The p<0.01 count is monotone in the spread cap: 0, 0, 2, 5, 16.** A cost effect shrinks
toward the null as the cap tightens; an edge does not. This one shrinks to nothing.

**2. The direction never moves.** Lose/win among significant cells is 10/1, 15/1, 19/1, 24/2,
40/3 at every cap. **If an edge were hiding under the cost, winners would appear as the cost is
removed. The opposite happens.** Together these are a stronger test than either alone.

The top unconditional cells are quarter totals and quarter spreads whose break-even sits a
median **+9.7pp above the decile centre** — the ask is 7 to 20 cents above the mid. Buying
there loses that spread every time. Untradeable in the direction it points (nobody crosses a
14¢ spread) and its mirror is the making study, already measured negative with power.

## ★ The estimator had to be replaced, and two implementations found it independently

The registered primary was `Var(t)` over game-clustered sandwich t-statistics. It returned
**Var(t) 18.6, max|t| 31.5** — an apparently enormous global effect. It was degeneracy.

**A cell whose bets all resolve the same way has no outcome variance**, so the sandwich SE
collapses onto the band's price dispersion and |t| explodes. Every one of the top twelve cells
was outcome-homogeneous. Against an exact test on the same cell the t overstated the evidence
by **five to thirty orders of magnitude**:

| cell | n | k | p from t | p exact |
|---|---:|---:|---:|---:|
| cfb full_game_winner dec 0.2 | 12 | 0 | 3.9e-12 | 6.3e-02 |
| nfl 1q_spread dec 0.0 | 68 | 0 | 7.9e-33 | 6.1e-02 |
| cfb 2q_total dec 0.8 | 46 | 46 | 1.2e-25 | 1.3e-02 |

**Two implementations, written independently with no shared code, produced the same artifact**
— max|t| 30.01/31.543, Var(t) 17.282/18.637, and in both the top twelve were all degenerate.
That agreement is what made it a finding rather than a bug report.

The primary is now an **exact Poisson-binomial on the win count** (Amendment 1), one trial per
game, against each trial's own break-even. Post-exclusion the sandwich reads Var(t) **1.503**
against a **G-implied null baseline of 1.148** — never against 1.000, because `Var(t_ν) = ν/(ν−2)`
makes a ragged-G null sit at 1.07–1.29 by construction.

**Second appearance of this defect**: `docs/math/extreme-hold_2026-09-13.md` needed the identical
correction a day earlier. Binary outcomes at reachable G make homogeneous cells common, so any
statistic built on P&L dispersion will meet it again.

## What is unexplained, and is left unexplained

The **≤1¢ row shows 11 cells at p<0.05 against 6.6 expected** and that excess does not vanish.
But its p<0.01 count is **zero against 1.3**, and its minimum p is *above* the null expectation.
An excess at p<0.05 with none at p<0.01 is the signature of many marginal cells rather than one
real one — most likely residual within-game clustering that one-trial-per-game only partly
removes. **Recorded as unexplained. Not "clean", and not "something here".**

## What this does and does not rule out

Registered in the pre-registration and restated because it must be: **this rules out edges above
roughly 5–15¢ depending on family. It cannot rule out edges between the ~2.1¢ cost hurdle and
that bound.** "We found nothing" and "nothing is there" are different sentences and only the
first is true.

## Defects found in this scan's own instrument

* **The G floor gated the sandwich path only.** 57 primary cells were ranking without it,
  including a **G=2** cell at p=8.9e-04 in the top ten. A two-game cell cannot nominate
  anything. Fixed; all 57 print with their reason; m went 383 → 327.
* **The within-game pick was biased.** First-by-slug is deterministic, which made it look safe —
  but slugs sort by line as a *string*, so the pick landed in one corner of the decile, biasing
  the break-even variation the Poisson-binomial exists to respect. Now nearest-to-decile-centre.
  **"Deterministic" and "unbiased" are different properties and only the first is visible in
  the code.**
* **The two-sided convention was implicit.** Twice-the-smaller-tail against the small-p method
  differ materially here (0.0122 vs 0.0131 at 46/46; 0.0634 vs 0.0459 at 0/12). Fixed to the
  `binomtest` convention so the published numbers stay on one, and asserted in
  `cfb/test_scan_statistic.py` against a brute-force enumeration over all 2^n outcomes — an
  independent implementation, because a test written from the same mental model reproduces its
  errors, which this one did before the brute force replaced it.

## One comparison that cannot be completed

A parallel implementation reported post-exclusion `Var(t) = 1.308` against this file's `1.503`.
The cell keys behind 1.308 were overwritten by later runs sharing an artifact path and were not
saved. **The comparison is therefore unresolvable and is recorded as unresolvable rather than
reconciled.** The two implementations' corroboration stands on the pre-exclusion max|t| and
cell-count agreement, which is where it was actually independent.
