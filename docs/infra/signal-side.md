# The signal side — design (Phase 1) and build (Phase 2)

**Status: BUILT (Phase 2, 2026-08-19), recording awaits operator deploy.**
Design approved by the manager as written; the Phase 2 appendix at the
bottom records what shipped and the registration. Original design below,
unedited.

**Status at design time: DESIGN, nothing built.** PULSE today sees score, period, an
estimated clock, tempo-from-score, and price. This designs the feed that
lets it see the game: live boxscore, play-by-play, who is on the floor, and
the pregame injury context — recorded point-in-time first, consumed by a
model only behind the same replay gate v2 lives behind.

## Endpoint scout (measured 2026-08-19, receipts inline)

One endpoint carries everything. `site.api.espn.com/.../wnba/summary?event=<id>`
for a finished game (401857152, LA@CON 2026-08-18) returned in one ~434KB
payload:

* **Team boxscore** — the full 12-stat block per team, including
  `fieldGoalsMade-fieldGoalsAttempted`, 3PT made-attempted and pct, FT,
  OREB/DREB, assists, steals, blocks, turnovers.
* **Player boxscore** — per athlete: MIN, PTS, FG, 3PT, FT, REB, AST, TO,
  STL, BLK, OREB, DREB, PF, +/− plus `starter`, `didNotPlay`, `ejected`,
  `reason`, `active`.
* **Plays, embedded** — 397 for that game, each with: play `id`,
  `sequenceNumber`, `period`, **game clock** (`clock.displayValue`),
  **`wallclock`** (ESPN's own UTC stamp per play), `type` (56 Substitution
  events, Personal/Shooting Foul, shot types with `shootingPlay`/
  `scoringPlay`/`pointsAttempted`, coordinates), `participants` (athlete
  ids), and running `homeScore`/`awayScore`.
* **`winprobability`** — ESPN's own model, one entry per play. A free
  external benchmark to score PULSE calibration against, at zero build cost.
* **`injuries`** — the summary-level injury block (2 entries that game).

Also measured:

* The standalone `site.api/.../playbyplay?event=` endpoint returns **2 bytes**
  for WNBA — dead. (`cdn.espn.com/core/wnba/playbyplay` works, 425KB, but is
  redundant given the embedded plays.) **The summary is the only endpoint
  this design polls per game.** Live-game detection reuses the scoreboard the
  live-odds-recorder already understands (its `state` field is the house's
  authoritative live signal).
* Scoreboard `displayClock` on **post** games reads a junk `10:00` — per-play
  clocks are the trustworthy ones. Live `displayClock` behaviour goes on the
  first-live-game verification checklist below rather than being assumed.
* House constraints honoured: ESPN 403s custom user agents (send library
  defaults — `core/feeds/espn_client.py` already does); stats.wnba.com
  refuses datacenter IPs and is not used; ESPN hosts have their own token
  budget separate from Polymarket's 20 req/s.

## (a) The poller: `espn-live-recorder`

A new compose-overlay service in the house pattern (own container, local
Postgres, `restart: unless-stopped`, alembic upgrade on start, heartbeat row,
no credentials — there are none to mount; ESPN is unauthenticated).

* Scoreboard poll every 30s (one small call) → the set of live games and
  their state. Off-slate, that is the service's entire traffic.
* Per live game: one summary call every **10s**. Budget: 2 concurrent games
  = 0.2 req/s + scoreboard ≈ **0.24 req/s against ESPN_RPS=3** — under a
  tenth of the budget the live-odds-recorder already runs unchallenged.
  Bandwidth ~43KB/s per live game.
* Writer discipline: this service is a READER of ESPN and a writer only of
  its own tables below. It does not touch `market_snapshots`,
  `pulse_decisions`, or anything of the tick recorder's — same isolation the
  quote and pulse engines keep.

## (b) Point-in-time storage — the non-negotiable

