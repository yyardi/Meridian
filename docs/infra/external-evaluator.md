# The external evaluator — design only, not authorised

**Every alarm we own asks the thing it watches whether the thing is working.**
Three people reached that conclusion today from different directions:

- `cycles == 0 AND games_in_progress > 0` needs a kickoff source, and `cycles`
  is emitted **by the recorder** — a container that no longer exists emits
  nothing, so absence of a heartbeat is *no observation*, not a zero.
- c7's alarm expects "did this league record anything in 6h" — still derived
  from our own write stream, just at a longer timescale. It reports
  `INSUFFICIENT` with the reason *no kickoff-time source wired*.
- `guard_coverage.py` is the working counter-example: it enumerates from a
  declared `RULES` dict, not from what it observed.

## The principle

**The expectation must be produced by something that does not depend on the
recorder running.** Anything derived from our own write stream inherits its
blindness — a dead writer produces no rows, and "no rows" then reads as "no
games", which is the failure being detected.

## Where the schedule comes from

ESPN's scoreboard. Not a fresh integration: the `groups` requirement is already
established — **query `groups=80` AND `groups=81` and union the event ids**, or
the schedule silently excludes FCS, which on 2026-09-06 was every live game.

Record `groups` on every row. The parameter nobody set has decided the
population twice in one day.

## Its own timer, its own table

```
game_schedule(
  league, espn_game_id, scheduled_start, actual_state, groups_queried,
  fetched_at, source
)
```

Written by a process whose **only** job is fetching the schedule. It shares no
container, no timer and no code path with any recorder — if it shared one, a
crash would take out both the observation and the expectation, and the
evaluator would see a consistent, silent, wrong world.

Cadence: every 10 minutes is ample. Kickoff times move on the scale of hours.

## What the evaluator asserts

Per league, per interval:

```
expected = games whose scheduled window covers now   (from game_schedule)
observed = rows arriving for that league             (from the tape)

expected > 0 AND observed == 0   ->  ALARM
expected > 0 AND observed > 0    ->  OK
expected == 0                    ->  OK (quiet, correctly)
schedule stale or unavailable    ->  UNKNOWN, never OK
```

**`UNKNOWN` is a state, not a fallback to OK.** An absent schedule must not read
as "no games scheduled" — that is the same absence-as-answer bug one level up,
and it is how the whole class works.

`observed` must be **row arrival**, not a counter the recorder reports about
itself, for the reason in the principle above.

## The recursion, named rather than discovered

If the schedule table can go stale, what watches the schedule?

**It terminates, and here is exactly where.** The evaluator checks
`max(fetched_at)` from the table — that is *data it reads*, not a process it
depends on. A stale schedule is detectable without any additional watcher, and
yields `UNKNOWN`.

**What does not terminate inside our infrastructure: if the evaluator itself
dies, nothing reports.** That is irreducible in-process. It needs a dead-man
switch outside — something that expects a heartbeat *from* the evaluator and
alarms on its absence, on infrastructure that is not ours.

**We do not have that today.** The honest statement is that the last link is
unwatched, not that the chain is closed. Saying so is the difference between a
monitoring design and a monitoring theatre.

## What it would have caught

This table is the spec's real content.

| event | caught? | why |
|---|---|---|
| **Dead container** (2026-09-05 22:08, container-name collision) | **YES** | schedule says games in progress, zero rows arriving. The case it exists for. |
| **One-sided kickoff window** (2026-09-06 20:01) | **Probably** | schedule says in progress from scheduled start; rows for that game stop. Depends on per-game granularity, not just per-league. |
| **Venue freeze** (2026-09-05 17:39) | **NO** | rows kept arriving at full cadence — 1.17M in the hour. Only *prices* froze. This evaluator watches arrival, not movement. |
| **ESPN outage** | **Must not false-alarm** | schedule unavailable → `UNKNOWN`, never ALARM. Getting this wrong makes the monitor worse than nothing. |

**The freeze row is the important one.** This does not replace the value-change
metric (*percent of live markets whose (bid, ask) changed in 10 minutes*, which
read 0.0% through the freeze against a healthy 26–41%). The two detect disjoint
failures: **arrival** versus **movement**. Neither subsumes the other, and
shipping one as though it covers both would leave the freeze undetected while
looking complete.

## Status

Design only. A new production monitor is not mine to authorise. Written because
three people independently needed it and nobody had written down what it is.
