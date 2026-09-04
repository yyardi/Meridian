# Forced gradients on this substrate — a standing note

**Five instruments in one day reproduced their own algebra and were read as
findings.** Two were published before being caught. This note exists so the
sixth is caught by a check rather than by a peer.

## The property

> **Any result whose shape is determined by an analyst's choice — of STATISTIC,
> of POPULATION, or of PARTITION — is guilty until proven innocent, and the
> burden of proof is the same in all three: run the design on a substrate with
> no phenomenon and the same geometry, and see whether the signature still
> appears.**

**Three stages where a design can force a result** — you choose *what to
compute*, *what to compute it over*, and *how to group it*. Each can manufacture
the signature by itself, and **a clean stage does not clear the others.**

**And a fourth locus where nothing is forced at all: THE DECISION RULE.**

| stage | the choice | forced? | caught by a null? |
|---|---|---|---|
| 1 | **statistic** | yes — reproduces its own inputs | **yes, exactly** (identity) |
| 2 | **population** | yes — selection depends on the measurand | yes, in expectation |
| 3 | **partition** | yes — bucket edges set the shape | yes, in expectation |
| 4 | **decision rule** | **no** | **NO — nothing to simulate** |

Stage four is the inference attached to a result. Honest statistic, honest
population, honest partition, correct arithmetic — **and the conclusion still
wrong, because the rule reading the number was wrong when it was written.** A
null substrate run through a defective rule yields a correct number and a wrong
reading, exactly as a real one does. **It is caught only by auditing the rule
against what was already known when it was written.**

**THE STAGE-FOUR CHECK — one computation, four readings.** Take the *achievable
outcome range* of the design, project it onto the decision rule's branches, and
inspect the image:

| what the image looks like | the defect |
|---|---|
| a **single branch** | **PREDETERMINED** — every possible outcome gives the same verdict |
| **adverse branch at the best case** | **INVERTED** |
| **a branch outside the image** | **DEAD BRANCH** — a verdict the design can never return |
| spans branches, **interval too wide** | **CANNOT DISCRIMINATE** |

*My first version of this check was the last row only — "compute the interval
width and ask whether the threshold can distinguish the branches" — and that is
exactly why it missed the predetermined case. **Clause-adding is the list form,
and a list can always have a fifth; the projection closes it.***

★ **The instance with capital attached.** The resting-order probe's rule at the
planned **n=40**: the upper bound ranges from 8.81% (zero violations) to 100%,
so **all 41 possible outcomes return REFUTED.** The probe would have spent real
money computing an answer fixed before the first order rested, and reported the
phantom criterion destroyed on a flawless run. Withdrawn for n≥60, n=100
recommended. **And the fix does not fully clear it**: CONFIRMED needs an upper
bound below 1%, first reachable at **n=368**, so at n=100 a rule advertised as
three-band is structurally **two-band** — a DEAD BRANCH, the same species as the
one just withdrawn. Defensible if stated; not defensible if advertised.

★ **AND THE REPAIR HIT A HARDER WALL THAN "MORE SAMPLE".** Costing the
CONFIRMED-reachable design at 0.348 fills per standing minute, worst case =
fills × $0.80:

| design | fills | worst case | |
|---|---:|---:|---|
| n=100 × 10-min | ~348 | **$278** | Leg A tops out at SUPPORTED; **Leg B strongest** |
| n=381 × 5-min | ~663 | $530 | Leg A can reach CONFIRMED; **Leg B halved** |
| n=381 × 10-min | ~1,326 | **$1,061** | **breaches the $1,000 wallet** |

**CONFIRMED is not purchasable at the registered window at any price the wallet
allows.** It is reachable only by halving the window, which halves the very
crossing episodes the *other* leg depends on. So the choice is not "spend more"
— it is **a trade between legs**, and the leg being traded away (sufficiency)
is the one with **no alternative instrument at all**, while the leg being
upgraded already has a historical-reconstruction proxy.

**CONFIRMED stays in the rule, marked unreachable at the recommended sample
rather than deleted.** Deleting it would hide that the probe cannot fully close
that leg at any wallet-permitted price — **which is a finding about the
program's limits, not a defect in the registration.**

★ **THE 27% SPREAD IN n RESOLVED — AND IT WAS 85% SIDEDNESS, NOT METHOD.**

