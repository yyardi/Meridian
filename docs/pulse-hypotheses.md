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

## Gate policy — operator directive, 2026-08-08

> *"consider doing more games than just 10 for hypothesis testing on pulse,
> maybe 15 games will benefit"* — the operator, verbatim

**Adopted, forward-only.** Recorded here in three parts, because a gate policy
that is applied retroactively stops being a pre-registration.

**1. New hypotheses default to 15 games.** Any hypothesis pre-registered from
2026-08-08 onward carries a **15-game** minimum unless its own docstring states
otherwise and says why. More power, and the operator's call. This is clean
precisely because it was made *before* any such hypothesis exists — nobody has
seen a number it could be tuned against.

**2. Existing gated verdicts are NOT reopened.** Four hypotheses failed on
pre-registered terms, and their intervals miss profitability by margins more
games cannot close:

| # | verdict | interval | the bar it had to clear |
|---|---|---|---|
| 1 run overreaction | FAIL | CI [−2.69¢, **+2.05¢**] | a **6¢** round trip |
| 2 first score | FAIL | CI [−9.73¢, **+1.97¢**] | zero, costs already inside |
| — adverse selection | FAIL | CI [−2.96¢, **−2.36¢**] | zero — entirely negative |
| 7 whale / depth | FAIL | CI [−0.25¢, **+0.68¢**] | 0.15× the half-spread |

Even at each interval's most favourable edge, #1 clears 2.05¢ of a 6¢ toll and
adverse selection never reaches zero at all. Re-running a dead hypothesis to a
longer gate **after seeing its numbers** is exactly the re-tuning this
preamble's own rule forbids: *the gate is written before the number is
computed.* Extending a gate is only honest when it is done blind.

**3. #6 keeps its pinned 10.** Tail volatility's gate was fixed before any
number existed and it is **mid-accrual with its direction already peeked**.
Changing its bar now — in either direction — would taint it. It closes at 10,
on its own terms. **(It did, on 2026-08-08: FAIL.)** Its write-up notes this
policy for any successor hypothesis.

**Any part of this is the operator's to override in person.** It is written
down this way so the reasoning is visible rather than assumed.

## Ledger discipline during accrual — house style, 2026-08-08

