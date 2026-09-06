# Is "positive drift, negative settlement" partly survivorship? — registered before the read

Written 2026-09-04, **before the comparison was computed.** B raised the
confound (`analysis/phantom_drift_geometry_null.py`, 17b78df) and deliberately
did not run it, because the test is "does settlement depend on how late in the
game the fill happened", and that is exactly the relationship that must be
pinned before anyone looks.

## The claim under test

`docs/math/markout-measured.md` records that **real-fill drift is positive at
every horizon** (+0.2 to +1.2¢) while the same fills **settle at −3.4¢**, and
concludes the loss is not in the immediate flow.

**The confound:** drift at horizon *h* is only computable for fills that have a
tick at *t+h*. Fills near the end of a game lose that window — the market
settles, the recorder stops, the game ends. **But late fills are exactly where
terminal information concentrates and where settlement is decided.** So drift
may be measured on a population biased toward early and mid-game fills,
systematically excluding the ones whose settlement loss is largest. If so,
"positive drift, negative settlement" is partly **two different populations**
rather than one paradox.

It would also explain the other refuted prediction — divergence still growing at
300s rather than decaying — since surviving fills are those with the most game
left to run.

## The comparison — fixed now

Population: **real fills only.** Estimator: **`clustered_mean`** (pooled mean,
game-cluster-robust SE), the standardised one. Unit: **cents of settlement P&L
per fill.** Clustered by **game**.

**PRIMARY TEST.** Split real fills into:
* **MEASURABLE** — has a non-null `mid300` (a 300s drift window exists)
* **CENSORED** — does not

and compare their settlement P&L. One comparison, no bucketing, no tuning.

**SECONDARY, reported whatever the primary says**, using `min_since_tip` from
the enriched pin, in bands **fixed here before the read**:
`[0–30, 30–60, 60–90, 90–120, >120]` minutes since tip — the same edges C
pre-declared for LATENESS, reused deliberately so no new degrees of freedom
enter. For each band: n, censoring rate, and settlement P&L.

Also reported: the same split at **h=60s**, the horizon the coverage correction
made the working one. If censoring drives the result it must weaken as coverage
rises (96.9% at 60s against 98.9% at 300s).

## Predictions, so this can be wrong

1. **If the confound is real:** CENSORED fills settle materially WORSE than
   MEASURABLE ones, and censoring concentrates in the late bands.
2. **If the paradox is real:** the two subsets settle indistinguishably, and the
   drift population is representative.
3. **Stated in advance because it is the likely outcome and the least
   satisfying:** at G=24 with per-game sd ~4¢, a difference smaller than ~2¢
   will not be resolvable. **An indistinguishable result is then NOT evidence
   that the paradox is real — it is an underpowered test**, and it must be
   reported as "cannot distinguish", never as "the paradox survives."

## What this cannot do

It tests whether the drift-measurable population is unrepresentative **on
settlement**. It cannot recover the drift of censored fills — that data does not
exist, by construction. So a clean result bounds the confound; it does not
remove it.

Nothing here gates. No in-sample result justifies capital.
