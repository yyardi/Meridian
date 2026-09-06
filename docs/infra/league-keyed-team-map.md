# Spec: a league-keyed venue team map

**SPEC ONLY — nothing here is built, and nothing touches prod.** Written because
`kalshi_games` has 32 NFL rows with NULL `game_start_time`, NULL
`polymarket_event_slug` and NULL `espn_game_id`, and one cause explains all of
them.

## The cause

`kalshi_games.game_start_time` is written only by `_link_polymarket`
(`core/kalshi/recorder.py:439`), which indexes our own `market_snapshots` by
(unordered ESPN pair, local date) and **skips any slug whose teams do not
resolve** — `UnknownTeamError`, caught, row dropped, nothing logged.

`core/team_mapping.py POLYMARKET_TO_ESPN` is **flat and WNBA-only**: 15 entries,
`atl chi conn dal gsv ind la lv min ny phx por sea tor wsh`. Every NFL slug is
skipped. There is no league gate anywhere — the team map *is* the gate, which is
why nothing errors and nothing logs.

## The precedent, which is the argument for the shape

**This codebase already solved this, one module over.**
`core/kalshi/mapping.py` has `LEAGUE_TABLES: dict[str, dict[str, str | None]]`
keyed `{wnba, nfl, cfb}`, with a populated 32-entry NFL table. And
`kalshi_games` keys identity on **`(league, game_key)`** with a comment saying
why: *"a cross-league pair (SEA/ATL on one Sunday) collides"*.

So the fix is not a new idea, it is applying an existing one to the venue-side
map: **`POLYMARKET_TO_ESPN` keyed by `(league, code)` rather than `code`.**

## The collisions, enumerated BEFORE the fix

A fix that handles the two that were noticed and misses a third is worse than
none. Measured across `KALSHI_TO_ESPN` (wnba), `KALSHI_TO_ESPN_NFL` and the
live `POLYMARKET_TO_ESPN`:

| code | resolves in |
|---|---|
| ATL, CHI, DAL, IND, LV, MIN, SEA, WSH | **wnba and nfl** |

**Eight, not two.** All eight are live in `POLYMARKET_TO_ESPN` today and today
resolve to the WNBA team. An NFL slug for any of them **does not raise** — it
silently returns the wrong sport's franchise. That is worse than the block it
hides behind: a skipped row is a NULL somebody can count, a mis-resolved row is
a wrong `espn_game_id` that looks valid.

### CFB collisions are UNKNOWN, not zero

`KALSHI_TO_ESPN_NCAAF` has 276 entries and **all 276 map to `None`.** An
intersection against it is computed on an empty set, so "CFB collides with
nothing" is vacuous rather than reassuring — a correct measurement of the wrong
quantity. **CFB must be enumerated from a real CFB ESPN code source before CFB
is added to the league map**, and until then CFB collision risk is unquantified.

## What an unmapped code must do

Today: raises `UnknownTeamError`, caught, row skipped, **nothing logged**. That
is what produced 32 NULL rows that nobody noticed for as long as they existed.

Required instead:

1. **Count skips per league** and emit the count every discovery cycle, including
   when it is zero. A league mapping zero games and a league playing zero games
   must not look the same.
2. **Raise on ambiguity, not just on absence.** With `(league, code)` keys, a
   lookup missing its league argument should fail loudly rather than falling
   back to a flat search — the flat search is the current bug.
3. **Never resolve across leagues.** A code valid in another league is an error,
   not a match.

## Backfill

`kalshi_games.game_start_time` and `polymarket_event_slug` are recoverable now:
`market_snapshots` holds 114,549 NFL rows across 32 games, **all with
`game_start_time`** (09-10 → 09-22), because that column comes from the venue
payload (`core/live_recorder.py:904`) and never touched the team map. Key the
backfill on `(league, unordered ESPN pair, local date)` — the same key
`_link_polymarket` already uses, plus the league.

## `espn_game_id` needs a third source

The venue supplies none for either league. `scripts/build_cfb_game_map.py`'s
approach — fuzzy match on ESPN scoreboard team names with a ±1 day window —
ports to NFL and is the **easier** case: 32 teams, no FCS tier, and none of the
`groups=80/81` overlap that made the CFB division labelling a fetch-order
artifact. Generalise `cfb_game_map` to a `game_map` with a `league` column
rather than adding a third single-league table.

## Do not use Kalshi `occurrence_datetime` as a start time

Measured 2026-09-03 on both boards it is **kickoff + 3h** — the expected
settlement stamp (NE/SEA: ESPN 00:20Z, venue 03:20Z). It is already stored
correctly as `venue_occurrence_time` and named for what it is. Reading it as a
kickoff shifts every poll window three hours late **with green logs**.
