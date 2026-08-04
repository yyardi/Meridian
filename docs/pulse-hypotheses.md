# PULSE hypothesis ledger

Every in-game idea, in one table. **This is the editable list — add a row, change a
status, strike one out.** Compiled 2026-08-02 from live observation during the
la-por, ind-min and conn-dal games; kept current since.

**Read [next-build.md](next-build.md) first** for the state of the three routes.
This doc is only the queue for Route B.

## Before adding a row, read this

There are **fourteen** hypotheses below and roughly **seven** games of tick data,
most at the old cadence. At the conventional 5% threshold, testing fourteen
independent ideas produces about one "significant" result **by chance alone**.
Finding something is the *expected* outcome even if nothing is there.

So: one hypothesis at a time, **each with its gate written before the number is
computed**, each earning its place on out-of-sample games. The alternative is a
strategy built on the luckiest of fourteen coin flips.

Sample size is **games**, never rows. One game emits ~130 markets × 5 ticks a
second; the row-level interval was measured to give 11% coverage against a nominal
95%. [math/clustered-errors.md](math/clustered-errors.md)

---

## The ledger

**Kind** — `signal` predicts a move · `rule` decides how to trade one · `input` is a
model feature, not a strategy.
**Status** — `not built` · `built, no data` · `measured` · `settled` · `deferred`.

| # | Kind | Hypothesis | Origin | Gate | Status |
|---|---|---|---|---|---|
| 1 | signal | **Run overreaction.** A team scores unanswered, the price lurches — does it revert further than the round-trip cost? | the core Route B question | 30 runs / 10 games | **built, no data** — [`core/pulse/overreaction.py`](../core/pulse/overreaction.py). 149 runs / **4 games** at 200ms. Runs met, games not. Reversion flat (−0.01¢), interval entirely below the 6¢ cost |
| 2 | signal | **First-score overreaction.** The opening basket moves the price far more than it should. | *"IND jumped so much from scoring first it was ridiculous"* | 30 trades / 10 games | **built, no data** — [`core/pulse/first_score.py`](../core/pulse/first_score.py). 18 trades / **3 games**. [math/first-score.md](math/first-score.md) |
| 3 | signal | **Lead cut.** A large lead narrowing moves the chart hard. | *"MIN had a 15 point lead cut to 8 and the charts moved 10%"* | — | not built — **fold into #1 as a covariate** |
| 4 | signal | **Late runs.** The same run matters more with less time left. | *"14-2 and odds dropped for MIN crazy"* | — | not built — **fold into #1 as a covariate** |
| 5 | signal | **Q4 tight-game moneyline.** Violent repricing in close endgames. | *"flips and flops 10-20% every few seconds"* | — | not built — **blocked on adverse selection.** Biggest prize, biggest trap |
| 6 | signal | **Tail volatility at the edges.** Deep rungs move most at the start and end of a game. | *"the tail odds move a ton at the start and end"* | — | not built — measurable from ticks already recorded. Overlaps [math/ladder-sigma.md](math/ladder-sigma.md) |
| 7 | signal | **Whale / depth.** Large resting size predicts the move toward it. | *"prediction market whales tend to know stuff"* | — / 10 games | **built, no data** — [`core/quote/depth_signal.py`](../core/quote/depth_signal.py). 46 appearances / **6 games** |
| 8 | rule | **Sell at fair value.** The exit target is the model's number, not a multiple of entry. | — | — | **settled.** Applied manually; now shown in the ticket UI |
| 9 | rule | **Stop-loss in EV terms.** Exit when *fair value* falls to your price — not when the price falls. | — | — | **missing, and the important one.** See below |
| 10 | rule | **Entry timing.** *"TOR tends to take off at the start, get in after Q1"* | — | — | deferred — a rule with no signal to time |
| 11 | rule | **Averaging down.** | — | — | ⚠️ **downstream of PULSE.** See below |
| 12 | input | **Quarter scoring rate → totals** | — | — | **partly measured.** Q1 total correlates +0.55 with the final (n=787); each extra Q1 point is worth **1.32** on the final, not 4.0. Hot starts regress ~3×. Residual sd ~16 |
| 13 | input | **Comparable matchups** (elite offence vs elite defence) | — | — | **measured pregame, underpowered.** n=53, CI ±4 points. Better used to *widen sigma* on unusual matchups than to shift the point estimate |
| 14 | input | **Streaks** | — | — | low priority — probably already captured by recency decay in the pregame features |

