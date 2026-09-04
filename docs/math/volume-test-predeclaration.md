# Pre-declaration — the direct volume test (consumed vs cancelled)

**Status:** pinned 2026-09-04, BEFORE the export exists and before any number
is computed. Nothing here may be revised after seeing data; revisions must be
appended with their reason.

**Question.** In the phantom-bid population the bid queue beneath our quote
vanished. The book cannot say whether it was **consumed** (sellers traded
through the level, so a real resting order would very likely have been filled
— the case the fill rule cannot book) or **cancelled** (quotes pulled, no
trade, a true phantom).

---

## 1. The instrument, and what it can and cannot say

`market_trade_stats`, live-recorder rows, joined
`snapshot_id -> market_snapshots.id` to recover `market_slug`. CFB only:
2026-09-03T21:51Z – 2026-09-04T05:25Z, ~91k rows, median poll cadence 220s.

**The counter is market-level.** `shares_traded` increments for trades at ANY
price in that market. So the weak form of this test asks "did trading occur",
which is not the question.

**But the table also carries `last_trade_px` / `last_trade_qty` /
`last_trade_at`** (core/storage/models.py:156-160). That permits the strong
form: *did a trade occur at or below our bid, inside this interval*. It sees
only the LAST trade before each poll, so it **under-counts** — a consuming
trade that was not the last one in the window is invisible.

That asymmetry is the point and it is declared here, not discovered later:

> **A positive is strong; a null is weak.** Observing a trade at or below B is
> direct evidence the level was consumed. Failing to observe one is consistent
> with consumption that was not the last print, or with the poll landing badly.
> A null may be reported only as "not detectable at this cadence", **never** as
> "no consumption occurred".

## 2. Unit, and the effective N

**The unit is the (market, 220s interval) cell, not the fill.** Measured on the
classified export before the volume data exists:

    CFB in-game fills                        20,720
    phantom BID fills                         6,313   (11 games, 437 markets)
    ask unmoved (|ask move| <= 1c)            3,261   (11 games, 402 markets)
    distinct (market, interval) cells           402   <- N

Median 5 fills per cell; exactly one cell per market, which is what a rung
that is only near-the-money briefly should look like. **N = 402 cells,
clustered into 11 games.** Not 3,261, and not 21,126.

## 3. The matched baseline — pinned, because this is where selection re-enters

A phantom-bid fill is *defined* by the bid falling past our quote. Price moves
are made of trades. So fill-cells carry elevated volume **whether or not our
level was touched**, and both hypotheses predict it — consumption trades at our
level, and information-driven cancellation means a maker pulled *because*
trades happened elsewhere. **Comparing against all intervals measures "did the
price move", which is already known.**

Therefore:

- **Treatment cells:** cells containing >= 1 ask-unmoved phantom-bid fill.
- **Control cells:** cells in the **same market** with **no** phantom-bid
  fill, matched on
  (a) the magnitude of the best-bid fall within the interval, bucketed
      [0], (0, 1c], (1c, 2c], (2c, 4c], >4c; and
  (b) game phase, bucketed by elapsed fraction of the game's in-game fill
      span into thirds.
- **B for a control cell** is the counterfactual quote: `best_bid` at the
  interval's start, since our rule is to join the touch. Same definition
  applies to treatment cells, so the two are constructed identically.
- Report achieved balance on (a) and (b) before any outcome. If balance
  fails, the comparison measures the matching.

## 4. Primary and secondary statistics

**Primary (strong form).** Share of cells with `last_trade_at` inside the
interval AND `last_trade_px <= B + 1e-9`. Treatment vs matched control,
game-clustered (11 games).

**Secondary (weak form).** Share of cells with any positive `shares_traded`
delta. Reported *beside* the primary, never alone, since it cannot address
price level.

**Counts before ratios** — cells, matched cells, and raw numerators printed
before any share.

## 5. Decision rule, fixed now

| outcome | reading |
|---|---|
| primary elevated in treatment, balance holds | consumption is real and the central number is measured on the losing half of the distribution |
| primary flat | **not detectable at this cadence.** NOT evidence that consumption did not happen (see §1) |
| secondary elevated, primary flat | consistent with price movement alone; carries no information about our level |
| balance fails on (a) or (b) | report the imbalance and no conclusion |

## 6. Integrity checks before anything is computed

- `shares_traded` monotone non-decreasing within market (manager measured zero
  negative deltas; re-verify on the export, since a counter reset would
  manufacture volume).
