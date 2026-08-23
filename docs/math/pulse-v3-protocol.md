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

## First run — 2026-08-20, n=2, NO DATA (the protocol working)

The eval shipped the same day (built after the manager's go; the machinery
is tested and waiting for game 10). Run off-prod against the restored
`meridian_eval` copy plus a delta pull of the signal tables. Verbatim:

```
signal-covered games          : 2
paired calibration points     : 6,370
Brier v1: 0.15590   Brier v3a: 0.12732
paired diff (v1−v3a), clustered: +0.02858  95% CI [-0.58893, +0.64609]  (G=2)
coverage gain (v1 suppressed, v3a priced): 6,456 ticks, Brier 0.10792
OT ticks unpriced by both (no registered OT model): 0
stale-clock fallback ticks    : 18
clock disagreement (est−exact minutes): n=6,352  p50=-1.04  p90=+0.00  max=-6.58
ESPN WP reference (matched winner ticks, n=437): espn 0.03863 | v1 0.01808 | v3a 0.01921
[v1] entries 157 | fills 67 | trips 62 | rides 5 | games 2 | BELOW FLOORS
[v3] entries 126 | fills 87 | trips 72 | rides 15 | games 2 | BELOW FLOORS

VERDICT: NO DATA
```

NO DATA is the verdict and the CI at G=2 is honestly enormous — nothing
here gates anything. Two diagnostics are worth recording at any n:

* **The coverage hole is half the tape.** 6,456 ticks — as many as the
  paired set — are ticks v1 must suppress (saturated estimator) while the
  venue clock lets v3a price, and v3a's calibration there (0.108) is fine.
  Whatever the eventual paired verdict, the exact clock's main value may be
  the ticks v1 cannot price at all, which the paired Brier cannot see by
  construction.
* **The estimator's bias is now a number**: the wall-clock interpolation
  runs a median 1.04 minutes FAST (max 6.6) against the venue clock —
  the long-suspected direction, measured for the first time.

Rerun on every +5 signal-covered games, per the runbook.

## First at-floor read — 2026-08-23, n=11: VERDICT PASS (by hairs, both clauses)

All three of the night's games recorded; both floors cleared (11 ≥ 10 games,
31,955 ≥ 3,000 paired points). Run off-prod on the restored copy. Verbatim:

```
signal-covered games          : 11
paired calibration points     : 31,955
Brier v1: 0.17910   Brier v3a: 0.14088
paired diff (v1−v3a), clustered: +0.03821  95% CI [+0.00006, +0.07637]  (G=11)
coverage gain (v1 suppressed, v3a priced): 34,080 ticks, Brier 0.12815
stale-clock fallback ticks    : 43
clock disagreement (est−exact minutes): n=31,912  p50=-0.90  max=-8.50
ESPN WP reference (matched winner ticks, n=2,370): espn 0.09324 | v1 0.11494 | v3a 0.11719
[v1] entries 978 | fills 515 | trips 466 | rides 49 | per-$ -0.0447 [-0.0969, +0.0076]
[v3] entries 842 | fills 602 | trips 520 | rides 82 | per-$ -0.0930 [-0.1445, -0.0416]
paired trading diff (v3a−v1), game means: -0.0622  95% CI [-0.1285, +0.0041]

VERDICT: PASS (go-live question goes to the operator)
```

**Implementation disclosure, before the verdict is read**: the shipped
verdict property checked only the Brier clause; the registration's second
clause ("money-at-price not measurably worse") was unimplemented. Fixed at
this read — the paired trading diff is now computed, printed, and gated on —
and the verdict on this data is unchanged by the fix. The gap and fix are in
the same PR as this row.

**The two-sided reading, stated plainly:**

* **Clause 1 (calibration): met, barely.** The paired Brier CI's lower
  bound is +0.00006 — six hundred-thousandths above zero. The point
  estimate is substantial (+0.038, a 21% Brier reduction) and reproduces
  the n=2 direction, but the interval essentially touches zero. A PASS by
  the registered letter; nobody should read it as emphatic.
* **Clause 2 (trading): met, barely, from the other side.** v3a's own
  trading is decisively negative (−9.3¢/$ CI excluding zero) and the
  paired diff's point estimate is −6.2¢/$ worse than v1; its CI reaches
  zero at +0.41¢. "Not measurably worse" holds by the registered letter.
* **The diagnostics explain the tension.** The coverage region — 34,080
  ticks v1 cannot price, MORE than the whole paired set — is where v3a's
  extra trades live (602 fills vs 515, 82 rides vs 49), and late-game maker
  fills are the most adversely selected fills there are. The exact clock
  makes the model's BELIEFS better everywhere; the registered naive entry
  rule then walks those better beliefs into the endgame's worst
  microstructure. Better sight, same legs.
* ESPN's reference WP beats both arms on matched late-game winner ticks at
  this n (0.093 vs 0.115/0.117) — flipped from the n=2 read; matched ticks
  are heavily endgame; not gate-relevant, recorded for honesty.

**What PASS means here**: the go-live question goes to the operator, per
the registration — for the ESTIMATES. The trading diagnostics
independently say the coverage region needs its own entry discipline
before anyone celebrates: that is the next registration's subject
(protocol §arms — one input per gate), designed from these numbers, not
ahead of them.
