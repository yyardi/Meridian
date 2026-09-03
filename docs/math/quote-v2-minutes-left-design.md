# QUOTE v2 `minutes_left` enrichment — design

Populate the two currently-NULL clock fields on `quote_v2_observations` —
`minutes_left` (Numeric) and `minutes_left_is_estimate` (Boolean) — for the
STATE/LATENESS and GUARDS arms. Design-first per the manager; deploy timing
(land-now vs post-A1) is the manager's call and this doc gives the inputs.

## Reuse, not reinvention

Two clock computations already exist and are pure/session-only. Both are reused
verbatim; nothing new is written except the wiring into `record_cycle`.

- **Estimator (the `is_estimate=True` path)** — `core/live_fv.py`
  `minutes_remaining(period, *, seconds_into_period, ot_number=0) -> Clock`
  (:146). Wall-clock interpolation because `market_snapshots` has no clock;
  `is_estimate=False` only at a period boundary / HT / FINAL; SATURATES late in
  a quarter (`usable=False`, :205-217) — which is exactly the LATENESS window,
  so the exact clock below is the high-value input.
- **Exact venue clock (the `is_estimate=False` path)** — `core/pulse/signals.py`
  `exact_clock(period, clock_seconds)` (:70), read via
  `latest_venue_clocks(session, espn_game_ids, max_staleness_seconds)` (:302),
  joined by `resolve_espn_game(session, event_slug) -> espn_game_id | None`
  (:267). Source table `espn_live_box_snapshots` is in the SAME Postgres the
  quoter already reads; the ESPN recorder fills it out-of-band, so this is a
  SELECT on the quoter's own session — **no in-binary HTTP**.

The seam contract (`core/pulse/signals.py:15-18`, `docs/infra/signal-side.md`
~L202): the exact clock sets `minutes_left_is_estimate=False` on the EXISTING
field — never a parallel exact-clock field.

Reference implementation to mirror: `core/pulse/live.py` `_estimate` (:664-706)
and the per-cycle read (:1361-1400); the recording precedent (how the pair is
stored from DB rows) is `core/game_detail.py` `_context_for` (:419-458).

## Algorithm in `record_cycle`

Per cycle, before building rows:
1. `self._period_starts.setdefault((event_slug, event_period), observed_at)` for
   each obs — first time we see a (slug, period), stamp it with the quoter's own
   `observed_at`; `seconds_into_period = observed_at − period_start`.
2. Resolve `espn_game_id` per `event_slug`, **cached** in
   `self._espn_game_ids` — `resolve_espn_game` scans a 24h window + a
   `team_game_logs` join and is far too heavy for the ≤1s loop, so it is called
   once per event (unresolved events retried on a throttle, e.g. ≥60s, since a
   game is absent from ESPN until it lists). This mirrors PULSE's
   `EventAnchors.espn_game_id` cache.
3. One batch read `latest_venue_clocks(session, resolved_ids,
   max_staleness_seconds=VENUE_CLOCK_STALENESS)` → `{event_slug: ExactClock}`.

Per observation:
- If `is_live` and `event_period`: `clock = minutes_remaining(event_period,
  seconds_into_period=…)`.
- If a fresh `ExactClock` exists for this event: override per `_estimate` —
  OT or regulation-ended → `minutes_left=0.0, is_estimate=False`; else
  `minutes_left=exact.minutes_left, is_estimate=False`.
- Store `minutes_left = Decimal(clock.minutes_left)`,
  `minutes_left_is_estimate = clock.is_estimate`.
- If NOT live or no period (all pregame rows): `minutes_left = NULL`,
  `minutes_left_is_estimate = NULL` (nullable Boolean: no clock ⇒ no
  clock-quality; a small, honest deviation from `game_detail`'s `False` default,
  which used a non-nullable column).

The OT/period indicator the LATENESS arm needs beyond regulation minutes is
already on the row as `event_period`; `minutes_left` carries regulation-minutes
(0.0 in OT, per `exact_clock`).

## The three constraints (manager's inputs), satisfied

1. **Stamp discipline** — `observed_at` stays the quoter's own read-time
   (unchanged from B14); `minutes_left*` are STATE fields, never fed to the
   detector, so reading ESPN state is enrichment like `event_score`, not a
   cross-process clock join.
2. **Off-decision-path** — every ESPN touch is a read on the record path's
   existing session; nothing mutates `_standing` or fills (proof 3 holds
   structurally). Cost control: `resolve_espn_game` is cached per event (not
   per tick) and the venue-clock read is one indexed query per cycle, so the
   record loop's `record_s` telemetry stays within budget. Imports of
   `signals`/`live_fv` are LAZY inside the helper (PULSE's pattern), keeping
   `engine_v2`'s module import graph — and the AST no-order/no-credential
   proof — clean and HTTP-client-free.
3. **Existing field** — the exact clock flips `minutes_left_is_estimate=False`
   on the existing field; no parallel field.

## Proof plan

- Three amendment-10 deploy proofs re-run green (equivalence untouched — the
  clock read is off the compared quoting path; AST still clean via lazy imports;
  off-decision-path holds — reads only).
- New `_selftest_minutes_left`: on ephemeral PG (which has
  `espn_live_box_snapshots` via the espn-signal migration), insert a venue-clock
  row and, with the resolution cache pre-seeded to that `espn_game_id`, assert
  `record_cycle` writes `minutes_left` with `is_estimate=False`; with no venue
  row assert the estimator path writes `is_estimate=True`; pregame asserts NULL.
  (Resolution is stubbed via the cache to avoid the heavy `team_game_logs`
  fixture; `resolve_espn_game` itself is already covered where it lives.)

## Deploy-window analysis — the input for land-now vs post-A1

The window closes at the FIRST OBSERVATION ROW (first WNBA listing, pregame,
possibly days before tip). But **the exact clock only produces values in-game**;
every row between first-listing and first-tip is pregame (`is_live=False`) →
`minutes_left = NULL` regardless of whether this is deployed. So the enrichment
would deploy DORMANT and first produce values at tip-off (Sept 17), after the
window has already closed.

The real trade is therefore about the in-game rows from Sept 17 until the next
allowed deploy:
- **Land-now** (before first listing): in-game rows carry exact `minutes_left`
  from the very first tip. Cost: a pre-listing deploy (its own rebind + full
  re-prove under amendment 11) raced against the board.
- **Post-A1 fallback** (~Sept 26-30, with fv): in-game rows Sept 17→A1 carry
  `minutes_left = NULL` — a disclosed coverage hole the LATENESS gate carries
  exactly as guard-2 carries the fv hole; from the post-A1 deploy on, exact
  clock. The LATENESS arm degrades to `event_period` (Q4/OT) resolution for that
  span, losing the 3:00/2:00/1:00 bands — which is the arm's highest-value
  window (Q4 collects the fattest half-spreads).

**Recommendation:** land-now IF the board shows comfortable runway before the
first WNBA listing (≥ several days) — the LATENESS arm is the PRIMARY arm and
the first ~2 weeks of live games are otherwise a hole in its most valuable
window. If listings look imminent, take the post-A1 fallback rather than race a
binary deploy against the board; the hole is honestly carried and the design
above is ready to deploy the moment the post-A1 window opens. The board read and
the call are the manager's.
