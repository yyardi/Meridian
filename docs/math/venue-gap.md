# The venue gap — Polymarket vs Kalshi

**This is the question the project was founded on.**

> *"Polymarket's thin WNBA board prices below the sportsbook consensus, and the
> model is mostly a translator that turns the book's number into a price for
> each ladder rung."* — the founding thesis

**Gate MET: 10 comparable games. Verdict: there is no venue gap.**

Across **773 line-identical contract-pairs** on 61 distinct contracts, the two
venues agree: median |gap| **0.00¢** (median of game medians), **97.2% of pairs
within one cent**, and **9 of 10 games have a median signed gap of exactly
zero**. Sign persistence is not measurable — only one game carries a sign at
all, so there is nothing to persist.

Module: [`core/kalshi/analysis.py`](../../core/kalshi/analysis.py) ·
pre-registered 2026-08-05 · run 2026-08-07

## The pre-registration, unchanged

Fixed 2026-08-05, before any matched data existed. Two statistics, on contracts
matched by market type and **identical line** — *"a half-point off is basis, not
a match"* — paired within **60 seconds**, clustered by game, at **≥10 matched
games**:

1. **Median |mid gap|**
2. **Sign persistence** — the fraction of games whose game-level median gap
   keeps one sign

Deliberately not reported: anything resembling a tradable edge. That is a
separate, separately-registered question.

## The numbers

| game | totals | spreads | ML | contracts | pairs | median signed | median \|gap\| |
|---|---:|---:|---:|---:|---:|---:|---:|
| 26AUG05DALWSH | 0 | 5 | 1 | 6 | 84 | +0.00¢ | 0.00¢ |
| 26AUG05LACHI | 0 | 5 | 1 | 6 | 102 | +0.00¢ | 0.00¢ |
| 26AUG05PHXATL | 8 | 4 | 1 | 13 | 156 | +0.00¢ | 0.00¢ |
| 26AUG05SEANY | 0 | 0 | 1 | **1** | 12 | +0.00¢ | 0.00¢ |
| 26AUG06LAMIN | 0 | 0 | 1 | **1** | 24 | +0.00¢ | 0.00¢ |
| 26AUG06LVIND | 0 | 2 | 1 | 3 | 66 | +0.00¢ | 1.00¢ |
| 26AUG06TORPDX | 0 | 5 | 1 | 6 | 144 | +0.00¢ | 0.00¢ |
| 26AUG07ATLWSH | 9 | 2 | 1 | 12 | 96 | +0.00¢ | 0.50¢ |
| 26AUG07GSDAL | 0 | 2 | 1 | 3 | 9 | +0.00¢ | 0.00¢ |
| 26AUG07PHXCONN | 9 | 0 | 1 | 10 | 80 | −0.50¢ | 0.50¢ |

| | |
|---|---|
| **median \|gap\|** (median of game medians) | **0.00¢** |
| **sign persistence** | **not measurable — 1 of 10 games has a nonzero median** |
| mean \|gap\|, clustered by game | 0.37¢ — CI [0.22, 0.52], G=10 |
| identical to the penny | 418 / 773 = 54.1% |
| within one cent | 751 / 773 = **97.2%** |

Sign is **Polymarket − Kalshi**. Pairing lag: median 12.9s, p90 25.2s, max
32.2s against the pinned 60s tolerance.

**The venues agree to within one tick.** On a 1¢ tick a mid can land on a half
cent, so 0.50¢ is the *smallest resolvable* disagreement — one venue's bid or
ask being one tick different. That is the scale of everything here.

### Sign persistence, stated honestly

Nine of ten games have a median gap of exactly zero. Only PHXCONN carries a
sign (−0.50¢). The arithmetic returns 1.0 because one of one game agrees with
itself; that is not a measurement. **There is no persistent direction**, which
is the stronger and more final version of what the statistic was asking.

### V22 secondary: the gap by time to tip-off

| hours to tip | pairs | median \|gap\| |
|---|---:|---:|
| 3–6h | 493 | **0.50¢** |
| 1–3h | 164 | 0.00¢ |
| 0–1h | 116 | 0.00¢ |

Worth having done. The headline 0.00¢ is not hiding a clock artifact — it is
the opposite: such disagreement as exists sits **3–6 hours out and converges to
exactly zero as tip-off approaches**. One tick apart early, identical late.

## The ladders are staggered, and that is the consequential finding

Before any price is compared, the strict line-identical rule has to find
something to compare.

| | Kalshi strikes | Polymarket lines | **line-identical** |
|---|---:|---:|---:|
| totals | 90 | 90 | **26** |
| spreads | 74 | 60 | **29** |

Both venues list **nine totals rungs per game at three-point spacing**. In
**7 of 10 games the two ladders sit exactly 1.0 point apart** — Kalshi
180.5/183.5/186.5…, Polymarket 181.5/184.5/187.5…. In the other three they
coincide exactly. Nothing is missing on either side; the ladders are simply
offset.