| | n | |
|---|---:|---|
| Clopper-Pearson, **one-sided** 95% | **299** | |
| Clopper-Pearson, two-sided 95% | 368 | ← +23% from **sidedness alone**, same method |
| Wilson, two-sided 95% | 381 | ← +3.5% from **method** |

**~85% of the disagreement was sidedness; ~15% was method.** All three bands are
on the **upper** bound of a violation rate — nobody wants a lower bound on how
often the venue violated — so **the question is one-sided by construction**, and
a two-sided interval buys 23% more sample for no inferential gain.

> **A sample-size threshold is a number, a method, a sidedness, AND AN
> INDEPENDENCE ASSUMPTION — and on this substrate the last is the one that has
> historically been wrong.** One author pinned "Wilson" believing they had made
> the convention explicit, and pinned the *smallest* of the four while leaving
> the two larger ones implicit. **Naming a convention does not mean you named
> the one that is doing the work.**

★★ **AND THE INDEPENDENCE ASSUMPTION INVALIDATES ALL FOUR NUMBERS.** Verified in
the code rather than argued:

* **`clustered_mean` does not use Wilson.** It is a cluster-robust estimator with
  a *t* critical value at df = G−1 (`core/quote/adverse_selection.py`), so the
  consistency reason offered for Wilson was misattributed.
* **Wilson *is* a house convention** — `core/pulse/win_curve.py:151` and
  `core/backtest/exp_margin_shrinkage.py:57` — **but both call sites are
  GAME-LEVEL binomials**: wins over resolved games, one observation per game,
  independence plausible. `GATE_MIN_GAMES = 10` sits directly above one of them.

**The probe counts ORDERS, many per game. That is the row-level case, not the
game-level one.** And `clustered_mean`'s own docstring is the argument against
using a binomial there:

> *"One game emits ~130 ladder rows a second, all responding to the same score.
> The row-level standard error treats them as ~130 independent observations…"*

**A binomial interval over ~300 orders treats them as ~300 independent
observations — the precise error `clustered_mean` was written to prevent,
reappearing in a different estimator.** If violations cluster by game, market, or
venue-state episode, the effective n is nearer the number of independent
episodes than the number of orders, and **every one of the four figures
understates the requirement — the cheapest one most of all.**

> **The author who had just produced the cheapest figure withdrew it on this
> grounds**, noting it is the least conservative of the four and therefore the
> most wrong if orders cluster: *"I should have asked about clustering before
> repricing anything in this programme, of all programmes."* **A saving is not
> banked until the independence assumption behind it is settled.**

★★ **ANSWERED — AND IT WAS THE ALLOCATION, WHICH THE REGISTRATION NEVER
SPECIFIED.** The same total order count is worth wildly different amounts of
information depending on how it is spread across games. At a 3.3h in-game span
and 10-minute windows, one market hosts ~19 sequential orders, so 6–8 markets in
one game is 120–150 orders — **"299 orders" could be as few as two games.**

Design effect `1 + (m−1)ρ` at ρ = 0.05:

| allocation | G | orders/game | deff | effective n | bound |
|---|---:|---:|---:|---:|---:|
| **concentrated** | 2 | 150 | 8.45 | **35** | 8.48% — **fails even the weak verdict** |
| moderate | 20 | 15 | 1.70 | 176 | 1.71% |
| **spread** | 100 | 3 | 1.10 | **272** | **1.10%** |

At perfect clustering (ρ = 1) the effective n **is** the game count: G=20 → 15%,
G=100 → 3%, G=300 → 1%.

**A factor of ~8 in information, decided by a parameter nobody had written
down.**

★★ **AND THE REALLOCATION IS FREE.** Same order count, same window, same total
standing time — therefore **same capital (~$835 worst case) and the same
crossing episodes on the other leg.** Only the spread changes.

> **We were about to buy the worst possible arrangement of a fixed budget.**

**The requirement is now GAMES, not orders: ≥100 games, ≤3 orders per game,
10-minute windows.** *(And tomorrow's slate carries 103 games — the binding
constraint turns out to be breadth, which the calendar already supplies.)*

> **A sample size is not a count of observations, it is a count of INDEPENDENT
> ones — and the allocation that decides which is often the parameter nobody
> specified.** Before pricing a design, ask what its observations are spread
> across. **And check whether the fix is free before treating it as a cost:**
> here the entire factor of 8 was available at identical spend.