---

## Notes on specific rows

### 1, 3 and 4 are one mechanism, not three

All ask whether the price overshoots a scoring event and comes back; they differ only
in magnitude, direction and time remaining. **Test them as a single study with those
as covariates.** Testing separately triples the multiple-comparisons burden and buys
nothing.

### 2 deserves to stand alone

It is the cleanest possible form of the hypothesis: near-zero information (one basket
out of ~170 points) against a large observed price move. If overreaction exists
anywhere in this market, it exists here — and a null result here is close to fatal
for the whole family.

### 5 is the biggest prize and the biggest trap

The measured spread blowouts land exactly where it lives: 3.1% of live ticks exceed
10¢, 0.6% exceed 25¢, worst observed 50¢, and Q4's p90 spread (9¢) is fatter than
Q1–Q3's (7¢) even though its median is tighter. **Quoting into that is quoting into
the moment the book gaps.** Do not attempt before adverse selection is measured.

### 9 is the gap in the whole system

Your edge is `fair value − price`. That gives two exits, and only one is ever built:

- **Take profit** — the market rises to your fair value. Edge collected, sell.
- **Stop** — *your fair value falls to the price*. Edge gone, exit, **even though the
  price has not moved.**

The second is what nobody builds. If a team goes down 15, a contract is worth ~3¢
regardless of what it is quoted at. Holding because you paid 19¢ is the sunk-cost
trade. **Exit when the model says the edge is gone, not when the price says you are
losing.** Both directions need a live fair value — which is exactly what PULSE
provides.

### 11, averaging down

Adding to a losing position is correct **only if fair value has not moved.** Buy at
19¢ against a 27¢ fair value, watch it fall to 14¢ because the team went down 12 —
fair value is now perhaps 8¢, and averaging down is buying more of something worth
less than you are paying. That is the sunk-cost trade in a quantitative costume, and
without a model it is indistinguishable from chasing.

It becomes legitimate the moment PULSE exists: *"fair value is still 27¢ and the
price fell to 14¢ on noise"* is a real reason to add. So it is **downstream of PULSE
working**, not part of building it. It is the exact mirror of #9 — the same question
asked in the profitable direction.

### 12 is the first brick of any live totals model

The shape that follows: **start from the pregame projection and update by how far
in-game pace differs from what was expected for that matchup.** Never extrapolate raw
pace — 12–12 after three minutes implies a 320-point game.

---

## Order of work

**Tier 1 — cheapest, most likely real**

1. Run overreaction (#1, with #3 and #4 as covariates) — built, **needs 6 more games**
2. First-score overreaction (#2) — built, **needs 7 more games**

Both are built and both report NO DATA for the same reason: **3 of 9 recorded games
have 200ms coverage**, and the other six are sampled every ~15 minutes, which cannot
resolve a 30-second reaction window. **The bottleneck is games, not code.** Do not
start #3 or #5 to fill the wait — that is how fourteen hypotheses become one lucky
coin flip.

**Tier 2 — only after Tier 1 reports**

3. Q4 tight-game moneyline (#5), and only after adverse selection is measured
4. Stop-loss in EV terms (#9), which needs the live fair value Tier 1 buys

**Tier 3 — cheap, independent, can run in parallel**

5. Tail volatility at start/end (#6) — measurable from ticks already recorded
6. Whale depth (#7) — built, waiting on games

**Deferred:** #10 (no signal to time yet), #11 (dangerous without a live model),
#12–14 (inputs for after a hypothesis passes).

---

## A note on the moneyline

[`core/executor.py`](../core/executor.py) defines `ANCHOR_MARKETS` (moneyline
excluded) and `PULSE_MARKETS` (**deliberately empty — undecided**).

ANCHOR's exclusion is a *pregame forecasting* result: the market's margin MAE (9.65)
beats ours (10.19), so betting our disagreement loses. It says nothing about a
strategy whose edge is latency rather than forecasting. **Do not inherit it, and do
not default PULSE to everything.** Set `PULSE_MARKETS` from PULSE's own measurements.

Relevant but not decisive: in-game price travel is 35.5¢ median for the moneyline
against 48¢ for ladder rungs — but n=4 (one winner market per game against ~9 rungs),
and a median across all games washes out exactly the close ones #5 is about.
