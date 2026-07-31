---
description: Build the ESPN sportsbook odds feed (live + historical)
---

# Goal: ESPN sportsbook odds feed

Build the sportsbook odds feed for **Meridian**. Build unit **4 of 12**, depends on `/goal:schema`. Read `README.md` first.

## Why this matters

The strongest signal found in manual testing was the **cross-market gap**: Polymarket US implied probability vs. sportsbook consensus for the same game, which showed 6–8 point divergences. Sportsbooks carry vastly more WNBA volume, so where they disagree, the book is more likely right.

This feed is also the **CLV benchmark** — closing lines are what the backtest measures predictions against.

## Why ESPN (and not a paid API)

ESPN provides live *and* historical odds for free with no key. The Odds API would cost $30/mo for the same data; its free tier (500 credits/mo) allows only ~5 polls/day. Verified during research — ESPN wins outright.

## Verified endpoints

### Live odds

```
GET https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20260730
```

`events[].competitions[0].odds` carries DraftKings:
```jsonc
[{ "provider": { "id": "100", "name": "DraftKings" },
   "details": "MIN -12.5", "overUnder": 186.5, "spread": 12.5,
   "awayTeamOdds": { "favorite": true, "moneyLine": ... },
   "homeTeamOdds": { ... } }]
```

⚠️ **Odds are stripped from past games on this endpoint** — a past-dated scoreboard returns games with no `odds` key. For history you must use the core API below. This is the single easiest thing to get wrong here.

### Historical odds — the important one

```
GET https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/events/{eventId}/competitions/{eventId}/odds
```

Note the event ID appears **twice** — as both event and competition.

```jsonc
{ "count": 2, "items": [{
    "provider": { "name": "ESPN BET" },
    "overUnder": 166.5, "spread": 15.5,
    "overOdds": -105.0, "underOdds": -115.0,
    "moneylineWinner": false, "spreadWinner": false,
    "awayTeamOdds": {...}, "homeTeamOdds": {...},
    "open":    { "total": { "american": "164.5" }, "over": {...}, "under": {...} },
    "close":   { "total": { "american": "166.5" }, "over": {...}, "under": {...} },
    "current": { ... }
}]}
```

### Coverage by season (verified — this varies and you must record which you got)

| Seasons | Available |
|---|---|
| **2024–2026** | `open` **and** `close` totals — true closing lines, plus movement direction. Typically 1–2 providers (ESPN BET, DraftKings) |
| **2020–2023** | Top-level `overUnder` / `spread` across **6–15 sportsbooks** (Bet365, Caesars, Westgate, Unibet...) — real consensus, but `open`/`close` objects are empty |

## Task

Build `core/feeds/espn_odds.py`:

1. **Live mode** — poll today's scoreboard, write `sportsbook_odds` rows with `captured_at`. Run alongside the recorder so Polymarket and sportsbook prices are comparable at the same timestamps.
2. **Historical mode** — given an ESPN game ID, fetch core-API odds and write one row **per provider**.
3. Parse `open` / `close` totals when present; leave null when not.
4. Set `is_closing_line=true` only when a genuine `close` object exists — never infer it.
5. **Consensus helper** — a function returning median line across providers for a game. Median, not mean: it resists one book posting a stale or outlier number.
6. Convert American odds to implied probability, and provide **vig removal** (normalize the two sides to sum to 1). Raw American odds include the book's margin; comparing them to Polymarket prices without de-vigging overstates the gap and would manufacture fake edge.

## Requirements

- `pydantic` validation; ESPN is undocumented and *will* drift.
- Polite rate limiting (~2–5 req/s), `tenacity` retries.
- Idempotent — upsert on `(espn_game_id, provider_name, captured_at)`.
- Store the full raw payload in `raw` JSONB.
- Never crash a batch on one bad game; log and continue.
- CLI: `--live` and `--historical --season 2024`.

## Done when

- Live mode writes today's games with spread/total/moneyline
- Historical mode on a 2025 game returns `open` and `close` totals
- Historical mode on a 2022 game returns 6–15 providers with null open/close, and `is_closing_line=false`
- De-vigged two-sided probabilities sum to 1.0 (within rounding)
- Consensus helper returns a sane median across providers
- Reruns produce no duplicates
