# Forced gradients on this substrate — a standing note

**Five instruments in one day reproduced their own algebra and were read as
findings.** Two were published before being caught. This note exists so the
sixth is caught by a check rather than by a peer.

## The property

> **On this substrate, any statistic cut by a variable X, over a population
> selected by an X-dependent rule, is guilty until proven innocent — and the
> burden of proof is a geometry-only null.**

The general form is C's, and the generality is the point. Written narrowly as
*"cut by spread"*, someone cuts by quote-age over a population selected by a
quote-age-dependent rule, sees no mention of spread, and ships it. **The check
must fire on the shape, not on the variable.**

Spread is simply the X that keeps recurring here, and it recurs for a structural
reason: **both of this substrate's selection mechanisms are spread-dependent** —
the classification rule (`real ⟺ excess ≥ s/2`) and the quoting gate
(`MAX_SPREAD = 0.15`). Any X sharing that property will behave the same way.

**Crucially, the statistic being algebraically clean of X is not a defence.**
Composition failed on the *statistic* (s on both sides). Drift *passes* on the
statistic — the quote price cancels, no s anywhere — and fails on the
*selection*. Clean algebra plus dirty selection is still forced.

## The five, 2026-09-04

| # | statistic | how it was forced | caught by |
|---|---|---|---|
| 1 | **capture vs mid** | `capture ≡ −overshoot`; corr +1.0000, residual 0.0000¢ | D (2026-09-03) |
| 2 | **width settlement gradient** | spread on both sides of the identity, so the gradient could not fail | D |
| 3 | **real-share composition by width** | `real ⟺ excess ≥ s/2`; a geometry-only null reproduces the monotone decline on both boards | B |
| 4 | **WIDTH cut's phantom-share column** | same rule; band variable IS the threshold variable | C, in their own shipped artifact |
| 5 | **phantom drift by width** | statistic clean of s, but a wider market *requires* a larger excursion to produce a phantom; excursion grows 3.6×, drift 3.5×, ratio flat at ~0.5 (corr 0.973) | flagged by MGR, null built by B |

## The tells

**A pair, and it is the pair that discriminates:**

1. **Confidence intervals an order of magnitude too tight** for a noisy economic
   quantity, and
2. **suspiciously clean monotonicity.**

The canonical demonstration, on *identical fills*: capture ran monotonic with
~0.3¢ CIs while settlement ran non-monotonic with ~8¢ CIs. One of those is a
measurement.

A third tell, from #3: **a degenerate cell that nobody would defend.** The ≤1¢
band read 99–100% real, because the bar is 0.5¢ and a 1¢ tick almost always
clears it. Nobody would read that as informed flow avoiding tight markets — and
the same algebra produced every other cell in the column.

## The principle, which is already in the record

> **A result that replicates because it CANNOT FAIL is not a replication.**

And its counterpart, from the asymmetry ruling in
`docs/math/adverse-selection-measured.md` — these look identical and are
opposites:

* The **phantom rate** replicating across sports (63.9% WNBA / 65.0% CFB)
  **confirms**: it is a property of the simulator, and stability across boards
  is exactly what the mechanism predicts.
* The **phantom gradient in spread** replicating across sports **confirms
  nothing**: one fill rule, two boards, same algebra.

Same word, opposite epistemic status. **Ask which one you have before quoting a
replication.**

## What to do about it

1. Before cutting a statistic by X, ask whether the population was selected by a
   rule involving X. If yes, build the geometry-only null **first** — hold the
   distribution fixed, move only the threshold, and see whether the gradient
   falls out.
2. If you cannot build the null, **say so in the printed output**, not in a
   message. A caveat in prose is a promise to remember; a caveat the artifact
   prints is a caveat that travels.
3. A statistic that is algebraically clean of X still needs step 1.

## Still open

The **h=0 decomposition** in `docs/math/markout-measured.md` shows 54% of the
phantom/real markout gap is the classification criterion restating itself.
Markout is now the low-variance metric, so someone will reach for that gap
precisely because its intervals are tight. **That is the sixth instance waiting
to happen.**

---

