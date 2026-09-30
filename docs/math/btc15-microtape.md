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
