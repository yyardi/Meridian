# Per-cycle heartbeats — how "dead" stopped being deniable

Built 2026-08-05, as the fix for
[B11](../findings.md#b11-in-detail--three-failures-stacked): the 200ms recorder
was dead for 23 hours and every reader called it "idle between games". Cost: 2
games of unrecoverable tick data.

## The mechanism

Every long-running writer upserts **one row** in `service_heartbeats` on
**every cycle, game or no game**: service name, `beat_at` (the database's own
clock, so a skewed container can't report itself alive into the future), the
interval it is currently on, cycle duration, and rows actually written. One row
per service, updated in place — the table never grows and the egress cost is
one tiny statement per cycle.

Each writer beats into **the same database it writes data to**. That is the
point, not a convenience: a heartbeat that goes to a different database than
the data can be alive while the data path is dead (B11's exact geometry, where
`/api/status` watched Supabase and the recorder wrote local).

| service              | beats every                  | database            |
|----------------------|------------------------------|---------------------|
| `pregame_recorder`   | 15–60 min (its own cadence)  | app DB (Supabase)   |
| `live_recorder`      | 200ms live · 120s idle       | **local** Postgres  |
| `live_odds_recorder` | 15s active · 300s idle       | app DB (Supabase)   |
| `scheduler`          | 20 min                       | app DB (Supabase)   |

## The rule (one definition: `core/heartbeat.py::verdict`)

* **DEAD** — beat older than **3× the interval the writer itself last
  reported**, regardless of game state. Never beaten counts as dead: the cost
  asymmetry (a missed outage loses games permanently, a false alarm costs a
  glance) rounds ambiguity down. "Idle" is only claimable *with* a fresh beat.
* **DEGRADED** — a live game, a fresh beat, and **zero rows** over the
  reader's window (5 min of local ticks). Alive-and-writing-nothing is the B1
  lesson — assert on outputs, not exit codes — and it is the state B11 sat in.
* The 3× rule has a **30s floor** (`MIN_STALE_SECONDS`): 3 × 200ms = 600ms
  would flap on any GC pause. The floor is far below every real outage and far
  above every real hiccup.

Both readers — `scripts/health.py` and `/api/status` — import this one
function, so they cannot drift apart. `/api/status` reads the app DB's beats
in its existing single round trip and the live recorder's beat from local
Postgres (`MERIDIAN_LOCAL_DATABASE_URL`, default `localhost:5433`).

## What it deliberately does not do

* **No alerting here.** This layer only makes silence *legible*. The looking
  is [the alerter](alerter.md) (added 2026-08-07), which evaluates these
  verdicts every 5 minutes and pushes transitions to the phone.
* **The scheduler's `rows_written` is NULL**, not 0 — its jobs report through
  `_safe`, and a fabricated zero would read as "measured, produced nothing".
* Per-cycle `rows_written` from the live recorder can legitimately be 0 on a
  write-batch boundary; the DEGRADED rule therefore judges rows over a 5-minute
  window, never a single beat.

## Rollout note

A container running pre-heartbeat code shows `NEVER beaten — DEAD` until it is
rebuilt (`docker compose up -d --build`). That is intended: the check refuses
to vouch for a writer it cannot hear.