# Second family: the threshold and the measurement are not the same quantity

A different failure with the same fingerprint — **an artifact that runs green
while measuring something other than what its author believes.** Added because
c7 hit it on 2026-09-04 *inside the alarm built to catch the other family*.

## The instance

The CFB live-recorder alarm was built to fire when snapshot cadence degrades.
The **baseline** was derived from a **median** (median snaps per market-minute =
2.0). The **query** was written as a **mean** (rows ÷ markets). On a healthy
11-game control those are:

| statistic | healthy value |
|---|---:|
| median writes/market/min | **1.90** |
| mean writes/market/min | **8.36** |
| p90 | 17.8 |
| max | 178 |

Writes are **change-triggered**, so an active market writes 178 times a minute
and a quiet one 5. **The mean measures market ACTIVITY; the median measures
recorder CADENCE.** The alarm's `ESCALATE below 1.2` threshold, applied to a
statistic that reads 8.36 when healthy, **would have required a sevenfold
degradation before firing.**

It was caught only because the alarm was exercised on a healthy control before
being needed. *An alarm first exercised during the incident is not an alarm.*

## The same fingerprint, five times in one day

Per-order vs per-tick · spread-cut vs spread-selected · estimator vs estimator ·
regime vs regime · median vs mean. **In every case the arithmetic was correct
and the two quantities were not the same thing.** None of them would have been
caught by re-reading the number.

## The fix, which differs from the first family's

The forced-gradient fix is a **geometry-only null**. This one's is narrower and
cheaper:

1. **Compute the threshold with the identical expression the alarm will run.**
   Not the same concept — the same code path. A baseline derived one way and
   applied another is two quantities wearing one name.
2. **Exercise the alarm on a healthy control before it is needed**, and on more
   than one, at different loads. Two independent healthy controls agreeing to
   two decimals is what made the corrected version trustworthy.
3. **Report two axes when one can be confounded by activity.** The corrected
   alarm reports sweeps/min (the loop's own health, independent of market
   activity) *and* median writes/market/min (what actually lands). A quiet board
   depresses the second and not the first — and that confusion is exactly what
   broke the original.
4. **Give the alarm a NOT-STARTED branch.** `live_games = 0` must read as
   "metric undefined", never as a degradation. Rule 22, applied to the alarm.

---

# Corollary: killing a confound cheaply, without resolving it

The inverse of the underpowered-null trap, and worth stating because the
instinct it corrects — *"we cannot rule this out, the CI is huge"* — is common
and wrong.

> **When a bias decomposes into `rate × effect` and the RATE is measured
> precisely, the bias is bounded however noisy the EFFECT is.**

Demonstrated 2026-09-04 on the drift survivorship confound. Censored fills
settle **−10.962¢ [−18.498, −3.427]** against measurable fills' −2.787¢ — an
8.2¢ effect with a 15¢-wide interval, nowhere near resolved. But the censoring
**rate** is 1.0% (133 of 13,651), measured exactly. So the aggregate bias is
0.010 × 8.176 = **0.08¢** on a −3.4¢ number, and **0.16¢ even at the interval's
most extreme edge.** The confound is real in direction and dead in magnitude,
and no additional data was needed to say so.

**The move:** before declaring a confound unresolvable, check whether it
factorises and whether one factor is a count you already have. A confound whose
prevalence is known cannot be large, however uncertain its severity.

*(B raised the confound, named the right suspect precisely enough to rule it
out, and then made this generalisation from having been directionally right and
materially wrong.)*

## A third instance in the alarm family, and the sharpest one

The corrected alarm was tested on a "slate start" control and passed. **It would
still have falsely ESCALATED three minutes into the slate** — the first moment
anyone would ever run it.

The query divided by a **fixed 10-minute window**. Three minutes after the first
game goes live, `now() - 10 minutes` contains 3 minutes of data and 7 of
nothing. Measured on real healthy data:

| span in window | fixed-divisor reading | verdict | span-derived reading | verdict |
|---:|---:|---|---:|---|
| 9.98 min | 17.8 | FINE | 17.8 | FINE |
| 2.95 min | 5.6 | **ESCALATE ✗** | 19.0 | FINE |
| 0.96 min | 2.1 | **ESCALATE ✗** | 21.8 | INSUFFICIENT WINDOW |

**Why every check missed it:** the slate-start control was fed a window
containing ten full minutes of data. The production predicate cannot have that
at slate start.

> **A control that supplies the instrument with conditions the production path
> cannot produce is not a control.**

Testing "the first ten minutes" *with ten minutes of data* tests a different
thing than the first ten minutes. Add to the fix list in this section:

5. **Derive the denominator from the data's own span**, and refuse to interpret
   below a minimum span. A nominal window is an assumption about data that may
   not be there.
6. **Build controls from the production predicate**, not from a hand-picked
   window that satisfies it. If the control cannot be produced by the real
   query at the real moment, it is testing something else.

*(Also caught in the same pass: the column named `sweeps_per_min` counted write
BATCHES, not board refreshes — 694 rows share one timestamp, and a full pass
over 1,477 markets takes ~2 stamps. Renamed. The number was right; the name was
a claim it did not support, and a reader consulting it once under pressure reads
the name.)*

---

# Third family: the bias is in the statistic's own expectation — no cut at all

**The first family is about CUTS: a statistic sliced by X over an X-selected
population. This one has no cut in it.** A single number, compared against
zero, where zero was never the right comparison. Added 2026-09-04, caught
**before** the observed value existed — the only instance of the day for which
that is true, and the reason it is worth its own heading.

## The instance

D's accumulator hypothesis needed a statistic for *"was our position on the
right side of the outcome, relative to what the market believed when we took it
on?"* The one declared, before any null was generated:

```
per real fill i:   x_i = side_i × (s_m(i) − mid_at_fill_i)
                   side = +1 for a bid fill (long YES), −1 for an ask fill
S = mean_i x_i,  in cents
```

Measuring against the mid rather than our quote price deliberately strips our
execution edge, leaving only the direction question. **I declared that a fair
accumulator scores S = 0.** That was wrong, and nothing about the statistic is
wrong — only the baseline I attached to it.

## The derivation, which needs no data at all

Under a fair market, a market's outcome has expectation equal to the market's
own belief: `E[s_m] = p_m`, taking `p_m` as the mean mid across our fills in
that market. Substituting:

```
E[S | fair] = mean_i side_i × (p_m(i) − mid_i)
```

Write each fill's mid as its market's mean plus a deviation, `mid_i = p_m + d_i`:

```
E[S | fair] = − mean_i ( side_i × d_i )
```

**So the fair-market expectation of S is exactly the negative of the covariance
between our trading direction and the price level within a market** — and the
fill rule guarantees that covariance is non-zero and negative. A resting bid
fills only when the mid comes DOWN to it, so bid fills (side = +1) sit at low
mids (d < 0). A resting ask fills only when the mid comes UP, so ask fills
(side = −1) sit at high mids (d > 0). Both products are negative, so both
sides contribute the *same sign* to E[S], and the expectation is positive.

Measured on the 13,651 real fills:

| | mean mid at fill | market's mean mid | contribution |
|---|---:|---:|---:|
| bid fills (long) | 0.4591 | 0.4897 | **+3.05¢** |
| ask fills (short) | 0.5467 | 0.5136 | **+3.30¢** |

```
E[S | fair]  =  +3.174¢     (closed form, no settlements read)
resampling null mean = +3.176¢   (4,000 draws)
```

**An analytic value and a simulated one agreeing to the third decimal is a
proof with a check attached.** A fair market scores +3.17¢ on this statistic.
Comparing S against zero would read a fair result as a 3-cent edge — on a
−3.4¢ effect, the entire answer.

## Why this one is different, and worse

The five in the first family announce themselves once you look: they are
gradients, and a suspiciously clean monotone column invites suspicion. **This
one has no shape to notice.** It is a single number, and a single number
compared against the wrong constant looks exactly like a single number compared
against the right one. There is no tell in the output — the check has to happen
before the output exists.

