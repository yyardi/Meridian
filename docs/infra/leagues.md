# League is a parameter

The dashboard header read `MERIDIAN · WNBA` on all three pages while
`core/config.py` carried a `MERIDIAN_LEAGUE` env var that nothing on the page
read. League is now one table — [`core/leagues.py`](../../core/leagues.py) —
and a tab strip in the header.

## The table, not a derivation

Same shape and same reasoning as `core.team_mapping.POLYMARKET_TO_ESPN`: **an
explicit table fails loudly where a derivation fails silently.** `get_league()`
raises `UnknownLeagueError` for anything not listed rather than guessing a slug,
because a silently unknown league renders an empty board and an empty board
looks like a quiet evening.

| league | recorded | notes |
|---|---|---|
| `wnba` | yes | what everything is fitted and measured on |
| `nba` | no | wired end to end, season starts October |

The slug is the venue's own and is the prefix of every event slug
(`wnba-ny-chi-2026-08-18`), so it is also the join key — no new column, no
migration.

## What is parameterised, and what is not

**Parameterised:** `/api/board`, `/api/picks`, `/api/events`, `/api/games`,
`/api/game/{slug}`, `/api/leagues`, and the header tabs on all three pages. The
choice is remembered per browser so the pages agree with one another.

**Not:** the model. It is fitted, gated and measured on WNBA alone. Pointing it
at another league is a modelling question — new priors, a refitted sigma, a
different pace and possession distribution — not a routing question, and the
NBA tab says so in as many words instead of showing an empty table that reads
as a bug. Per-league tuning is explicitly out of scope here.

## Empty states are written down

Every league carries its own `empty_state` string and a test asserts none is
blank. An empty board and a broken board look identical on screen, and only one
of them is fine.

## The silent-drop guard

A market slug that matches no known league is dropped from `/api/picks` — and
**counted**, in `filtered.unknown_league`. A rising number there means the venue
changed its slug format, which is exactly the failure that would otherwise
present as a board quietly going empty.
