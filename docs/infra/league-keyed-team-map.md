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

### CFB: the all-`None` table is correct, and it is the model to copy

`KALSHI_TO_ESPN_NCAAF` has 276 entries and **all 276 map to `None`**, so my
first intersection ran on an empty set and "CFB collides with nothing" was
vacuous — a correct measurement of the wrong quantity. Chasing that produced the
opposite of what it looked like.

**It is not dead code and the `None`s are not a hole.** Both are load-bearing,
for two different reasons:

* **The 276 keys** are read at `mapping.py:522` to split variable-length game
  keys — `26SEP03MASSRUTG` → `MASS`/`RUTG` — by testing candidate substrings for
  membership. Delete the table and college key parsing stops.
* **The `None` values** make `_to_espn` (`mapping.py:474`) **raise
  `UnknownTeamError`** with a stated reason: *"the college code space diverges
  from ESPN's and is not derivable (4 of 11 games measured divergent,
  2026-09-03)"*. It is pinned by `test_ncaaf_codes_have_no_espn_identity`, whose
  docstring says `first_espn` **must raise rather than hand back a confident
  wrong abbreviation**.

**So CFB does not share NFL's defect — it has the opposite, on purpose.** NFL
fails by *absence*: the code is missing from a flat map, `UnknownTeamError` is
caught upstream, and the row is dropped with nothing logged. CFB fails by
*declaration*: the code is present, the identity is explicitly unknown, and the
lookup refuses. **The behaviour this spec asks for on unmapped codes already
exists in this file for CFB.** Cite it rather than reinventing it.

The table therefore **cannot be deleted** (keys) and **must not be populated**
(the `None` is the safety property).

**CFB's ESPN identity comes from a different route entirely** — `cfb_game_map`'s
fuzzy match on ESPN scoreboard names — so *code* collisions do not apply to it.
Its analogous hazard is **split ambiguity**: `MEMORE` parses as `MEM`+`ORE` or
`ME`+`MORE`, i.e. Memphis/Oregon or Maine/Morehead St. Already handled by
requiring the venue's `sub_title`, and pinned by a test.

### The codebase's own count is one short

`mapping.py:370` states *"Seven codes exist in BOTH tables (ATL, CHI, DAL, IND,
LV, MIN, SEA)"*. The measured intersection is **eight** — **`WSH` is in both**
and is omitted from the comment. Correct the comment when the map is changed;
an undercount in the place someone checks is how the ninth gets missed.

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

## The test that would have caught this

ce asked for a test failing if any league's code table is empty or all-`None`.
**As stated it would fail CFB, which is correct today.** The defensible form
separates the two failure modes:

1. **Every league table is non-empty.** No exceptions — an empty table makes
   every membership test false and every intersection vacuous, which is the
   defect that made this spec's first pass wrong.
2. **Every league declares its ESPN-identity policy**, `mapped` or
   `codes_only`, and the test asserts the table matches the declaration:
   `mapped` ⇒ no `None` values; `codes_only` ⇒ all values `None`. CFB is
   `codes_only` and passes; a WNBA or NFL table that silently drifted to
   all-`None` fails.
3. **No set operation over a league table without asserting it is non-empty
   first.** The vacuous result was not a wrong number — it was a correct
   computation over nothing, which no recomputation catches.

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