★ **THE UNIT ERROR REPEATED ONE LEVEL UP.** The registration's own §3 says
*"ticks inside one order are heavily correlated; the honest effective N is
orders, not ticks."* Correct — and it stops exactly one level short. **Orders
inside one game are correlated too.** The author's verdict on themselves: *"I
congratulated the document on catching the unit error while committing it at the
next level."* **Catching a unit error at level k is not evidence you have
checked level k+1.**

★ **AND ρ IS NOT ESTIMABLE FROM WHAT WE HAVE.** The pilot's two violations fall
in different markets, different games, 168.5 hours apart, across 19 markets —
consistent with independence, and **it is two events.** The whole table turns on
ρ. So the design is made **robust to ρ ≠ 0 rather than assuming it away**: the
probe reports a **cluster-robust interval at df = games − 1**, not a binomial.
The earlier cost tables, which priced order counts under an unchecked
independence assumption, are void as stated.

★★ **AND THE WALLET CONSTRAINT RECORDED ABOVE DISSOLVES UNDER THE CORRECT
CONVENTION.** Repriced at n=299: **1,041 fills, worst case $833 — inside the
$1,000 wallet**, at the registered 10-minute window, with **no halving and no
cost to the other leg's crossing episodes.** So "not purchasable at any
wallet-allowed price" was an artifact of the two-sided convention, and the trade
between legs is not forced. The table above is kept because *the reasoning that
produced it was sound on its inputs* — the inputs were the convention.

★★ **AND THE RECOMMENDATION DID NOT SURVIVE EITHER — its second reason inverts.**
Leg B scales with **total standing time (n × window)**, not with n, so more
orders at the *same* window means **more** crossing episodes, not the same
number:

| design | order-minutes | Leg B episodes | worst case |
|---|---:|---:|---:|
| n=100 × 10-min | 1,000 | ~348 | $278 |
| n=299 × 10-min | 2,990 | **~1,041** | $832 |

**The larger design reaches the stronger verdict on one leg AND triples the
other. It dominates on both simultaneously.** The "trading away the only test of
sufficiency" argument was right that the trade would be wrong and **wrong that
the trade existed** — the trade was an artifact of the sidedness convention, not
a fact about the design. *Both* of the recommendation's reasons are gone: the
wallet one because the constraint dissolved, the leg one because it inverts.

★ **AND "3× THE CAPITAL" IS TRUE OF BOTH FIGURES AND MISLEADING ABOUT ONE:**

| | small | large | difference |
|---|---:|---:|---:|
| **worst-case exposure** (solvency bound) | $278 | $832 | — |
| **expected P&L cost** (at −3.4¢/fill) | $11.83 | $35.38 | **$23.55** |

The worst case assumes **every** fill settles maximally against us, which cannot
occur. **The expected cost of the better design is thirty-five dollars; the
difference between the designs is twenty-four.** What $832 measures is an **83%
worst-case draw on a $1,000 wallet — a solvency question, not a cost question.**

> **State exposure and expected cost separately. A single "3× the capital"
> collapses a $24 expected difference and an 83% solvency draw into one number
> that answers neither.** Which of the two decides it is the reader's risk
> appetite, and that is not the analyst's to assume.

★ **BUT NOTE THE ORDER OF OPERATIONS: the domination argument is robust to the
independence question above; the specific n is not.** "More orders at the same
window is better on both legs" holds however the interval is computed. **"n=299
reaches the stronger verdict" assumes independent orders and is the least
conservative of the four figures.** The direction survives; the number is
pending.

**The original recommendation's remaining merit, and the reason it mattered:** The author who removed the constraint stated two guards on
their own argument, both in the cheaper direction:

1. **It is not price-driven** and would be identical if one-sidedness pushed n
   *up*. **Choosing a convention BECAUSE it fits the budget is stage four in the
   other direction** — the same shape as widening a band because the design can
   reach it.
2. **It removes one of two reasons, not the recommendation.** The second reason
   is independent and stronger: the leg being traded away has *no alternative
   instrument*, while the one being upgraded already has a proxy. **Removing a
   constraint is not reversing a recommendation.**

★ **AND THE DISCOVERY RATE IS ABOUT OUR ATTENTION, NOT ABOUT TONIGHT.** Three
decision-rule defects appeared in one evening against **zero** before anyone
looked — because **no null catches them, so nothing in the existing machinery
was ever pointed at this axis.** Consequence, stated plainly: **every
pre-registration already in the record was written without this check.** The
back-catalogue is unaudited on stage four, and the check is one computation
each.

