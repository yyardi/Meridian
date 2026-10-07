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

## 2026-10-07 — Question 1 (Pricing), screened: FAILS the registered bar

**Verdict.** The taker leg fails: buying YES at the displayed ask whenever model − ask − fee > 0
and holding to settlement lost **−2.70¢ per contract [−3.63, −1.76]** (mean per contract,
window-clustered 95% CI; 8,834 contracts, 3,483 windows, 42 UTC days, 2026-08-27 → 10-07), and
lost at every one of the four minutes. The log-loss leg passes only against the registered
"market" (the last print, normalised), at minutes 5, 10 and 13. That print is often stale.
Against the book mid at the same instants the model loses at minute 1, ties at 5 and 10, and
wins only at minute 13 on log loss, while losing on Brier at every minute. Under the bar,
**directional trading on this market closes.** This is a screen on recorded data. Nothing
below is a result or an edge.

Code: `analysis/coinrace/pricing_data.py` (fetch), `pricing_model.py` (model and scoring),
`pricing_screen.py` (`models`, `report`, `tables`, `hand`); tests in
`tests/test_coinrace_pricing.py`. Data: `~/MeridianArchive/coinrace/data/pricing_*.parquet`.
Everything runs as one process under `nice -n 19` with single-threaded numerical libraries,
on the operator's laptop.

### Data

- **Markets.** `/markets?series_ticker=KXCRYPTOLEAD15M&status=settled`: 21,250 markets in
  4,250 windows, 2026-08-20 16:00Z → 10-07 03:30Z. The listing starts at 08-20, not 08-25,
  with almost no volume before 08-24. The ticker's time is the window END in US Eastern time.
  It equals `close_time` on all 21,250 markets, and `close_time − open_time` = 900 s on all of
  them. Truth is the market's `settlement_value`: 1, or 0.5 for each coin in a two-coin tie
  (24 windows). The event's `expiration_value` is blank or disagrees across sibling markets
  in 25 events, so it is not used.
- **Spot (the proxy).** Coinbase Exchange 1-minute candles for BTC, ETH, SOL, XRP and
  HYPE-USD, all five listed on Coinbase. 2026-08-10 → 10-07 03:4xZ, 414,494 rows (the extra
  two weeks before 08-24 warm up the first covariances). A minute with no trade has no candle:
  HYPE lacks one in 5.0% of minutes, XRP in 0.02%, BTC, ETH and SOL in none. Such minutes
  carry the last close forward.
- **Book.** Kalshi's per-minute candlesticks (batch `/markets/candlesticks`) for 21,004 of the
  21,250 markets. The yes-ask close of the candle ending at open + 60·m is the ask at minute m.
  89% of the asks come from that exact candle. The rest come from the latest earlier candle in
  the same window, on the assumption that a missing candle means an unchanged book.
  Cross-check against the trade tape: the candle's last price matches the tape's last print
  within 0.5¢ on 95.1% of 12,259 market-minutes that have both, and within 1¢ on 97.1%.
- **Prints.** `trades.parquet` from the coinrace-microstructure agent covers windows closing
  2026-09-15 18:15Z → 10-07 03:30Z (21.4 days): 155,264 prints on 9,757 markets. Its summed
  contracts equal each market's listed volume on all 9,757.

### The proxy, and the bound it puts on everything else

Each end's 60-s time-weighted average is approximated from one Coinbase minute candle (the
minute before the window opens, and the window's last minute). The proxy formula was fixed
before looking at outcomes; the alternatives are reported here, not chosen among. Agreement
is measured on the 4,226 single-winner windows: does the proxy's highest-return coin match
the settled winner?

| TWA proxy (Coinbase 1-min candle) | windows | agrees with settled winner | all candles present: windows | agrees |
|---|---:|---:|---:|---:|
| close to close (no averaging) | 4,226 | 84.90% | 3,948 | 85.18% |
| (open+close)/2 | 4,226 | 90.75% | 3,948 | 90.96% |
| (high+low+close)/3 | 4,226 | 90.75% | 3,948 | 91.06% |
| **(open+high+low+close)/4 — used** | 4,226 | **92.45%** | 3,948 | 92.71% |

**The proxy picks the settled winner in 92.45% of windows.** The misses are all close races.
Grouped by the gap between the proxy's top two returns, agreement is 61% under 1 bp (n=386),
79% at 1–2 bp (374), 91% at 2–5 bp (894), 98.7% at 5–10 bp (942) and 100% above 10 bp
(1,630). Bitstamp's candles do worse: 85.4% alone, and 90.3% averaged with Coinbase. Coinbase
alone is kept. So in roughly one window in thirteen, a model fed this proxy is computing the
wrong race at the finish, and that is where the market, which can watch the index itself, is
best placed.

