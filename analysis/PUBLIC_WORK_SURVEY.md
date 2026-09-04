# What public work says, read the way we read our own

Assignment: meridian-14, 2026-09-04. Not a link dump — the question is *why the
ones that work, work, and why the ones that fail, fail*.

**Reliability tiers used throughout, because they get conflated constantly:**

* **[KNOWN]** — peer-reviewed or large-N transaction data, method visible.
* **[CLAIMED]** — asserted in a blog, vendor page or affiliate site, no method.
* **[UNTESTED]** — a plausible mechanism nobody appears to have measured.

Everything below is a claim about someone else's measurement, not a
measurement. Backtested returns from a blog post are the least reliable object
in this programme.

---

## ★ THE FINDING THAT SHOULD CHANGE OUR MIND FIRST

**We may have retired the wrong quantity.** Today we treated `capture`
(`mid_at_fill − our_price`, forced ≤ 0 by the fill rule) as an artifact to be
discarded. The market-microstructure literature treats exactly that quantity as
**the central real cost of market making**, not an artifact.

DeLise (2024), *The Negative Drift of a Limit Order Fill* **[KNOWN — theory
plus one instrument]** proves that in a discrete market model, and confirms
empirically on 10-Year US Treasury futures, that:

> limit order fills are **caused by and coincide with** adverse price
> movements — theoretical drift **−0.48 ticks**, empirical **−0.45 ticks**,
> with **P(fill | adverse move) = 0.99**.

**That is our Rule A, formalised.** We found the mid at-or-past our quote on
100.0% of fills and called it a selection artifact. DeLise's model *assumes*
fills are caused by adverse moves — because in real books they are — and
derives the cost from it. **The forcing IS the phenomenon.**

The distinction that survives: our capture is inflated by a simulator that
fills us whenever the mid touches our price, where a real book fills us only
when someone actually crosses. So our number is not his number. **But
"capture is forced, therefore meaningless" does not follow**, and that
inference is load-bearing in today's conclusions. Half a tick of adverse drift
per fill against a 1¢ tick is ~0.5¢ — against `s/2` of 1.256¢. That is a thin
but positive margin, and it is the shape of the whole market-making question.

---

## 1. Where does the edge come from, in the ones that claim one?

Against our four categories:

**Better forecast than the market (PULSE's premise).** The bar is higher than
in sports betting. **[KNOWN]** Polymarket's mean absolute calibration error is
~2.1pp, against ~6.4pp for public sportsbook lines and ~8.9pp for polling
averages. **A prediction market is a harder benchmark to beat than a
sportsbook**, and much of the public "beat the model" literature is written
against sportsbooks. Reichenbach & Walther **[KNOWN]** find ~3% of Polymarket
traders account for most price discovery, and the other 97% lose in aggregate
to that minority — so an edge here means being in the 3%, not in the crowd.

**Earning the spread (QUOTE's premise).** **[KNOWN]** Bürgi, Deng & Whelan
(2026), 300,000+ Kalshi contracts: **Makers earn higher returns than Takers**,
and both show a favourite–longshot pattern. Bartlett & O'Hara (2026), 41.6M
Kalshi trades: market makers **earn twice as much per contract** in
single-name markets despite greater informed price impact, because effective
spreads widen only modestly. **This is the strongest public support for the
market-making side of our programme.**

**Structural inefficiency.** **[KNOWN]** and it is large: on Kalshi, contracts
priced under 10¢ **lose over 60%** of money staked; contracts above 50¢ earn a
**small, statistically significant positive** return; the average return across
all contracts is about **−20%**. Whelan et al. show belief disagreement alone
cannot reproduce this — **behavioural probability-overweighting is necessary**.

**Latency.** **[CLAIMED]** — a Medium piece asserts average cross-venue
arbitrage duration fell to 2.7s from 12.3s in 2024, with 73% of arb profit
taken by sub-100ms bots. No method given. **But it agrees with my own
measurement tonight** (620 matched CFB cells, max gross gap +1.00¢ = one tick,
Kalshi fee ~1.34¢), which is an independent reason to believe the direction if
not the number.

---

## 2. The failures, which are more informative than the successes

The manager's prior was *fees, fills, and backtest-versus-live divergence*.
**Supported on all three, and the ordering is roughly that.**

**Fees are the whole house edge, and the game is zero-sum before them.**
**[KNOWN]** Whelan et al.: *"Prior to fees, Kalshi participants simply swap
money, so by definition the average return prior to fees across the total
volume of money invested is zero."* Average realised return −20%. **Any edge
we claim must be someone else's identified loss.** They identify who: buyers
of cheap contracts, and Takers more than Makers.

**Fills.** DeLise above. Also **[KNOWN]** the standard conservative backtest
convention: a limit order is counted filled only when price trades *through*
its level, not merely *to* it, precisely because queue position is unobservable
from Market-By-Price data. **Our Rule A is the optimistic convention; the
literature's default is the pessimistic one.**

**Backtest-vs-live.** **[KNOWN]** Bailey & López de Prado's Deflated Sharpe
Ratio, and Bailey/Borwein/López de Prado/Zhu, *Pseudo-Mathematics and Financial
Charlatanism* (Notices of the AMS, 2014): with enough trials the maximum Sharpe
is inflated even when every candidate is pure noise. The correction requires
knowing **how many variations were tried** — which almost no public sports
model reports, and which we do not currently track either.

**The concrete failures.** **[KNOWN, on-the-record]** Kalshi's own in-house
trading arm is **not profitable** and is under 6% of maker volume in sports.
**[CLAIMED]** an AI-trading-bot audit found ~−1.1% on Polymarket and −22.6% on
Kalshi over Feb–Mar. **[KNOWN]** Reichenbach & Walther: only **12%** of the
biggest winners by raw profit outperformed chance, and about **60% of "lucky
winners" became losers** on held-out events — a multiple-testing correction
applied properly, and the single most sobering number in this survey.

---

## 3. Our venues specifically — and a direct contradiction of ours

**★ THE FAVOURITE–LONGSHOT RETRACTION NEEDS RE-EXAMINING.** This afternoon a
favourite–longshot finding here was retracted as a one-sided sampling
artifact. **The effect is robustly documented on Kalshi** — Whelan et al., 300k
contracts, holding *across a wide range of market categories*, with the
maker/taker split measured separately.

Those two are compatible and must not be conflated: **our measurement was
broken; the phenomenon is real in the literature.** The retraction was correct
about our instrument and would be wrong if read as "there is no
favourite–longshot bias on Kalshi." Given today, that misreading is likely.

**Who the counterparty is.** **[KNOWN]** Bartlett & O'Hara: traders
systematically **overbet YES in markets that predominantly settle NO**,
generating a *behavioural surplus that cross-subsidises adverse selection*.
That is the mechanism by which making can pay despite informed flow — and it
means the counterparty is **partly** behavioural retail, not uniformly informed.
**If that holds on CFB, the sign of some of today's assumptions changes.**

**But note the asymmetry we should not skip:** Bartlett & O'Hara also find
one-sided order flow predicts maker losses in **single-name** markets but not
broad-based ones (adapted VPIN). Game markets are single-name. **The toxicity
we would face is on the worse side of their split.**

---

## 4. Method — how serious people establish an edge

**The benchmark is the market, not the outcome.** In sports betting the
standard is **closing line value** — did you beat the price the market settled
at. **[CLAIMED]** affiliate sources put ~2% CLV at ~4% ROI; treat the number as
unsourced, but the *principle* is what matters and it is exactly C's current
test: Brier(model) vs Brier(market). **That is the right test and it is the
standard one.** Scoring against outcomes alone, without the market as
benchmark, is the most common way public models fool themselves.

**Nobody appears to have solved the resting-order counterfactual.**
**[UNTESTED]** The literature's answer is not a solution but a convention —
assume the back of the queue, require trade-through, or model queue position
probabilistically (hftbacktest ships several such models; Moallemi has a queue
valuation paper). **All are assumptions, none is a measurement.** Our
resting-order probe would, if run, produce something the public literature does
not have. That is a genuine argument for the spend, and stronger than "we would
like more data."

**Report the trial count.** The Deflated Sharpe correction needs it. We should
be recording how many variants were tried before a result is quoted — we
currently do not, and today's twelve forced-gradient instances are the same
disease in a different organ.

---

## What would change our mind, ranked

1. **Capture may be the real cost, not an artifact** — DeLise. Highest-value
   correction in this survey, and it runs against today's conclusions.
2. **Making is publicly supported on Kalshi** — Whelan et al. and Bartlett &
   O'Hara both find makers out-earn takers on the actual venue we trade.
3. **The favourite–longshot retraction should not travel as "no such effect."**
4. **A forecast edge must beat a 2.1pp-calibrated market**, not a sportsbook —
   the PULSE fork is harder than the sports-betting literature implies.
5. **Single-name markets are the toxic side** of Bartlett & O'Hara's split, and
   game markets are single-name.

## Sources

DeLise, *The Negative Drift of a Limit Order Fill*, arXiv:2407.16527 ·
Bürgi, Deng & Whelan, *Makers and Takers: The Economics of the Kalshi
Prediction Market*, UCD 2026 · Bartlett & O'Hara, *Adverse Selection in
Prediction Markets: Evidence from Kalshi*, SSRN 6615739 · Reichenbach &
Walther, *Accuracy, Skill, and Bias on Polymarket*, SSRN 5910522 · Bailey &
López de Prado, *The Deflated Sharpe Ratio*, SSRN 2460551 ·
Bailey/Borwein/López de Prado/Zhu, *Pseudo-Mathematics and Financial
Charlatanism*, Notices of the AMS 2014 · hftbacktest order-fill documentation ·
Moallemi, *A Model for Queue Position Valuation in a Limit Order Book*.
