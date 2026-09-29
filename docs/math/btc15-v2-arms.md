# BTC15 v2 — price-aware strategy arms

2026-09-28. Iteration 1 of the Bitcoin Up-or-Down harness asked an LLM for `p_up` once
per window and bought the side it favoured **at whatever the ask was**. It lost.
This document says why, what the history of the same contract says would have
worked instead, and what now runs.

## Why iteration 1 lost

Live record, 2026-09-28 01:00Z–19:00Z (paper):

| | 15-minute | hourly |
|---|---|---|
| fills | 63 | 17 |
| P&L | −$8.74 (then halted by the $10 guard) | +$0.23 |
| Brier: model / market mid / random walk | 0.2448 / 0.2429 / 0.2510 | 0.2433 / 0.2418 / 0.2496 |
| fills that cost more than the model's own probability | 98 % | 94 % |
| mean expected value per fill, by the model's own number | −3.1¢ | −2.5¢ |

The model's probability tracked the market's mid within a few cents and was slightly
**less** calibrated than it. Buying the favoured side at the ask then pays the spread
and the fee on a view the model itself rates as fair or worse. A high hit rate does
not rescue that: the break-even hit rate is the average price paid (≈ 65¢ with the
fee here), and a 76¢ favourite that loses costs as much as three of its wins earn.
The payoff asymmetry is priced in; paying above one's own probability is not.

## What history says (Kalshi KXBTC15M, same contract)

Polymarket US publishes no price history, so the history is Kalshi's `KXBTC15M` — the
same contract on the same BRTI averages — with its per-minute yes bid/ask and trade
range, beside Coinbase's 1-minute Bitcoin prices: **4,263 settled windows,
2026-08-14 → 2026-09-28, 53,084 decision-minutes.** At minute k a rule sees only that
minute's quotes and prices and the 60 minutes before them; features come from
`core/btc15/quant.py`, the module the live arms run. Chronological split: the first
27 days fit anything fitted and choose among configurations; the last 19 days are
read once. Fees at the venue's 0.0695·p(1−p) rounded up to the cent; makers pay none.
Mean P&L per contract with a day-clustered interval.

**The market is the best forecaster in the room.** Its mid beats a driftless random
walk to the settlement average at every minute (Brier 0.2364 vs 0.2396 at minute 1,
0.1168 vs 0.1249 at minute 13). A logistic model on the market's logit, the distance
in volatility units, 1/5/15-minute momentum, a volatility ratio and the time elapsed
puts 0.90 of its weight on the market's own logit and ties it out of sample (Brier
0.1715 vs 0.1711).

| held-out 19 days (1,779 windows) | trades | mean / contract | t |
|---|---:|---:|---:|
| always the favourite at minute 1 (iteration 1's rule) | 1,779 | −3.50¢ | −3.14 |
| random walk, buy only when EV > margin (0 … 10¢) | 391–1,774 | −2.0 … −4.0¢ | −1.1 … −3.0 |
| fitted model, buy only when EV > margin | 12–1,288 | −1.0 … −7.6¢ | n.s. |
| resting bid at the market's own mid − margin (control) | 1,458–1,654 | −1.2 … −2.0¢ | −1.0 … −1.7 |
| resting bid at random-walk or fitted fair − margin | 442–1,464 | −0.8 … −3.5¢ | up to −2.9 |

**Selection does not survive.** Of 72 configurations (probability × taker/maker ×
margin × timing), the five best on the first 27 days (train t +1.1 … +1.4) are all
negative on the last 19 (−0.75 … −2.2¢). An early read on 10 days had shown a random-walk
maker at +9.7¢; it vanished on the full set, which is why nothing was chosen on it.

At minute resolution, on the deeper venue, public price features carry no edge net of
costs, and resting orders lose to adverse selection. Two things the history cannot
see: **speed** below the minute, and **the venue against Kalshi** — no Polymarket
history exists. The live ledger has one hint on the second: at iteration 1's 71
decision instants Kalshi's same-window mid was slightly better calibrated than the
venue's (Brier 0.2440 vs 0.2457), the two differed by more than 5¢ in 32 windows, and
buying on the venue whenever Kalshi's mid cleared the ask and fee by 2¢ would have made
35 trades for +$1.55. Those quotes were read up to 10 s apart, so part of that gap can
be timing; the arms read both venues in the same tick.

## What runs now

Every window, beside the model's own call (kept as the control `favourite`), each
**arm** watches the same book every 3 s and keeps its own ledger and $10 allocation
(`core/btc15/arms.py`; probabilities from `core/btc15/quant.py`, the same code the
backtest ran):

| arm | probability | execution | margin |
|---|---|---|---:|
| `favourite` | the LLM | iteration 1: buys the favoured side at the ask (control) | — |
| `kalshi_taker` | Kalshi's mid on the same window, same tick, spread ≤ 3¢ | buys at the venue's ask | 2¢ |
| `kalshi_taker_wide` | the same | buys at the venue's ask | 4¢ |
| `kalshi_maker` | the same | rests a zero-fee bid | 1¢ |
| `llm_taker` | the LLM, within 60 s of its answer | buys at the ask | 2¢ |
| `llm_maker` | the LLM | rests a zero-fee bid | 2¢ |
| `mid_maker` | the venue's own mid, side by a coin keyed on the window (control) | rests a bid from minute 5 | 2¢ |

The hourly instance runs `llm_taker`, `llm_maker` and `mid_maker` (Kalshi lists no
hourly twin). The fitted model's coefficients (`core/btc15/quant_coef.json`, refitted on
all 46 days with their provenance) are shown to the LLM as a baseline; no arm trades
on them, because they lost out of sample.