It also cannot be caught afterwards. **Once the observed value exists, a
3-cent offset is indistinguishable from a finding somebody was hoping for.**
This is the concrete argument for building nulls *first* rather than as
validation: not that it is more rigorous, but that after the fact the
information needed to catch it is gone.

## The rule

> **Before comparing a statistic to zero, derive what a fair process scores on
> it. If the population was selected by the price path — and every fill
> population is — the answer is usually not zero, and it is usually derivable
> with no data beyond the selection rule itself.**

The recurring shape, stated so it fires on the next one: **any statistic that
compares an outcome against a per-observation reference price, aggregated over
a population whose direction correlates with that reference price, has a
non-zero fair-market expectation equal to that covariance.** Reference prices
that qualify: mid at fill, mid at quote, arrival price, VWAP over a window that
includes your own trades.

## What to do about it

1. **Derive `E[statistic | fair]` in closed form before generating anything.**
   If it is not zero, the bar is that value, and the write-up says so in the
   sentence that reports the result — never "S versus zero".
2. **Check the closed form against a simulation.** Agreement to the third
   decimal turns an argument into a verification; disagreement means one of
   them encodes an assumption you did not intend.
3. **Resample at the level the randomness lives.** Settlement is constant
   within a market here (0 of 564 markets carry two values), so a per-fill
   interval over 13,651 fills is `√(13,651/564) ≈ 4.9×` too narrow. The null
   inherits the dependence for free; a per-row CI manufactures significance.
4. **State the firewall explicitly rather than asking to be trusted on it.** A
   null built by someone who has seen the answer is a weaker null. For this
   one: construction (a) never reads observed settlements, (b) reads them only
   to permute and evaluates no identity permutation, no observed value is
   computed anywhere in the script, and the author had not seen it.
5. **Mutation-test the null itself** (rule 4). It must read inside its own band
   on a fair synthetic and decisively outside on an injected effect. The step
   gets skipped because a null feels like infrastructure; it is an instrument.

## A by-product worth keeping: two nulls disagreeing is information

Two constructions were built because the manager asked for both, on the
grounds that disagreement would be informative. It was:

| null | centre | 95% band |
|---|---:|---|
| (a) resample each market's outcome at its own mean mid | +3.18¢ | [+2.15, +4.24] |
| (b) permute observed outcomes across markets, within p-decile strata | +2.18¢ | [+1.31, +3.12] |

Near-identical dispersion, centres 0.99¢ apart. **(a) assumes the mid is
calibrated and draws outcomes from it; (b) inherits the observed outcome rate
within each price decile and breaks only the pairing between markets and
outcomes. The gap is therefore the contribution of the market's own
calibration error over our fills** — a quantity neither null was built to
measure, visible only because both were built.

**(b) is the primary bar** for a position question, because it does not
additionally assume calibration, which is a separate claim carrying its own
evidence. (a) belongs beside it as the sensitivity that adds that assumption.

*(Instance and derivation: B. Both-constructions instruction and the ruling on
(b): MGR. Artifact: `analysis/accumulator_martingale_null.py`.)*

---

# Fourth entry: power and independence do not rank together

Not a forced gradient — it belongs here because **the temptation is identical**:
ship the tighter number and call it a confirmation.

Three instruments read the same underlying fact (did a trade print at or below
our bid) and rank *differently* on power and on independence:

| instrument | base rate | power | independent of `last_trade_px`? |
|---|---:|---|---|
| `last_trade_px` | 20.6% | most (one print/interval) | — (it *is* the primary) |
| interval **VWAP** | higher | **more** — all the interval's volume | **NO** — same trade tape |
| **`low_px` fall** | 6.8% | **least** | **YES** — extremes are a different mechanism |

> **VWAP buys resolution. It does not buy a second opinion.**

VWAP and `last_trade_px` are **correlated instruments, not separate evidence**.
The witness was weak *precisely because* it was independent. So:

**If you want corroboration rather than a tighter interval, a sharper version of
the primary will not give it to you.** Build the precision instrument if
precision is what you need, label it as one, and never report it as confirming.

