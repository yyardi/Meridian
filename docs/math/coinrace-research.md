# Coin Race (KXCRYPTOLEAD15M): the market, and the research program registered before any of it runs

2026-10-07. The operator's ask: find what can be done algorithmically on this market, with real
data, before any money or the incentive program.

## The contract

Every 15 minutes Kalshi lists five markets, one per coin — BTC, ETH, SOL, XRP, HYPE — asking
which has the highest return over the window. Return = (end − start) / start, where start and end
are each the time-weighted average of CF Benchmarks' spot rate over the 60 seconds before the
window's start and end (the market's own rule text). Exactly one market resolves YES. Fee type
`quadratic`: takers pay 0.07·p(1−p) per contract rounded up to the cent; resting orders pay
nothing. The liquidity program also pays $20 a market a window to resting size near the touch
(docs/math/kalshi-incentive-farming.md).

History on the public API at registration: **4,000 settled windows (20,000 markets) from
2026-08-25 to 2026-10-07, 13.0M contracts traded.** Winner frequency: HYPE 32.1%, XRP 21.7%,
BTC 16.9%, SOL 15.8%, ETH 13.1% — the most volatile coin wins most often, as a race of
correlated random walks predicts; whether the market prices that correctly is question 1.

## Questions (screens on recorded data; none of them is a result)

A screen chooses what runs live; only a live paper arm at live prices is a result
(operator rule, 2026-09-30). Each bar is fixed here, before the data.

1. **Pricing.** A model of P(coin i wins | the five coins' spot path so far, their vols and
   correlations, time left, the 60-s averaging at both ends), Monte Carlo of correlated paths
   with parameters estimated only from data before the day being scored. Scored walk-forward
   by day against the market's own last trade price at minutes 1, 5, 10 and 13 of each
   window. **Passes** if its log-loss beats the market's at some minute with a day-clustered
   95% CI excluding zero, AND a taker rule at the model's edge net of fees is positive with a
   window-clustered CI excluding zero. Otherwise directional trading on this market closes.
2. **Basket.** Exactly one of five pays $1, so the five YES prices sum to 1 in a frictionless
   book. Buying all five YES at the asks costs Σask + five taker fees; selling all five (buying
   all five NO) pays the mirror. On the per-minute book samples since 2026-10-03
   (`farm_scorer.sqlite`, `lip_sample`) and the live tape once it exists: how often either
   basket clears $0 after fees, by how much, at what displayed size, for how long. **Passes**
   at ≥ $50 a day at displayed size, not 80% in five windows.
3. **Farming fill cost.** The program pays resting size near the touch; the cost is being hit by
   someone who knows more. From the public prints: for a resting bid at 1–3¢ and one tick in
   front of the best bid, the fills per window and the settlement P&L per fill, by minute of
   the window. **Passes** if the expected fill cost at 1,000 a side is under 30% of the paper
   reward at the same size (docs/math/kalshi-incentive-farming.md).
4. **Late-window lag** (needs a live book tape and second-level spot; recorded after the prod
   disk is freed). Does the book trail the spot-implied probability in the last three minutes by
   more than the round-trip fee? Registered when the tape exists.

## What follows a pass

A paper arm on the live tape at zero cost, with its read registered before its first fill.
Live money (a Kalshi trading key and collateral) is the operator's switch.

## 2026-10-07 — Questions 2 (basket) and 3 (farming fill cost): screens on recorded data

Screens, not results. **Q2 basket: FAIL.** One clearing minute in 3.34 days of the registered
sample (≤ $8.73 a day); on the tape a five-leg taker already collects $11.61 a day. **Q3 farming
fill cost: PASS on the point estimate**, before anyone responds: $0.89 per market-window over the
program period's 2,070 market-windows (14–17% of the paper reward; interval to 44%), $0.59 to
$1.07 on all 21,245 (9–20%; interval to 29%). The per-window loss tail fails the farming doc's
item 3.