### The model

At t seconds into the window (t ≤ 840), coin i's start average A_i is known and its spot
S_i(t) is observed. Model log prices as a driftless Brownian motion with per-second
covariance Σ. The end average's log return is then Gaussian:

    X = x(t) + N(0, Σ·v(t)),   x_i(t) = log S_i(t) − log A_i,   v(t) = (840 − t) + 60/3 = 860 − t s

The second term is the variance of the 60-s average: a third of a minute. P(coin i wins) is
a four-dimensional Gaussian orthant probability. It is computed by Rao-Blackwellised
quasi-Monte Carlo: draw X and average Φ((E[X_i | X_−i] − max_{j≠i} X_j) / sd(X_i | X_−i)).
Against brute-force counting with 2·10⁶ paths it is within 0.002 (tested). S_i(t) is the
close of the Coinbase candle ending at open + t.

Walk-forward by UTC day. Covariances come from candles strictly before the scored day's 00:00Z.
The fitted scalars (β, k, σ_p, ν) are refit every seven days, on the settled windows of the
seven days before the refit date, which is never after the scored day. Each step adds one
thing to the last model kept, and is kept if it lowers pooled out-of-sample log loss. Pooled
means the per-window mean over the four minutes, compared day-clustered on the windows both
models priced. Step order was fixed before running.

| model | vs | pooled Δ log loss [95% CI] | min 1 | min 5 | min 10 | min 13 | windows / days | kept |
|---|---|---:|---:|---:|---:|---:|---:|---|
| M1 + covariance from 5-min returns (was 1-min) | M0 | −0.0035 [−0.0062, −0.0008] | +0.0010 | −0.0029 | −0.0060 | −0.0061 | 4,250 / 48 | yes |
| M2 + hour-of-day vol profile | M1 | +0.0053 [−0.0002, +0.0108] | +0.0063 | +0.0073 | +0.0056 | +0.0019 | 4,250 / 48 | no |
| M3 + trailing-60-min realised-vol state, (RV/week)^β | M1 | **−0.0310 [−0.0418, −0.0201]** | −0.0111 | −0.0319 | −0.0421 | −0.0389 | 3,882 / 42 | yes |
| M4 + variance scale k, proxy noise σ_p | M3 | −0.0004 [−0.0019, +0.0011] | +0.0012 | −0.0009 | −0.0013 | −0.0006 | 3,882 / 42 | yes |
| M5 + Student-t scale mixture (ν) | M4 | −0.0008 [−0.0025, +0.0008] | +0.0027 | −0.0013 | −0.0032 | −0.0016 | 3,882 / 42 | yes |

M0 is a Gaussian with the zero-mean covariance of 1-minute returns over seven days. Almost all
of the gain is M3: the coins' vol over the last hour, relative to the week. M4 and M5 pass the
"lowers log loss" rule only on their point estimates. Their CIs straddle zero, and M5 is worse
at minute 1. The final model is M5. Its out-of-sample log loss on 3,882 windows over 42 days is
1.4949, 1.2183, 0.8374 and 0.4856 at minutes 1, 5, 10 and 13. Uniform scores 1.6094 and
climatology 1.5571. It is calibrated within a few points in every probability bin at every
minute: at minute 13, bin 0.70–0.90 has mean p 0.805 and frequency 0.833 (n=1,090), and bin
0.90–1.00 has 0.971 and 0.973 (n=1,581). The fitted scalars by refit week: β 0.5–1.0,
k 0.85–1.2, σ_p 0–2 bp, ν ∞, 8 or 4.

Monte Carlo cost was cut to what the comparison needs. Scoring uses 2,048 Sobol draws. Against
8,192 on four days, the largest probability difference is 0.0034 and the mean |Δ log loss| per
window is 0.0013. Fitting uses 256 draws.

### Model vs market (registered: the last print at or before open + 60·m, five normalised to sum to 1)

Windows count only when all five markets have printed by the minute. That selects windows with
active books in every coin: 30 at minute 1, 660 at 5, 1,422 at 10 and 1,670 at 13, out of the
tape's 2,030 windows.

