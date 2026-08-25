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

## 2026-08-21 — SIZING SEMANTICS CHANGED MID-ACCRUAL (operator decision)

Any analysis of the tape MUST split on this date. Rows decided before the
2026-08-21 pre-tip deploy carry LIVE-FAITHFUL sizing: exposure caps
(position / game / daily / absolute-dollar) shrank or blocked entries, and
on 2026-08-20 the daily cap — which then never released returned money —
silently blocked TWO ENTIRE GAMES of decisions (the 02:00Z pair; zero rows;
PR #48's receipts).

Rows decided after the deploy carry SHADOW sizing: `contracts`/`stake_usd`
are the model's full desired fractional-Kelly size; exposure caps never
shrink or block. When a cap WOULD have bound in live mode, the row says so —
`binding_constraint` holds the cap's label and `capped_stake_usd` /
`capped_contracts` hold the live-faithful size (0 = the cap would have
blocked entirely; NULL = no cap would have bound). Model-intent gates (no
edge, edge under threshold) and venue realities (min bankroll, venue minimum
quantity on the desired size) still refuse; the per-event position-count cap
(3) still binds as a tape-sanity control.

Approximation, stated: the capped annotation is evaluated against the SHADOW
book's exposure. It is exact until the first moment a cap binds and the
books diverge; after that it approximates what a live book would have
carried. The live-faithful subset is therefore indicative, not a replay —
a true live replay recomputes from the tape.

Live-mode enforcement is one env flip (`MERIDIAN_PULSE_ENFORCE_CAPS=1`),
under which the release-on-return fix (money returns to the daily budget on
entry withdrawal and exit fill; rides stay held) governs the committed-money
counter. The same release logic runs in shadow mode too, keeping the
annotations' daily-cap reference honest.

### 2026-08-22 addendum: the count cap annotates too

Operator follow-up to the 2026-08-21 semantics change: the per-event
position-count cap (3) now also annotates rather than binds in shadow mode —
the market past the cap enters at full desired size with
`binding_constraint = 'max_open_per_event'` and capped size 0 (live blocks
before sizing, so the live-faithful size is zero regardless of what the
dollar caps would have said; the count label wins as the stronger
statement). Live mode blocks outright, unchanged. With this, every
exposure-shaped control in the shadow engine is annotate-only: the tape is
the model's full intent, and "what live would have done" is a filter, not a
gap.

## 2026-08-23 — RULING: the registered quantity across the sizing change

Both tape floors appeared crossed on raw counts (575 entries / 12 games).
The ruling, as registration owner, on what the 2026-08-21 semantics change
did to the registered measurement:

**The metric survived; the population did not.** The registered per-$
metric (capture/cost per contract; rides at settlement) is SIZE-INVARIANT
per fill — fills are price-based and per-fill outcomes do not depend on
contracts. So the semantics change cannot bias the metric. What it changed
is WHICH entries exist: post-change, the tape contains entries live sizing
would have blocked.

**The registered continuous population is the live-faithful subset**: every
pre-change entry (live-faithful by construction) plus post-change entries
where no cap bound (`capped_stake_usd IS NULL`) or the cap merely shrank
(`> 0` — live entered smaller; identical per-$ outcome). Cap-blocked
intents (`capped_stake_usd = 0`) are excluded from the registered series.
`core/pulse/live_report.py` implements this as its default population; the
full-intent view renders WITHOUT verdict language, structurally.

**Registered verdict under the ruling: NO DATA — the floor is NOT crossed.**
The live-faithful population holds **52 filled entries of the 100 floor**
(10 games). The 575-entry count that appeared to cross was the full-intent
tape. The registered accrual continues; no verdict attaches at 52/100.

**The full-intent series** (from 2026-08-21, its own dated start) is
descriptive: 336 fills / 12 games, round-trip capture +8.5¢/$
[+6.4, +10.6] (G=7), rides small and negative. Two reasons no one may act
on it: it is outside the registration, and the fill rule's optimism is
doubled on round trips — that +8.5¢ is an upper bound of upper bounds. If
the operator wants the full-intent tape gate-eligible, it takes a NEW
registration with fresh floors dated from 2026-08-21 — appendable here on
request.

Caveats inherited: post-change cap annotations were evaluated against the
shadow book (the stated approximation), so the post-change live-faithful
subset is indicative, exact until the first cap divergence per day.

## 2026-08-23, later — RULING AMENDED after D's audit; verdict unchanged: NO DATA

D's corrected facts, accepted: the floor counts FILLED entries (336 pooled,
not 575 decided), and the regime boundary is a TIMESTAMP — first annotated
entry 2026-08-21 23:33:26.867748Z — not annotation-presence (21 post-change
entries carry NULL because no cap bound; a presence marker misfiles them
into the pre-change era). The boundary correction does NOT alter the
population filter above: a NULL annotation means "live would have entered
exactly so" in both eras, which is why NULL rows belong to the registered
population regardless of era. It alters only era-split bookkeeping, D's
decomposition of which is adopted: (a) caps-bound era 26 filled / 7 games;
(c) post-change live-faithful 26 filled / 4 games; (b) post-change
full-intent 310 filled / 6 games.

