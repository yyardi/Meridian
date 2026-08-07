# The fill watcher and pre-authorized exits

*One topic: how the system learns what happened to a real order, and the one
kind of order it may send without a click. Added 2026-08-05.*

## Why it exists

"Accepted" and "filled" are different events, and until this the `orders`
table only recorded the first. Orders #1–3 read `accepted=True` while a human
cancelled two of them in the venue's app (V17) — the table had no way to know.
And the attached exit (below) needs a trigger: "when the entry fills" is a
fact only the venue can report.

## What it does

A background thread inside the API process — the only process that places
orders, so the read-back loop lives next to the write path. Every 60 seconds:

1. `GET /v1/portfolio/activities` and `GET /v1/portfolio/positions` — two
   requests a minute, ~1% of the ~5 req/s throttle on the authenticated host
   (V12).
2. Every accepted order with a venue order id gets a venue-truth
   `fill_status`: `FILLED / PARTIAL / OPEN / CANCELLED / EXPIRED`, plus
   `filled_quantity`. `NULL` means "never reconciled", which is a different
   claim from `OPEN` ("reconciled, confirmed resting") — the book-tier lesson
   applied to orders.
3. Pending exits whose entries reached a terminal state are acted on (below).
4. A `fill_watcher` heartbeat is upserted (B11 rule: silence must be loud).
   `/api/status` judges it only on hosts where ordering is enabled — the same
   token gate the order endpoint fails closed on — and `scripts/health.py`
   judges it whenever there is anything to reconcile.

**Attribution is by venue order id only.** The account also contains hand
trades, sometimes in the same market at similar prices. An activity that does
not carry one of our venue order ids is ignored — never matched by market,
price, size, or any similarity, and the positions endpoint is never used to
infer a fill. A position delta cannot distinguish a button order's fill from a
hand trade.

**Payload shapes are the observed ones (V19), and parsing stays defensive.**
An activity that does not match the observed shape is logged
(`fill_watcher_unparsed_activity`) and skipped, never guessed at. If the
dashboard disagrees with the venue's app, read that log line first — it is
the schema-drift alarm.

**Terminal states for orders the activities feed cannot see.** Two verified
gaps (V19): a zero-fill cancel emits no activity ever, and
`POSITION_RESOLUTION` only arrives for markets where we held a position — so
a cancelled or never-filled order would stay OPEN forever on activities
alone. The fallback is the venue's **public settlement endpoint** (no auth,
one call per market, cached forever once settled): an explicit `settlement`
of 0 or 1 means the market is done, the order can never fill, and it goes
EXPIRED. A failed lookup never expires anything — "could not ask" is not
"settled". The same check guards the exit path: an exit whose market has
settled is DELETED, not submitted — a sell cannot execute there, and the
position (if any) pays at settlement. True CANCELLED (human cancels in the
app, market still trading) remains undetectable until settlement; the row
reads OPEN and its exit PENDING, both visible to the human who did the
cancelling.

**Catch-up after downtime.** While the watcher runs, fills land on page one
within a cycle. After an outage it walks up to 10 paced pages (~1000 events);
anything older is caught by the settlement fallback, and a monotonic guard
ensures a fill count never regresses when history pages out (the first live
night: 3 pages was not enough once a slate of settlements landed on top of
the fills, and FILLED orders read OPEN again).

## The attached exit

The ticket gains "then sell at ___", pre-filled with model fair value
(hypothesis #8: the edge is collected when the market reaches the model),
human-editable, deletable. Stored in `pending_exits` at click time; submitted
by the watcher when the entry fills. It is **pre-authorized** in the V18 sense
— every term fixed by the human, only the timing the machine's.

The rules, each load-bearing:

1. **Market slug copied from the entry row at click time**, never re-looked-up
   at submit. A slug lookup at submit time is a chance to sell a different
   market than the one bought.
2. **Price immutable** — sent exactly as typed even if the market moved 30¢.
   No chasing, ever. A stale exit is the human's to cancel. (Rules 1–2 are
   why nothing here reads `is_live`: in-game, where prices move 30¢, is the
   target use.)
3. **Exit quantity = venue-reported filled quantity**, never ordered quantity.
   Never oversell. Entry partially filled and still open → the exit *waits*:
   fills may still arrive, and per-slice exits would need amendment logic
   this system refuses to have.
4. **Same outcome side the entry bought**, with the V14 frame conversion
   (`price.value = 1 − cost` for NO) applied **once, at click time**, server
   side. `pending_exits` stores both the typed cost (`typed_price`) and the
   YES-frame `limit_price`; the watcher sends the stored number verbatim.
   Unit-tested on both intents.
5. **Entry cancelled or expired unfilled → exit DELETED**, with a log line
   (`pending_exit_deleted`). Cancelled/expired *with* a partial fill → the
   position exists, so the exit fires for the filled quantity.
6. **One retry on submit failure, then FAILED loudly** — red on the picks
   page's order panel, `pre_authorized_exit_FAILED` in the log, DEAD in
   `scripts/health.py`. Never silently dropped: the human believes that exit
   is protecting them. A definitive venue rejection is not retried (same
   order, same answer) and fails the same loud way.
7. If the *entry* is definitively rejected (or never sent), the exit is
   deleted — nothing to protect. If the entry's fate is ambiguous (transport
   error), the exit stays PENDING, because the entry may exist and later fill.

The link between exit and entry is `pending_exits.entry_order_id` — our own
order id, explicit, one-to-one (UNIQUE). Nothing is ever matched by
market/price/size similarity.

## What did not change

`Executor.execute` still cannot reach the venue. `PolymarketAuthedClient`
still has no verb but GET. The kill switch and SHADOW defaults are untouched.
`orders_autonomous` still means "an order whose terms no human specified" and
must read 0 forever — see V18 in [findings.md](../findings.md) for the
amended constraint pair that keeps it that way.
