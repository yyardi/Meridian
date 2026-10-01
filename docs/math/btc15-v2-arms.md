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

## The edge on the tab (2026-09-30)

The Strategies table and the "Edge per contract" chart show each arm's **realised edge**.
That is the mean P&L per settled contract (payout − price − fee), in cents, with a 95 %
interval of ±1.96·sd/√n. The trades are treated as independent: one contract per window,
and the windows do not overlap. Beside it is the **edge claimed at entry**: p(side) −
price − fee, where p is what the arm traded on (Kalshi's mid for the takers, the model's
own p_up for the agent). The realised edge should converge to the claimed one if the rule
is right. A third column counts fills since the checkpoint, which moved to 05:08:42Z on 09-30 (see
"Fresh quotes" below). This is the
population the read uses; the agent's target is 40 and the 4¢ arm's is 300. The chart
plots the running estimate from each arm's fifth contract. Only the selected arm shows
its band, and a narrowing band means the estimate is settling.

Standing at 2026-09-30 02:00Z, all contracts. **Every number in this table was priced off two
REST quotes that update only every ~25–30 s; see "Both quotes are stale" below. None of it is
executable evidence until that is fixed.**

| arm | n | realised edge (95 %) | claimed at entry |
|---|---:|---:|---:|
| llm_agent | 14 | +30.6¢ (+6.3, +55.0) | +4.1¢ |
| kalshi_taker_4c | 115 | +5.5¢ (−2.7, +13.7) | +7.8¢ |
| kalshi_taker_2c | 119 | +1.7¢ (−6.5, +9.8) | +5.6¢ |

The tab renames two arms. `kalshi_taker` is shown as `kalshi_taker_2c` and
`kalshi_taker_wide` as `kalshi_taker_4c`, to match the margin sweep. The ledger files, the
API's `arm=` key and the checkpoint rule above keep the original names.

## Both quotes are stale (2026-09-30 02:16Z)

`analysis/btc15/quote_freshness_probe.py` read three quotes once a second for the 02:15Z window.
It got 97 samples with a venue book:

| source | used by | distinct states in 97 s | unchanged for |
|---|---|---:|---|
| Kalshi `/markets/<t>/orderbook` | nothing yet | 97 | changes every second |
| Kalshi `/markets` list touch | the Kalshi arms' p, the quote tape | 3 | mean 32 s, longest 58 s |
| venue `/v1/markets/<slug>/book` | every arm's entry **and paper fill** | 4 | mean 24 s, longest 30 s, sizes identical to the cent |

What this does to the record:

- **The Kalshi arms' anchor is a price up to a minute old.** On the same samples, the list
  mid and the order-book mid differed by a median of 4¢ (p90 12¢). "Kalshi's mid" in every
  arm, in the quote tape and in `replay_kalshi_margins.py` is the list touch.
- **Paper fills are at a price that may not have existed.** A book whose sizes do not change
  for 30 s while Kalshi's changes every second looks like a cached read, not a quiet market.
  The venue's stream is the test of that, and it has not been run on BTC. If the book is
  cached, a fill at the cached ask after Bitcoin has moved is a look-ahead, and it flatters
  whichever side the move favoured.
- **Artefacts of the same staleness in `analysis/btc15/kalshi_side.py`** (tape 21:45Z–01:45Z,
  16 windows):
  - After a ≥ 3¢ gap, "Kalshi closes 71–78 % of it within 30–60 s, the venue 31–34 %". That
    is the list catching up.
  - A locked pair (YES on one venue, NO on the other) priced below $1 after both fees on
    24 % of ticks. On Kalshi's live order book the positive locks in the probe fell exactly
    where the venue's REST book was frozen.
- **What stands:**
  - The two contracts settle alike: 198 of 198 windows from 09-28 00:30Z to 09-30 01:45Z
    gave the same result on both venues.
  - Kalshi's order book is deep: thousands of contracts at the touch.

Until the arms read the venue's stream and Kalshi's order book, the table above measures the
rule against stale prices, and the checkpoint cannot be read on it.

## Fresh quotes, and the checkpoint moves (2026-09-30 05:08:42Z)

The cause is confirmed in the venue's own headers: `/v1/markets/<slug>/book` is served with
`cache-control: public, max-age=30` and `cf-cache-status: HIT`. From the restart at 05:08:42Z:

- **The venue's book** comes from its market-data stream (`core/btc15/stream_book.py`, the
  sports recorder's `StreamConnection` subscribed to the window in play). With the stream
  configured, a tick whose book is not the stream's (socket down, or no book yet for the
  window) enters nothing, fills nothing and writes no tape row. The cached REST book is never
  a fallback.
- **Kalshi's touch** comes from `/markets/<t>/orderbook` (best YES bid; ask = $1 − best NO
  bid). An unreadable or one-sided book is no touch, never the list's.
- **First minutes live:** 32 tape rows in 2 minutes. The stream's sizes changed every few
  seconds, and Kalshi's order-book touch sat within a cent of the venue's, where the stale
  pair had shown gaps of 4¢ at the median. The Kalshi arms will fire less.
- **The checkpoint counts fills from 05:08:42Z.** Every earlier fill was entered and priced
  on a quote up to ~30 s old. Settlements were always the venue's own, so wins and losses
  are real; only the prices are suspect, and staleness flatters a paper fill. The targets
  stand (agent 40, `kalshi_taker_4c` 300), counted from here. The earlier record stays in
  the "all" columns for reference and is not evidence either way.

## Message-driven arms and a re-quoting maker (2026-09-30 ~16:30Z)

Every claim below names how to check it.

**Measured on the live tape (`quotes` in the model's ledger, one row per main-loop pass since
the 05:08:42Z fix; 8,363 tick pairs over 41 windows). The pass is scheduled every second but
measured at a median gap of 3.63 s (p90 4.11 s) from 05:08Z to 16:20Z and 1.79 s (p90 2.04 s)
since the 16:22Z restart: the loop stalls on REST reads (spot polls, Kalshi's book) and eight
arms' SQLite writes. Reproduce: gaps of `t` in `quotes`. The message-driven path is the only
sub-second one; the second session measured this first and it was re-derived here.**

| what | value | check |
|---|---|---|
| Poly-vs-Kalshi mid gap, same second | median 0.4¢, p90 1.1¢, p99 3.0¢, max 9¢ | `analysis/btc15/kalshi_side.py`, or any SQL over `quotes` |
| ticks with a gap ≥ 6¢ | 2 of 8,703 | same |
| Poly's own mid moving ≥ 6¢ within 10 s | 15.8 % of ticks | same tape |
| lead-lag at 3 s: corr(Kalshi move now, Poly move next) / reverse | +0.049 / +0.004 | `scratchpad/maker_size.py` logic, reproducible from `quotes` |
| the venue's REST book | `cache-control: public, max-age=30`, `cf-cache-status: HIT` | `curl -sD - https://gateway.polymarket.us/v1/markets/<slug>/book -o /dev/null` |
| a two-sided maker at Kalshi mid ∓ 1–3¢, re-priced every 3 s, filled on trade-through | −2.6 to −4.4¢ a fill, 76–80 fills / 41 windows | same script |
| does OUR spot feed lead either book? corr(spot move in the prior 2 s, book's next move) | Poly +0.034, Kalshi +0.022; contemporaneous +0.357; a taker on ≥ $15/$25/$40 spot moves: −4.4 / −0.7 / −2.9¢ at 30 s, −9.6 / −4.9 / −26.2¢ held | `scratchpad/spot_lead.py` logic over `ticks` + `quotes` (8,177 pairs, 41 windows) |
| the last-minute snipe | in the final ~25 s the losing side leaves Poly's book (0.99 / no offer); 4 entries in 41 windows, one a confident loss | `scratchpad/endgame_size.py` logic over `quotes` + `ticks` |

**What two browser tabs show is not a gap.** At 15:58:29Z the Kalshi page read "Up 47¢"
while both live books were 63–66; 47/48 was the book's price at 15:57:52–55. Browsers
throttle background tabs, so the tab not in focus freezes and shows a stale number when
switched to. The dashboard's "This window" panel now prints both venues' live books from the
same tape row, read within the same pass, so this can be checked without a browser tab in
the middle.

**What changed:**

- `kalshi_requote` arm (`core/btc15/arms.py`, kind `requote`): two zero-fee quotes on Poly
  at Kalshi's live mid −2¢ / +2¢, never crossing Poly's book, moved on every price message,
  filled only when Poly trades **through** one of them (the touch crosses by a tick), one
  contract per window, held to settlement. Kalshi leads Poly, so this makes on the laggard
  priced off the leader. At 3-s staleness it lost 2.6¢ a fill to adverse selection; the
  message-driven version cuts the stale window to about a second, and only a live run says
  whether that is enough. Expected value is unknown, not positive.
- The arms act on **every venue book message** (`Harness.on_stream_update`), on the socket's
  thread, using the Kalshi read of the last second (`KALSHI_FRESH_S` = 2.5 s; older is no
  price). The main loop reads Kalshi's order book on each pass (`book_every_s` 3 → 1, a
  pass every ~1.8 s as measured; the `/markets` list is cached 10 s) and writes the tape.
- The seven earlier arms are unchanged and keep running.

**Against the underlying, not the other venue (2026-09-30 ~17:40Z).** A 15-minute Up/Down
contract is a digital option on spot minus strike; if it is ever wrong, it is wrong against
spot, and the question is whether our spot feed sees a move before the quotes do. It does not:
the books move with spot inside the same tape row (corr +0.36) and our feed's prior 2-s move
predicts nothing of their next move (+0.03 / +0.02). Our 1-s four-exchange REST composite is
the laggard: its own 2-s moves are autocorrelated (+0.21), which is what a feed that smears a
move across seconds looks like. A taker on large spot moves loses at every threshold. What this
does not test is a sub-second websocket spot feed, which the second session is adding; the
same correlation at 100–500 ms is the test to run on it, and it is the only speed hypothesis
left.

**Not built, and why:** the last-minute snipe (the book empties first); a Kalshi-side taker
(Kalshi leads, so it would be trading on the laggard's noise); anything on polymarket.com
(different venue, geo-blocked; see below).

## What the public "BTC 15-min" bots actually are (surveyed 2026-09-30)

A read-only survey: web search, `gh search code` for `api.polymarket.us` / `gateway.polymarket.us`,
then 20 repositories cloned and grepped for API hosts, because READMEs were not trusted. Venue
rules were read from the venues themselves.

- **All 13 concrete BTC-15-min bots with hosts in their code trade polymarket.com** (global
  CLOB on Polygon: `clob.polymarket.com`, `gamma-api`, `ws-live-data`; geo-blocked in the US).
  Examples: [Jonmaa/btc-polymarket-bot](https://github.com/Jonmaa/btc-polymarket-bot),
  [aulekator/Polymarket-BTC-15-Minute-Trading-Bot](https://github.com/aulekator/Polymarket-BTC-15-Minute-Trading-Bot),
  [masterputra169/polymarket-btc-15-minutes](https://github.com/masterputra169/polymarket-btc-15-minutes),
  [CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot](https://github.com/CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot),
  [defi-ape/polymarket-kalshi-arbitrage-bot](https://github.com/defi-ape/polymarket-kalshi-arbitrage-bot).
  The global venue settles BTC-15m on a Chainlink 60-s TWAP (since 2026-08-07); the US venue
  and Kalshi settle on the same BRTI 60-print average (the venue's own market text, and
  Kalshi's rules). A global-vs-Kalshi "arb" is therefore two different indices and strikes;
  US-vs-Kalshi is the same contract on two books, which is what this harness reads.
- **Of ~30 repositories touching the US venue, none is a public BTC-15-min bot trading it
  live.** The closest is [pisano18/kals](https://github.com/pisano18/kals): a Kalshi
  KXBTC15M taker bot with a dry-run Polymarket US order path and one manual fill. Its
  reconciled Kalshi ledger is **−$469 on KXBTC15M since 09-17**. Its claim that the US venue
  had "126 of 269 windows with zero trades" came from a REST read, and REST here is a 30-s
  cache: **measured on the venue's own TRADE stream** (docs/math/btc15-microtape.md, 17:18–
  18:22Z, a volatile US afternoon hour), the five 15-minute windows printed 2,510–7,014 trades
  and 154k–245k contracts each, zero windows with zero prints. That is a rate for that hour;
  the night's tape gives the day.
- **No source shows a verifiable Polymarket BTC-15-min P&L.** The viral figures
  ($313 → $438k; $50 → $280k) trace to dashboard screenshots and a tweet. The most careful
  dry run (masterputra169, 448 trades) concludes "neither model beats the market price".
- The Poly-vs-Kalshi "arbitrage" repos are a one-leg directional rule (Kalshi YES at 93–96¢
  and Poly ≥ 10¢ cheaper → buy Poly), not a hedge, on the global venue, with no ledger.

**Fees, from [docs.polymarket.us/fees](https://docs.polymarket.us/fees) (effective 2026-09-25):**
taker Θ = 0.0695; **maker rebate Θ = −0.0125**, applied at the trade; both rounded to the
nearest cent by banker's rounding. `core/fees.py` books the maker at zero (no rebate) and
`core/btc15/quant.fee` rounds the taker fee **up**, so the harness overstates its own costs by
up to 1¢ at prices ≤ 7¢ or ≥ 93¢ and by the rebate on every maker fill. Both errors are in the
conservative direction and are left as they are. The same page announces the table-tennis
taker coefficient becoming 0.10 at 23:59 ET on 2026-09-30.

## The Kalshi takers are retired (2026-09-30 ~17:30Z, the operator's call)

All six (2/3/4/5/6/8¢) are off. On live books they made 3/2/2/1/1/0 trades in 41 windows: the
same-second gap they need (fee plus margin, 4–10¢) occurred on 2 of 8,703 ticks. The gap they
traded before the 05:08Z fix was the venue's 30-second REST cache. Their ledgers are kept
under `retired/`. The checkpoint's `kalshi_taker_wide` target is void with them; the agent's
40 stands. What runs: `llm_agent`, `kalshi_requote`, and the print-judged `touch_maker` and
`touch_maker_k` from the sub-second build (docs/math/btc15-microtape.md), whose fills accrue
on flow rather than on a gap and are scored by 60-second mark-outs as well as settlement.

## The spot trigger: interim split, the A/B, and what waits for the read (2026-09-30 ~20:45Z)

The registered toxicity instrument (`analysis/btc15/maker_fill_toxicity.py`, the second
session's; threshold registered before the night: $10 over 500 ms, 60-s mark-out, read once
at 2026-10-01 12:00Z), run on a read-only snapshot at 20:21Z. **An interim look at n = 36,
not the read**, recorded because it was looked at:

| 60-s mark-out, maker fills 17:18–20:21Z | n | mean | t |
|---|---:|---:|---:|
| spot moved ≥ $10 against us within 500 ms before the fill | 16 | −8.4¢ | −2.7 |
| the rest | 20 | −2.5¢ | −1.0 |
| (250 ms) spot-preceded / the rest | 15 / 21 | −10.2¢ / −1.5¢ | −3.3 / −0.6 |

That is the registered shape: the losses sit in the fills that followed a spot move, the
rest is around zero. Two things follow, and one caution.

**The build (the second session's, on `btc15/edge-arms`; nothing deploys before the read).**
A maker arm with a spot trigger: on the Coinbase socket's own thread, the move over the prior
window is computed on every quote; when it clears the threshold the arm pulls the
**threatened** side only (an up-move threatens the offer, a down-move the bid), so the other
side keeps its place in the queue; a pulled side cannot be filled by prints or a trade-through;
it re-joins once the venue's book has re-priced a tick in the move's direction, or after two
seconds. Two variants were designed independently (this session's pulled both sides and
re-joined once spot had been calm for the window); the threatened-side, socket-thread version
is the better one on latency and on queue position, and is the one built.

**The A/B.** Two new arms, `touch_maker_t` and `touch_maker_kt`, identical to `touch_maker`
and `touch_maker_k` but for the trigger, run beside them on the same windows and books. The
controls are untouched. The difference between each pair's record, fill by fill, is the
trigger's value; nothing else differs.

**Caution.** "The rest" is −2.5¢ (t −1.0), not positive: removing the spot-preceded fills does
not by itself make the join arm profitable on this sample; it removes the identified loss and
leaves what a resting order at the touch earns on flow that is not informed, which the night
measures. And at n = 36 the split is one look; the read at 12:05Z decides.

## The read (2026-10-01 13:15Z): the trigger does not deploy

The registered read of the night (`analysis/btc15/maker_fill_toxicity.py`, $10 over 500 ms,
60-s mark-out, fills 17:18Z–12:00Z, read once), run on a fresh read-only snapshot; the second
session ran it independently at 13:20Z on its own snapshot and got the same numbers within
noise (−4.9¢ n 51 vs −3.5¢ n 125).

| 60-s mark-out, 15-minute maker fills | n | mean | t |
|---|---:|---:|---:|
| spot moved ≥ $10 against us within 500 ms before the fill | 49 | −5.0¢ | −3.0 |
| the rest | 119 | −3.4¢ | −3.8 |
| difference | | −1.6¢ | −0.9 (Welch) |
| by fill type: trade-through / print | 113 / 71 | −5.1¢ / −1.0¢ | |

The gate required the rest to carry no loss. It carries most of it: the interim split at
n = 36 (−8.4¢ vs −2.5¢) was sampling noise that regressed to a loss everywhere, and the split
that is real is by **fill type**, not by spot. A resting order at the back of the touch queue
fills on sweeps (−5.1¢) and rarely on benign flow (−1.0¢), which is the queue-position
mechanism the continuous-making replay found (docs/math/btc15-microtape.md). The spot
trigger would remove about three in ten fills and a quarter of the loss and leave a
3.5¢-a-fill loser. **Not deployed.** `touch_maker_t` / `touch_maker_kt` moved out of
`DEFAULT_ARMS` into an unrun `SPOT_TRIGGER_AB` tuple; the spec options stay.

With this, every channel on Polymarket US BTC-15m is measured non-positive for this stack:
directional (the market beats the walk, the logistic and the LLM), cross-venue (the
same-second gap to Kalshi is 0.4¢), passive making (adverse-only at the back of the queue),
priority making (first at a new level earns the rebate and nothing else), and the final
minute (priced within seconds on both venues). The four arms keep accruing at zero cost; the
instrument stays.

Also from the snapshot: the venue listed **no 15-minute windows from 10:00Z to 11:59Z** on
2026-10-01 (no `windows` rows for 1000z–1145z, the hourly bot's stream at zero in the same
hours, zero prints, the 1100z book still 404). The bot logged nothing and resubscribed at
12:00Z. A fill drought across every arm at once is a venue question before it is an arm one.

## The hourly A/B (2026-10-01 ~16:25Z): the trigger's twin runs beside the control on btc1h

The second session replayed one-contract making at the touch (back of the queue, |pos| ≤ 1,
rebate credited; `analysis/btc15/mm_replay.py`, now with `--spot-from` because the hourly
tape carried no spot) on the night's tapes: 15m, 71 windows, −43.8¢ ± 6.7 a window plain and
−29.1¢ ± 5.9 with the trigger; **1h, 19 windows, −16.1¢ ± 11.6 plain and −0.5¢ ± 10.3 with
the trigger** (7.8 trade-throughs a window against 20 on the 15m). A replay over recorded
tapes is not a result and is not shown as one; it is used here for the one thing it can do,
choose which configuration to run live. The hourly market is the first maker read that is
not negative, and zero within ±20¢ a window is not money, so the question goes to the live
record at zero cost.

**What runs.** On btc1h, `touch_maker` (the control, unchanged, 23 fills since 09-30
17:18Z) and `touch_maker_t` (identical but for the spot trigger: the threatened side is
pulled when coinbase moves $10 within 250 ms, re-joined when the book re-prices a tick) on
the same windows and the same book messages. Spot sockets are on for the hourly bot from
this restart (the trigger is evaluated on the coinbase socket thread); the hourly tape also
carries spot from here. No model, no credits, paper.

**The registered read, written before any of it exists.** Read once, at the earlier of 60
settled fills on `touch_maker_t` or 2026-10-05 12:00Z, on a read-only snapshot of both
hourly arm ledgers, fills from this restart onward only:

1. Primary, the twin on its own: mean net per window to settlement at the ledger's zero-fee
   maker convention (the −1.25¢ rebate stated beside it, not added), with se and 95% CI,
   n = windows with a twin fill. The twin is a candidate for anything beyond paper only if
   the mean is positive and the CI excludes zero. Zero within the CI closes the hourly
   maker channel as the 15m one is closed.
2. Secondary, the trigger's value: twin − control per window, paired on the windows both
   filled, mean ± se; and per-fill 60-s mark-out, twin vs control, Welch t. No decision rides
   on it except the operator's standing rule: the arm that loses is retired.
3. Stated with every number: n fills, n windows, the restart timestamp, the snapshot path.

Deployed by checkout of `docker-compose.btc15.yml` and a recreate of btc1h alone; the
15-minute bot is untouched.