| minute | windows / days | log loss model | market | climatology | model − market [95% CI, day-clustered] | Brier model | market | model − market [95% CI] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 30 / 12 | 1.2891 | 1.3521 | 1.5549 | −0.0630 [−0.3065, +0.1805] | 0.6651 | 0.6956 | −0.0305 [−0.1599, +0.0989] |
| 5 | 660 / 23 | 1.1121 | 1.2192 | 1.5411 | −0.1071 [−0.1516, −0.0626] | 0.5792 | 0.6132 | −0.0340 [−0.0548, −0.0131] |
| 10 | 1,422 / 23 | 0.8064 | 0.9015 | 1.5472 | −0.0951 [−0.1187, −0.0714] | 0.4263 | 0.4614 | −0.0352 [−0.0459, −0.0245] |
| 13 | 1,670 / 23 | 0.4782 | 0.6093 | 1.5501 | −0.1312 [−0.1677, −0.0946] | 0.2648 | 0.3110 | −0.0461 [−0.0629, −0.0294] |

**Read this table as a statement about stale prints, not about pricing.** A last print can be
minutes old: in the hand check below, XRP's last print, 24 s before the minute, is 0.32, above
the 0.23 ask that was live at the minute. The same comparison against the book mid, normalised
the same way (supplementary, not registered), uses every window the model priced:

| minute | windows / days | log loss model | mid | model − mid [95% CI] | Brier model | mid | model − mid [95% CI] |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3,882 / 42 | 1.4949 | 1.4837 | +0.0112 [+0.0030, +0.0194] | 0.7476 | 0.7435 | +0.0042 [+0.0003, +0.0080] |
| 5 | 3,882 / 42 | 1.2183 | 1.2097 | +0.0087 [−0.0021, +0.0194] | 0.6224 | 0.6164 | +0.0060 [+0.0013, +0.0107] |
| 10 | 3,882 / 42 | 0.8374 | 0.8439 | −0.0065 [−0.0181, +0.0051] | 0.4441 | 0.4364 | +0.0077 [+0.0025, +0.0128] |
| 13 | 3,882 / 42 | 0.4856 | 0.4996 | −0.0140 [−0.0263, −0.0018] | 0.2664 | 0.2549 | +0.0116 [+0.0053, +0.0178] |

Against a live quote the model is not better. Its one log-loss win, at minute 13, comes with a
worse Brier score, and the log-loss win sits entirely in races that are already decided.
Split the 3,882 minute-13 windows by the model's largest probability. Where that is ≥ 0.95
(n=1,177; the favourite won 98.6%), the model's mean favourite probability is 0.986 against the
normalised mid's 0.906. That gap contributes −81 to the summed log-loss difference of −55. The
gap comes from the tick grid, not from information: a loser's mid cannot go below ~0.005 and
the favourite's ask stops at 0.99, so the normalised mid is pulled away from 1. Nobody can buy
it there at a profit either: 0.99 + a 1¢ fee. Where the model's largest probability is
< 0.8 (n=1,716), the mid beats the model on both scores (Δ log loss +44, Δ Brier +59, summed).
Four minutes were tested and there is no adjustment for multiplicity.

### Taker rule (registered): buy one YES at the ask when model − ask − fee > 0, hold to settlement

Ask: the Kalshi candle ask at the minute. Fee: ⌈0.07·a·(1−a)⌉ to the cent for one contract.
Size at the ask is not checked; one contract is assumed fillable. P&L = settlement value
(1, 0.5 on a tie, 0) − ask − fee.

| minute | contracts | windows | days | mean ask | mean claimed edge | mean P&L / contract [95% CI, window-clustered] | win rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,925 | 1,726 | 42 | 0.244 | +3.35¢ | −3.13¢ [−4.90, −1.37] | 23.1% |
| 5 | 2,275 | 1,969 | 42 | 0.258 | +3.91¢ | −2.64¢ [−4.18, −1.11] | 24.8% |
| 10 | 2,453 | 2,083 | 42 | 0.308 | +4.85¢ | −2.12¢ [−3.49, −0.74] | 30.2% |
| 13 | 2,181 | 1,939 | 42 | 0.344 | +7.65¢ | −3.03¢ [−4.43, −1.63] | 32.9% |
| **all** | **8,834** | **3,483** | **42** | 0.290 | +4.97¢ | **−2.70¢ [−3.63, −1.76]** | 27.9% |

On the 23 days the print tape covers, the result is the same: −2.95¢ [−4.33, −1.56] on 4,191
contracts in 1,788 windows. The model claimed +4.97¢ a contract and realised −2.70¢. Where the
model and the book disagree, the book is usually right.

By claimed edge (shape only; a threshold picked from this table would be a new hypothesis, not
a test of this one):

