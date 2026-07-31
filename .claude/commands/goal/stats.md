---
description: Build the ESPN team game-log fetcher (point-in-time correct)
---

# Goal: ESPN stats fetcher

Build the team stats fetcher for **Meridian**. Build unit **3 of 12**, depends on `/goal:schema`. Read `README.md` first.

## Why ESPN

It's free, needs no API key, and returns a **whole season per call**. Alternatives were evaluated and rejected: `stats.wnba.com` refuses connections from datacenter IPs; SportsDataIO has no public pricing tier.

The API is undocumented but stable and widely used. Treat it as untrusted input and validate at the boundary.

## Verified endpoints

### Full season of games for one team — one call

```
GET https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{teamId}/schedule?season=2026
```

Returns ~46–49 events with `homeAway`, final scores, dates, completion status, and **`seasonType`**. **~15 calls rebuild the entire league season.**

Response shape:
```jsonc
{ "events": [{
    "id": "401856953",
    "date": "2026-04-25T23:30Z",
    "seasonType": { "id": "2", "name": "Regular Season" },
    "competitions": [{
      "status": { "type": { "completed": true } },
      "competitors": [
        { "team": { "id": "16", "abbreviation": "WSH" }, "homeAway": "home", "score": { "value": 66.0 } },
        { "team": { "id": "8",  "abbreviation": "MIN" }, "homeAway": "away", "score": { "value": 77.0 } }]
    }]
}]}
```

⚠️ `score` is sometimes a dict (`{"value": 66.0}`) and sometimes a bare value depending on endpoint. Handle both.

### ⚠️ Preseason games are returned by default — exclude them

`seasonType.id` takes three values, all present in the default response:

| id | name | Action |
|---|---|---|
| `1` | Preseason | **Never write.** Exhibition games with non-competitive rotations |
| `2` | Regular Season | Write. The basis for all PPG and win-loss record features |
| `3` | Postseason | Write, tagged. Real games we predict on, but excluded from record calculations |

Verified: NY Liberty 2025 returns **49 events = 2 preseason + 44 regular + 3 postseason** from a single default call.

This is easy to miss, because filtering on `completed` alone lets preseason through — and preseason results would silently corrupt **both** offensive/defensive PPG and win-loss record. Filter on `seasonType.id` explicitly.

You do **not** need `?seasontype=3` to get playoffs; the default call already includes them.

### Team list

```
GET https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams
```

Use this to discover team IDs rather than hardcoding them.

### Daily scoreboard (for incremental updates)

```
GET https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20260730
```

`dates` is `YYYYMMDD`.

## Task

Build `core/feeds/espn_stats.py`:

1. Discover all WNBA teams and their ESPN IDs.
2. For each team, fetch the season schedule and write **one `team_game_logs` row per team per completed game** — so each game produces two rows (one per team's perspective), with `points_scored` / `points_allowed` oriented to that team.
3. **Persist `season_type` from `seasonType.id`, and skip every preseason (`1`) game.**
4. Support both a **full-season backfill** (any season 2020–present) and a **daily incremental** update.
5. Upsert on `(espn_game_id, team_id)` — reruns must be safe.
6. Only write completed games. Skip in-progress ones; they'll be captured next run.

## Design rule: no lookahead, enforced structurally

Store **immutable per-game rows only**. Do not compute or store season aggregates like "team PPG" in this unit — that's `/goal:features`, which derives them `as_of` a date.

The reason is structural, not stylistic: a mutable `season_stats` row overwritten nightly means a backtest of a July 15 game silently reads September's numbers. The results look plausible and are worthless. One row per game makes that bug impossible to write.

## Requirements

- `pydantic` models for ESPN responses; fail loudly on schema drift.
- Polite rate limiting (~2–5 req/s) and a descriptive User-Agent. ESPN publishes no limits; don't hammer it.
- `tenacity` retries with backoff.
- Idempotent — running twice changes nothing.
- Structured logging: teams processed, games written, games skipped.
- CLI: `python -m core.feeds.espn_stats --season 2026` and `--backfill 2020-2026`.

## Done when

- Backfilling 2026 populates `team_game_logs` with ~2 rows per completed league game
- Every game appears exactly twice, once per team, with `points_scored`/`points_allowed` mirrored
- Rerunning produces zero new rows
- A spot-check against a known box score matches
- `--backfill 2020-2026` completes and row counts per season look sane
- **`SELECT count(*) FROM team_game_logs WHERE season_type = 1` returns 0** (no preseason leaked in)
- Both `season_type` 2 and 3 are present for a season where a team made the playoffs — verify against NY Liberty (team id `9`) 2025, which should yield 44 regular + 3 postseason games and 0 preseason
