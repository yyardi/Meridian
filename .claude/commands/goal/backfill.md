---
description: Backfill historical WNBA odds, game logs, and Polymarket settlements
---

# Goal: Historical backfill

Build the one-shot historical backfill for **Meridian**. Build unit **5 of 12**, depends on `/goal:stats` and `/goal:odds`. Read `README.md` first.

## Why this exists

The original project assumption was that Polymarket US had no historical data, so the recorder running forward was the only source — implying months before any meaningful backtest.

That's half true. Polymarket US launched ~2026-03, so no multi-year *venue* history can exist. But **ESPN has ~6 seasons of free sportsbook closing lines**, which splits one question into two:

| Question | Data | Available |
|---|---|---|
| Does the fair-value model beat a closing line? | ESPN historical odds 2020–2026 | **Now** |
| Does an edge exist on *this venue*? | Recorder, forward | Accrues daily |

The first question decides whether the model is worth anything at all, and it's answerable immediately on ~1,000+ games. **This unit unlocks the real backtest.**

## Task

Build `core/backfill.py` — an idempotent, resumable job that populates:

### 1. Team game logs, 2020–2026
Via `core/feeds/espn_stats.py`. ~15 teams × 7 seasons.

Persist `season_type` (`1` Preseason / `2` Regular / `3` Postseason) throughout, and **exclude preseason entirely** — it would corrupt both PPG and win-loss record. See `/goal:stats`.

### 2. Historical sportsbook odds, 2020–2026
For every completed game, pull core-API odds:
```
GET https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/events/{id}/competitions/{id}/odds
```
Write one `sportsbook_odds` row per provider.

### 3. Polymarket settlements (2026 only)
```
GET https://gateway.polymarket.us/v1/markets?tagIds=94&closed=true&limit=100&offset=N
GET https://gateway.polymarket.us/v1/markets/{slug}/settlement
```
`tagId=94` is WNBA. Settlement returns `{"slug":"...","settlement":0}` — `1` = Yes, `0` = No. Free, no API key. Write to `resolved_outcomes`.

## Critical: report CLV coverage honestly

Odds coverage is **not uniform across seasons**, and the backtest must know this:

| Seasons | What exists |
|---|---|
| **2024–2026** | `open` + `close` totals → **true closing lines**, usable for CLV |
| **2020–2023** | `overUnder`/`spread` across 6–15 books → consensus only, **no closing line** |

Set `is_closing_line` accurately per row. Never infer a closing line from a current line — that would silently corrupt the headline CLV metric, which is the primary measure of edge.

At the end, print a **coverage report**, split by season type so playoff sample size is visible:
```
Season  Reg  Post  Pre(skipped)  With odds  With TRUE closing line  Providers (median)
2020    132    12             8        128                       0                  6
...
2025    176    19            10        174                     174                  2
TOTAL:  N regular + M postseason games, X% with closing lines usable for CLV
```

The postseason column matters: the record feature is down-weighted in playoffs (`/goal:fairvalue`), and the backtest reports playoffs as a separate cohort. If that cohort is ~15–20 games/season, no playoff-specific conclusion is supportable — the report should make that obvious at a glance.

## Requirements

- **Resumable.** Track progress; a crash at season 4 of 7 must not restart from scratch.
- **Idempotent.** Reruns must not duplicate.
- Rate limit ~2–5 req/s against ESPN. This is thousands of requests — be polite and expect it to take a while.
- `--dry-run` that reports what would be fetched without writing.
- Per-season progress logging; this is a long job and silence is indistinguishable from a hang.
- Never let one missing game kill the run. Some events legitimately have no odds. Log and continue.

## Watch out for

- **All-Star games and exhibitions** pollute the data — a 2023-07-15 game showed a total of 249.5 (All-Star, "Team Wilson"). Detect and flag/exclude non-regular-season games; they'll wreck any model fit.
- Season boundaries: the WNBA runs roughly May–September, plus playoffs.
- Some events return zero odds providers. Expected, not an error.

## Done when

- `team_game_logs` covers 2020–2026 with plausible per-season counts
- `sportsbook_odds` populated, with `is_closing_line` true only for 2024+
- `resolved_outcomes` populated for closed 2026 Polymarket markets
- The coverage report prints and its numbers are believable
- Rerunning adds zero rows
- Killing mid-run and restarting resumes rather than restarting
- All-Star/exhibition games are flagged or excluded
- **Zero rows with `season_type = 1`** — preseason never made it in
- Postseason counts are non-zero for seasons that had playoffs, and small (~15–20/season)
