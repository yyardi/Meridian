# Data sources

Every external API, verified with live calls. All free, none require a key for the data layer.

## Polymarket US

**Two hosts, and the distinction matters:**

| Host | Auth | Use |
|---|---|---|
| `gateway.polymarket.us` | **none** | markets, events, sports, search — everything the recorder needs |
| `api.polymarket.us` | key required | orders, portfolio, reports |

> ⚠️ **Not** `clob.polymarket.com`. That's Polymarket **International** — EIP-712 wallet signing, geo-blocks US order placement. Different platform. Do not use `py-clob-client`.

**Rate limit: 20 requests/second** (per IP public, per key authenticated). On 429: stop, wait ≥1s, exponential backoff, max 3 retries.

### Whole WNBA board in one call

```
GET gateway.polymarket.us/v2/leagues/wnba/events?limit=50
```

Every event with all markets **and best bid/ask embedded** — one request snapshots the entire board.

WNBA is `slug=wnba`, `id=28`, `tagId=94`. A typical game carries **18 markets**: a totals ladder (~3-point steps), a spread ladder, and moneyline.

Market types: `basketball_team_full_game_total` / `_spread` / `_winner`
Slug prefixes: `tsc-` totals · `asc-` spreads · `aec-` moneyline

### Depth and settlement

```
GET gateway.polymarket.us/v1/markets/{slug}/book
GET gateway.polymarket.us/v1/markets/{slug}/settlement   → {"settlement": 0}
```

Settlement is **free ground truth** for every closed market: `1` = Yes, `0` = No.

```
GET gateway.polymarket.us/v1/markets?tagIds=94&closed=true
```

Closed-market history reaches back to season start (2026-05). The platform launched ~2026-03, so **no multi-year Polymarket history exists.**

### Historical candles (needs a key)

```
POST api.polymarket.us/v1beta1/report/trades/stats
```

OHLC + volume, intervals `1m|5m|15m|1h|4h|1d`. Only useful back to platform launch.

## ESPN — free, undocumented, no key

Unofficial but stable and widely used. Treat as untrusted input; validate at the boundary.

| Host | Use |
|---|---|
| `site.api.espn.com` | scoreboards, schedules |
| `sports.core.api.espn.com` | **historical odds** |

### Team game logs — a season per call

```
GET site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{id}/schedule?season=2026
```

~15 calls rebuild the entire league season. The backbone of point-in-time correctness.

⚠️ **Preseason is included by default.** Verified: NY Liberty 2025 returns 49 events = 2 preseason + 44 regular + 3 postseason. Filtering only on `completed` lets exhibition games pollute PPG and record.

```
seasonType.id →  1 = Preseason (never store)
                 2 = Regular Season
                 3 = Postseason
```

Playoffs are already in the default response — no `?seasontype=3` needed.

### Live odds

```
GET site.api.espn.com/.../wnba/scoreboard?dates=20260730
```

`events[].competitions[0].odds` carries DraftKings spread, total, moneyline.

⚠️ **Odds are stripped from past games here.** For history, use the core API.

### Historical odds — the CLV benchmark

```
GET sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/events/{id}/competitions/{id}/odds
```

(Event ID appears twice — as both event and competition.)

| Seasons | Available |
|---|---|
| **2024–2026** | `open` **and** `close` totals → true CLV benchmark. 1–2 providers |
| **2020–2023** | `overUnder`/`spread` across **6–15 books** (real consensus), no open/close split |

This is why a meaningful backtest is possible *now* rather than after months of recording — see [../math/clv.md](../math/clv.md).

## Coverage summary

| Need | Source | Cost | History |
|---|---|---|---|
| Market prices | Polymarket gateway | \$0 | forward only |
| Resolutions | Polymarket settlement | \$0 | since 2026-03 |
| Team stats | ESPN | \$0 | 2020+ |
| Live odds | ESPN scoreboard | \$0 | today |
| Historical odds | ESPN core | \$0 | 2020+ |

## Data-quality traps

1. **Preseason games** — excluded via `season_type = 1`
2. **All-Star games** — a 2023-07-15 fixture showed a 249.5 total ("Team Wilson"). Detect and exclude; they'll wreck a model fit
3. **`score` shape varies** — sometimes `{"value": 66.0}`, sometimes a bare value
4. **`gameId` is an int** upstream, text in our schema — coerce at the boundary
5. **Illiquid ladder rungs** — one quoted `bid 0.03 / ask 0.39`. Filter on spread width before trusting an implied probability