Scripts: `analysis/coinrace/fetch_trades.py`, `basket_screen.py`,
`farm_fill_screen.py`; tests `tests/test_coinrace_microstructure.py`. Data under
`~/MeridianArchive/coinrace/` on the operator's Mac (not in the repo).

### Data

- **Trades.** Every public print of every settled market, `GET /markets/trades?ticker=…` page by
  page, newest windows first, ≤ 4 requests/s: **368,476 trades, 13,066,077 contracts, 19,876
  markets in 4,146 windows, closing 2026-08-20 16:15Z → 10-07 03:30Z (47.48 days)**, fetched
  03:40–05:08Z on 10-07 in 88 min (`trades.parquet`, `trades.COVERAGE.txt`). The summed contracts
  equal the market's listed `volume_fp` on every one of the 19,876 markets with a trade, so no
  print is missing. Markets
  listed with zero volume (1,374) were not requested. Results per market (incl. 24 two-coin ties
  that settle 0.5 each) come from the listing; every window's settlements sum to $1.
- **What a print fills.** `taker_side` is the side the taker bought: `taker_side='no'` fills a
  resting YES bid at `yes_price`, `'yes'` fills a resting NO bid at `no_price`. Checked against
  the book: of the prints within 10 s after a farm-scorer sample (10-03 19:25Z → 10-07 03:30Z),
  `'no'` prints sat exactly at the sampled YES bid 53.0% of the time and at the YES ask 0.7% (n =
  1,563); `'yes'` prints sat at the ask 31.9% and at the bid 0.7% (n = 1,701). The rest are
  sweeps or moves inside the 10 s. `taker_outcome_side` equals `taker_side` on every row, and
  `taker_book_side` is a function of it, so neither adds information.
- **Control on the mapping and the settlement join (can fail).** The farming doc's realised
  P&L of every print into a ≤ 5¢ bid over its 80 windows (10-02 23:15Z → 10-03 19:00Z),
  recomputed from this tape: 3,481 trades and 120,349 contracts (doc: the same); YES side
  −$58.52 and NO side +$33.26 (doc: the same); window 26OCT030145 −$25.75 (doc: the same).
  The doc's total of −$25.24 is 2¢ off its own two components, which sum to −$25.26. The doc's
  contract counts into ≤ 5¢ bids (19,190 and 5,518) are both 14.8% above this tape's (16,708 and
  4,811) while every P&L figure matches. That is a different count definition in the doc; it is
  not a mapping error, because a swapped side would flip the P&L.
- **Book, two instruments.** (a) The farm scorer's once-a-minute `lip_sample` (19,514 Coin Race
  rows, 10-03 19:25Z → 10-07 03:37Z; best bid, reference, depth, no size at the best level). Its
  book tracker kept fully cancelled levels alive as ~0-size phantom best prices (fixed on main in
  cad12b5; samples before ~04:00Z 10-07 are suspect). No Coin Race row is crossed (0 of 19,514),
  but the sample's best bid sits above BOTH venue candle closes bracketing it on 10.7% of YES-side
  and 12.6% of NO-side samples. A phantom can only raise a best bid, so it makes the other
  side's basket look cheaper: on this instrument the basket screen is biased toward "clears".
  (b) The venue's own 1-minute candlesticks (`yes_bid` / `yes_ask` close per market-minute, all
  21,004 traded markets since 08-20; fetched by the pricing agent, `pricing_book_1m.parquet`),
  which the tracker defect cannot touch. Neither instrument sees inside a minute.

### Question 2 — Basket

Per window-minute with all five books: YES basket net = $1 − Σ YES ask − Σ taker fee; NO basket
net = $4 − Σ (1 − YES bid) − Σ fee; fee = ⌈0.07·c·p(1−p)⌉ to the cent per leg order of c
contracts (at c = 1 every leg costs ≥ 1¢, so a basket needs ≥ 5¢ of incoherence; at c = 200 the
rounding is negligible). An episode = consecutive sampled minutes of one window that clear,
taken once at its first minute.