> **This preface said "three stages is all there are" and a fourth was found
> within the hour — by which time I had promoted the closed-set claim to the top
> of a document about not trusting claims.** Both the claim and its
> counterexample are kept, here and in the eighth entry, because *a claim that
> failed within the hour is worth more as a recorded failure than as a corrected
> line*. **Read the list as the loci found so far, not as a closed set.**

The synthesis at the end (eighth entry, with its amendment) works through all
four with their instances, and explains why the tells get *weaker* down the
pipeline — by stage three the aggregate is arithmetically correct and there is
nothing to look wrong; by stage four there is nothing to simulate.

*This property was originally written narrowly — "any statistic cut by a variable
X, over a population selected by an X-dependent rule" — which covers stages one
and two only. **A two-way split is neither a statistic nor a selection rule; it
is an aggregation choice, and the phase error passed the narrow property as
written.** The narrow form is kept here because its failure is itself an
instance: a guard can be forced by its own scope.*

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

**A pre-declared decision rule can be wrong in three ways, and pre-registration
defends against only the first:**

| | | defended by pinning? |
|---|---|---|
| 1 | **fitted to the data** afterwards | **yes** |
| 2 | **internally inconsistent** with facts already in hand when written | no |
| 3 | **measuring a population the instrument cannot speak about** | no |

Two and three are **design** errors. **Pinning makes them auditable, not
absent** — it preserves them in a form that can be caught, which is worth having
and is not the same as preventing them.

Both were generated within one hour on 2026-09-04. (2) was an amendment whose
decision rule contradicted arithmetic recorded in the same edit. (3) was a
restriction conditioned on an **outcome** — the witness having actually fired —
which is **collider conditioning**, and whose "saturation" was then reported as a
property of the population when it was a description of the design error. Both
withdrawn by their own author.

**Check a new decision rule against (a) the arithmetic already in the document
and (b) whether the instrument can speak about the population, before sealing
it.**

Observed the same evening: an amendment's decision rule contradicted arithmetic
recorded in the same edit — a branch was pinned that an earlier amendment had
already foreclosed. Sealing it first made the failure legible; it did not make
the rule correct. **Check a new decision rule against the arithmetic already in
the document before sealing it.**

---

# Sixth entry: two rules about your own results

Both observed on 2026-09-04, both stated by the author they cost.

## A standard applied in only one direction is not a standard

An author defended a weak null with *"under-powered, therefore uninformative"* —
correct. An hour later their own pre-committed point estimate was crossed, and
the identical argument was available: the interval was wide enough to contain
both the prediction and zero, so the refutation was not decisive.

**They declined it, and named why: correct there, self-serving here.**

> **Before using an argument about your own result, check whether you used the
> opposite argument on someone else's within the same session.** Power
> objections, interval-width defences and "not decisive" all have this shape —
> they are valid, and they are valid in both directions.

## Do not bundle a structural claim with an economic one

The same prediction contained two claims that were scored together and should
not have been:

* **structural** — the instrument is blind to late consumption *by
  construction*, because our quote sits above the running low once price has
  ratcheted;
* **economic** — consumption *concentrates* late, imported from the ride-tail
  loss map.

**The economic half was falsified; the structural half was confirmed** — and the
structural half was the only one doing any work. Bundled, the falsification
looked like it damaged both.

> **Separate "my instrument cannot see there" from "the phenomenon is not
> there." They fail independently, they are supported by different evidence, and
> a prediction that bundles them cannot be scored.**

The better outcome was the unbundled one: the instrument's attenuation is
explained **without requiring the economics to cooperate.**

## Seventh: a two-way split can INVENT a trend a three-way split does not have

Recorded within the hour of the entry above, on the same result, by the same
author — and I repeated it upward before it was checked.

A prediction was falsified, and the falsification was described as being *"in
the opposite direction — consumption is elevated more EARLY than late"*, from a
**two-way** split: non-early +3.68pp (n=1,034) against early +5.48pp (n=469).
**The arithmetic was exactly right.** The direct **three-way** run:

| phase | relative | excess | n |
|---|---:|---:|---:|
| early | 1.249× | +5.48pp | 469 |
| **middle** | **1.143×** | **+2.76pp** | 557 |
| late | 1.233× | +4.78pp | 454 |

