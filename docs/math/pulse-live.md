# PULSE live run — registration

**Status: REGISTERED, NOTHING COMPUTED.** This document is written before the
engine's first cycle, and this section may not be edited after data accrues —
append below the line instead.

Module: `core/pulse/live.py` (decision loop) · `core/pulse/live_report.py`
(scoring) · `core/pulse/storage.py` (the `pulse_decisions` tape)

## Why this exists

Everything this system has shadow-traded so far was decided pregame by the
anchor model — 11,273 of 11,283 shadow orders, measured on the deep-dive page.
PULSE was the point of the 200ms recorder, and until now no code consumed that
stream in real time. This engine is the live half: three continuously updated
estimates, shadow decisions with the full game state attached, and position
management in the operator's own model of in-game trading — *capitalize
repeatedly during the game, don't hold to settlement*.

## The three estimates (all existing, none invented here)

1. **Winner** — the anchored win curve (`docs/math/win-curve.md`), the same
   formula the live-FV strip renders. Needs the pregame moneyline mid; without
   one there is no fair value (a 50/50 prior between unequal teams is wrong,
   not neutral — the #16 lesson).
2. **Total** — the tempo projection (`docs/math/live-totals-fv.md`): pregame
   v4 ladder anchor plus a fitted fraction of the scoring surprise, fitted
   per-period residual sd, positioned against every recorded rung.
3. **Spread** — the win curve's margin model at the rung:
   `P(final margin + line > 0)`.

### Spread YES-frame, verified 2026-08-18

The frame was measured against the recorded stream itself, not assumed: take
each event's true final score from its FT ticks, take each spread market's
last decisively priced Q4 book (mid < 0.05 or > 0.95), and compare. **196/196
markets agree that YES settles 1 iff the first team's final margin plus the
stored line is positive.** The same method reproduces the verified V19 winner
frame 37/37.

One methodological artifact is worth recording because it briefly looked like
a counterexample: an earlier query took each market's last tick *with a
two-sided book* and required only an extreme mid — which for
`asc-wnba-la-chi-2026-08-05-pos-7pt5` grabbed a **mid-game** Q4 tick (85-95,
LA −10, priced 0.985) because the FT rows carry NULL books. The market was
pricing the true final, 88-95: LA covered +7.5. The disagreement was the
query's, not the venue's — and the fix (finals from FT ticks) is the method
above.

**Push boundary:** every spread line in the recorded data is a half-point
(zero whole-number lines exist), so `margin + line == 0` has never been
observable and push semantics are unverified. The engine refuses to price a
whole-number spread line rather than guess.

## What the engine does — registered before first run

Per live market, per 1s cycle, from the newest tick:

* **Entry**: a maker limit joining the touch on the side the estimate favours
  (bid for `yes`, ask for `no`), only when the clock estimate is usable, the
  mid is inside [0.05, 0.95], the spread ≤ 0.15, and fractional Kelly
  (`core/kelly_sizing.py`, the strategy config's own thresholds and caps,
  including game and daily exposure) sizes it above the venue minimum against
  the **real stored bankroll** (`core/bankroll.py`, `allow_fetch=False` —
  a missing or stale reading refuses entries, never a default). At most 3
  open positions or resting entries per event.
* **Entry management**: the limit rests where it was born — no chasing — and
  is withdrawn the moment the current estimate no longer clears zero at that
  price.
* **Exit**: the moment an entry fills, an exit limit rests at entry ± 5¢ (the
  profit target). If the model's own estimate crosses back through the entry
  by 10¢, the exit reprices to the touch (a cut, still a limit; fills remain
  price-based — a dead clock cannot panic a position). When an exit fills the
  market may be re-entered: that is the roll.
* **Fallback**: a position whose exit never fills rides to settlement and is
  scored money-at-price there (C11). The fallback is reported separately from
  round trips so neither hides the other.

Fill rule: a resting order fills when a NEWER observation's mid crosses it —
the adverse-selection study's endpoint rule, the quote engine's rule, with the
same signed bias. **A loss here is trustworthy; a profit is an upper bound and
authorises nothing** — and a round trip needed two optimistic fills, so its
profits are upper bounds twice over.

Every decision row carries the full context at decision time: score, margin,
period, clock estimate (labelled), tempo (total so far, projected total,
residual sd), market bid/ask, fair value, net edge, action, limit price, size,
and the bankroll the size was computed against. Rows land in
`pulse_decisions` with the game tape's join keys (`event_slug`,
`market_slug`, `decided_at`) and a `phase` marker (`in_play` / `pregame`) for
the tape view's seam.

## Floors and verdicts, fixed now

* **Floors: ≥ 100 filled entries AND ≥ 10 distinct games with a fill.** Below
  either, `core/pulse/live_report.py` prints NO DATA with counts only. No
  performance claim below the floor; no metric added after data accrues
  counts as registered.
* **Primary metric**: per-$ round-trip capture, clustered by game (C4),
  settlement-scored rides reported beside it (C11). **PASS** (reopens a
  question, authorises nothing): clustered mean > 0 with the 95% CI excluding
  zero, at floor. **FAIL**: floor met, CI at or below zero. Anything else is
  NO DATA.
* No existing gate changes. The anchor model's registrations are untouched.

## Deliberate limitations, stated up front

* The loop reads each market's newest tick once per second; sub-cycle touches
  and round trips are invisible. This undercounts both fills and
  opportunities; the direction of the fill bias is stated above.
* Minutes remaining is the live-FV strip's estimate, exact only at period
  boundaries, suppressed when unusable (OT, exhausted clock) — no decision is
  made on a suppressed clock.
* Daily exposure tracking is in-process (resets on restart). Game exposure is
  recomputed from open state and does not survive a restart either: a
  restarted engine re-enters fresh. Both are shadow-run bookkeeping, not
  venue exposure.
* Anchors are pregame quantities pinned at first sight; a game with no
  pregame quote or no v4 ladder trades nothing on the estimates that need
  them.

## Ops notes

* Compose overlay: **`docker-compose.pulse.yml`** —
  `docker compose -f docker-compose.yml -f docker-compose.pulse.yml up -d pulse-engine`.
  Deploy is operator-gated between slates; fold into the main file after a
  watched slate.
* Heartbeat service name `pulse_engine`, defined in the engine module. Add to
  `APP_DB_SERVICES` when the overlay actually deploys — listing an undeployed
  service would read DEAD on every host (the fill-watcher precedent).
* Env vars, read with defaults: `MERIDIAN_PULSE_INTERVAL_SECONDS` (1),
  `MERIDIAN_PULSE_SETTLE_EVERY_SECONDS` (600), `MERIDIAN_PULSE_PROFIT_TARGET`
  (0.05), `MERIDIAN_PULSE_STOP_ADVERSE` (0.10),
  `MERIDIAN_PULSE_HOLD_LOG_SECONDS` (60),
  `MERIDIAN_PULSE_MAX_OPEN_PER_EVENT` (3).
* Model lives in `core/pulse/storage.py` beside its writer (the quote
  engine's precedent); migration `e6f2a8b93c51` chains `d2a6f18c40b7`.

---

*Registered 2026-08-18, before the first cycle. Results append below this
line, never above it.*
