# PULSE v3 replay protocol — registered before the sample exists

**Status: REGISTERED, NOTHING COMPUTED.** Written 2026-08-20 with exactly
**2 signal-recorded games** in `espn_live_*` (1,472 in-game box snapshots,
794 plays) — far below any floor, which is the point: the protocol is fixed
while the data cannot yet flatter anyone. This section may not be edited
after the eval first runs at floor — append below the line.

Operator's framing, honored as the design principle: **"make signal, not
just blindly trade edge."** v3 is measured signal-by-signal, never as a
bundle whose parts can hide behind each other.

## The arms

* **v1** — the incumbent live baseline (pregame price + score + the
  ESTIMATED clock + league sigma). Unchanged, as always.
* **v3a — the exact clock, alone.** Identical to v1 except `minutes_left`
  comes from the venue's own clock (`core/pulse/signals.exact_clock` over
  `espn_live_box_snapshots`), which removes the late-quarter saturation
  hole and makes OT priceable. This is the ONLY gate-eligible v3 arm in
  this registration.
* **Exploratory arms, reported but NOT gate-eligible** (each needs its own
  registration before it may gate): v3b = v3a + pace-decomposed totals
  (possessions vs efficiency splitting the surprise term); v3c = v3a +
  shooting-split volatility context. Their paired diffs print as accruing
  diagnostics so the next registration is written from measurements, not
  hunches.

One input per gate is deliberate. A bundled v3 that passed would not say
WHICH signal earned it; a bundled v3 that failed would bury a good clock
under a bad pace model.

## The join

`espn_game_id ↔ event_slug` via `core.team_mapping` (slug codes → ESPN
abbrevs, the CONN/POR hazard handled where it is maintained) plus the game
date (slug date vs the summary header's ET date). A game that does not join
unambiguously is EXCLUDED and counted in the report — never guessed.

## Point-in-time mechanics

Per game, prefetch every `espn_live_box_snapshots` and `espn_live_plays`
row once, ordered by `first_seen_at`; walk them with the market tick tape
under a two-pointer sweep. At market tick `t`, the signal state is the
newest signal row with `first_seen_at <= t` — the bound the tables were
built for, enforced in the prefetch query and the pointer, never in caller
discipline.

**Staleness fallback, registered**: a clock reading older than **60s** at
`t` (recorder outage, feed stall) makes v3a fall back to v1's estimator
FOR THAT TICK, and the tick is counted in a `fallback_ticks` diagnostic. A
dead recorder must degrade v3 to v1, never poison it — the same refusal
shape as v2's form guard.

## Cohort

Signal-covered games only: ≥1 in-game box snapshot AND joined market ticks.
No mixed cohorts; a game without signal coverage is out of scope, not a
degraded member.

## Metrics (the v2 family, plus the signal-specific ones)

1. **Paired Brier**, clustered by game (C4), v1 vs v3a at every sampled
   tick where BOTH arms price.
2. **Money at price** (C11): the registered PULSE rule at unit size, both
   arms, floors applied per arm.
3. **Coverage gain** — the clock's distinctive value: the count of ticks
   where v1's clock is unusable (saturated late-quarter, OT) but v3a
   prices, with v3a's Brier on exactly that subset reported alone. This is
   where the exact clock either is or is not a signal.
4. **Clock disagreement** — distribution of (estimated − exact) minutes at
   matched ticks: the direct measurement of how wrong the wall-clock
   interpolation has been all along.
5. **ESPN-WP reference line** — Brier of ESPN's own recorded win
   probability at matched instants, beside both arms. External benchmark
   only; never gate-eligible (it is not our model and not tradable).

## Floors and criterion, fixed now

* **Floors: ≥10 signal-covered games AND ≥3,000 paired calibration
  points.** Below either: accruing, counts only. (~5 games this week is
  NO DATA by construction; the eval still runs and prints counts.)
* **PASS** (go-live question goes to the operator): paired Brier diff's
  game-clustered 95% CI excludes zero in v3a's favour at floor, AND v3a's
  money-at-price is not measurably worse than v1's. **FAIL**: floor met,
  CI at or below zero. Anything else: NO DATA.
* On PASS the live flag moves to `MERIDIAN_PULSE_ESTIMATES=v3` with the
  same per-row honesty v2 shipped: rows record what actually priced them
  (`estimates_version='v3'`; a fallback tick's decision row says `v1`),
  and `live_report` already splits by version.

## Runbook

The eval extends `core/pulse/replay_eval.py` with a `--v3` mode (build
gated on the manager's word, per the standing phase discipline; this doc is
the registration it will implement). Rerun on every +5 signal-covered
games, or weekly, whichever comes first; results append below the line
with the archive size at run time.

---

*Registered 2026-08-20, at n=2 signal-covered games. Results append below
this line, never above it.*
