# BTC15 — the sub-second record, the print-based maker fill, and the loop that no longer waits

2026-09-30. Three defects in the harness's instruments, what replaced them, and the one
speed question the replacement can answer. Nothing here is a result; the arms it enables
are live paper arms and their records accrue in their own ledgers.

## What the once-a-second tape actually was

Measured on the 15-minute ledger (`ticks`, `quotes`; reproduce with any SQL over the
gaps between consecutive `t`):

| period | ticks: median gap | p90 | gaps > 1.5 s | quotes: median gap |
|---|---:|---:|---:|---:|
| 09-28 12–18Z | 1.00 s | 1.82 s | 13 % | — (no arms) |
| 09-30 06–12Z | 1.00 s | 1.12 s | 4 % | 3.68 s |
| 09-30 14–16:20Z | 1.00 s | 1.99 s | 17 % | 3.55 s |
| 09-30 16:22Z– (message-driven deploy) | 1.00 s | 1.11 s | 4 % | 1.85 s |

The loop polled four REST tickers on its own thread with a 2.5-s timeout, so one slow
exchange skipped the composite's next second; the arms' pass read Kalshi's order book over
HTTP and did eight ledgers' sqlite work on the same path, so "one row per second" was one
row per 1.85–3.7 s. My first read of the tape mistook that cadence for the venue's book
being absent 70 % of the time — the book is two-sided at 1c with ~500 contracts a side
through minute 12 (`analysis`: see §"last minute" below).

## What runs instead

- **Exchange sockets** (`core/btc15/spot_ws.py`): Coinbase and Kraken tickers over their
  public websockets, one thread each (verified live 2026-09-30: Coinbase a quote every
  ~9 ms, Kraken every ~650 ms). Bitstamp and Gemini stay on REST, each on its own poller
  thread once a second; a REST poll never overwrites a socket quote fresher than 3 s, and
  an exchange whose socket has been silent 3 s is polled again (the socket reconnects with
  doubling backoff, 1 → 30 s); a quote older than 5 s leaves the median as before.
  `PriceFeed.tick` only reads the latest quote per exchange — it never touches the
  network. `ticks` keeps its meaning: the median mid of the four, once a second, beside `n`.
  **Measured, a 180-s local run with sockets and no arms** (`ticks` gaps): median 1.004 s,
  p90 1.005 s, p99 1.006 s, max 1.006 s, none over 1.5 s; 179 of 180 ticks had all four
  exchanges. The `quotes` cadence with the arms is a prod measurement, to be written here
  after the first hour.
- **Kalshi on a reader thread** (`Harness.start_kalshi_reader`, every 0.5 s): the cache
  keeps its contract — stamped at the read's start, no price once older than 2.5 s, and
  `kalshi_quote` never fetches inline while the reader runs.
- **The microtape** (`core/btc15/microtape.py`, `<ledger>-microtape.sqlite`): every venue
  book message (`book_msgs`), every print (`trades`: price, quantity, taker and maker
  intent) and every socket quote whose touch moved (`spot`), stamped at receipt on the
  harness's clock, written by one thread from a queue the socket threads never block on;
  rows older than 3 days pruned hourly (`MERIDIAN_BTC15_MICROTAPE_DAYS`). **Growth,
  measured on the same local run:** 409 Coinbase + 145 Kraken deduped rows in 183 s →
  ~261,000 spot rows a day; a vacuumed copy held 126 B a row → ~33 MB a day for spot, so
  under 100 MB resident at 3 days before `book_msgs` (a prod figure, per message).
- **Prints in memory** (`StreamBook.prints`): the window's prints, the fill evidence a maker
  arm reads.
- **Markouts** (`ledger.markouts`): the venue's touch 5, 30, 60 and 300 s after every fill
  in every ledger, from the live book only (a horizon past the close is never asked; one
  missed by a restart is recorded empty once), on their own thread, never in the pass or
  on the arms lock. The table is created on open, so the eight existing ledgers gain it on
  restart. A settlement is a ±50c coin per contract;
  the mid a minute after a fill moves a few cents — this is the low-noise read of what a
  fill was worth, spread capture and adverse selection included.

## The join arms and their fill model

