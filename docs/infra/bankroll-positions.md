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

## The `cashValue` ambiguity, and how it is contained

Polymarket's own docs disagree about the one field that matters:

* REST reference: `cashValue` = "Unrealized PnL for the position"
* Python SDK reference: `cashValue` = "Current unrealized value" (market value)

Those give different equities. Until a real open position settles it, the
module (a) takes the SDK reading, (b) **clamps** every position's value to
±quantity — a binary contract is worth at most $1, so the wrong reading can
mis-state equity by at most the position's own size — and (c) self-verifies:
`verify_position_value()` cross-checks `cashValue` against our own recorder's
mid whenever the position is in a market we record, and logs a verdict
(`bankroll_cashvalue_semantics`: `value` / `pnl` / `ambiguous`). The next
open position in a WNBA market answers the question with data.

Positions in markets we do not record (the operator's hand trades on other
sports) cannot be cross-checked; they get the clamp only.

## Failure shape

A positions read that fails degrades: the snapshot carries
`positions_read_ok: false` and the pages render **"positions unread"** — an
unread position book is a different claim from an empty one, exactly as an
unknown bankroll is a different claim from $0.

One signing gotcha, learned the 401 way: the cursor must travel as `params=`
— the Ed25519 signature covers the bare path, and a query string embedded in
the path signs the wrong message.

## Still open (support question)

Which `cashValue` reading is correct, and whether `assetNotional` is *meant*
to stay 0 while positions are open. Asked of Polymarket support; either
answer tightens this module.
