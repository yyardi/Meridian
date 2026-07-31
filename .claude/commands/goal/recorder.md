---
description: Build the Polymarket US market snapshot recorder
---

# Goal: Polymarket US recorder

Build the market snapshot recorder for **Meridian**. This is build unit **2 of 12** and depends on `/goal:schema`. Read `README.md` first.

**This is the highest-priority unit.** Market snapshots are unrecoverable — every night this isn't running is line movement that no longer exists anywhere. Stats and odds can be backfilled; this cannot.

## Critical: use the right API

Polymarket US is a **separate platform** from Polymarket International. Do **not** use `py-clob-client` or anything targeting `clob.polymarket.com` — that's the international CLOB, uses EIP-712 wallet signing, and geo-blocks US order placement.

Two hosts:
- **`gateway.polymarket.us`** — public, **no API key needed**. This is all the recorder uses.
- `api.polymarket.us` — authenticated, not needed here.

Official docs: https://docs.polymarket.us — verify endpoint shapes against them if anything below doesn't match.

## Verified endpoints

### Whole WNBA board in one call

```
GET https://gateway.polymarket.us/v2/leagues/wnba/events?limit=50
```

Returns every event with all markets **and best bid/ask embedded**. One request snapshots everything.

```jsonc
{ "events": [{
    "id": "62459", "slug": "wnba-gsv-phx-2026-07-29",
    "title": "Golden State vs. Phoenix",
    "startTime": "2026-07-30T02:00:00Z", "gameId": 13002436,
    "eventState": { "score": "46-34", "period": "Q3", "live": true },
    "teams": [{ "abbreviation": "gsv", "record": "15-15" }],
    "markets": [{
      "id": "298081",
      "slug": "tsc-wnba-gsv-phx-2026-07-29-144pt5",
      "sportsMarketType": "basketball_team_full_game_total",
      "line": 144.5,
      "bestBidQuote": { "value": "0.9100" },
      "bestAskQuote": { "value": "0.9600" },
      "orderPriceMinTickSize": 0.01,
      "minimumTradeQty": 0.01,
      "feeCoefficient": 0.06,
      "marketSides": [
        { "description": "Over",  "long": true,  "price": "0.9100" },
        { "description": "Under", "long": false, "price": "0.9600" }]
    }]
}]}
```

Market types: `basketball_team_full_game_total` / `_spread` / `_winner`.
Slug prefixes: `tsc-` totals, `asc-` spreads, `aec-` moneyline. A typical game has **18 markets** (totals ladder, spread ladder, moneyline).

### Order book depth

```
GET https://gateway.polymarket.us/v1/markets/{slug}/book
```

```jsonc
{ "marketData": { "marketSlug": "...",
    "bids":   [{ "px": { "value": "0.5100" }, "qty": "1559.0000" }],
    "offers": [{ "px": { "value": "0.5300" }, "qty": "1505.7800" }] }}
```

## Rate limits

**20 requests/second** per IP. (Older notes saying 60/min are wrong.) On HTTP 429: stop, wait ≥1s, exponential backoff, max 3 retries.

⚠️ Rejections reading `Global Rate Limit Exceeded` during high-latency windows are *transient latency rejects*, not real rate limiting — do not throttle in response to them.

Budget per snapshot cycle: 1 call for the board + ~1 per market for depth (~150 for a full slate). Trivial against 20/sec.

## Task

Build `core/recorder.py` plus a runnable entrypoint:

1. Fetch the WNBA board; write one `market_snapshots` row per market with a shared `captured_at`.
2. For each market, fetch depth and write `book_levels` rows.
3. Store the full raw payload in the `raw` JSONB column — reparsing later beats re-fetching never.
4. Adaptive cadence, configurable:
   - within 6h of tip-off: every **15 min**
   - otherwise: every **60 min**
   - live games: record but flag `is_live=true` (no intra-game trading in v1, but the data is free)
5. Rate limiting with a token bucket, conservatively ~10 req/s (half the ceiling).
6. Retries via `tenacity` with exponential backoff.
7. Structured logging (`structlog`): markets captured, duration, failures.

## Requirements

- **Idempotent** — a crash mid-run then rerun must not corrupt data. Snapshots are append-only, keyed by `(market_slug, captured_at)`.
- **Never crash the loop.** One bad market must not kill the run; log and continue. A recorder that dies at 2am silently is the main failure mode.
- Validate responses with `pydantic` at the boundary — a changed ESPN/Polymarket field should raise a clear parse error, not silently write nulls.
- Use `httpx` with explicit timeouts.
- Wire in `NUMERIC`-safe parsing: prices arrive as strings (`"0.9100"`) — parse to `Decimal`, never `float`.
- Config via env/`config.py`: poll intervals, league slug, depth on/off.

## Done when

- One manual run writes snapshots + depth for every current WNBA market
- `SELECT count(*), max(captured_at) FROM market_snapshots` shows fresh rows
- Killing the process mid-run and restarting produces no duplicates or partial corruption
- Rate limiter demonstrably holds under the ceiling (log request timings)
- A forced failure on one market logs an error and the run still completes
