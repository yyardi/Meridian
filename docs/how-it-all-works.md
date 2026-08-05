# How it all works

Read this before anything else. It explains the whole project in plain language, then gets specific enough that you can argue with the maths. If something here sounds wrong to you, it might be — the flaws in this project have been found by exactly that kind of reading.

## 1. What we are actually doing

We buy and sell contracts that pay **$1 if something happens** and **$0 if it doesn't**.

Example: "Will Aces vs Liberty score more than 175 points combined?" If you think yes, you buy the YES contract. If it costs 52¢ and the answer turns out to be yes, you get $1 — you made 48¢. If not, you lost 52¢.

The price *is* a probability. 52¢ means the market thinks there's a 52% chance.

**So the entire game is: find contracts priced wrong, and buy them.** If something is really 60% likely but sells for 52¢, buying it is profitable *on average*, even though you'll still lose 40% of the time.

## 2. Why this is hard

You are not the only one doing this. The price already reflects everything thousands of bettors and professional bookmakers know. To make money you have to be **more right than all of them combined**, on this specific game, right now.

That is a very high bar, and most of this project is about honestly measuring whether we clear it. Usually we don't. That's not failure — that's the measurement working.

## 3. The two prices we compare

| | What it is | How good is it? |
|---|---|---|
| **The sportsbook line** | What DraftKings, FanDuel etc. say. Billions wagered, sharp money, tight prices. | Very accurate. |
| **Polymarket US** | A prediction market. WNBA is a small, thin corner of it. | Less accurate — that's the opportunity. |

The whole thesis: **the sportsbook is smart, Polymarket's WNBA board is thin, so when they disagree the sportsbook is probably right.** We want to buy the mispriced side on Polymarket.

## 4. What the model does

We predict a game's total score:

```
projected_total = how much the home team usually scores
                + how much the away team usually concedes
                − the league average (so we don't double-count)
```

Then, since totals are roughly bell-curve distributed around that projection, we convert it to a probability:

$$
P(\text{total} > \text{line}) = \Phi\!\left(\frac{\text{our projection} - \text{line}}{\sigma}\right)
$$

$\sigma$ (sigma) is how spread out game totals are — about 19 points. Big sigma means games are unpredictable, so being 5 points away from the line doesn't mean much.

**This is deliberately simple.** A WNBA season is only ~250 games. Fancy models memorise datasets that small and then fail on new data. The simple version is the thing anything fancier has to beat.

## 5. The single most important idea: the winner's curse

This is the one that trips everyone up, and it's the answer to *"if the dashboard says +13%, am I about to lose money?"*

Suppose our model says the total will be 182 and the sportsbook line is 175. We're 7 points apart. Naively that's a huge edge.

**But there are only two possible explanations:**

1. We know something the market doesn't. *(great)*
2. Our model is wrong about this game. *(bad)*

And here is the thing: **the bigger the disagreement, the more likely it's explanation 2.** The market is right far more often than we are. So the games where we look most confident are disproportionately the games where we've made a mistake.

This isn't a hunch — it's measured. Regress what actually happened against what we predicted:

$$
(\text{actual} - \text{market}) = \text{slope} \times (\text{model} - \text{market})
$$

If our disagreement were pure information, slope would be **1.0**. If it were pure noise, **0.0**.

> **Measured on WNBA totals: slope = 0.161–0.231.**

**About 80% of every disagreement we produce is our own error.** So a 7-point gap is really worth about 1.1–1.6 points.

Here is what that does to a number on the dashboard, at sigma = 19:

| Dashboard shows | = points apart | After shrinking | **True edge** |
|---|---|---|---|
| +5% | 2.4 | 0.6 | **1.2%** |
| +10% | 4.8 | 1.1 | **2.3%** |
| **+13%** | **6.3** | **1.5** | **3.1%** |
| +20% | 10.0 | 2.3 | **4.8%** |

**A +13% displayed edge was really about +3%.** Still positive — but four times smaller than it looked, and small enough that fees and the bid-ask spread eat most of it.

And empirically, the very biggest disagreements are actively bad:

| model vs line | bets | hit rate | ROI |
|---|---|---|---|
| 0–2 pts | 186 | 48.9% | −6.85% |
| 2–4 pts | 127 | 55.9% | **+6.50%** |
| 4–6 pts | 78 | 50.0% | −4.86% |
| 6–9 pts | 60 | 55.0% | **+4.98%** |
| **9–12 pts** | 19 | **42.1%** | **−20.19%** |

*(breakeven is 52.4%)*

The sweet spot is a **moderate** disagreement. The extremes lose badly. This is why the UI flags anything over 15% with a "?" — that's not a jackpot, it's a bug signal.

### The bug we just fixed

The backtest **always** applied this shrinkage. The live dashboard **never did**. So every validated number described a shrunk model, while the screen you were looking at showed raw, unshrunk edges — inflated roughly fourfold. Fixed as of v4: the live path now shrinks, and the model version was bumped so the old and new predictions can never be blended in the same performance query.

## 6. How we know if we're any good: CLV

The obvious test is "did we win money?" That is a **terrible** test at our size.

If our true edge is 55%, then after 40 bets the standard error is ~7.9%. So a genuinely good model shows anywhere from 47% to 63%. A winning model and a losing model produce overlapping results. You cannot tell them apart. It takes *thousands* of bets.