| instrument | population | n | YES basket clears | NO basket clears | net per basket when it clears | displayed size | $ a day at displayed size | top 5 windows |
|---|---|---|---|---|---|---|---|---|
| farm-scorer minute sample (the registered substrate; biased toward clearing) | 10-03 19:25Z → 10-07 03:30Z, 3.34 days | 3,195 five-leg minutes, 321 windows; 0 crossed rows to exclude | 1 minute = 1 episode | never (best −0.03¢ at 200 a leg) | +12¢ at 1 a leg, +14.63¢ at 200 | < 200 on at least one leg | **≤ $8.73** (the episode at 199 a leg) | 100% (one window) |
| venue 1-min candles | the same period | 3,065 five-leg minutes, 321 windows | 1 = the same episode | 1 at 200 a leg (+0.23¢) | +15¢ / +17.7¢ | not recorded | — | — |
| venue 1-min candles | 08-20 → 10-07, 47.5 days | 34,263 five-leg minutes, 4,096 windows | 25 episodes at 200 a leg (0.53 a day, ≤ 4 min long); 19 at 1 a leg | 37 episodes at 200 a leg (0.78 a day, ≤ 2 min); 1 at 1 a leg | median +4.0¢ (YES), +0.45¢ (NO) at 200 | not recorded | $50/day would need **1,795** a leg on every YES episode, or 7,803 on every NO one | — |
| tape: five-leg baskets someone executed | program period 10-02 20:00Z → 10-07 03:30Z, 4.31 days | 120 baskets in 90 of 414 windows | 33 (4 of ≥ 10 a leg) | 87 (38 of ≥ 10 a leg) | ≥ 10 a leg: NO median +0.68¢, YES +3.09¢ | ≥ 10 a leg: median 120 | **$13.58** realised by the taker | 51% |
| tape | all history 08-20 → 10-07, 47.47 days | 1,629 baskets in 977 of 4,146 traded windows | 257 (33 of ≥ 10 a leg) | 1,372 (428 of ≥ 10 a leg) | ≥ 10 a leg: NO median +0.86¢, YES +1.89¢ | ≥ 10 a leg: NO median 61 (p90 120), YES 100 | **$11.61** realised by the taker | 24% |

**The executed baskets, measured** (tape, all history, 47.47 days; ≥ 10 contracts a leg; the
smaller ones are probes, below).

| | NO basket, ≥ 10 a leg | YES basket, ≥ 10 a leg |
|---|--:|--:|
| baskets (per day) · windows | 428 (9.0) · 301 | 33 (0.7) · 22 |
| size a leg, p10 · p50 · p90 | 10 · 61 · 120 | 17 · 100 · 200 |
| Σ paid, p10 · p50 · p90 (pays $4 / $1) | 394 · 397 · 398¢ | 90 · 94 · 97¢ |
| five taker fees per basket, p50 | 2.32¢ | 4.51¢ |
| net per basket, p10 · p50 · p90 | +0.15 · +0.86 · +2.70¢ | +0.37 · +1.89 · +5.79¢ |
| net positive | 418 of 428 | 33 of 33 |
| net realised, total (per day) | $463.00 ($9.75) | $86.47 ($1.82) |
| minute of the window, p10 · p50 · p90 | 2.4 · 6.7 · 11.7 | 4.5 · 7.0 · 13.8 |
| legs' spread in time, p50 | 1.4 ms | 1.7 ms |
| baskets that took more than one price level on some leg | 33 | 2 |
| back in the same window, median wait | 18 s (127 repeats) | 2.5 s (11) |
| **residue**: the same basket at the venue's next minute close (median lag 31 s) still clears, at 1 a leg · 200 a leg | 0 · 11 of 314 (median −6.5¢) | 1 · 4 of 18 |