| claimed edge (model − ask − fee) | contracts | mean claimed | mean P&L [95% CI] |
|---|---:|---:|---:|
| 0–2¢ | 3,354 | +0.90¢ | −3.63¢ [−4.81, −2.45] |
| 2–5¢ | 2,592 | +3.29¢ | −2.95¢ [−4.45, −1.45] |
| 5–10¢ | 1,693 | +7.08¢ | −2.05¢ [−4.13, +0.04] |
| 10–20¢ | 916 | +13.64¢ | −1.26¢ [−4.16, +1.63] |
| > 20¢ | 279 | +28.30¢ | +2.13¢ [−3.29, +7.56] |

### The control that must fail

The same pipeline (same model probabilities, prints and asks) was rerun 20 times with outcome
vectors shuffled across windows within each UTC day. That keeps each day's winner mix and
destroys the link to the path.

- **No seed passes the bar** (0 of 20). No seed passes the log-loss leg alone. In no seed and
  at no minute does the model beat climatology with a CI excluding zero.
- Model minus climatology, mean over seeds (min..max): +0.234 (−0.085..+0.410) at minute 1,
  +0.594 at 5, +1.388 at 10, +2.741 at 13. With real outcomes the same difference is −0.06,
  −0.34, −0.72 and −1.07. The model's skill is in the outcomes, not in the scoring.
- Taker rule under shuffle: −8.74¢ per contract mean. The highest CI upper bound across seeds
  is −6.39¢ (n 8,834).

### One window by hand

`KXCRYPTOLEAD15M-26OCT062330`: Oct 6, 11:15–11:30 PM EDT, i.e. 03:15–03:30Z. Minute 10 is
03:25:00Z. Model M5 for day 10-07 uses the scalars refit on 09-24..09-30: β 0.5, k 0.85,
σ_p 1 bp, ν 4.

| coin | start minute 03:14 O/H/L/C | A = OHLC/4 | S(10) = close of 03:24 | x (bp) | remaining sd (bp) | model p | last print (age) | ask / bid | settled |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 83948.00 / 83948.01 / 83916.16 / 83930.69 | 83935.715 | 84005.58 | +8.32 | 8.93 | 0.0859 | 0.06 (71 s) | 0.16 / 0.12 | 0 |
| ETH | 2611.20 / 2611.20 / 2610.39 / 2610.63 | 2610.855 | 2607.90 | −11.32 | 10.02 | 0.0002 | 0.01 (50 s) | 0.06 / 0.01 | 0 |
| SOL | 118.14 / 118.16 / 118.08 / 118.15 | 118.1325 | 118.24 | +9.10 | 12.40 | 0.1003 | 0.12 (29 s) | 0.17 / 0.10 | 0 |
| XRP | 1.4613 / 1.4619 / 1.4607 / 1.4615 | 1.46135 | 1.4630 | +11.28 | 12.84 | 0.2236 | 0.32 (24 s) | 0.23 / 0.14 | 0 |
| HYPE | 90.70 / 90.75 / 90.70 / 90.72 | 90.7175 | 90.86 | +15.70 | 16.24 | 0.5900 | 0.54 (8 s) | 0.55 / 0.50 | **1** |

- x_BTC = ln(84005.58 / 83935.715) = 8.32 bp. The remaining sd is the k- and β-scaled 5-min
  covariance times v(600) = 260 s, plus σ_p². Remaining correlations are 0.79–0.85 among BTC,
  ETH, SOL and XRP, and 0.51–0.56 with HYPE.
- The same covariance with 10⁶ plain pseudo-random t paths gives 0.0852, 0.0002, 0.1001,
  0.2231, 0.5914. The stored walk-forward probabilities match the recomputation exactly.
- Market: the prints sum to 1.05 and normalise to HYPE 0.514. Log loss: model −ln 0.590 =
  0.528, market −ln 0.514 = 0.665, mid −ln 0.515 = 0.664.
- Taker rule: only HYPE qualifies (0.590 − 0.55 − fee 0.02 = +0.020). It buys at 0.55 and
  settles at 1: +0.43. On XRP, 0.2236 − 0.23 − 0.02 < 0, so no trade.
- The proxy's end-of-window returns rank HYPE +16.25 bp, ETH −12.45, XRP +4.79, SOL +2.33,
  BTC +1.42. The proxy agrees with the settlement here.
- Reproduce with `python analysis/coinrace/pricing_screen.py hand KXCRYPTOLEAD15M-26OCT062330 10`.

### What this leaves

The registered verdict stands: directional taking against this book fails. The
model is calibrated and beats climatology by a wide margin, yet it does not beat a live quote,
and its disagreements with the book lose money after the spread. The five asks sum to a median
of 1.21–1.25 at the four minutes (3,882 windows), and a 92.45% proxy cannot see the close finishes that decide the remainder.
Questions 2 and 3 (basket, farming fill cost) do not depend on this model and are unaffected.