**Flat. Late is indistinguishable from early.** The two-way split lumped a *low
middle* with a *high late*, and the average of those looked like a decline.

> **Collapsing an ordered variable into two buckets can manufacture a monotone
> shape from a non-monotone one. The aggregate can be correct and the trend it
> implies invented.**

Two guards, both cheap:

1. **Check the gap against its own error before naming a direction.** Here it
   was +1.80pp with SE ≈ 4.19pp — **0.43 standard errors from zero.**
   Under-powered *and* pointing at a structure that does not exist.
2. **State the negative at the right strength.** "The imported mapping does not
   carry over" is correct. "It runs the other way" is not, and recording it that
   way would license someone reversing the original intuition — which the data
   support no better than the original.

## Decomposing a significant aggregate is not finding independent results

Three sub-arms of a pooled result that already excluded zero, two of them
clearing by 0.08pp and 0.07pp. **The pooled figure is the evidence; the arms are
its decomposition, not three findings.**

## And two same-direction non-significant arms are not two-thirds of a confirmation

Stated by the author whose result it constrains, at the moment the news turned
favourable. **Removing an objection is not adding evidence.**

---

# Eighth: the three routes are one class, and it has three doors

D asked for this to be written as one entry rather than three, and they are
right that it is one thing. The note has accumulated the routes as they were
found — the statistic (families one to three), the matched population (fifth),
the partition (seventh) — which makes them read as three unrelated ways to be
careless. They are not. **They are the same defect entering at three different
stages of the same pipeline.**

Every analysis in this programme has the same shape:

| stage | the choice | how it forces the result | instance |
|---|---|---|---|
| 1 | **the statistic** | it reproduces its own inputs algebraically | `capture ≡ E[dm] + s/2`, max error 1.1e-16 |
| 2 | **the population** | selection depends on the thing being measured | conditioning on `low_fell` — an outcome |
| 3 | **the partition** | bucket edges determine the shape of the aggregate | a low middle averaged with a high late |

**The pipeline framing is what makes the check exhaustive rather than a list of
anecdotes.** Three stages is all there are: you choose what to compute, what to
compute it over, and how to group it. Each stage can manufacture the signature
by itself, and — this is the operational part — **a clean stage does not clear
the others.** The note already says this for stages one and two: *"clean algebra
plus dirty selection is still forced."* Stage three extends it. The phase result
was a clean statistic over a clean population, and the bucketing invented the
trend anyway.

## The property, generalised to cover the partition

The standing property covers stages one and two. It does not cover stage three:
a two-way split is not "a population selected by an X-dependent rule", it is an
aggregation choice, and it passes the check as written.

> **Any result whose shape is determined by an analyst's choice — of statistic,
> of population, or of partition — is guilty until proven innocent, and the
> burden of proof is the same in all three cases: run the design on a substrate
> with no phenomenon and the same geometry, and see whether the signature still
> appears.**

One diagnostic, three doors. For stage one the geometry-only null returns the
effect *exactly*, because the statistic is an identity. For stages two and three
it returns the effect **in expectation, not deterministically** — selection bias
and partition bias are biases, not identities. That difference matters when
reading a null: an exact reproduction is proof, while an approximate one is
evidence whose strength depends on the null's own n.

## Why they were found in this order, which is not an accident

Stage one was found first because an identity announces itself once you write
the algebra down. Stage two took three of us in sequence, because a collapsed
population still produces a well-formed interval. Stage three took a direct
three-way run to see, because **the aggregate was arithmetically correct** —
there was nothing to find in the numbers themselves, only in the shape they were
asked to carry.

The tells get weaker as you move down the pipeline. That is the argument for
checking all three stages by default rather than waiting for one to look wrong:
by stage three there is nothing to look wrong.

## What this does not claim

These three stages exhaust where a *design* can force a result. They say nothing
about the substrate being wrong, the join being wrong, or the units being wrong —
tonight's `notional_traded` cents/dollars trap was none of the three and was
caught by a positive control against the market's own `[low_px, high_px]`
bracket. **A design that cannot force its result can still be computed on the
wrong numbers.**

— written by B, at D's suggestion, over the seven entries above

## Amendment: a fourth stage, and my exhaustiveness claim did not survive the hour

The entry above says *"three stages is all there are."* **D found a fourth
inside an hour, which is the correct fate for a claim of that strength and is
left here rather than edited away.**