- Poll cadence distribution reported, not assumed to be 220s.
- `last_trade_at` staleness distribution reported. On the sweeper's NFL rows it
  ran median 5,788s; if CFB live-recorder rows are similarly stale the strong
  form is dead and only the weak form survives — **check this first**, it
  decides whether §4's primary exists at all.
- Interval alignment owned here, not pre-differenced upstream.

## 7. What this cannot settle, whatever it returns

It cannot attribute a specific trade to a specific fill, and never will at
3.7-minute cadence. It cannot observe the counterfactual directly: whether OUR
order, behind a median 28 contracts of queue (A2), would have been reached even
where a trade did occur at our price.

---

## AMENDMENT 1 — 2026-09-04, after §6 integrity checks, before any outcome

Appended rather than edited in place, per §0. Two changes, both forced by what
the integrity checks found.

**(a) The cell is the real poll interval, not a synthetic 220s grid.** Polls
are irregular and 42.3% of rows carry a NULL stats block, which must be
skipped rather than read as zero volume. Skipping lengthens the surrounding
interval. Measured on consecutive stats-bearing rows: 51,130 intervals,
duration median 214s, p90 361s, **max 5,364s**. Counter is clean — zero
negative deltas, so no resets.

**(b) Matching MUST include interval duration.** A longer interval is more
likely to contain a fill AND more likely to contain a trade, so duration is a
common cause and was missing from §3. Without it the test would recover a
duration effect and read it as consumption. Added as matching key (c),
bucketed [<180s], [180–260s], [260–400s], [>400s].

This is the fifth selection-on-a-common-cause found today. It was found by
running the pre-declared integrity checks before the outcome, which is what
they are for.

**Ceiling revised downward by the staleness check.** `last_trade_at` runs
median 800s against a ~214s interval; only **26.4%** of stats-bearing polls
have their last trade inside their own interval, and 19.5% of intervals
contain their own last print. So the median CFB rung trades about once every
13 minutes.

That is itself close to an answer, and it must be stated before the test
rather than after: **there are not enough trades for most phantom-bid fills to
correspond to one.** With trades arriving every ~800s and intervals ~214s
long, the unconditional chance that any interval contains a trade is ~21%. The
primary can therefore only ever confirm consumption for a minority of cells,
and a high treatment share would be surprising rather than expected.

The strong form survives but is thin: it can speak only to the ~20% of
intervals that contain a print at all.

## AMENDMENT 2 — 2026-09-04, N CORRECTION. The pre-declared 402 was wrong.

**§2's "402 cells" was an artifact of a broken expression, not a fact.** The
bucket index was computed as `filled_at.astype('int64') // 10**9 // 220` on a
tz-aware column; the arithmetic collapsed and assigned **every fill to a single
bucket**, so `groupby([market, bucket])` returned exactly one cell per market —
402 markets, 402 "cells".

The tell was visible and I recorded it: the cell count exactly equalled the
market count, and a median per-market fill span of 3,362s cannot fit in one
220s bucket. **I then "verified" it by re-running the same expression**, which
of course reproduced it. Checking a number by repeating its own computation is
not a check.

**Correct count, from real poll intervals via an independent method
(searchsorted against actual poll boundaries): 2,230 treatment cells**, of
which 1,471 fall in strata that contain at least one control. Controls: 6,115.
Games: 11.

This correction went outward — 402 was quoted to the manager, into the export
README, and into an operator alert. It is corrected in all of them.

## AMENDMENT 3 — estimator, same date, before the result was read

The pooled treatment-vs-control comparison originally implied by §4 is **not**
matching: the arms differ in stratum composition (pooled duration medians 246s
treat vs 88s control), so pooled rates carry the composition. The estimator is
now explicitly **within-stratum**: each treatment cell is compared against its
own stratum's control rate, and the per-cell excesses are game-clustered.

The difference is not cosmetic. Pooled would have reported the primary as
25% vs 11%; stratified reports 25.2% against a matched expectation of 21.0%.
**The confound was worth about three times the effect.**

---

## RESULT — 2026-09-04

    PRIMARY   print at/below B inside the interval
      treatment 25.17%   matched-control 21.04%
      EXCESS +4.13% [+1.33%, +6.93%]   excludes zero

    SECONDARY any positive volume delta
      treatment 64.69%   matched-control 52.22%
      EXCESS +12.47% [+8.96%, +15.99%]  excludes zero

**Reading, under the pre-declared rule.** The primary is elevated, so by §5
this is evidence that consumption is real: the bids beneath our quote were, at
least sometimes, traded through rather than pulled. Those are fills a real
resting order could have received and the fill rule cannot book.