Below 10 a leg (median 1) are 944 NO and 224 YES probes, netting −$4.03 and +$5.46: a taker
testing the book, not a profit. What the tape shows is one or more automated takers buying all
five legs at once, the legs landing within milliseconds of each other. Each leg takes the top
price level; 120 is the rung size of the market maker's ladder the farming doc saw on 10-03.
The taker comes back within seconds when the book refreshes, and by the next minute close
nothing that clears at 1 a leg is left. How fast it reacts to a basket appearing is not
measurable here (the book is minute-resolution). A second taker would have to beat it to each
refresh, for a pool that has paid $11.61 a day in total.

**One basket by hand.** Sample 2026-10-06 03:24:38Z, window 26OCT052330 (closes 03:30Z), minute
9.6. NO bids BTC 91, ETH 92, HYPE 94, SOL 69, XRP 73 → YES asks 9 + 8 + 6 + 31 + 27 = 81¢. Fees at
1 a leg: 1 + 1 + 1 + 2 + 2 = 7¢ → **+12¢**. At 200 a leg: 0.575 + 0.52 + 0.395 + 1.50 + 1.38 =
4.37¢ → **+14.63¢**. Not a phantom: the venue's candle closing 03:25:00Z shows YES asks 9, 8, 6, 31,
24 (Σ 78¢). On the tape, someone bought all five YES at once at 03:22:58.748Z (119 a leg at
13/8/9/31/31, Σ 92¢) and at 03:24:31Z (30 a leg at 9/8/6/31/40, Σ 94¢). The sample shows at
least one leg under 200 contracts at its best NO bid (reference below best), so the displayed
size was < 200.

**Control (can fail).** The closest the NO basket came is −0.03¢ at 200 a leg (sample 10-04
17:22:06Z, window 26OCT041330: YES bids 15/17/7/64/1). Moving one leg 2¢ toward the basket (SOL's
NO ask 36 → 34¢) flips it to **+2.01¢** (BTC +1.88¢, XRP +1.84¢). The change is the 2¢ plus SOL's
0.04¢ fee saving, as the arithmetic requires. A separate test moves only the YES bids, then only
the NO bids, and checks that each basket moves only with its own side. Both are pinned in
`tests/test_coinrace_microstructure.py`.

**What a one-minute sample cannot see.** On the tape the five legs of an executed basket land
within milliseconds of each other: median 1.4 ms over the 1,629 baskets, 89% within 10 ms.
Anything that clears and is taken inside a minute is invisible to both book instruments, and
that is exactly how the executed baskets look. So
the tape row is the sub-minute instrument: it counts what someone else captured, at the size
they took. What it cannot count is a basket that cleared and that nobody took; the residue
measurement bounds that from the next minute close.

**Verdict, question 2: FAIL**, against the registered bar of ≥ $50 a day at displayed size,
not 80% in five windows. The registered instrument shows one clearing minute in 3.34 days,
worth ≤ $8.73 a day even at the 199-a-leg ceiling, and that minute is 100% of its total. The
venue's own book agrees. The tape shows the opportunity exists below a minute but is already
taken: a five-leg taker collects $11.61 a day on this market, and the residue it leaves at
the next minute close almost never clears. Capturing every basket it captured would still fall
short of $50 a day. Directional trading's question 1 is unaffected; the basket closes.

### Question 3 — Farming fill cost

A hypothetical bid of 1,000 resting on one side of one market is filled by takers who sell into
that side (rule above). Placements:

- **Fixed 1¢, 2¢, 3¢, first in queue.** Every print at ≤ P passes through us first:
  fills = min(1,000, cumulative contracts printed at ≤ P).
- **Fixed P, behind 1,000.** The farmers' 1,000-lot ahead absorbs the first 1,000:
  fills = min(1,000, max(0, cumulative − 1,000)).
- **Front, live.** One tick in front of the best bid at the moment of each sell. The best bid just
  before a sweep is the sweep's top print price (a taker order's prints share `created_time`),
  so every contract sold into the side fills us first at top + 1¢, while that is ≤ 10¢. Our
  1,000 at that price is then the side's reference, which is the farming doc's "reference ≤ 10¢".