> ★ **AND "MORE CELLS ON THE WEAK ROUTE" — my own first answer — IS ALSO WRONG,
> corrected the same evening by measurement.** On shared ground the weak route's
> treatment base rates were **69% and 83%**: a new session low essentially *is*
> the event being tested, so nearly every cell scores positive in both arms.
> **There is no headroom for treatment to exceed control.** Extra cells shrink
> the interval around a contrast that is structurally near zero.
>
> **A saturated instrument does not become informative by being run more.**
>
> The real requirement is harder than "more data": **corroboration needs an
> instrument that fires where the outcome is NOT nearly guaranteed.** Check the
> base rate in the region where two routes overlap *before* commissioning
> collection on either — a ceiling effect and a power problem look identical
> from the interval alone.

## And the convergence rule has TWO legs, not one

**Same estimand** *and* **independent route.** The witness established the
second and left the first open: it fires only on a new session low and is biased
toward early-game intervals, so **if consumption varies by game phase it
measures early-game consumption while the primary measures all-phase
consumption — two different quantities, between which neither agreement nor
disagreement is informative.**

That ambiguity is cheap to resolve and the resolution is a filter, not an
instrument: **restrict the PRIMARY to the witness's own population.** If the
primary drops to the witness's level they agree within it and the gap is a phase
effect; if it holds, the witness disagrees on shared ground. Either way it
converts an underpowered null into a matched-population comparison, which is the
only form in which a weak route can speak.

## The reason attached to a downgrade decides the next action

"A second route **contradicted** it" argues for **dropping** the line.
"The second route **could not resolve**" argues for **funding more cells** on
it. Same number, opposite actions. **State which one you have.**

## A portable version of the flattering-direction check

Not a virtue, a procedure, and stated that way by the author who used it after
having been wrong in that exact direction ninety minutes earlier:

> **An argument that improves your own result gets its direction stated in the
> same sentence it is made.**

---

# Fifth entry: a forced gradient can arrive through a MATCHED POPULATION

The three families above are about a **statistic**. This one is about a
**restriction**, and it fooled three of us in sequence.

To settle whether a weak second route agreed with a primary, we restricted the
primary to "the witness's own population." That phrase has two readings and only
one is a test:

* **(a) intervals where the witness COULD fire** — our quote at or below the
  running session low. **Inside this population, any qualifying print IS a new
  session low.** The two instruments collapse onto nearly the same event and
  differ only in masking. **Agreement here is substantially algebraic and will
  appear whether or not the phenomenon is real.**
* **(b) the witness's PHASE population** — early-game intervals — *without* the
  mechanical coupling. The instruments stay distinct, so agreement or
  disagreement carries information.

**(a) was run.** The tell was visible in the result and was correctly diagnosed
as saturation — treatment base rates of **69% and 83%** on 42 cells, no headroom
for treatment to exceed control — but the *reason* for the saturation is the
collapse, and "the routes agree" was reported before that was named.

> **When you restrict one instrument to another's population, ask whether the
> restriction makes them measure the same event. If it does, agreement is
> arithmetic.**

**A ceiling effect and a power problem look identical from the interval alone.**
Check the base rate in the overlap region before running, not after.

## And the transfer model is part of the comparison

Reading "the witness's interval excludes the primary's point estimate" as
inconsistency assumes the effect transfers as an **absolute** percentage-point
elevation. It cannot when one instrument's events are a strict **subset** of the
other's — the transfer is sub-proportional by construction. On the relative
scale the primary's own effect predicts a value that sits comfortably *inside*
the witness's interval. **Two intervals cannot be compared without stating how
the effect is assumed to transfer between their populations.**

## Pre-declaration has a hole, and it is not fitting

> **Pre-declaration protects against fitting the RULE to the DATA. It does not
> protect against a rule that was WRONG WHEN WRITTEN.**

Observed the same evening: an amendment's decision rule contradicted arithmetic
recorded in the same edit — a branch was pinned that an earlier amendment had
already foreclosed. Sealing it first made the failure legible; it did not make
the rule correct. **Check a new decision rule against the arithmetic already in
the document before sealing it.**
