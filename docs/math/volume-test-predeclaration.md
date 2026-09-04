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

---

No in-sample result justifies capital. The forward test is the evidence.
