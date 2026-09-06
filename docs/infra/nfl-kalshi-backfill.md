# Spec: backfilling `kalshi_games` for NFL

**SPEC ONLY. Nothing built, nothing touches prod.**

## ★ This is not a Thursday emergency, and the evidence is in two lines

The concern was that NULL `kalshi_games.game_start_time` breaks liveness for
week 1. **It does not.**

* `core/board.py market_state()` derives state from **`snap.game_start_time`
  where `snap` is a `MarketSnapshot`** — `market_snapshots`, not
  `kalshi_games`. That column is populated on **114,549 NFL rows across all 32
  games**, through 2026-09-22.
* **Nothing in the quoting path reads `kalshi_games` at all.** Grep across
  `core/quote/`, `core/board.py` and `core/pulse/` returns no reference.

So NFL live quoting has what it needs on Thursday. `kalshi_games` feeds the
**Kalshi cross-venue comparison** (`core/kalshi/analysis.py`), and that question
was closed on cost — the combined taker floor `0.13·p(1−p)` exceeds the largest
gap ever observed, at every price where the book is tradeable.

**Revised statement for the operator:** without this backfill we lose **neither**
live quoting **nor** the tape. What stays unavailable is the NFL cross-venue
join, for an analysis already closed as unprofitable. **This is a normal fix.**

## The join key — names, not ESPN codes

**Do not key on the ESPN pair.** `_link_polymarket` does, via
`POLYMARKET_TO_ESPN`, and that map is WNBA-only with **eight codes (ATL CHI DAL
IND LV MIN SEA WSH) that resolve to the WNBA team** rather than raising. Keying
an NFL backfill on it writes confident wrong pairings.

Use the approach Quant B already proved on CFB (`5dabfa5`): match on **date +
unordered normalised name pair, taken from both venues' own payloads**.

```
kalshi side       event.sub_title  ("SJSU vs EMU (Sep 4)")  + event.title
polymarket side   teams[].abbreviation + teams[].safeName   (from market_snapshots.raw)

key = ( local_date , frozenset({normalise(name_a), normalise(name_b)}) )

UPDATE kalshi_games k
   SET game_start_time      = m.start,
       polymarket_event_slug = m.event_slug
  FROM (
        SELECT event_slug, max(game_start_time) AS start
          FROM market_snapshots
         WHERE event_slug IS NOT NULL
           AND game_start_time IS NOT NULL
         GROUP BY event_slug
       ) m
 WHERE k.league = 'nfl'
   AND k.game_start_time IS NULL
   AND key(k) = key(m)          -- date + unordered normalised name pair
```

**Why this is the right key and not a workaround:** it never consults the venue
team map, so the eight collisions cannot reach it. B's CFB run was
over-determined with **zero conflicts in either direction** — a wrong name match
would have surfaced as a conflict, which is the positive control this key has
and the code key does not.

**Its own hazard, and it is real:** names are the bridge and they are not
authoritative. B's SDST case — Kalshi *South Dakota St.* against Polymarket
*San Diego St.* — silently joins two different games. NFL is the easier case
(32 unambiguous franchises, no FCS tier) but the check is the same: **assert
zero conflicts in both directions before writing, and refuse the whole batch if
any appear.**

## What it populates, and what it cannot

| column | source | status |
|---|---|---|
| `game_start_time` | `market_snapshots.game_start_time` | available now |
| `polymarket_event_slug` | `market_snapshots.event_slug` | available now |
| `espn_game_id` | **neither venue** | separate step |

The venue sends no `espnId` for either league, and `settlement_sources` names
the NFL as settlement authority rather than an id source. `espn_game_id`
therefore needs the fuzzy scoreboard-name matcher from
`scripts/build_cfb_game_map.py` (±1 day window), which ports to NFL and is the
easier case. **Separate step, separate PR, not on this critical path** — nothing
in quoting needs it.

## Order of operations

**The name key removes the dependency.** Because the join never touches
`POLYMARKET_TO_ESPN`, the backfill and the league-keyed map fix are
**independent** and may be done in either order.

**That independence holds only for the name key.** If anyone implements this via
the ESPN pair instead, the ordering becomes mandatory and unforgiving:

> **map fix FIRST, backfill SECOND.** Run in the other order and the eight
> colliding codes write wrong `espn_game_id`s and wrong pairings that look
> valid, into a table whose whole purpose is identity. A skipped row is a NULL
> somebody can count; a mis-paired row is a lie that survives review.

## What it does with a row it cannot pair

Not silence. Silence is what left 32 NULLs unnoticed for as long as they existed.

1. **Count unpaired rows per league and emit the count every run, including
   when it is zero.** A league that pairs nothing and a league that has nothing
   to pair are currently indistinguishable — that is the whole defect.
2. **Refuse the batch on any name conflict**, in either direction, rather than
   writing the unambiguous subset. A partial write with a conflict in it is
   worse than no write, because the conflict is what tells you the key is wrong.
3. **Never fall back to the ESPN-code key** when the name key fails. That is the
   path with the eight collisions on it.

---

*Specced 2026-09-06. Nothing built.*
