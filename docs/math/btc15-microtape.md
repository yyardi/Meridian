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