`touch_maker` (prob `mid`, the control) and `touch_maker_k` (prob `kalshi`, margin 1c)
quote both sides at the venue's own touch on every message and re-join it when it moves.
Queue model, stated once: an order placed at price P at t0 stands behind the size displayed
at P at t0. It fills when the prints at P or through it **on its side** since t0 sum to more
than that size, or when the book trades through P. Size arriving at P after us is behind us
and ignored; size that leaves P without printing is not credited. Sides from the venue's own
recorded prints (WNBA, 2026-09-19, each beside the touch before it): a taker `BUY_SHORT` or
`SELL_LONG` prints at the YES bid and fills a resting bid; `BUY_LONG` or `SELL_SHORT` at the
ask fills a resting offer; with the taker undefined, the maker's intent names the resting
side; both undefined counts for neither. The gated arm quotes a side only when Kalshi's mid
is at least 1c better than our price. One contract per window per arm, held to settlement,
fee 0; the venue's maker rebate (docs.polymarket.us/fees, effective 2026-09-25, −0.0125)
is **not** credited. The retired `mid_maker` rested alone and was filled only by
trade-throughs (−13c): these are what joining the market maker's queue earns, judged by
prints.

## The one speed question, and how it is decided

On the 1-s composite the Manager measured no lead over either book (corr +0.03 at 2 s; the
composite's own autocorrelation +0.21 says it smears moves). `analysis/btc15/microtape_leadlag.py`
asks the same at 100–2000 ms on the microtape: the correlation of spot's move over the
prior W ms with the next book message's mid move, the reverse direction, the share of book
messages after a ≥ $10–40 spot move whose displayed book is unchanged since a second before
the move, and a taker at 300 ms reaction marked at the mid 5 s and 30 s on. If every W reads
~0, speed on this venue is closed and that is written once; if it is real, the arm to add is
the `walk` taker keyed on the socket feed. Sizing only; nothing it prints is edge.

## The last minute, re-derived (sizing note, not a result)

45 live windows since the fresh-quote fix. The winner's offer leaves the venue's book 50–90 s
before the close (`0.99 / None`), Kalshi's book goes one-sided ~74 s out, and the market
maker re-prices within one tape row of a spot move. A taker on the partial 60-s settlement
average had n ≤ 14 at every margin and window and every interval spanned zero. Not built.

## The first hour on prod (2026-09-30 17:18–18:22Z), measured

Three restarts inside the hour, each resetting the status counters while the ledgers and the
microtape carried across: 17:18:03Z (this build, 468c981), 17:36:59Z (the Kalshi key; the
relay's first URL was wrong and 404'd on both signed paths, corrected in aacfcb6 — the value
feed is a channel on the one socket at `/trade-api/ws/v2`), 18:04:31Z (1285bb2, below).

**Cadence, four arms on the pass, both bots, gaps of `t` since 17:18:30Z** (the maxima are the
restarts): 15m `ticks` n=3,808 median 1.000 s, p90 1.001, p99 1.001, max 12.0, share > 1.5 s
0.0008; `quotes` n=3,771, 1.000 / 1.001 / 1.001 / 21.0 / 0.0021. Hourly the same to the
millisecond. The tape was 3.6 s a row this morning and 1.76 s after the 16:22Z deploy.

**Growth, from the prod files:** 15m microtape 763k `book_msgs`, 503k `trades`, 264k `spot`
(deduped) and 61k `brti` rows a day at this hour's rates; 16.5 MB in 64 min including the WAL,
so under ~370 MB a day and ~1.1 GB resident at 3 days (36 GB free). Hourly: 418k book messages
and 53k prints a day, ~180 MB. The laptop's 33 MB/day was spot alone.

**Sockets from the AWS box:** Coinbase ~350 messages a minute (139 rows a minute after
dedupe), Kraken ~100 (44 rows); zero reconnects on either across the three restarts; the
venue's stream zero reconnects. The venue's stream is a **10 Hz snapshot feed** — book
messages every ~100 ms — so its re-pricing is quantised at 100 ms.

**Prints per window on the TRADE channel** (the measured replacement for a third party's
"126 of 269 windows with zero trades", which came from a REST read; REST here is a 30-s cache):

| window (15m) | prints | contracts | first→last print |
|---|---:|---:|---:|
| 1715z (from 17:18) | 2,510 | 154,335 | 701 s |
| 1730z | 4,240 | 185,482 | 881 s |
| 1745z | 6,051 | 229,000 | 879 s |
| 1800z | 7,014 | 244,734 | 890 s |
| 1815z (first 7 min) | 2,626 | 74,531 | 436 s |
| hourly 1700z | 1,824 | 90,778 | 2,491 s |

Zero windows with zero prints, 5 of 5; a US afternoon during a volatile hour, so a rate for
this hour, not the day. The night's tape gives the day.

**The relay** (Kalshi's `cfbenchmarks_value`, from 17:37Z): 60 ticks a minute, receive minus
CF's calculation time median 0.07 s, zero reconnects. Against the venue, n=1 each so far:
`last_60s_15m` at the close minus `expiration_value` **−$0.25**; `avg_60s` at the open minus
`strike` −$0.70; our composite's `proxy_close` on the same windows −$2.27 (n=2, sd 3.78);
composite minus relay value at the same second −$2.34, sd 5.36, max |45|. The relay is the
settlement quantity to within a quarter dollar on one window; n accrues every quarter hour
(`analysis/btc15/brti_relay_check.py`).

**A defect the first 40 minutes showed** (fixed in 1285bb2, zero errors since 18:04:31Z):
`sqlite3.InterfaceError: bad parameter or other API misuse` three times on the 15m bot and
twice on the hourly, all from `ledger.decision()` on the model's ledger — one connection shared
by the main loop, the stream thread and the new markout thread, with only writes under the
lock. Every statement is under it now; a three-thread hammer test raises without the lock and
passes with it. Each collision had cost one pass (once a whole main-loop second), never the
process.

**Every maker fill of the hour, with its queue evidence** (fee 0; markouts are the venue's mid
at the horizon minus the price paid, in the side's own terms; n=4 per arm, nothing to conclude):

| arm | window | side @ price | filled by | 5 s | 30 s | 60 s | 300 s | settled |
|---|---|---|---|---:|---:|---:|---:|---:|
| kalshi_requote | 1730z | YES 0.41 | through | −0.5 | −10.5 | −11.5 | −32.5 | −41c |
| kalshi_requote | 1745z | YES 0.81 | through | −9.5 | −17.5 | −9.5 | −2.5 | +19c |
| kalshi_requote | 1800z | YES 0.58 | through | −6.5 | −9.5 | −24.5 | −27.5 | −58c |
| kalshi_requote | 1815z | NO 0.57 | through | +5.5 | +6.5 | +12.5 | +24.5 | open |
| touch_maker | 1730z | NO 0.60 | prints 240 > 170 ahead | −0.5 | −2.5 | +14.5 | +28.5 | +40c |
| touch_maker | 1745z | NO 0.53 | prints 159 > 90 ahead | +0.5 | −1.5 | −9.5 | −39.5 | −53c |
| touch_maker | 1800z | NO 0.40 | through | +0.5 | +8.5 | +17.5 | +24.5 | +60c |
| touch_maker | 1815z | NO 0.55 | through | +3.5 | +5.5 | +4.5 | +10.5 | open |
| touch_maker_k | 1715z | NO 0.73 | prints 541 > 233 ahead | −0.5 | +9.0 | +13.5 | +23.5 | +27c |
| touch_maker_k | 1730z | YES 0.41 | through | −0.5 | −10.5 | −11.5 | −32.5 | −41c |
| touch_maker_k | 1745z | YES 0.47 | prints 336 > 150 ahead | −1.5 | +1.5 | +9.5 | +39.5 | +53c |
| touch_maker_k | 1800z | YES 0.55 | through | −3.5 | −6.5 | −21.5 | −24.5 | −55c |
| touch_maker_k | 1815z | NO 0.57 | through | +5.5 | +6.5 | +12.5 | +24.5 | open |
| hourly touch_maker | 1700z | YES 0.34 | through | −1.5 | +0.5 | −4.5 | −17.0 | −34c |
| hourly touch_maker | 1800z | NO 0.50 | prints 59 > 50 ahead | 0.0 | +5.5 | +9.5 | +12.5 | open |

What the table can already say: the requote arm's four fills are all trade-throughs and its
markouts are negative at every horizon on three of them (the control's behaviour, as sized);
the join arms' fills split between print-fills and through-fills, and the through-fills are
the ones with the 60-s markouts of −10 to −22c. The registered read
(`analysis/btc15/maker_fill_toxicity.py`: $10 over the 500 ms before the fill instant, 60-s
markout) runs on the night's tape, not on fifteen fills. The lead-lag instrument's 4-minute
smoke test on this tape read corr +0.31 between spot's move over the prior 250 ms and the next
book message's mid move (+0.17 at 2 s; reverse +0.08–0.14) — a schema check on one window
during a 20c drop, not a result.

## The spot trigger, built before the read and switched on only by it (2026-09-30 evening)

An interim look at three hours of the tape with `maker_fill_toxicity.py` (36 maker fills; the
registered read is the night's, at 12:05Z): the join arms' 60-s markouts were −8.4c (n=16,
t −2.7) on fills preceded by a ≥ $10 coinbase move within 500 ms and −2.5c (n=20, t −1.0) on
the rest; at 250 ms, −10.2c (n=15) against −1.5c (n=21). The lead-lag instrument on the same
three hours (91,500 book messages): corr(spot's move over the prior 250 ms, the next book
message's mid move) +0.30, +0.23 at 500 ms, +0.12 at 2 s; reverse +0.15 at 250 ms; a taker
reacting 300 ms after a ≥ $10 move marks −1.95c at 5 s (n=419, t −10) — the round trip — so
the lead is worth nothing to a taker and something to a maker whose quote stands stale for
those milliseconds.

The trigger (`ArmSpec.spot_pull_usd`, `core/btc15/arms.py`): on every coinbase socket quote,
on the socket's thread, the harness computes spot's move over the prior `spot_pull_ms`
(250) from a ring of mids and, when it clears `spot_pull_usd`, pulls the threatened side of
each triggered join arm under the arms lock without blocking (a miss is counted in
`spot_trigger_counts.lock_missed`) — the offer on an up-move, the bid on a down-move, so the
other side keeps its queue place. A pulled side is filled by neither prints nor a
trade-through; it re-joins once the book has re-priced a tick in the move's direction or
after `spot_repost_s` (2 s). It runs as an A/B: `touch_maker_t` and `touch_maker_kt` beside
the untouched `touch_maker` and `touch_maker_k`, so the difference on the same windows is the
trigger's value. `spot_pull_sides="both"` and `spot_rejoin="calm"` exist as options with no
arm on them. Nothing on prod changes until the 12:05Z read confirms the shape on the night's n.

## The final minute off the relay: closed on both venues (2026-10-01 01:40Z, 30 windows)

With the relay's exact partial closing average in hand, the question was whether either venue
still offers the loser once the average has decided the window. A first replay said yes
(+12 to +46c) and was wrong twice over: it chose the side from the result, and it priced the
remaining variance from the median absolute 1-s change of the smoothed index ($0.89) while the
relay's realised moves are fat-tailed — sd $3.9 at 1 s, $12 at 10 s, $26.9 at 60 s, $36 at 2 min.
Redone with the side chosen by p and the realised move curve as the variance (sizing only):

| venue | margin | fired (of 30) | won | mean / contract | median τ, ask |
|---|---:|---:|---:|---:|---|
| Poly | 0.5c | 11 | 7 | −6.3c | 83 s, 0.58 |
| Poly | 2c | 10 | 6 | −6.8c | 84 s, 0.57 |
| Kalshi | 0.1c | 21 | 16 | −6.3c | 86 s, 0.975 |
| Kalshi | 0.5c | 13 | 8 | −10.5c | 85 s, 0.72 |
| Kalshi | 2c | 11 | 6 | −11.8c | 84 s, 0.56 |

Calibration of the relay model over the last 90 s, pooled: where it says 0.6–0.9 the outcome
rate is 0.61–0.68, where it says 0.9–1.0 it is 0.97. The venue's price is the better model of
the partial average, and both venues track it within seconds (raw rows in the scratchpad
`endgame_relay2.py`). Kalshi's book stays two-sided to the last seconds at deci-cent prices
(0.002/0.003 five seconds out, 1915z) where the venue's is one-sided from ~10 s; the size
resting there was not taped — `kalshi_book` in the microtape now records ten levels a side at
every reader pass, so that one number can be read tomorrow. Also checked: the venue serves
BTC up-or-down only (`cpc-eth-/sol-/xrp-updown-15m-…/book` 404 while BTC's answers), so there
is no second asset to run the arms on.

## Continuous making at the touch, sized on the tape (2026-10-01 02:00Z, 31 windows; sizing, not a result)

`analysis/btc15/mm_replay.py`: one contract quoted at the venue's touch on both sides, re-joined
at the back of the queue whenever the touch moves, filled by prints beyond the size ahead or by
a trade-through (the arms' model), position capped at ±1, inventory settled at the result, the
venue's maker rebate (0.0125·p(1−p)) credited per fill — the live ledgers book it at zero.

| | fills / window | of which trade-throughs | net / window | with the rebate | adverse selection at 60 s |
|---|---:|---:|---:|---:|---:|
| touch maker | 74 | 27 | −74c ± 12 | −55c ± 11 | −29c |
| with the spot trigger ($10 / 250 ms) | 67 | 22 | −53c ± 11 | −36c ± 10 | −25c |

At ~5,000 prints a window a passive quote at the back of the touch queue fills every ten to
fifteen seconds, and loses on average: the fills come when the market is moving through the
level (a third are trade-throughs) and the half-spread earned on the rest does not cover the
move that follows. The trigger removes about a third of the loss, not the sign. This is the
tape's answer to "does market making print here"; the A/B arms give the live one, one contract
a window, from the first restart after the 12:05Z read.

## The priority race: first at the new level before the market maker (2026-10-01 02:40Z; 700 events, sizing)

The back of the touch queue is the adverse-only position (above). The position that could
flip the sign is first in queue at the NEW level the instant spot moves, before the market
maker re-prices. `analysis/btc15/priority_race.py` on 31 windows, 700 coinbase moves of
≥ $10 within 250 ms (one event per 5 s), 578 of which the venue re-priced within 30 s:

| | |
|---|---|
| coinbase quote → first re-priced book message | median **77 ms**, p25 39, p75 170, p90 2,708 ms (10 Hz snapshots: 100 ms resolution) |
| re-price moved both sides in one message | 450 of 578; one side first 128, the other following after a median 104 ms |
| a post at 50 / 100 / 200 / 300 ms after the coinbase quote precedes the re-price | 69 % / 35 % / 22 % / 19 % (an upper bound on being first) |
| first in queue at the new level, filled by the first opposite print before the level moved | 242 of 578 levels (level life median 200 ms) |
| markout of those fills, 30 s / 60 s | +0.01c ± 0.52 / +0.02c ± 0.69; **+0.22c / +0.23c with the rebate** |
| the first opposite print at the level | median 12 contracts (p25 3, p75 39); total opposite flow while the level stood median 101, mean 516 |

Two things bound it. With a one-tick spread the new bid level is the old ask, so a bid there
crosses the resting offers unless they have already left — only the one-sided fifth of
re-prices, for ~100 ms — or it is a taker fill, which is the −2c measured above. And the
first-in-queue fill earns nothing before the rebate: the markout is zero to half a cent, and
the rebate is 0.2c a contract. At the flow sizes seen (median 101 contracts hit the level
while it stands) that is ~20c an event, ~7 events a window, won in perhaps a third of the
races from AWS: tens of dollars a day on a real order engine with inventory on every event.
The latency race is measured, not lost; the prize at this venue's spread and rebate is not an
arm. Closed as such; the one-contract A/B remains the live read of the join arms.

## The registered read (2026-10-01 13:20Z, the night from 17:18Z: 20 h, 71 windows)

Read once, as registered on 2026-09-30 17:25Z (`analysis/btc15/maker_fill_toxicity.py`: X = $10
over the 500 ms before the fill instant, 60-s markout primary). Population: every fee-0 fill
of touch_maker, touch_maker_k and kalshi_requote on the 15m bot (176 fills with a spot read)
and the hourly touch_maker (18).

| 15m, markout | spot moved ≥ $10 against us within … before the fill | the rest |
|---|---|---|
| 60 s, 250 ms | n=49, **−5.5c**, t −3.4 | n=127, **−3.3c**, t −3.8 |
| 60 s, 500 ms (registered) | n=51, **−4.9c**, t −3.1 | n=125, **−3.5c**, t −4.0 |
| 60 s, 1000 ms | n=54, −4.9c, t −3.3 | n=122, −3.4c, t −3.9 |
| 30 s, 500 ms | n=51, −4.4c, t −3.8 | n=125, −2.9c, t −4.4 |

Hourly: 1 fill spot-preceded (−6.5c) against 17 (−0.9c, t −0.7) — nothing to read.

**Decision, per the registration:** the condition was that the spot-preceded bucket carries
the negative markouts *and the rest does not*. The first half holds (the bucket is 1.5–2c
worse); the second does not — the rest is −3.5c at t −4. The trigger would remove about three
in ten fills and a quarter of the loss and leave a maker that loses 3.5c a fill. It is not
switched on: `touch_maker_t` and `touch_maker_kt` come out of the default arms before they
ever run (the spec options stay, tested, for a future A/B with a different quote). This
agrees with the continuous-making replay (−36c a window with the trigger and the rebate) and
with the priority race (the prize at this spread is the rebate).

**The rest of the night, same tape:**

- **Spot → book lead-lag** (520k book messages): corr +0.25 at 100 ms, **+0.29 at 250 ms**,
  +0.22 at 500 ms, +0.16 at 1 s, +0.11 at 2 s; reverse +0.13 at 250 ms. A taker 300 ms after a
  ≥ $10 move: **−2.1c at 5 s (n=1,887, t −22), −2.4c at 30 s (t −12)**; after ≥ $40 moves,
  −3.2c (n=41). Speed as a taker on this venue is closed, with power.
- **The relay is the settlement number:** `last_60s_15m` at the close minus `expiration_value`
  −$0.07 ± 0.24 (n=4); `avg_60s` at the open minus `strike` −$0.06 ± 0.40 (n=69); our
  composite's `proxy_close` −$3.76 ± 3.07 (n=70) — its bias drifted from −$2.1 to −$3.8 over
  the day. Receive minus CF calculation time 80 ms; 70,739 ticks, one socket close, zero gaps
  over 3.3 s.
- **Prints per window:** 15m median 5,045 prints and 220k contracts (p10 2,865, p90 6,440),
  **1 window of 71 with zero prints** (the venue's mid-morning UTC board gap, STATUS §0d);
  quietest hours 09–13Z (1,100–2,600 a window). Hourly median 2,954 prints, 85k contracts,
  1 of 19 with zero.
- **Fill audit** (`taker_fill_evidence.py`, maker fills included): 85 fills with a print at
  the price on our side, 99 where prints had gone through the display before the fill instant,
  9 with no print, 2 without a book message.

Every channel on this venue's BTC 15-minute market is now measured for this stack and none
prints: directional and cross-venue (STATUS §0cl, docs/math/btc15-v2-arms.md), the final
minute, passive making at the back of the queue, first-in-queue making, and the spot
trigger. The four live arms keep accruing at zero cost as the record; nothing is proposed for
live money.

## Kalshi's last seconds, read off the depth tape (2026-10-01 14:35Z; 5 windows)

The last unmeasured number: how much rests on the LOSER at the last tenths of a cent on
Kalshi's book in the final seconds (`analysis/btc15/kalshi_last_seconds.py` on the
`kalshi_book` tape, running since the 13:21Z restart). In 4 of the 5 settled windows the
losing side had **no resting bid at all** at 10, 5, 3 and 1 s before the close; in the fifth
(1345z) the eventual loser's best bid was 0.80 with 3,146 contracts ten seconds out and 0.074
one second out — a window that flipped in its final seconds, i.e. live uncertainty, not a
lottery bid. Dollars resting on sure losers within a cent of zero: **$0 in every window.** The
0.002/0.003 touches seen on 09-30 were the exception, not the rule, and carry no size. Nothing
to sell to; closed. The read is one command and can be repeated on a full day's tape.

## Pending, for the operator

Kalshi relays BRTI itself to any API key — websocket `wss://external-api-ws.kalshi.com/cfbenchmarks_value`,
channel `cfbenchmarks_value`, index `BRTI`, one tick a second carrying `avg_60s_data` (the
trailing 60-s mean) and `last_60s_windowed_average_15min` (the settlement average, in the
final minute) — which is the quantity our four-exchange composite proxies with a −$2.10 bias
and $3.34 sd against `expiration_value` (241 windows). The handshake is RSA-PSS signed
(`KALSHI-ACCESS-KEY`, `-TIMESTAMP`, `-SIGNATURE` over `{ts}GET/trade-api/ws/v2`), so it needs
a Kalshi API key. *(Done 2026-09-30 ~17:30Z: the operator added `KALSHI_API_KEY_ID` and
`KALSHI_PRIVATE_KEY_B64` to `.env`; the relay has run since 17:37Z — see the first-hour section.)*
The client is built and tested against the documented message shape
(`core/btc15/brti_relay.py`; 15-minute bot only): with `KALSHI_API_KEY_ID` and
`KALSHI_PRIVATE_KEY_PATH` (a PEM file, mounted read-only) in `.env` and a recreate, every tick
lands in the microtape's `brti` table beside the composite, and the status file shows the
relay's counters. The path the value host expects in the signature is undocumented (the trade
socket signs `/trade-api/ws/v2`); the URL's own path is signed by default and
`KALSHI_WS_SIGN_PATH` overrides it — the first live handshake says which. With it, the
settlement proxy becomes the venue's own number. Nothing trades on it until it is recorded
beside `expiration_value` and the error measured.