**A row that is still accruing carries its status and its count, and nothing
else.** `NO DATA — 9 of 10 open-phase games` is a complete ledger entry (that
was #6's row until its gate closed on 2026-08-08 — the example is historical).
An interim mean, interval or direction is not permitted in this table.

Why the ledger specifically, when the same numbers are printed elsewhere: the
module prints them on every run — that is its job — and the write-up may keep
them under an explicit dated **"INTERIM — not for decisions"** heading. But
**the ledger is the surface people skim.** A direction republished here every
slate becomes an anchor, and an anchor invites deciding the gate early — which
is gate-peeking wearing the costume of a status update.

Coverage facts are fine and often the most useful thing in the row ("6 of 15
games yield no open-phase window"). Those describe the sample, not the answer.

Applied to #6 while it accrued; applies to #17 and everything registered after it.

---

## The ledger

**Kind** — `signal` predicts a move · `rule` decides how to trade one · `input` is a
model feature, not a strategy.
**Status** — `not built` · `built, no data` · `measured` · `settled` · `deferred`.

| # | Kind | Hypothesis | Origin | Gate | Status |
|---|---|---|---|---|---|
| 1 | signal | **Run overreaction.** A team scores unanswered, the price lurches — does it revert further than the round-trip cost? | the core Route B question | 30 runs / 10 games | **FAIL — gated, 2026-08-06.** 444 runs / 11 games: reversion −0.32¢ at +5min, CI [−2.69¢, +2.05¢] vs a 6¢ cost. Runs move prices ~11¢ **and the prices stay** — repricing, not panic. The fade family is dead on its pre-registered terms |
| 2 | signal | **First-score overreaction.** The opening basket moves the price far more than it should. | *"IND jumped so much from scoring first it was ridiculous"* | 30 trades / 10 games | **FAIL — gated, 2026-08-07.** 75 trades / 11 games: **−3.88¢/contract** at +5 min, CI [−9.73, +1.97]. Signal-only reversion also spans zero (+1.09¢), so this is not the fill proxy — there is no reversion to discard. The strongest form of the fade claim, and it is null. [math/first-score.md](math/first-score.md) |
| 3 | signal | **Lead cut.** A large lead narrowing moves the chart hard. | *"MIN had a 15 point lead cut to 8 and the charts moved 10%"* | — | **dead with #1** (2026-08-06) — same mechanism, and re-testing it separately after #1 failed would be threshold-shopping |
| 4 | signal | **Late runs.** The same run matters more with less time left. | *"14-2 and odds dropped for MIN crazy"* | — | **dead with #1** (2026-08-06) — same reasoning |
| 5 | signal | **Q4 tight-game moneyline.** Violent repricing in close endgames. | *"flips and flops 10-20% every few seconds"* | — | not built — **blocked on adverse selection.** Biggest prize, biggest trap |
| 6 | signal | **Tail volatility at the edges.** Deep rungs move most at the start and end of a game. | *"the tail odds move a ton at the start and end"* | both edges > mid, CI excluding zero, 10 games (pinned pre-policy) | **FAIL — gated, 2026-08-08.** 28,514 windows / 17 games, open edge reaching its 10th game. The hypothesis needs **both** edges livelier than mid-game; the open edge is the **opposite**: **−0.651¢, CI [−0.888, −0.415]** — tails are *quieter* at the open. The close edge passes alone (+0.686¢, 16 games) but the **body** gains **+2.150¢** there, 3.1× more, so that half is a whole-board phase effect rather than a tail one — the pre-registered control. **Deep-tier rungs were never measurable** (30s cadence vs the near tier's 0.20s, C1). Last of the original fourteen to be judged. [math/tail-volatility.md](math/tail-volatility.md) |
| 7 | signal | **Whale / depth.** Large resting size predicts the move toward it. | *"prediction market whales tend to know stuff"* | — / 10 games | **FAIL — gated, 2026-08-06.** 473 appearances / 15 games: move toward the whale +0.22¢ at +60s, CI [−0.25¢, +0.68¢], 0.15× the half-spread. Resting size does not predict the next move |
| 8 | rule | **Sell at fair value.** The exit target is the model's number, not a multiple of entry. | — | — | **settled.** Applied manually; now shown in the ticket UI |
| 9 | rule | **Stop-loss in EV terms.** Exit when *fair value* falls to your price — not when the price falls. | — | — | **missing, and the important one.** See below |
| 10 | rule | **Entry timing.** *"TOR tends to take off at the start, get in after Q1"* | — | — | deferred — a rule with no signal to time |
| 11 | rule | **Averaging down.** | — | — | ⚠️ **downstream of PULSE.** See below |
| 12 | input | **Quarter scoring rate → totals** | — | ungated (input/display) | **BUILT as a live FV, 2026-08-07** — [`core/live_totals_fv.py`](../core/live_totals_fv.py), rendered display-only on /picks and feeding `ev_guard`. Two corrections to the original spec, both fitted on the same 787 games: **1.32 is a Q1 coefficient, not a constant** (1.318 / 1.208 / 1.128 → 1.000 as points bank), and **the win curve's 2.98/2.77/2.40 are MARGIN sigmas** — the totals residual sd is 15.88 / 13.03 / 9.67 and rises per √minute where the margin one falls, so borrowing it understated end-Q3 uncertainty ~27%. [math/live-totals-fv.md](math/live-totals-fv.md) |
| 13 | input | **Comparable matchups** (elite offence vs elite defence) | — | — | **measured pregame, underpowered.** n=53, CI ±4 points. Better used to *widen sigma* on unusual matchups than to shift the point estimate |
| 14 | input | **Streaks** | — | — | low priority — probably already captured by recency decay in the pregame features |
| 16 | signal | **Trailing-team live ML underpricing.** In tight games the market prices the trailing team's live win probability below the historical base rate for that game state | *"i took IND to win at 30% when they were down just 5 in a tight game... cashed at 45"* (2026-08-06, real money, +50%) | mean edge > 2¢, 95% CI clustered by game excluding zero, ≥10 games | **PASS on its stated terms — and NOT TRADABLE, 2026-08-07.** 40 obs / 19 games: +6.84¢, CI [+0.84, +12.83]. But the base rate is team-blind and the price is not: **anchored on the pregame price the same states give −2.20¢, CI [−3.90, −0.49]** — the sign flips. The four biggest "edges" are all heavy pregame underdogs. The gate was the wrong question, recorded as passed because it was pre-registered. [math/win-curve.md](math/win-curve.md), correction C12 |
| 17 | signal | **Tight-game ML reversion to 50/50.** In a tight game (small boxscore margin), a moneyline that has deviated far from 50/50 reverts toward it. | *"won a fourth quarter ml on phx cuz i saw it was extremely tight and phx suddenly dropped to 33 from 50, bought, sold 45... dallas-gsv is tight so deviation shud return to 50/50, buy either side below 35, sell at 50"* (2026-08-08T02:19Z, real money) | Q4, margin ≤3, mid ≤0.35, maker fill, exit at 0.50 or settlement, P&L net of costs, clustered by game; **30 trades / 15 games** — plus a **co-primary anchoring check** | **REGISTERED 2026-08-08T02:19Z, nothing computed.** [`core/pulse/tight_game_reversion.py`](../core/pulse/tight_game_reversion.py). First hypothesis under the 15-game policy. Registered **while GS-DAL was in progress and before its Q4 resolved**; earlier games may be used. **Condition (5) is mandatory**: the same statistic against a *pregame-anchored* target, not just flat 0.50 — #16 passed at +6.84¢ against a team-blind anchor and inverted to −2.20¢ against a team-aware one, and a tight game between unequal teams does not belong at 50/50. Differs from the dead #1 by conditioning on **state** (boxscore) rather than on a **price move** — the origin quote contains both, and #1 already killed the price-move half |
| 15 | input | **Team-specific lead survival.** Some teams hold leads worse than the league curve; a live model's P(win \| lead, time) should know which | *"dallas isnt great at holding onto leads theyve blown so many"* (2026-08-06) | ungated diagnostic | **MEASURED — effect is not there, 2026-08-07.** Against the team-blind league curve the spread looks like 9.0¢ and DAL looks bad (−0.067). Anchor each team on its **own** win rate and the whole spread collapses to **2.1¢**, DAL to −0.012, MIN to +0.006. The league-curve column was reproducing the standings, not a trait. Dallas loses games; it does not specifically blow leads. [math/win-curve.md](math/win-curve.md) |

---

## The rule that came out of #16 and #15

Both landed on the same mistake, and it is now a standing rule:

> **A historical base rate is a fair-value benchmark only if it conditions on
> everything the price conditions on.**

The league win curve does not know which teams are playing. The market does.
Compare the two and you measure the curve's ignorance, which looks exactly
like an edge and points exactly the wrong way — #16's +6.84¢ became −2.20¢
once the base rate was anchored on the pregame price, and #15's 9.0¢ team
effect became 2.1¢ once each team was anchored on its own win rate.

So: **any future row of the form "the market disagrees with a historical
frequency" must carry the anchoring check inside its gate, written before it
runs.** Adding it afterwards is how a pre-registration becomes decoration.
Same error family as C4, C5 and C11 in [findings.md](findings.md).

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

1. Run overreaction (#1, with #3 and #4 as covariates) — **FAILED 2026-08-06**
2. First-score overreaction (#2) — **FAILED 2026-08-07**

**Tier 1 is closed. Both fades failed on their pre-registered terms**, and the games
arrived to answer them: 20 games replayed at a 0.20s median cadence, 3.58M ticks,
the 0-0 → first-score transition observed in all 20. The old blocker on this list —
"only 3 games have full 200ms coverage" — is gone; it was a real constraint and it
was resolved by waiting, which is the cheapest thing this project has ever done.

#2 was designed as the strongest form of the claim: one basket out of ~170 points is
as close to a pure-noise event as the sport offers, so if prices overshoot anywhere
they overshoot there. They do not, and the signal-only diagnostic spans zero too, so
it is not a fill-model artifact. **#3 and #4 were already struck out with #1 as the
same mechanism — do not revive them.**

What Tier 1 did buy is the thing Tier 2 needed: a live fair value
([math/win-curve.md](math/win-curve.md)), now rendered display-only on /picks.

**Tier 2 — only after Tier 1 reports**

3. Q4 tight-game moneyline (#5), and only after adverse selection is measured
4. Stop-loss in EV terms (#9), which needs the live fair value Tier 1 buys

**Tier 3 — cheap, independent, can run in parallel**

5. Tail volatility at start/end (#6) — **built, NO DATA and pointing away** (2026-08-07)
6. Whale depth (#7) — **FAILED** (2026-08-06)

**Tier 3 is now built out.** #6 needs two more games with Q1 tail coverage to close
its open edge; on current direction that closes as a FAIL, not a pass in waiting.

**Deferred:** #10 (no signal to time yet), #11 (dangerous without a live model),
#12–14 (inputs for after a hypothesis passes).

---

## Where the ledger stands

Every `signal` row has now been built and gated except #5, which is blocked:

| verdict | rows |
|---|---|
| **FAIL** | #1, #2, **#6**, #7 (and #3, #4 struck out with #1) |
| **PASS but not tradable** | #16 |
| **registered, not computed** | #17 |
| **not built, blocked** | #5 — needs adverse selection, which itself FAILED |
| **measured, effect absent** | #15 |

**Route B has no surviving candidate.** That is a result, not a gap: seven
independent in-game ideas were pre-registered and none produced a tradable edge,
which is roughly what a market that is not obviously broken should look like.
What the work did produce is a live fair value ([math/win-curve.md](math/win-curve.md)),
which is the input rule #9 always needed.

Before adding a row #17, read the two standing rules above — the anchoring rule
from #16/#15, and the control-naming rule from #6 — and note that fourteen
hypotheses against this much data was always going to produce one apparent
winner by chance. It produced #16, and the anchoring check caught it.

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