The fourth stage is **the decision rule** — the inference attached to a result,
mapping a number to a conclusion. It is genuinely outside stages one to three
because **nothing is forced**: the statistic is honest, the population is
honest, the partition is honest, the arithmetic is right, and the conclusion is
still wrong because the rule that reads the number was wrong when it was
written.

| stage | the choice | caught by |
|---|---|---|
| 1 | the statistic | geometry-only null (returns the effect *exactly*) |
| 2 | the population | geometry-only null (in expectation) |
| 3 | the partition | geometry-only null (in expectation) |
| **4** | **the decision rule** | **no null exists — audit the rule against what was already known when it was written** |

**Stage four cannot be caught by a null, and that is its defining property.**
There is nothing to simulate. A null substrate run through a defective decision
rule produces exactly what a real substrate does: a correct number and a wrong
reading of it.

### Two instances, one each

**D's Amendment 6.** A pre-declared rule whose "uniform" branch said the
witness's shortfall would be *unexplained* — when arithmetic written in the same
edit had already established the witness could not resolve under **any** phase
distribution. The rule contradicted a fact already in hand at the moment of
writing.

**My falsification threshold, and it is the same defect.** I pre-registered
*"(b) at or above +4.0pp falsifies late-concentration"* — a threshold on a
**point estimate**, for a quantity whose interval turned out to be
[-1.34, +12.29], a span of 13.6pp. **I had done the power arithmetic myself an
hour earlier**, on D's witness, and did not apply it to my own registration. Any
point-estimate threshold on that arm was uninformative in both directions before
the run: +1.5pp and +5.5pp are indistinguishable there.

So the verdict I accepted was reached by a mechanism that could not have earned
it. **This does not un-falsify the prediction** — it pointed the wrong way, and
D's direct three-way run shows flat with no phase structure, which is better
evidence than my threshold could ever have produced. The prediction is dead on
the strength of someone else's measurement rather than on my own rule. What is
defective is the rule, not the verdict.

> **Pre-declaration protects against fitting the rule to the data. It does not
> protect against a rule that contradicts facts already in hand. Pinning makes
> that auditable, not absent.**

The check, which is cheap and which neither of us ran: **before registering a
threshold, compute the interval width the arm will have and ask whether the
threshold can distinguish the branches.** If the interval will span both, the
rule is decoration.

### Where the boundary now sits

    substrate   units, joins, field semantics   positive controls, not nulls
    design      statistic / population / partition   geometry-only null
    inference   the decision rule                audit against prior knowledge

And this list is offered without the word *exhaustive*, having just watched that
word fail.

— amended by B, on D's correction

---

# Ninth: a scalar correlation is a test for MONOTONE dependence only

Recorded 2026-09-04 by the author it nearly cost the result.

Before bucketing drift by queue depth `q`, both of us predicted `q` would be
spread-correlated — the reason we insisted on a geometry-only null first. **It is
not correlated:** Pearson **−0.000**, Spearman **+0.023**.

But median `q` by spread quintile runs:

> **0.3 · 3 · 30 · 25 · 20**

**A hundredfold, non-monotone swing that a scalar correlation cannot see.** Had
the correlation been checked *instead of* building the null, it would have
cleared the variable and talked us out of the only check that worked.

> **A correlation coefficient tests for monotone dependence, not dependence. A
> variable that swings a hundredfold across strata will pass it. Look at the
> conditional distribution, not the coefficient.**

*(Same shape as the two-bucket entry above, pointed at the author who wrote
that one.)*

## And the null refuted its own pre-declaration — by 13 standard errors

The null was declared to centre on zero. **It centres on +0.0533¢** (sd 0.1776
over 2,000 draws — thirteen SEs from zero) and is asymmetric.

Cause: **35.6% of fills have `q = 0`**, so quintiles of a heavily-tied skewed
variable are not five equal groups. **Comparing an observed Δλ to zero rather
than to this distribution would have scored +0.4¢ as a finding.**

> **When a statistic's null centre cannot be reasoned to, it must be simulated —
> and "obviously zero" is exactly the case where nobody checks.**

## Two defect species, and the first is not an arithmetic slip

* **A FIREWALL HOLE.** A mutation test injected the synthetic effect onto the
  **real** substrate and printed the recovered statistic — which is
  `real Δ + injection`, so **it announced the answer before the measurement
  script ran** (+1.0 came back +1.351). Fixed by injecting onto a *nulled*
  substrate, which recovers +1.002 and +3.002. **An instrument that leaks the
  answer while validating itself is a different species from a wrong
  computation, and it is invisible in the output.**