**Every row is stamped `first_seen_at` = the instant OUR poller observed it.**
ESPN's `wallclock` is stored as *data* beside it, never as the knowability
stamp: plays arrive in batches with unknown lag, and the (wallclock,
first_seen_at) pair makes that lag a measurable quantity instead of a silent
bias. A future replay may use a row iff `first_seen_at <= t` — the same
discipline `market_snapshots.captured_at` and `core/features` already carry.
Storing whole 434KB summaries per poll (~390MB/game) is rejected; the tables
below keep a game to roughly 1-2MB:

* **`espn_live_plays`** — append-only, one row per play id (INSERT ...
  ON CONFLICT DO NOTHING; a play never updates, and re-observed plays are
  no-ops). Parsed columns: espn_game_id, play_id, sequence, period,
  game_clock_seconds, wallclock, type_id, type_text, team_id, athlete ids,
  scoring_play, score_value, points_attempted, shooting_play, home_score,
  away_score, text; raw play JSONB; `first_seen_at`. ~400 rows/game.
* **`espn_live_box_snapshots`** — one row per (game, poll): parsed TEAM
  stat columns for both sides plus the summary status block's period and
  game clock. ~900 rows/game, no raw payload.
* **`espn_live_player_snapshots`** — parsed player rows at 60s cadence (not
  every poll): minutes, pts, shooting splits, PF, +/−, `starter`, `active`,
  `ejected`, `didNotPlay`, `reason`. ~2-3K rows/game. Substitution plays are
  the fine-grained on/off ground truth; these snapshots are the coarse
  cross-check and the foul-trouble/availability source.
* **`espn_live_win_probability`** — append-only per play id:
  home_win_pct, `first_seen_at`. The free benchmark.
* **`espn_live_injury_observations`** — the summary injuries block, one row
  per (game, athlete, status) ON CHANGE only, `first_seen_at`. Raw material
  for the availability delta — **record-only** (see (c)).

Retention: these are small next to the tick stream (which writes ~657K
rows/day); no special retention needed initially, revisit with
`core/retention.py` if player snapshots grow tiresome.

## (c) The first signal set — pure functions, not materialized rows

Signals are **computed at read/replay time from the raw tables**, never
stored: a materialized signal freezes its own bugs into the archive, while
raw-plus-stamps lets every future replay recompute under the current
definition. (The one exception to "nothing derived is stored" is the parsed
columns above, which are transcriptions, not computations.)

Ranked by expected value to PULSE:

1. **The exact game clock** (box snapshot status, ≤10s stale). Today's
   minutes-left is wall-clock interpolation that saturates late in quarters
   and forces FV suppression exactly when in-game prices move most (the
   `Clock.usable=False` hole), and OT is unpriceable. An exact clock removes
   the estimate's saturation, prices late-Q4, and makes OT modelable. This
   is the single highest-value signal and it is nearly free.
2. **Pace decomposition** — cumulative possessions per team from plays
   (FGA − OREB + TO + 0.44·FTA), so the totals projection can separate
   "high because fast" from "high because hot" — pace persists, shooting
   luck mean-reverts. Today's surprise coefficient treats them identically.
3. **Team shooting splits by period** (from `shooting_play` aggregation):
   the efficiency half of the same decomposition, plus 3PT-variance context
   for the volatility input.
4. **Foul trouble / star on-off** (player PF + Substitution events +
   starter flags): recorded from day one by (b); the derived signal ships
   after 1-3, because it needs on/off bookkeeping that deserves its own
   tests.
5. **Scoring runs** (windowed score deltas over plays): recorded trivially;
   consumption is explicitly hypothesis-shaped (the fade family is CLOSED —
   any run-based entry rule needs its own registered gate).
6. **Availability delta** (pregame injury report vs actual
   starters/minutes/DNP): **RECORD-ONLY.** Builder B's oracle arm has since
   delivered its verdict — even the hindsight upper bound on roster
   awareness has a game-clustered CI crossing zero ([−6.63, +16.85] pts,
   `docs/math/injury-delta.md`) — so nothing here consumes availability
   until B's accruing measurement separates from zero. B owns the pregame
   injury features; this design only records the live-side observations
   that would join against them.

