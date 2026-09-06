# Liveness predicate for the live recorder — spec, not deployed

**`core/live_recorder.py:319` takes liveness from `event.is_live`, which is
`event_state.live` and nothing else. On 2026-09-05 that flag went false while
32 games were being played. The recorder correctly recorded nothing, kept a
green heartbeat, and Saturday's late price tape does not exist.**

## The measurement that decides the design

The venue's **own payload** carried the contradiction. `EventState` has
`live`, but also `score`, `period` and `ended` — and those kept arriving:

| hour | rows | `is_live` true | has period | **rescued by period alone** |
|---|---:|---:|---:|---:|
| 09-05 22 | 188,394 | 183,723 | 187,259 | 3,536 |
| 09-05 23 | 12,690 | **2,227** | 10,894 | **8,667** |
| 09-06 01 | 11,620 | **1,530** | 10,614 | **9,084** |
| 09-06 03 | 12,567 | **814** | 11,861 | **11,047** |

**No second source is required.** The fix is local to the same response.

## The predicate

```python
def is_in_progress(event, *, now) -> bool | None:
    """True/False, or None = cannot determine. None must RECORD (fail open)."""
    st = event.event_state
    # 1. `ended` is the ONLY positive evidence of completion, and the only
    #    thing that may stop recording. Nothing else is a stop signal.
    if st and st.ended:
        return False
    # 2. Any of these independently establishes in-progress.
    if st and st.live:
        return True
    # PERIOD IS AN ALLOWLIST, NOT A NON-EMPTY TEST. Measured domain across
    # both leagues: 'NS' (not started), '' (pregame, state block present),
    # 'Q1'..'Q4' (playing). An earlier draft of this spec used
    # `period not in (None, "")`, which read 'NS' as evidence of play and
    # fired on 87 future events including every NFL game six days out. Caught
    # by observing the predicate live, not by review.
    if st and _PLAYING_PERIOD.match(st.period or ""):
        return True
    if st and st.score not in (None, "", "0-0"):
        return True                      # '0-0' is posted pregame
    # 3. Schedule + elapsed, when the state block says nothing at all.
    start = _start_time(event.start_time)
    if start:
        if now < start - PRE_TIPOFF:
            return False                 # genuinely not started
        # ONCE INSIDE THE PRE-TIPOFF WINDOW WE RECORD, through to the end of
        # any plausible game. An earlier draft required `start <= now`, which
        # excluded the whole pre-tipoff window and returned False for a game
        # 15 minutes from kickoff -- failing CLOSED on a window the current
        # recorder already handles correctly. Caught by observing it live.
        return now <= start + MAX_GAME_DURATION
    # 4. No state, no start time. UNDETERMINED.
    return None
```

```python
_PLAYING_PERIOD = re.compile(r"^(Q[1-4]|OT\d*|H[12]|P\d+)$", re.I)
```

`MAX_GAME_DURATION = 6h` — CFB runs 3.5–4h, plus overtime and weather delays.
Too generous costs cheap extra rows; too tight costs unrecoverable tape.

## Why fail open

**Missing data is unrecoverable; extra rows are cheap.** The venue serves no
historical book, so a game we decline to record is gone permanently. A game we
record unnecessarily costs storage and one predicate at read time. The
asymmetry is total, and the current code fails *closed* — the expensive
direction.

Concretely: `None` records. `False` requires positive evidence (`ended`, or a
start time comfortably outside any plausible game window).

## The absence rule this encodes

**A missing `live` flag is not evidence of not-live.** The old predicate read
absence as a negative answer. `ended` is the only field permitted to mean
"stop", because it is the only one that asserts completion rather than merely
failing to assert progress.

## What would have caught it, with no new dependency

```
cycles == 0 AND events_scheduled_in_progress > 0   ->  ALARM
```

`events_scheduled_in_progress` is computable from `start_time` alone, already
in the response. The recorder logs `cycles` every 2 minutes and logged
`cycles: 0` for hours with no alarm.

**This outranks the cross-source ESPN monitor** because it needs no second
provider and would have fired within minutes. The ESPN cross-check is still
worth building — it catches cases where the venue's schedule is also wrong —
but it is the second line, not the first.

Third state required either way: if the schedule itself is unavailable, the
condition is `UNKNOWN`, not `OK`. An absent schedule must not read as "no
games scheduled", which is the same absence-as-answer bug one level up.

## A second default that silently changed the population

`core/feeds/espn_cfb_recorder.py` calls `get_scoreboard(date)` with **no
`groups` parameter**. ESPN defaults to `groups=80` (FBS), so the recorder
cannot see FCS games at all.

Measured 2026-09-06: **0 games recorded in three hours while two FCS games were
live** (TXSO @ PV in the 3rd quarter, SCST vs FAMU delayed). Verified in the
database, not inferred from logs.

Bounded: FCS-vs-FCS is 1.5% of our CFB fill volume. Real, not urgent.

**Fix:** query `groups=80` and `groups=81` and union the event ids — the id
sets overlap for cross-division games, which is a feature, not a collision.
`scripts/build_cfb_game_map.py` already does exactly this, so the precedent is
in the repo.

**And record the parameter wherever it is queried.** The default is the whole
story here, and a future reader cannot tell a deliberate FBS-only query from an
omitted argument. This is the second time in one day the same default cost
something: it also made "all games" and "FBS games" return identical lists,
which read as *no FCS games exist*.

## Status

Specified, not deployed. Prod changes go through the operator. The 15 revived
quote-engine tests pin the current rule; changing the predicate is where that
friction correctly lands.