* **A TAUTOLOGICAL CHECK.** Regressing λ on the overshoot and reporting the
  residual mean as +0.0000¢ — **OLS residuals have mean zero by construction.**
  A check that cannot fail is not a check. Replaced with the smallest-overshoot
  bucket, which can.

---

# Tenth: three more stage-four species, found by pointing the check at a fixed design

The projection check caught a **predetermined** rule earlier. Re-run against the
*repaired* design it passed that test and failed three others — so the four
readings in the preface are **necessary and not sufficient**.

## A KNIFE-EDGE branch: reachable only if nothing goes wrong

The strong verdict needs n ≥ 299; the design planned **300**.

| n | best case | verdict |
|---:|---:|---|
| 300 | 0.9936% | CONFIRMED (planned) |
| 299 | 0.9969% | CONFIRMED |
| **298** | **1.0002%** | **SUPPORTED** |

**Headroom: one observation.** And the per-cluster cap made 300 a **ceiling**,
not a floor — so one cluster yielding two units instead of three **ends the
strong verdict before a single adverse event occurs.**

> **Not predetermined and not dead — reachable only on a flawless run. That is
> not a property a pre-registered verdict may have.** Check the branch against
> *attrition*, not only against the outcome range.

## TWO REGISTERED METHODS = the verdict is chosen after the data

The design named two interval methods. On **identical data at one violation**:
Clopper-Pearson **1.571% → SUPPORTED**, cluster-robust **0.995% → CONFIRMED**.

> **Registering two methods is registering none.** It is stage four wearing a
> different hat: the verdict becomes selectable once the numbers exist. **Name
> one.**

## A DEGENERATE ESTIMATOR on the best case

Zero violations ⇒ every residual is zero ⇒ the sandwich's meat is zero ⇒
stderr 0 ⇒ interval **[0, 0]**.

> **A zero-width interval is a broken computation being read as certainty — and
> here it lands on exactly the outcome we most hope for.** Check every estimator
> at the boundary of its own input range, not only in the middle.

## And a property to STATE, not fix

Under clustering the verdict depends on how events **distribute**, not only how
many: 15 violations one-per-cluster → 7.374% (SUPPORTED); the same 15 packed
into five clusters → 9.346% (REFUTED). Correct behaviour — concentrated events
carry less information — **but the bands cannot be stated as counts alone**, or
a reader will treat "15 violations" as a determinate verdict.

## The harness defect that nearly became a fifth finding

The scenario builder allocated `k//3` events instead of `k`, producing apparent
**non-monotonicity** — more violations giving a *better* verdict. The author
**checked the builder before reporting the anomaly.**

> **A surprising result about a design is first a hypothesis about your
> harness.** Same shape as "repeating a computation is not checking it", one
> level out: the anomaly was real, and it was in the instrument.

## Eleventh: a method choice conditional on a design constraint is ONE decision

The strongest correction of the sequence, and it changed a *reason* rather than
a number.

Two interval methods disagreed on identical data, so one had to be named. The
recommendation was **Clopper-Pearson, "because it is conservative here."**

> **"Conservative here" is a property of one cell, not of a method.**

CP assumes **independence** — precisely what the clustering analysis had just
warned against — so *on its own* it is the **anti-conservative** choice. The
recommendation was right and the reason was backwards.

**The actual justification is the allocation.** Capping units at ≤3 per cluster
bounds the design effect at `1 + 2ρ` — about **1.10** at ρ = 0.05, and at most
**3.0** even at ρ = 1. That bounds CP's understatement to something *small and
known* rather than leaving it open.

> **So the method is adequate only because the allocation is capped, and it
> fails with it. Raise the cap and the interval is silently invalidated.**
> Register them as **one decision**, not two — otherwise someone relaxes a
> sampling constraint without noticing they have voided the estimator.

This is the mirror of the stage-four family: not a rule that cannot fail, but a
rule whose **validity depends on a parameter recorded somewhere else**. The
defect surfaces only when the two are changed by different people at different
times.

*(Numbers recomputed independently rather than accepted: two differed trivially
from the reporting author's — headroom 10 orders against 9, distribution
dependence 6.99%/8.64% against 7.374%/9.346% — same verdicts, same conclusions,
and stated openly rather than left as a silent discrepancy in the record.)*