## (d) Integration contract — PULSE v3, replay-gated

Identical shape to v2, because v2's discipline held:

* Signals enter as `ArmParams`/`EventAnchors`-style inputs; decision rows
  carry `estimates_version='v3'`; `live_report` already splits by version,
  so generations cannot blend.
* **Go-live criterion**: `core/pulse/replay_eval.py` grows a v3 arm that
  replays from the point-in-time signal tables (`first_seen_at <= t`,
  enforced in the query); v3 replaces the live default only if the paired
  clustered comparison beats the incumbent under the same criterion family
  v2 registered — CI excluding zero in v3's favour at ≥10 games, money at
  price not worse. Until then `MERIDIAN_PULSE_ESTIMATES` stays put.
* No gate changes anywhere; new accruing rows are registered in the Phase 2
  doc before the first poll.
* **The archive is the point.** The recorder starts writing the moment it
  deploys, before any model consumes a byte — every recorded game is a
  future replay game, and v3 is testable exactly as fast as the archive
  grows.

## First-live-game verification checklist (Phase 2, before trusting live data)

Measured on a finished game above; these need one live game to confirm:

1. Summary during play: does `plays` grow incrementally? Does the boxscore
   update? At what cadence relative to our 10s poll?
2. Live `status.displayClock`/period on the summary header — real, or the
   scoreboard's post-game junk?
3. `active` flag semantics on player rows (on-floor-now vs on-roster) —
   cross-check against Substitution plays.
4. Play `wallclock` vs our `first_seen_at`: measure the feed lag
   distribution; it bounds how "live" any pbp-derived signal can claim to be.
5. The injuries block during play: static or live-updated on an in-game exit?

Phase 2 scope if approved: the recorder + the five tables + signals 1-3 as
pure functions with tests, registration doc, compose overlay, and the live
checklist run on the first slate the operator deploys against. Signals 4-6
accrue raw material from day one and ship as functions later.

---

## Phase 2 — shipped 2026-08-19

* **Recorder**: `core/feeds/espn_live_recorder.py`, service
  `espn_live_recorder`, overlay `docker-compose.espn-live.yml`. The
  heartbeat beats EVERY cycle — `rows_written=0, game_live=False` overnight
  is IDLE, not DEAD; /api/status judges every service that has ever beaten
  (the B11 rule), so skipping idle beats would read the whole header STALE.
* **Tables**: migration `a9b4e6d13f75` — plays (append-only by ESPN play
  id), box snapshots (one per poll; carries `season_type` from the NESTED
  spelling, the #25 trap, and `clock_source` so header-vs-play clock
  provenance is queryable), player snapshots (60s), win probability
  (append-only), injury observations (unique per game/athlete/status —
  on-change-only structurally, and RECORD-ONLY per B's delivered oracle
  verdict).
* **Signals 1-3**: `core/pulse/signals.py`, pure functions; the loaders put
  `first_seen_at <= t` in the SQL, not in caller discipline. No
  materialization — one resolution of each quantity, ever (the
  analytics-path lesson, docs/infra/analytics-path.md, inverted).
* **Clock integration contract** (agreed with the tape view's author): when
  the exact clock reaches the FV path it flips
  `minutes_left_is_estimate=False` on the EXISTING field — never a parallel
  exact-clock field. The UI's "est." labels and OT rendering then correct
  themselves with zero UI changes.
* **The #25 guard**: a live game whose summary parses to zero rows logs
  `espn_live_empty_payload` at ERROR level — the quiet-failure shape made
  loud. On the first-live-game checklist alongside the five questions above,
  answered by `python -m core.feeds.espn_live_recorder --checklist`.
* **Registration of accruing rows**: the five tables are observations, not
  measurements — no verdict is ever computed from them directly. Any model
  consumption is PULSE v3 behind §(d)'s replay gate, with per-row
  `estimates_version` labelling. No existing gate changed. Recording starts
  the moment the operator runs the overlay; the archive is the deliverable.