A taker buys the better side at its ask the first second
`p_side − ask − fee > margin`, never otherwise. A maker rests one zero-fee bid below
fair value (the venue charges makers nothing) and is filled only when the book trades
**through** its price by a tick; it is cancelled 90 s before the close. At most one
contract per arm per window; a window an arm declines is recorded as `no_edge` or
`expired`, so not trading is data. Paper fills from polled touches miss brief crosses,
which under-counts fills and over-weights the adverse ones — the conservative
direction.

The model now sees the fitted model's probability as a baseline and is told that a
probability which repeats the market never trades.

## Iteration 3 — the LLM trades for itself (2026-09-28, evening)

The operator's example ran Astra as the decision-maker and profited; iteration 1 did
not run it that way. Measured: its reasoning effort was left blank, and across 111
decisions the model spent **at most 71 thinking tokens** (mean output 240 tokens) —
it answered without reasoning. It was also never allowed to decline or to choose a
price: the harness bought its favourite at the ask every window.

The `llm_agent` arm changes the approach rather than the gate:

- **The model reasons.** Decisions run at high effort (measured on a live prompt:
  ~350 thinking tokens, ~15 s, ~$0.08 a call; extra-high: ~920 tokens, ~31 s, ~$0.11).
  Lessons run at low effort.
- **The model decides the trade.** It sees the live book on both sides, Kalshi's price
  for the same window, the fee rules (taking pays 0.0695·q·(1−q); resting pays nothing
  but fills when the market moves against it), the 45-day finding that the market is
  hard to beat, and its own trading record. It answers `buy_up`, `buy_down` or `pass`,
  with `limit_price`, the most it will pay. At or above the ask it takes; below it
  rests; a pass costs nothing and is recorded.
- **A second look.** A first-look pass is asked once more at minute 6 of a 15-minute
  window (minute 30 of an hour), when the picture is clearer, if at least 3 minutes
  remain and the day's budget allows.
- **Budget.** $15/day for the 15-minute instance, $5/day for the hourly one; the
  prompt is trimmed to the last 12 calls and 8 lessons.

It runs beside every other arm on the same windows, so its record is compared with
Kalshi's price, the model's probability used mechanically, and the controls.

## The checkpoint, agreed with the operator 2026-09-29 20:05Z, written before it is reached

Standing at 20:02Z (15-minute arms since 2026-09-28 19:37Z, ~99 windows; the agent
since 04:50Z, 62 windows):

| arm | trades | mean / contract | t |
|---|---:|---:|---:|
| llm_agent | 10 | +34.1¢ | +2.4 |
| kalshi_taker_wide | 91 | +4.5¢ | +0.95 |
| kalshi_taker | 95 | −0.5¢ | −0.1 |
| llm_taker | 76 | −1.5¢ | −0.3 |
| llm_maker | 73 | −5.7¢ | −1.1 |
| kalshi_maker | 82 | −7.9¢ | −1.6 |
| mid_maker (control) | 72 | −13.0¢ | −2.7 |

Everything keeps running unchanged (budgets $15/day 15-minute, $5/day hourly). The
read is taken once, when **llm_agent has 40 settled trades** and **kalshi_taker_wide
has 300**, whichever comes second; neither is read for a go/no-go before then:

- An arm is a **live candidate** only if its mean P&L per contract is positive and its
  t is at least 2.0 on those trades **counted from this checkpoint's standing onward**
  (the trades above chose the arms and cannot also confirm them), and its return on
  staked is positive over the whole run.
- The maker arms are switched off at the read unless one of them meets the same bar.
- Seven arms are running, so one of them clearing t = 2 by luck is not rare; a
  candidate goes live at the smallest size the venue allows, never as a sized bet.

## Margin sweep and the joint quote tape (2026-09-29 21:45Z)

The Kalshi taker now also runs at 3¢, 5¢, 6¢ and 8¢ beside 2¢ (`kalshi_taker`) and 4¢
(`kalshi_taker_wide`), each with its own ledger and $10; they cost no API. They are
exploratory: the checkpoint above still counts `llm_agent` and `kalshi_taker_wide`
only. Six margins read on the same trades would crown one by luck, so the margin is
chosen from the **joint quote tape** instead: every arms tick (3 s) the harness writes
the venue's touch and Kalshi's same-window touch to `quotes` in the model's ledger, and
`analysis/btc15/replay_kalshi_margins.py` replays the live rule (same `quant.edge`, same
Kalshi-mid rule, first qualifying tick per window, one contract at the ask plus fee) at
1¢…10¢, ranks margins on the earlier days and reads the chosen one once on the later days.
