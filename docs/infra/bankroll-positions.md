# Positions make the bankroll live

`core/bankroll.py` · `GET /v1/portfolio/positions` ·
[docs.polymarket.us](https://docs.polymarket.us/api-reference/portfolio/get-user-positions)

## The bug this fixes

The operator held an open position while the dashboard said `positions $0.00`.
Two causes, only one of which was already fixed:

1. The page showed the scheduler's stored reading (up to 20 min old). Fixed in
   the declutter pass: the page polls `refresh=true` every 60s.
2. **A fresh venue read *also* said 0.** `assetNotional` in
   `/v1/account/balances` does not carry positions on this venue — verified
   live during the open position. Positions live at
   `GET /v1/portfolio/positions`: a **map** of market slug → position
   (observed flat: `{"positions": {}, "nextCursor": "", "eof": true}`).

## Two numbers, deliberately distinct

| Field | Definition | Who uses it |
|---|---|---|
| `bankroll` | `min(currentBalance, buyingPower)` — unchanged | **Sizing** (Kelly). Position value is not spendable on the next order. |
| `equity` | `bankroll` + Σ clamped position values | **Display**. What the account is worth. |

## The `cashValue` ambiguity — settled by support, still verified by us

Polymarket's docs disagreed about the one field that matters: the REST
reference called `cashValue` "Unrealized PnL", the SDK reference "Current
unrealized value". **Support settled it (2026-08-18):**

* `cashValue` **is the position's current market value** — not `cost + cashValue`.
* Unrealized PnL is therefore `cashValue − cost` (exposed as `unrealized`).
* `assetNotional` staying 0 with open positions is **intended**: position
  exposure is represented only through the positions endpoint.

Two guards stay anyway. The clamp to ±quantity now bounds venue-side bugs
rather than a doc reading. And `verify_position_value()` still cross-checks
`cashValue` against our own recorder's mid for positions in recorded markets
— a confirmation in an email is not yet an observation in a log, and a `pnl`
verdict now means the venue disagrees with its own support, which deserves to
be loud. Positions in markets we do not record get the clamp only.

`python -m core.bankroll --raw` prints the raw balances and positions bodies
side by side — the artifact support asked for to reconcile fields precisely,
capturable the next time a position is open. Redact the account id before
sending.

## Failure shape

A positions read that fails degrades: the snapshot carries
`positions_read_ok: false` and the pages render **"positions unread"** — an
unread position book is a different claim from an empty one, exactly as an
unknown bankroll is a different claim from $0.

One signing gotcha, learned the 401 way: the cursor must travel as `params=`
— the Ed25519 signature covers the bare path, and a query string embedded in
the path signs the wrong message.

## History

Asked of Polymarket support 2026-08-18; answered the same day (see above).
The REST reference's "Unrealized PnL" description was the wrong half; support
noted it is likely a documentation issue, not account behaviour.