**The verdict question, answered from the registration text.** The floors
row reads: "≥ 100 filled entries AND ≥ 10 distinct games with a fill.
Below either, counts only." The only basis that reaches 100 filled is the
POOLED mixed-semantics tape (336) — and the 2026-08-21 dated note above
commands: "Any analysis of the tape MUST split on this date." Pooling
full-intent rows with live-faithful rows into one scored series is
precisely the analysis that note forbids. The registered live-faithful
series — which MAY pool across the date, because the population filter
removes exactly what changed (which rows exist and at what size; the per-$
metric is size-invariant) — holds 52 filled. Every honest reading lands in
the same place: **NO DATA. The floor has not been validly reached by any
population the registration covers.** No verdict tonight, and that is the
registration working, not failing: the candidate numbers have now been seen
by three parties, which is exactly the contamination the floor exists to
make irrelevant.

**Forward, two series:**

1. The **registered live-faithful series continues accruing** (52/100
   filled, 10 games) unchanged. Post-change it accrues slowly by nature —
   full-intent sizing means most entries carry a binding annotation — and
   that is fine; slow honest accrual beats fast contaminated accrual.
2. The **full-intent series gets the fresh registration below**, gating
   ONLY on games played after its registration date. The six existing
   full-intent games (310 fills, and a seen +8.5¢/$ that flatters them)
   are DESCRIPTIVE CONTEXT PERMANENTLY — they can never enter the gate,
   because their numbers have been seen. Discarding six good-looking games
   from the gate is the price of having peeked; the registration pays it
   without complaint.

## Full-intent series — registration (2026-08-23, before its games exist)

* **Population**: all entries with `decided_at` after 2026-08-23 12:00Z
  (this registration's timestamp precedes every eligible game; the six
  prior full-intent games are excluded above). Full-intent sizing
  semantics as deployed 2026-08-21; per-row `estimates_version` labelling
  applies as everywhere.
* **Metric**: identical to the parent registration — per-$ round-trip
  capture clustered by game (C4), rides at settlement (C11) reported
  separately, fill-rule optimism caveat doubled on trips.
* **Floors**: ≥ 100 filled entries AND ≥ 10 distinct games with a fill,
  counted STRICTLY from the population above. Below either: counts only.
* **PASS** (reopens a question, authorises nothing): clustered round-trip
  capture > 0 with the 95% CI excluding zero at floor, at the same time as
  the ride leg not being measurably worse than flat. **FAIL**: floor met,
  CI at or below zero. Anything else NO DATA.
* No metric may be added after data accrues; results append below the
  results line of this document with dated rows, as ever.

## 2026-08-23 — THE v3 REGIME (registered BEFORE the deploy it governs)

Operator decision: the live engine's estimates flip to v3. This note is
written before the deploy, so the third semantics change of this tape is
deliberate where the first was a bug and the second was a rescue.

**Population marker**: rows with `estimates_version = 'v3'`, which begin at
the deploy instant (target: before 19:30Z 2026-08-23, ahead of the Sunday
slate). Per-row honesty as ever — a tick where the venue clock is missing
or stale (>60s) prices with the v1 estimator and its row says `v1`; the
engine mode is not the row label.

**What changes**: `minutes_left` comes from the venue's own clock (the
signal archive's `espn_live_box_snapshots`, resolved per event by the same
team-mapping join the replay eval registered), so
`minutes_left_is_estimate = False` on v3 rows — every "est." label on the
tape and UI corrects itself per the standing seam contract. The
coverage region — late-quarter ticks where the wall-clock estimator
saturates and v1 must abstain — is now PRICED live. Overtime remains
unpriced: no OT model is registered, and the venue clock does not change
that.

**What does NOT change, stated so nobody re-derives it**: sizing semantics
are untouched by an estimates flip. The live-faithful registered series
and the freshly-registered full-intent series both CONTINUE uninterrupted
across this boundary — their populations are defined by sizing annotations
and timestamps, not by which estimator priced a row. Scoring already
splits by `estimates_version`, so v1-priced and v3-priced rows never blend
in a performance number.

**What v3 consumes from the signal archive — one field, said plainly**:
the venue CLOCK (period + seconds remaining, from the box snapshots).
Nothing else. Recorded but UNCONSUMED, so nobody later assumes the model
sees more than it does: team shooting splits, per-player box lines (foul
trouble, minutes, on/off raw material), substitution and every other play
event, pace/possession counts, ESPN's own win probability (benchmark
only), and the injuries block (record-only by B's oracle verdict). Each of
those enters the model only through its own future registration — v3d
(entry discipline, registered 2026-08-23) being the first candidate, and
it consumes no new field either.

**Basis for the flip**: the v3a at-floor read (docs/math/pulse-v3-protocol.md,
2026-08-23): calibration PASS at floor on both registered clauses, with
the trading caution recorded there and addressed separately by the v3d
registration — the flip adopts the better BELIEFS; it changes no entry
rule.

## 2026-08-24 — STOP RULE CHANGED: the #9 EV stop (deploys with PR #67's rebuild)

Registered first (docs/math/pulse-ev-stop.md), built second, per the
standing order. From the deploy: the stop fires when FAIR VALUE falls to
the position's entry price (edge exhaustion, ledger #9's own sentence, no
tunable) instead of waiting for 10¢ of believed-lost value past the entry
(the sunk-cost-anchored rule). Per-row regime marker: exit `reason` reads
'ev_stop' under the new rule, 'fv_adverse' under the old — the tape
self-describes. Mechanical reversion is one env flip
(MERIDIAN_PULSE_STOP_RULE=adverse). Sizing populations untouched; the
round-trip series' rule regime splits on the reason column.