- **Front, minute book.** One tick in front of the venue candle's best bid at the last minute end
  before the print (p = b + 1 ≤ 10¢). For the window's first minute, before any candle closes, the
  previous print into the same side is used; prints with neither are not quoted. In the program
  period: candle 23,041 prints, previous print 322, unquoted 371; median book age 28 s, p90 54 s.
  A quote left at b + 1 while the book falls pays more than the live quote. A quote that has not
  moved up misses fills. The two placements bracket a quoter in between.

P&L per filled contract at our price p: +(1 − p) if the side wins, −p if not; a tie pays 0.5.
1,000 a side means at most 1,000 filled per side per window (no refill). Every figure is
**before anyone responds**: our size does not change the takers' flow, nobody steps in front
inside a minute, and the queue ahead is constant. The denominator is every market-window in
the population, including those with no print.

Paper reward to compare against (docs/math/kalshi-incentive-farming.md, `f1000c`, before anyone
responds): $2,566–3,087 a day over 480 market-windows = **$5.35–6.43 per market-window**; the
registered bar is a fill cost under 30% of that, **$1.60–1.93 per market-window**.

**Program period** (10-02 20:00Z → 10-07 03:30Z, the farmers' regime, the only one with a
reward): 414 windows, 2,070 market-windows, 4.31 days; best bid from the venue candles.
Estimators: fills and P&L are means per market-window over every market-window (equal weight),
both sides summed; "per filled contract" is the fills-weighted ratio; CIs are bootstrap over
windows and over days.

| placement, 1,000 a side | fills per market-window (YES · NO) | market-windows with a fill | P&L per filled contract | P&L per market-window (95% CI: window · day) | cost ÷ reward |
|---|--:|--:|--:|--:|--:|
| **front, live**, ≤ 10¢ | 140.7 (114.5 · 26.2) | 74.3% | −0.63¢ | **−$0.89** (−2.33, +0.81 · −2.89, +2.11) | **14–17%** |
| front, minute book, ≤ 10¢ | 107.0 (97.0 · 10.0) | 62.9% | −0.84¢ | **−$0.89** (−2.14, +0.63 · −2.64, +1.32) | 14–17% |
| 1¢ first in queue | 92.9 (75.5 · 17.5) | 57.8% | +0.27¢ | +$0.25 (−0.54, +1.47 · −0.84, +1.91) | gain |
| 1¢ behind 1,000 | 7.8 (6.7 · 1.1) | 2.3% | −0.07¢ | −$0.01 (−0.11, +0.16 · −0.16, +0.16) | 0% |
| 2¢ first | 101.7 (83.1 · 18.7) | 61.3% | −0.07¢ | −$0.07 (−1.14, +1.36 · −1.43, +1.81) | 1% |
| 2¢ behind 1,000 | 8.7 (7.6 · 1.1) | 2.5% | −1.17¢ | −$0.10 (−0.24, +0.08 · −0.35, +0.11) | 2% |
| 3¢ first | 112.9 (91.0 · 21.9) | 64.5% | −1.00¢ | −$1.13 (−2.29, +0.32 · −2.95, +1.35) | 18–21% |
| 3¢ behind 1,000 | 9.4 (8.0 · 1.4) | 2.8% | −2.23¢ | −$0.21 (−0.38, −0.01 · −0.58, +0.06) | 3–4% |

The uncapped front (every side, up to 98¢) is a ceiling only: −$32.42 per market-window
(−38.39, −26.72), 316 fills, as the farming doc expected for the leading coin's side.

**By minute of the window** (program period; fills · P&L in $ per market-window, both sides):