**Three things that bound it, all pre-declared rather than discovered:**

1. **The level-specific signal is a third of the market-wide one** (+4.13pp
   against +12.47pp). That gap is exactly what the price-movement confound
   predicts: most of the extra volume around our fills is *not* at or below our
   bid. Had only the secondary been run, the effect would have looked three
   times larger than the level-specific evidence supports.
2. **+4.13pp is a LOWER bound.** `last_trade_px` shows only the last print
   before each poll, so consuming trades that were not last are invisible. How
   much larger the true share is cannot be recovered at this cadence.
3. **It is a minority effect as measured.** ~75% of phantom-bid fills have no
   observed print at or below B in their interval. Consumption is real and is
   not the whole story of the phantom population.

This does not overturn the geometry result; it qualifies its scope. The fill
rule can only book fills with capture <= 0, and this shows the excluded
population is not empty.

## AMENDMENT 4 — never-traded cells restored. Result survived.

The instruction to skip NULL-stats rows was wrong: a missing block means the
market **has not traded yet** (B: every market's first stats row carries
volume > 0, 1,544/1,544; the block switches on at the first trade and never
off, 0 interleaved gaps in 38,717). Those are the cleanest zero-volume
observations in the export and the original design discarded them.

Restored as genuine zero-volume cells in both arms. 2.7% of ask-unmoved
phantom-bid fills sat in that territory.

    before  EXCESS +4.13% [+1.33%, +6.93%]   n 1,471 / 6,115
    after   EXCESS +4.24% [+1.26%, +7.22%]   n 1,503 / 6,372

**The result survived a mis-specified substrate instruction**, which is worth
recording as such rather than quietly restating the new number.

## ★ AMENDMENT 5 — an INDEPENDENT witness, and it does NOT confirm the primary

`last_trade_px` sees only the last print, and 81.1% of volume-bearing intervals
hold two or more (median ~3.2). A fall in `low_px` is **unmaskable**: the
session low is monotone, so a decrease during an interval witnesses a print at
exactly that price inside it, and no later print can hide it. If the new low is
<= B, a print at or below our bid provably occurred.

This is a different route to the same fact — deliberately not the same
computation twice.

    PRIMARY   treatment 24.80%  control 20.56%  EXCESS +4.24% [+1.26, +7.22]  excludes zero
    WITNESS   treatment  7.64%  control  6.81%  EXCESS +0.83% [-1.21, +2.87]  SPANS ZERO
    SECONDARY treatment 63.72%  control 51.04%  EXCESS +12.68% [+8.91, +16.45] excludes zero

**The independent check points the same way and does not reach significance.**
On a relative scale the primary is 1.21x elevated and the witness 1.12x, so the
sign agrees; the witness's interval includes zero.

