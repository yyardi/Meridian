# Pre-registration: the horizon ladder past 300s

**Committed before the data exists and before anything is run.** The horizons,
the statistic, the turnover definitions, the censoring rule and the power floor
are all fixed here. Nothing below may be added, dropped or re-cut after the
numbers appear.

Written by Quant B, 2026-09-04, at meridian-14's assignment. The question is
theirs: real-fill drift is **positive at every horizon measured so far**
(+0.2 to +1.2¢ over 10s–300s) while the same fills settle at **−3.4¢**. 300s is
~3% of a football game. **The loss lives somewhere between five minutes and
settlement and nobody has looked there.**

---

## 1. The horizons — named now, in this order, and no others

    30s   60s   300s   900s   1800s   3600s   settlement

`settlement` is already in the export and is the KNOWN terminal value. The
ladder does not discover the endpoint; it fills the gap between 300s and it.

**No horizon may be added later.** If 3600s proves unreachable the ladder stops
short and says so; it does not grow a 2700s rung chosen because it worked.

## 2. The statistic

    drift_i(h) = side_i × (mid_{i,h} − mid_{i,fill}),  in cents
                 side = +1 for a bid fill (we bought), −1 for an ask fill

**Positive = favourable to us**, matching meridian-14's convention in the
markout run. Note this is the NEGATIVE of the λ used in `lambda_q_measure.py`;
the two must never be quoted side by side without saying which is which.

Reported game-clustered throughout (`clustered_mean`, clusters are games, df =
G−1). Never row-level.

## 3. ★ THE PRIMARY ANALYSIS IS A BALANCED PANEL

**The same fills at every rung.** A fill enters the primary analysis only if it
has a valid mid at EVERY horizon in the ladder.

This is the central design decision and it exists because of the failure
recorded in `FORCED_GRADIENTS.md`: comparing drift(30s) on all fills to
drift(3600s) on the fills that survived is comparing two different populations,
and **any apparent turnover could be composition rather than price**. A balanced
panel cannot produce that artifact — the shape is measured on one population.

Feasibility, measured on fill TIMING only (no drift touched), tail defined to
the last fill in each game, which understates available tape:

| horizon | fills with that much tape after them | games |
|---|---:|---:|
| 300s | 13,841 (98.9%) | 11 |
| 900s | 13,349 (95.3%) | 10 |
| 1800s | 12,292 (87.8%) | 10 |
| 3600s | 9,817 (70.1%) | 10 |

**Balanced panel through 3600s: n ≈ 9,817, 10 games, 349 markets.** The ladder
is runnable. The unbalanced per-horizon series is reported as SECONDARY, always
beside its censoring rate, and never used to claim a shape.

## 4. ★ CENSORING IS REPORTED BEFORE ANY LEVEL IS INTERPRETED

Censoring here is **not random and gets worse with h by construction** — a 1h
horizon is unavailable for late-game fills, and late-game is exactly where this
programme keeps finding the economics.

**Rule, fixed now:** the censoring rate at each horizon is printed FIRST. The
survivorship bias is bounded by rate × effect, as it was for 300s (1.0% rate →
0.08¢, materially dead). At 3600s the rate is ~30%, so **that bound will not
stay small and the balanced panel is the answer, not the bound.** If the
balanced-panel and unbalanced series disagree in shape, the balanced one is
reported and the disagreement is stated as the finding.

## 5. ★ "TURNS OVER" — two different claims, both defined before the run

These are distinct and will not be conflated afterwards:

* **TURNOVER-SIGN.** The smallest h whose game-clustered CI for drift(h) lies
  entirely **below zero**. This is "the fill is now losing money on paper."
* **TURNOVER-PEAK.** The smallest h where the **paired** increment
  drift(h_{k+1}) − drift(h_k), game-clustered on the balanced panel, has a CI
  entirely below zero. This is "the drift has stopped rising", which is a much
  weaker claim and must not be reported as the first.

Pairing on the balanced panel makes TURNOVER-PEAK the more powerful of the two;
that is a property of the design, declared now so it is not discovered later.

**If neither fires by 3600s**, the pre-declared reading is: the settlement loss
is **not a price path inside the first hour**. Combined with a known −3.4¢
terminal value, that supports meridian-14's alternative — a terminal-outcome
mechanism rather than a drift mechanism — and that is a finding, not a null
result.

## 6. ★ THE POWER FLOOR, computed before the threshold is set

The mistake this replaces is mine: earlier today I pre-registered a
point-estimate threshold on an arm whose interval turned out to span 13.6¢, so
the rule could not separate its branches before the run.

At G ≈ 10 clusters the game-clustered CI half-width on this substrate's drift
ran **≈ 0.26¢** (`lambda_q_measure.py`, n≈11,300, 11 games). So:

> **Effects below ~0.3¢ are not detectable here. TURNOVER-SIGN cannot fire on a
> drift whose true value is between −0.3¢ and 0. Any "no turnover" conclusion is
> bounded by that floor and will be stated with it.**

Projection of the decision rule onto its achievable outcomes: both TURNOVER
verdicts are reachable (drift is currently +0.2 to +1.2¢ and settlement is
−3.4¢, so the achievable range spans zero comfortably), and "neither fires" is
also reachable. **No branch is predetermined and none is dead.**

## 7. ★ THE FOUR-DOOR CHECK ON THIS DESIGN

* **Statistic.** Drift at any h inherits the fill trigger: the mid is at-or-past
  our quote on 100% of fills (median overshoot 1.50¢), so early rungs carry
  reversion from a selected extreme. **This contaminates the SHAPE, because
  reversion decays with h while information does not.**
  *Control, declared now:* report the ladder **separately by overshoot
  quintile**. Reversion scales with overshoot (established: λ runs −0.43¢ to
  −4.51¢ across those quintiles). **If the ladder's shape is the same in every
  overshoot bucket, reversion is not driving it. If the shape scales with
  overshoot, it is.** This is the discriminator and it is fixed before the run.
* **Population.** Selected by the fill rule, and the balanced panel selects
  further on game duration — longer games are over-represented at long
  horizons. Reported as a caveat on the panel, with the game count at each rung.
* **Partition.** The ladder is the partition. Horizons are named in §1 and
  cannot be re-cut. Overshoot quintiles are the only secondary cut and are named
  here.
* **Decision rule.** §5 and §6. Both branches reachable, power floor stated.

## 8. What is needed to run this

The existing export carries `mid30/mid60/mid300` and `settlement` only. **The
ladder needs `mid900`, `mid1800`, `mid3600` on the same rows**, same window
(2026-09-04T00:58:46Z → 05:33:43Z), same single-binary cohort
(`engine_commit = 63e7f1b8…`), same side-specific price-identity gate.

I have no prod access, so this is an operator or meridian-14 run. **Nothing in
this file may be revised once that export exists.**