| minute | front, live | front, minute book | 1¢ first | 1¢ behind 1,000 |
|--:|--:|--:|--:|--:|
| 0 | 0.9 · +0.02 | 0.2 · −0.01 | 0.0 · 0.00 | 0.0 · 0.00 |
| 1 | 1.4 · −0.08 | 1.0 · −0.05 | 0.3 · −0.00 | 0.0 · 0.00 |
| 2 | 1.5 · −0.02 | 1.2 · −0.01 | 0.2 · −0.00 | 0.0 · 0.00 |
| 3 | 3.3 · −0.19 | 2.9 · −0.17 | 0.4 · −0.00 | 0.0 · 0.00 |
| 4 | 2.4 · +0.09 | 2.2 · +0.10 | 0.5 · +0.05 | 0.0 · 0.00 |
| 5 | 6.7 · −0.16 | 5.9 · −0.12 | 2.2 · +0.03 | 0.3 · −0.00 |
| 6 | 7.1 · +0.94 | 6.9 · +0.89 | 2.6 · +0.43 | 0.5 · +0.05 |
| 7 | 9.3 · −0.12 | 8.4 · −0.09 | 3.6 · +0.01 | 0.0 · 0.00 |
| 8 | 11.7 · −0.42 | 10.9 · −0.37 | 5.9 · −0.06 | 0.1 · −0.00 |
| 9 | 11.8 · −0.32 | 11.3 · −0.29 | 7.4 · −0.07 | 0.4 · −0.00 |
| 10 | 16.6 · −0.16 | 15.6 · −0.29 | 13.6 · −0.12 | 1.5 · +0.00 |
| 11 | 15.9 · +0.11 | 15.3 · −0.13 | 14.0 · −0.05 | 1.1 · −0.01 |
| 12 | 9.5 · −0.06 | 8.3 · −0.07 | 8.2 · +0.04 | 0.5 · −0.01 |
| 13 | 12.3 · +0.07 | 9.9 · −0.09 | 10.3 · +0.10 | 0.9 · −0.01 |
| 14 | 30.4 · −0.58 | 7.1 · −0.20 | 23.8 · −0.09 | 2.5 · −0.03 |

Fills build through the window, and the last minute is the costliest for the live front. A
single minute's P&L is set by a handful of winners. Minute 6's +$0.94 is +$1,945 in total, and
three market-windows supply $1,633 of it (ETH 26OCT061200 +$931, BTC 26OCT040215 +$412, BTC
26OCT021730 +$290).

**The mean rests on a tail.** Live front, program period: losses −$4.51 and wins +$3.61 per
market-window. The wins come mostly from 24 market-windows (1.2%) above +$100, each a lot of
up to 1,000 bought at 1–10¢ on a side that then won. Leave those 24 out and the cost is
$3.89 (61–73% of the reward). Leaving them out is not a valid estimator, because the wins are
real; it shows how much a few lottery outcomes decide the figure over four days.

**Sensitivities** (P&L per market-window, 95% CI window-clustered; cost ÷ reward on the point estimate):

