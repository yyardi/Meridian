# PULSE v3d — coverage-region entry discipline (registration)

**Status: REGISTERED, NOTHING BUILT, NOTHING COMPUTED.** Written 2026-08-23
~04:30Z, before implementation exists and before any v3d number can be
known. Per protocol #38's rule: one input per gate. This section may not be
edited after the eval first runs at floor — append below the line.

## The hypothesis, and where it came from (stated, not hidden)

The v3a at-floor read (docs/math/pulse-v3-protocol.md, 2026-08-23 row)
found: beliefs improved everywhere — including the 34,080-tick coverage
region v1 cannot price (v3a Brier 0.128 there) — while v3a's TRADING was
decisively negative (−9.3¢/$) and worse than v1 in point (−6.2¢/$ paired).
The diagnosis written in that row: *better sight, same legs* — the naive
maker entry rule walks improved beliefs into the endgame's adverse
selection, where late-game fills are the most informed flow there is.

The hypothesis is therefore post-hoc (formed from seen diagnostics); the
TEST below is pre-registered forward. That ordering is stated because it is
the whole point.

## The rule — zero tunable parameters, deliberately

**v3d = v3a's estimates everywhere; NEW entries only where v1's own clock
estimator is usable.** Exits, stops, and holds keep operating in the
coverage region (an open position is always managed); only entry
eligibility is gated, and the gate is the PRE-EXISTING `Clock.usable`
boundary — the exact line that defines the coverage region — not a fitted
threshold. No parameter was chosen after seeing data, because there is no
parameter.

This isolates one question: **is v3a's trading deficit the coverage
region?** If v3d's trading matches or beats v1 while keeping v3a's beliefs,
the clock's gains are bankable without endgame exposure and the deficit is
located. If v3d still trails v1, the deficit is NOT (only) the endgame and
the diagnosis was wrong — worth exactly as much to know.

## Metric and comparison

* **Primary (the gate)**: paired per-game trading diff (v3d − v1),
  money-at-price at unit size, game-clustered — the same machinery and
  fill-rule caveats as the v3a read. Secondary lines: v3d − v3a paired
  diff (the direct measure of what the discipline recovered), and both
  arms' own per-$ CIs.
* **Beliefs are NOT re-gated**: v3d's estimates are v3a's by construction;
  the Brier comparison is settled by the v3a registration and is printed
  as a consistency check only (it must be identical on mutually-priced
  ticks; any difference is a bug, not a finding).

## Floors and the forward gate (the tape ruling's pattern)

* **Gate-eligible population: signal-covered games first recorded after
  2026-08-23 12:00Z.** The 11 existing archive games are DESCRIPTIVE
  CONTEXT PERMANENTLY — their v1 and v3a trading numbers have been seen by
  three parties, and although no v3d number exists yet, the exam is dated
  after the syllabus was read. A labelled backtest line over those 11 games
  may print beside the gate, marked descriptive, never gating.
* **Floors: ≥ 10 gate-eligible games AND ≥ 100 v3d filled entries within
  them.** Below either: counts only, NO DATA.
* **PASS** (reopens the trading question for the clock regime; authorises
  nothing): paired (v3d − v1) clustered 95% CI excludes zero in v3d's
  favour at floor, OR includes zero while v3d's own per-$ CI does — i.e.
  v3d at least stops the bleeding measurably. **FAIL**: floor met, v3d
  measurably worse than v1. Anything else NO DATA. (The asymmetric PASS is
  registered deliberately: the discipline's job is to not lose what v1
  does not lose, while keeping v3a's beliefs; beating v1 outright is not
  required of an entry filter.)

## Implementation note (for the build, which awaits the manager's word)

One flag in the replay eval's arm construction: same estimate path as v3a,
entry eligibility conditioned on the tick's v1 `Clock.usable`. No engine
change is implied by this registration; live adoption would be its own
decision after an at-floor read, per house rule.

---

*Registered 2026-08-23, before implementation. Results append below this
line, never above it.*