So we use **closing line value** instead.

The **closing line** is the final price right before tip-off — the market's smartest, most-informed number. CLV asks: **did we get a better price than the close?**

Bet the Over at 170, the line closes at 173 → we beat the close by 3 points, *regardless of what happens in the game*. We bought at a price the market later agreed was too cheap.

Why this is so much better: outcomes are ~50/50 coin flips layered on top of our edge, and that coin-flip noise drowns everything. CLV strips it out — we observe a continuous measurement on **every** bet instead of one noisy bit. It converges roughly **10× faster**.

> **Our champion beats the close by +1.75 points, 95% CI [+1.45, +2.06].** The interval excludes zero in every season and every fill model. That is a real, measured edge.

## 7. What that edge is worth in money

Points aren't money. To compare against ROI you convert to price terms (Buchdahl's rule):

$$
\mathbb{E}[\text{ROI}] = \frac{p_{\text{close}}}{p_{\text{paid}}} - 1
$$

You must **de-vig** first. Bookmakers price both sides to sum over 100% (a −110/−110 market implies 52.4% + 52.4% = 104.8%). That extra 4.8% is their cut, not anyone's real probability.

| | Value |
|---|---|
| CLV in points | +1.75 |
| CLV as probability | **+4.16pp** |
| **Expected ROI** | **+2.50%, CI [+0.85%, +4.16%]** |
| Realised (maker-only) | +1.98% |

**The CI excludes zero.** That's the honest answer to "is this worth anything": yes, about 2.5% per bet — *if* we only ever post resting orders.

Because under pessimistic fills it's +0.11% [−1.18%, +1.40%] — **zero**. Maker-only isn't a preference, it's the whole edge.

## 8. Maker vs taker (why that matters so much)

- **Taker**: you cross the spread and buy immediately. Instant, but you pay the spread and a fee.
- **Maker**: you post an order at your price and *wait*. You might not get filled — but if you do, you got your price and you **don't pay the taker fee**. The venue also advertises a maker rebate, but we have never actually seen one land, so don't count on it.

Our entire edge is smaller than the spread. So taking destroys it and making preserves it. Every result in this project is reported maker-only, and the executor cannot even represent a market order.

## 9. The one rule that makes all of this trustworthy

**Point-in-time correctness.** Every feature is computed `as_of` a timestamp, using only games strictly before it.

This sounds pedantic. It is the difference between a real result and a fantasy. If you accidentally let the model see the future — even slightly, even through a season-average table that was updated later — you get a beautiful backtest that evaporates the moment real money is involved. The failure is *silent*: nothing crashes, the numbers just quietly become lies.

So `as_of` is a required argument everywhere with no default. "Current season stats" is not expressible in the code. Lookahead is made *structurally impossible* rather than merely discouraged.

## 10. What we've tested, and what happened

| Idea | Result |
|---|---|
| Simple efficiency model | ✅ **Adopted** — +1.75 CLV |
| Recent form weighting | ✅ Adopted |
| Home-court advantage | ✅ Adopted (measured +2.2, not folklore's 3–4) |
| Market shrinkage | ✅ **Adopted, and now live** |
| Home/away splits | ❌ Noise — each split is only ~22 games |
| Win-loss record | ❌ Predicted null, confirmed null |
| Possession structure | ❌ No improvement |
| MLB expansion | ❌ Measured 1¢ spreads — no gap to trade |
| **Injury/lineup awareness** | ❌ Even a *cheating* version that knows the real lineup gains no CLV |
| **Moneyline** | ❌ 25–33% hit rate. **Now switched off** |
| **Pace interaction** | ❌ Worth 0.05 points against a 3-point threshold |

That's a lot of ❌. **That is what a working research process looks like.** Nine of ten ideas failing is normal; the point is failing cheaply and knowing which one didn't.

## 11. Where the money actually is (and isn't)

The injury experiment taught us something precise. When we gave the model perfect hindsight knowledge of who played:

- ROI went **up** (knowing lineups predicts games)
- CLV stayed **flat** (the closing line already knew)

Lineups are public before tip-off. The market prices them. **Being informed isn't worth anything — being *early* is.**

That's the whole case for the news-window idea: a star is ruled out, the sportsbook repricing in seconds, and thin Polymarket possibly still showing the old number minutes later. That gap is the trade.

## 12. Current status, honestly

- **Real money traded: $0.** Everything is shadow mode with a kill switch on.
- The edge is real but small, and only under maker-only fills.
- The remaining gates are a 60-day live shadow record and a calibration check.
- The shadow clock **just reset** — the model changed (v3 → v4), so the old record describes a model that no longer runs. Annoying, but the alternative is measuring a model we're not using.

## Where to go deeper

| Doc | Question |
|---|---|
| [clv.md](math/clv.md) | Why CLV instead of win rate |
| [what-the-edge-is-worth.md](math/what-the-edge-is-worth.md) | The money conversion |
| [market-shrinkage.md](math/market-shrinkage.md) | The winner's curse, in full |
| [availability.md](math/availability.md) | The injury experiment |
| [point-in-time.md](math/point-in-time.md) | How lookahead is made impossible |
| [performance-targets.md](math/performance-targets.md) | Pre-registered bars for "good" |