| population, book | front, live | front, minute book | n market-windows |
|---|--:|--:|--:|
| program period, orders pulled at T − 60 s (the registered live step) | −$0.31 (−1.67, +1.33), 5–6% | −$0.69 (−1.92, +0.80), 11–13% | 2,070 |
| farm-sample period 10-03 19:30Z →, venue candles | −$0.82 (−2.66, +1.32), 13–15% | −$0.90 (−2.46, +0.96), 14–17% | 1,600 |
| the same, farm-scorer book (defect-flagged) | — | −$1.19 (−2.75, +0.69), 18–22%; at reference + 1¢ (the scorer's own `f1000c` placement): −$1.23 (−2.88, +0.72), 19–23% | 1,600 |
| before the program, 08-20 → 10-02 20:00Z (no farmers, no reward) | −$0.55 (−1.12, +0.03), 9–10% | −$1.09 (−1.56, −0.60), 17–20% | 19,175 |
| **all history**, 08-20 → 10-07 (47.47 days) | **−$0.59 (−1.13, −0.03), 9–11%**; day-clustered (−1.21, +0.05) | **−$1.07 (−1.50, −0.58), 17–20%**; day-clustered (−1.57, −0.58) | 21,245 |

On all history the live front fills 118.3 per market-window (91.8 YES · 26.4 NO) at −0.50¢ a
contract. The mean still rests on a tail: 190 market-windows (0.9%) above +$100; without them
the figure is −$3.35. The 1¢ bid first in queue gains +$0.80 (+0.41, +1.23): on this tape,
takers who dump at 1¢ are wrong more than 1% of the time. Being first at 1¢ is a race at the
window's open against farmers already resting 1,000 there, so this is not a placement anyone
has shown is available.

**Loss tail per window** (five markets, both sides, 1,000 a side; the farming doc's registered
item 3 as read here, loss = −P&L per window): live front, program period, p90 **$49.48**, p99
$95.22, max **$111.04** (414 windows; 40 lose more than $50). Minute-book front: p90 $39.55,
max $115.67. All history: live p90 $44.50, max $275.99 (4,249 windows). That item's bars
(p90 < $15, max < $50) are exceeded several times over on this definition. The doc's own tail
figures were per market-side for some rows and per window for others, so the definition is
stated here, not assumed.

**One fill by hand.** Window 26OCT050245 (06:30–06:45Z on 10-05; HYPE won, BTC settled NO),
BTC YES side. 06:32:31.407Z: a print at YES 2¢ × 120 (`taker_side='no'`, one leg of a
five-leg NO basket). The live front sits at 3¢ and takes all 120 (−$3.60). The minute-book
front read the 06:32:00 candle's 7¢ best bid, sits at 8¢, and takes them at 8¢ (−$9.60).
06:35:52.552Z: a dump at 1¢ × 1,526.6. Both fronts sit at 2¢ and take the remaining 880
(−$17.60). The side's total is −$21.20 live and −$27.20 on the minute book; later prints find
the lot full. The first fill shows the bracket in miniature: a quote left behind by a falling
book pays 5¢ more per contract.

**Verdict, question 3: PASS on the registered bar, before anyone responds, and not by a wide
margin on the reward's own days.** The bar is an expected fill cost at 1,000 a side under 30%
of the paper reward ($1.60–1.93 per market-window). Placement: one tick in front on every side
at ≤ 10¢, the reward's own placement.

- Program period (the reward's regime, 2,070 market-windows): **$0.89** per market-window on both
  placements, **14–17%** of the reward. Its 95% interval reaches $2.33 (36–44%), so the 4.3 days
  alone do not exclude failing.
- All history (21,245 market-windows, 90% of them before the farmers arrived): **$0.59** live
  (9–11%, interval's adverse end $1.13 = 18–21%), **$1.07** on the minute book (17–20%, adverse
  end $1.50–1.57 = 23–29%).

What the pass does not cover:

1. **The response.** Both the reward and the fills are paper figures before the incumbents
   step in front. They cut both, and only the live step measures that.
2. **The reward figure is itself a corrected read.** Its registered confirmation is the fixed
   scorer's 48 h ending 10-09 04:00Z, and this comparison should be redone against that number.
3. **A tail decides the mean.** About 1% of market-windows (a lot bought at 1–10¢ on a side that
   then won) carry it. Without them the cost is $3.35–3.89 per market-window (52–73%). The
   registered live step (48 windows = 240 market-windows) should expect 2–3 such wins (0.9–1.2%
   of 240). Its realised fill P&L will have a wide spread around −$142 to −$214 (240 × $0.59–0.89).
4. **The per-window loss tail fails the farming doc's item 3 as read here:** p90 $44–49, max
   $111–276 per window against bars of $15 and $50. A drawdown of that size is ordinary, not rare.
5. **Pulling at T − 60 s, as the registered live step does,** lowers the live cost to $0.31
   (5–6%). The last minute is the costliest minute for the live front.

As a screen this clears the farming live step to the operator's switch, unchanged: one window's
five markets, 1,000 a side one tick in front on sides ≤ 10¢, pulled at T − 60 s, N = 48. The
step's own pass (realised reward ≥ 60% of paper, net of fills ≥ $0) is the result.