Why the witness is weaker, stated so it is not used as an excuse: it fires only
on a NEW session low, which is a strict subset of prints at or below B (base
rate 6.8% against the primary's 20.6%), and new lows get rarer as a session
ratchets down, so it is biased toward early-game intervals. It is an
under-powered instrument and its null is weak evidence.

**Consequence for how this may be quoted.** The primary stands as the
pre-declared reading, but the only independent route available does not
corroborate it at significance. That is a real weakening. The honest summary is
that consumption is *indicated* — one significant route, one same-signed
non-significant route, both under-counting by construction — and not
established.

### Amendment 5a — the witness is UNINFORMATIVE, not disconfirming (B, arithmetic)

The primary's relative elevation is 1.206x. Applied to the witness's own base
rate of 6.8% that predicts **+1.40pp**, and the witness measured +0.83pp
[-1.21, +2.87]. **The predicted value sits inside the measured interval.** In
relative terms the witness spans [0.822x, 1.422x], containing both the null
(1.000x) and the primary (1.206x). Separating them needs a half-width under
0.70pp against the 2.04pp it has — roughly 8x the cells.

So no route disagreed; one route was too blunt to speak. **This restores
nothing** — "indicated, not established" stands, and an uninformative witness
is not a supportive one — but "the witness did not corroborate" must not be
read as "a second route contradicted it".

## ★ AMENDMENT 6 — PHASE SPLIT. Prediction pinned BEFORE the run.

B's falsification, so the witness's early-game bias is not a post-hoc rescue.
The witness fires only on a NEW session low; late in a game, after the price
has ratcheted, B is likelier to sit above the running low, so late-game
consumption is invisible to it **by construction**.

Split the primary's excess by game phase (the thirds already in the design).
The mapping is fixed here, before the numbers exist:

| primary effect by phase | reading |
|---|---|
| concentrated LATE | the witness samples the wrong part of the game; its shortfall is explained and the finding survives at its current strength |
| roughly UNIFORM | the witness should have seen its share; the shortfall is **unexplained and counts against** the finding |
| concentrated EARLY | the witness was best placed to see it and did not; **counts strongly against** |

Late-concentration is independently predicted by the program's ride-tail loss
map, so it is not a free parameter — it is a commitment that could fail.

### Amendment 6 RESULT — roughly uniform. The late-concentration bet failed.

    phase    nT     treat    ctrl    excess
    early    469   27.51%  22.03%   +5.48% [-1.34%, +12.29%]  spans 0
    middle   557   22.08%  19.32%   +2.77% [+0.08%,  +5.45%]  excludes 0
    LATE     454   25.33%  20.55%   +4.78% [+0.07%,  +9.49%]  excludes 0

The three are statistically indistinguishable and the largest point estimate is
**early**, not late. So the effect is roughly uniform across game phase and the
ride-tail-concentration prediction did not come true. Under the mapping pinned
above, that is the branch that counts against.

### ★ BUT MY OWN MAPPING WAS INTERNALLY INCONSISTENT, and that must be said

Amendment 6's "uniform" branch reads *"the witness should have seen its share,
so the shortfall is unexplained"*. **That branch was already foreclosed by
Amendment 5a, which I wrote in the same edit.** 5a establishes that the
witness's half-width (2.04pp) cannot separate the null from the primary's
predicted +1.40pp under ANY phase distribution. A test the instrument cannot
perform does not become performable because the effect is uniform.

So I pinned a decision rule whose branch contradicted arithmetic I already had
in hand. The pinning was correct procedure applied to a mis-specified rule,
which is its own failure mode: **pre-declaration protects against fitting the
rule to the data, not against a rule that was wrong when written.**

**The correct reading, stated with that error accounted for:**

- The witness's silence is fully explained by power alone (5a). It stands.
- The early-game-bias story is an ADDITIONAL explanation, and the phase split
  does **not** support it. That excuse is dead.
- The finding is therefore neither strengthened nor further weakened by this
  cut. What died is one of my proposed defences of the witness, not the
  witness's silence, which never needed that defence.
- **"Indicated, not established" is unchanged**, and the ride-tail prediction
  failing is a small independent mark against reading too much into the
  mechanism.

## Robustness to B's eligibility predicate (not pre-declared — sensitivity only)

    as reported (all cells)             +4.24% [+1.26%, +7.22%]   nT 1,480
    quote at both ends                  +4.31% [+1.35%, +7.27%]   nT 1,480
    bid actually MOVED                  +5.34% [+2.01%, +8.68%]   nT 1,188
    bid moved DOWN (seller-side)        +7.83% [+1.97%, +13.69%]  nT   587

Restricting to cells with a real bid-side move — the only ones a bid-move
matched baseline can legitimately use — **strengthens** the effect, and it is
largest exactly where the mechanism requires it (sellers hitting bids). B
flagged the risk that ineligible cells would flatter the result; they were
diluting it instead. These cuts were NOT pre-declared and are reported as
sensitivities, not as the headline.

---

No in-sample result justifies capital. The forward test is the evidence.

## ★ AMENDMENT 7 — c7's matched-population test. Expected branch pinned first.

The convergence rule's SAME-ESTIMAND leg is unestablished for the witness: it
fires only on new session lows, so it may measure a different quantity than the
all-interval primary. c7's fix: restrict the PRIMARY to the witness's own
population and compare on shared ground.

**My expectation, declared before looking, and it is the branch that hurts:**
I expect the primary on new-session-low intervals to be **at least as large as
+4.24%**, not to fall to the witness's +0.83%. Two reasons:

1. The phase split (Amendment 6) came back roughly uniform, so the
   "gap is a phase effect" explanation has already lost its support.
2. A new session low is made by sellers pushing the price down. That is
   precisely where consumption should be MOST likely, not least — so the
   witness's population should if anything be enriched for the phenomenon.

If that is right, the witness disagrees on shared ground and "indicated" is
generous. I would rather record that prediction and be wrong than record it
after seeing the answer.

### Amendment 7 RESULT — my prediction was WRONG, and c7's first branch holds

    PRIMARY, all cells (reference)        nT=1,450  treat 25.17%  +4.13% [+1.33%, +6.93%]  excl 0
    PRIMARY, new-session-low cells only   nT=   42  treat 69.05% -11.90% [-25.86%, +2.05%] spans 0
    WITNESS, same cells (shared ground)   nT=   42  treat 83.33%  -5.95% [-20.71%, +8.81%] spans 0

**I predicted the primary would hold at >= +4.24% on the witness's population.
It fell to -11.90%.** The reasoning was that new session lows are seller-driven
and should be enriched for consumption. Wrong.

**c7's first branch holds: on shared ground the two routes AGREE** — both
negative point estimates, both spanning zero. So the witness does not
contradict the primary. The "a second route disagreed" reading is now
positively excluded rather than merely unsupported.

**But the shared ground is SATURATED and tiny, which is a third independent
reason the witness was never going to speak.** Base rates on new-low cells are
69% (primary) and 83% (witness) in the treatment arm — a new session low
essentially IS a print at or below a touch-joining quote, so nearly every such
cell scores positive in BOTH arms. There is no headroom for treatment to exceed
control, and n=42. A ceiling effect on 42 cells cannot corroborate anything.

**Net position, unchanged in strength:** the primary's +4.24% comes from the
non-new-low population, where the witness cannot speak at all — not from
population where they disagree. "Indicated, not established" stands exactly as
before, with one worry removed rather than any support added.

### ★ Amendment 7 IS CONTAMINATED — I conditioned on a post-treatment variable

B's warning (arriving after the run) names two readings of "the witness's own
population": (a) intervals where the witness COULD fire — B at or below the
running session low — where any print at/below B IS a new low, so the two
instruments collapse onto nearly the same event and agreement is largely
algebraic; and (b) the witness's PHASE population, where they stay distinct.

**I ran neither. I restricted on `low_fell` — the low actually having FALLEN
during the interval — which is an OUTCOME, not a pre-condition.** Conditioning
on the low having fallen conditions on a print having occurred at a new low,
which is most of the event being measured. That is worse than (a): it is
collider conditioning, not merely a coupled population.

It also explains the saturation I reported as a curiosity: 69% and 83% base
rates are not a feature of new-low intervals, they are what conditioning on the
outcome produces. **My "third independent reason the witness cannot speak" was
a description of my own design error.**

Amendment 7's numbers are withdrawn as a test of agreement. What survives is
only the negative observation that my pinned prediction (primary holds at
>= +4.24%) was wrong on that population — and even that is on contaminated
ground.

### AMENDMENT 8 — the clean version, (b). Expectation pinned before the run.

Compare primary and witness on the witness's PHASE population (early-game
third), where the instruments remain distinct.

