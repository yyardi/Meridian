# Kalshi recorder — the second transactable venue

**Why, pre-registered (2026-08-05, before any matched data existed).** The
venue-gap thesis (findings Q1) measures Polymarket against the sportsbook
opening line, which cannot be transacted. Kalshi is a second CFTC-regulated
venue quoting the same WNBA games on public, unauthenticated endpoints.
Recording it alongside turns "is Polymarket mispriced?" into a same-minute
comparison of two transactable prices.

**The gate, fixed in advance:** no conclusion until **≥10 matched games**;
then report exactly median |mid gap| and sign persistence on matched
contracts, clustered by game — and nothing else. The gate lives in
`core/kalshi/analysis.py`, whose `report()` refuses to emit numbers below it
and raises `NotImplementedError` above it: the statistics get written only
when there is a sample to run them on. Rows are not games (the PULSE lesson);
`python -m core.kalshi --gate` says where the sample stands.

## What it records

Three full-game series, discovered daily, polled at 60s from 6h before
tip-off until tip (pregame only — that is the registered window):

| series | market_type | strike |
|---|---|---|
| `KXWNBAGAME` | winner | none (structured, per team) |
| `KXWNBASPREAD` | spread | `floor_strike` 15.5 = "wins by > 15.5", per team |
| `KXWNBATOTAL` | total | `floor_strike` 178.5 = "combined > 178.5" |

One `/markets?event_ticker=` request per series per game returns top-of-book
(`yes_bid/yes_ask_dollars`, decimal strings), last price, sizes, and the full
settlement rules — 3 requests per game per minute, no per-market book calls.
The no side is not stored: on Kalshi it is the yes side's complement
(no_bid = 1 − yes_ask, verified on live payloads).

## Tables

- **`kalshi_games`** — one row per game, the venue-mapping table. No shared ID
  exists anywhere, so the join key is the unordered ESPN team pair + local
  date, exactly like Polymarket's (`core/team_mapping.py`). Kalshi's ticker
  order is stored verbatim but never read as home/away — Polymarket's slug
  order flipped convention mid-season, and Kalshi's earns the same distrust
  until measured. `game_start_time` is copied from our own
  `market_snapshots`, because Kalshi's WNBA events carry no start time
  (`strike_date` is null — verified against the venue). A game with no
  Polymarket link has no start time and is structurally unpollable, which is
  the "matched games only" scope rule enforced by shape rather than by filter.
- **`kalshi_contracts`** — each contract's line and settlement terms
  **verbatim** (`rules_primary/secondary`, strikes, full raw payload), as a
  change log: a row when terms change, read as-of like `injury_reports`.
  Strike/settlement mismatches between venues are basis risk; this is the
  audit trail that keeps them checkable instead of assumed away.
- **`kalshi_snapshots`** — `market_snapshots` for Kalshi: mandatory
  `captured_at` shared per cycle, append-only, unique `(ticker, captured_at)`
  so a crashed-and-rerun recorder is idempotent. Slim on purpose: terms live
  in the change log, so a snapshot row is ~10 numbers, not 1 KB of repeated
  rules text (docs/infra/supabase-quota.md is why that matters).

## Kalshi ↔ ESPN team codes

Kalshi is a **third** abbreviation space. Two codes differ from ESPN:
`CONN → CON` and `PDX → POR`. The explicit table is `KALSHI_TO_ESPN` in
`core/kalshi/mapping.py`; event tickers concatenate the two codes with no
delimiter (`26AUG05PHXATL`), so parsing demands exactly one valid split and a
test proves uniqueness over every franchise pair. Non-franchise events
(all-star: `26JUL25SPNCOO`) fail to parse and are skipped, correctly.

## Rate limits and load

Kalshi's published limits are token-based per authenticated account (Basic:
200 read tokens/s at 10/request = 20 req/s sustained;
docs.kalshi.com/getting_started/rate_limits, read 2026-08-05). Nothing is
published for unauthenticated traffic, so we assume at best Basic and cap at
5 req/s. Actual demand: ~12 requests/minute on a 4-game night, ~10 requests
per discovery. Idle cycles touch only our own database.

Fees, for later tradability math (not yet stored): `KXWNBAGAME` is
`quadratic_with_maker_fees`, spread/total are `quadratic` (series endpoint,
2026-08-05).

## Read-only, by construction

No auth, no keys: `KalshiConfig` has no credential field and
`KalshiPublicClient` exposes GET-shaped methods only — an order is not
expressible, the same principle as the gateway client.

## Running it

It runs as the `kalshi-recorder` compose service (container
`meridian-kalshi-recorder`), started with everything else by
`docker compose up` and restarted automatically on crash or reboot. It ran
twice as a manual foreground process and died twice with its terminal — don't
run it that way.

The loop polls at 60s in-window, 15min idle, discovery every 6h, and beats the
`kalshi_recorder` service heartbeat every cycle, so `scripts/health.py` and
`/api/status` cover it automatically.

One-off runs for testing (against whatever `DATABASE_URL` you export):

```bash
.venv/bin/python -m core.kalshi --once
```

```bash
.venv/bin/python -m core.kalshi --gate
```
