---
description: Build the shadow-mode executor — limit orders only, by construction
---

# Goal: Shadow-mode executor

Build the execution layer for **Meridian**. Build unit **11 of 12**, depends on `/goal:kelly`. Read `README.md` first.

**This unit places no real orders.** v1 is shadow mode only: it logs what it *would* trade. Real execution is a later milestone, gated behind a human-confirm step and a validated track record.

## Hard rule: limit orders only, enforced by construction

The executor must expose **no market-order code path at all.**

Not a convention, not a default parameter, not a documented warning. Design it so a market order is **unrepresentable**:

- No `order_type` parameter that could be passed a market value
- The order-construction function takes a **required** `limit_price`
- Internally always `"ORDER_TYPE_LIMIT"`, hardcoded, never parameterized
- A test asserts no market-order type string appears anywhere in the module

Two reasons, both real:
1. A market order into a thin ladder rung can fill far from the intended price — one rung was observed at `bid 0.03 / ask 0.39`.
2. **Economics.** Taker fee is `+0.06 × C × p × (1−p)`; maker is `−0.0125` — a *rebate*. A resting limit order gets paid; a market order pays. At p=0.50 that's 1.5¢/contract versus +0.3¢. On a 2¢ spread this is most of the edge.

## Use the correct SDK

```bash
pip install polymarket-us       # Python 3.10+
```
```python
from polymarket_us import PolymarketUS
client = PolymarketUS(key_id=..., secret_key=...)
```

⚠️ Do **not** use `py-clob-client` or anything targeting `clob.polymarket.com`. That's Polymarket **International** — EIP-712 wallet signing, and it geo-blocks US order placement. Wrong platform entirely.

The SDK handles request signing internally. **Do not hand-roll auth.**

Credentials come from env (`POLYMARKET_KEY_ID`, `POLYMARKET_SECRET_KEY`), never hardcoded, never logged. Obtaining them: app account → identity verification → sign in at `polymarket.us/developer` → create key. An account alone is not sufficient.

Docs: https://docs.polymarket.us — verify order schemas against the current API reference.

## Task

Build `core/executor.py` with three modes, only the first enabled in v1:

### Mode 1 — SHADOW (v1, the only one active)
- Takes predictions + Kelly sizes
- Logs the full intended order: market, side, limit price, size, model price, market price, edge, expected fee/rebate
- Writes to a `shadow_orders` table for later comparison against what actually happened
- **Places nothing.** No authenticated call is ever made.

### Mode 2 — HUMAN_CONFIRM (v2, build the scaffold, leave disabled)
- Surfaces the recommended trade: line, model price, market price, Kelly size, edge
- Requires explicit interactive confirmation before placing
- Behind a config flag defaulting to off

### Mode 3 — AUTONOMOUS (future, do not implement)
- Leave a clearly marked stub that raises `NotImplementedError`
- Only after a real, positive, walk-forward-validated track record

## Shadow-mode fidelity

Shadow logs are only useful if they'd have been real orders, so:
- Respect `orderPriceMinTickSize` (0.01) — round limit prices to a valid tick
- Respect `minimumTradeQty` (0.01) — flag when Kelly size falls below it (likely at a $25–40 bankroll)
- Record the book state at decision time, so fill probability can be assessed later
- Record whether the limit price would have **rested** (maker, earns rebate) or **crossed** (taker, pays fee)

## Requirements

- **Kill switch** — a single config flag disabling all order placement, checked before any authenticated call.
- Never log secrets. Redact keys in all output.
- Structured logging of every decision, including declines to trade and why.
- Idempotency keys on orders so a retry can't double-place (matters for v2).
- Config in `strategies/wnba_totals/config.py`; default mode `SHADOW`.

## Tests

1. **No market-order path exists** — grep the module for market-order type strings; assert absent
2. `limit_price` is required; omitting it is a type error
3. Shadow mode makes zero authenticated network calls (assert with a mocked client)
4. Kill switch blocks placement
5. Prices round to valid ticks
6. Sub-minimum sizes are flagged, not silently rounded up
7. Maker/taker classification is correct against a known book

## Done when

- Shadow mode logs intended orders for real current predictions
- No code path can construct a market order
- Zero authenticated calls occur in shadow mode
- Shadow orders record the maker/taker classification and expected fee
- The autonomous stub raises rather than executing
- No secret ever appears in logs