**Expected: the witness early-phase excess is positive but does not clear zero,
and the comparison stays uninformative for the power reason (5a) rather than
becoming decisive.** I do not expect this to rescue or sink anything. Saying so
in advance because my last prediction failed and the temptation after a failure
is to predict something bolder.

### Amendment 8 RESULT — expectation held; the witness's weakness was a pooling artifact

    EARLY PHASE (the witness's own population, instruments distinct)
      PRIMARY  nT=469  treat 27.51%  ctrl 22.03%  rel 1.249x  +5.48% [-1.34%, +12.29%]  spans 0
      WITNESS  nT=469  treat 13.65%  ctrl  9.17%  rel 1.488x  +4.48% [-1.01%,  +9.96%]  spans 0

    ALL PHASES (reference)
      PRIMARY  nT=1,480  rel 1.206x  +4.24% [+1.26%, +7.22%]  excludes 0
      WITNESS  nT=1,480  rel 1.122x  +0.83% [-1.21%,  +2.87%]  spans 0

**My pinned expectation held on both counts**: the witness's early-phase excess
is positive and does not clear zero, and the comparison remains uninformative
for the power reason rather than becoming decisive.

**The finding I did not predict: on the population where the witness can
actually operate, its RELATIVE elevation (1.488x) EXCEEDS the primary's
(1.249x).** The all-phase figure of 1.122x was diluted by late intervals where
the witness structurally cannot fire — after the price has ratcheted, B sits
above the running low and consumption is invisible to it by construction.

So the witness's apparent weakness relative to the primary was **a pooling
artifact**, not a disagreement. On clean shared ground the two instruments point
the same way, with the independent one pointing slightly harder.

**This is consistency, not corroboration.** Both intervals span zero at n=469.
"Indicated, not established" is unchanged. What changes is that the witness can
no longer be read as a mark against the finding in any of the three available
framings: it does not contradict (Amendment 7, on contaminated ground), it
cannot resolve (5a, power), and where it can operate it agrees in direction and
exceeds in relative magnitude (here).