> **Speculation, clearly labelled as such and not tested:** the venues appear
> to copy each other's *spacing* while avoiding each other's *lines*. Both
> chose nine rungs three points apart; in most games they land on opposite
> half-point grids. If that is deliberate — product differentiation, or simply
> not wanting to be the second-best price on an identical contract — then
> line-identical arbitrage was never going to be available at scale, and the
> thinness of this comparison is a feature of the market rather than a limit of
> the measurement. **This is a hypothesis about intent from ten games of
> ladders. It has no gate and should not be repeated as fact.**

**Consequence for the gate's power.** Two games (SEANY, LAMIN) contribute a
single contract each — their moneyline — because neither their totals nor their
spreads overlap. One game supplies 13 of 61 contracts. So "10 comparable games"
is a weaker sample than it sounds, and more games will not fix it if the
staggering persists: they will add moneylines and little else.

**The gate may therefore need restating in matched contracts as well as games.**
Changing a pre-registered gate is the operator's call alone, so it is flagged in
the return brief rather than decided here.

## Reconciliation with an independent spot-check

The manager re-ran the totals leg independently — exact-line join, 5-minute
buckets, against the primary. Two implementations, three shared games:

| game | manager median \|gap\| | this module | manager signed | this module signed |
|---|---:|---:|---:|---:|
| PHXATL | 0.00¢ | **0.00¢** | −0.19¢ | **+0.21¢** |
| ATLWSH | 0.50¢ | **0.50¢** | −0.44¢ | **+0.45¢** |
| PHXCONN | 1.00¢ | 0.50¢ | +0.83¢ | **−0.79¢** |

**Every signed number is sign-flipped with magnitudes agreeing to ≤0.04¢** —
the manager computes Kalshi − Polymarket, this module the reverse. A convention
difference, not a bug, and the tight magnitude agreement is a strong
cross-validation of the matching. Two of three medians agree exactly; PHXCONN's
1.00¢ against 0.50¢ is the 5-minute bucketing against one-pair-per-Kalshi-
observation.

### The bug the spot-check caught

The first implementation paired *every* Polymarket snapshot with its nearest
Kalshi snapshot, reusing one Kalshi observation many times. Polymarket's
pregame density varies wildly **between contracts of the same game**, so pair
counts came out at 17, 17, 17, 17, 2398, 2398, 2398, 2398 — a 140× imbalance
inside PHXATL alone — and the mean signed gap read **+0.30¢**, essentially all
of it one dense contract quoting +1.00¢.

`build_pairs` now allows **one pair per (contract, Kalshi observation)**, Kalshi
being the coarser 60s side. The same figure becomes **+0.21¢**, per-contract
counts become uniform, and the pair count drops from 68,493 to 773.

The pre-registered **median was 0.00¢ before and after**. The spec asked for a
median, and the median survived a weighting error that moved the mean by half a
cent. That is an argument for the original pre-registration, not against it.

## How the matching was validated

A frame error would leave every number inside [0, 1] and be invisible — the
V14/V15 failure mode. Four independent checks:

1. **Moneyline.** Polymarket YES = the slug's first team (V20); Kalshi's ticker
   suffix names the team. A wrong team would show ≈ ±(1 − 2p). Gaps are 0.00¢.
2. **Both spread directions.** `-neg-X` from team T is *"T wins by more than
   X"* — Kalshi's own wording, paired directly. `-pos-X` from T is *"T loses by
   less than X, or wins"*, the **complement** of *"the opponent wins by over
   X"*, so it pairs with the opponent's contract and inverts. Both land
   penny-identical.
3. **The complement identity closes.** DAL-WSH at ±1.5: P(DAL by >1.5) = 0.525,
   P(WSH by >1.5) = 0.435, summing to 0.96 — the missing 4% being exactly the
   probability of a one-point game. And Polymarket's `DAL +1.5` = 0.565 equals
   `1 − P(WSH by >1.5)` to the penny.
4. **An independent implementation agrees** on magnitude across three games
   (above), having been written separately and joined differently.

## Scope limits

- **61 contracts across 10 games**, unevenly spread: one game supplies a fifth
  of them, two supply one each. Clustering by game is what stops 773 pairs
  reading as 773 independent observations.
- **Pregame only**, per the spec. Nothing here is about in-game prices.
- **The full-sample run reads the primary**, because `market_snapshots` cannot
  be mirrored locally — `sync_local` refuses `--stream` (the live recorder
  authors it locally, and an id-keyed upsert would destroy ticks that cannot be
  refetched). Running the module against the local mirror gives a smaller,
  legitimate, different sample. **The gate number depends on which database you
  ask**, and that should be stated whenever it is quoted.

## What this means

The founding thesis was that Polymarket's thin WNBA board misprices relative to
a sharper reference. Measured against a second real venue, on contracts that
are identical line-for-line, **it does not.** The two books quote the same
number, within one tick, and converge to exactly identical as tip-off
approaches.

That does not retroactively void ANCHOR's measured CLV — that was against
sportsbook closing lines, a different reference. But it removes the mechanism
the thesis assumed, and it lands beside C13, where ANCHOR's own edge fell to
−2.33% once fills were measured honestly.
