# QUOTE v2 — Program Registration (DRAFT — C's first-refusal window OPEN)

**Status: DRAFT of record, landed 2026-09-02 so the attack window reads landed
text, not a relay (rule 11 — the rule this project has re-learned expensively
twice). NOTHING is registered by this commit. The registration cutoff is the
commit that lands the post-window final text and says so; until then every
clause below is attackable. Author: research agent. Structure note carried
from the author: this registers the PROGRAM — frame, arm inventory,
sequencing, standing clauses. Each arm's GATE registers separately when its
precondition clears, because three of four arm designs depend on results not
yet read; registering their gates now would mean writing floors for cohorts
whose shape we don't know, which is how gates that cannot close get born.**

## Window log (running; appended by the manager as checks land — the log
records status, it does not amend the draft; only dated author amendments do)

- **C — first refusal, structural:** OPEN. Requested the text of record;
  this landing is that text.
- **D — premise-numbers check: PASSED 2026-09-02.** All six premise citations
  confirmed against #211 as landed (−1.60 [−1.69, −1.50] n=17,032 G=13;
  markout +0.76/+0.91/+0.90; Q4 half-spreads 2.34/2.31/2.18 vs nets
  −2.75/−3.33/−2.61; congestion −1.74 vs clear −1.43/−1.44; character
  −1.70/−1.57/−1.52 overlapping CIs; coverage 12,679/17,032 fills, markout
  clusters G=9). One precision amendment proposed for the premise wording:
  "13 games with fills (12 settled at the v1 verdict)" — both numbers are
  true; the draft should say so in one clause so no reader mistakes two true
  numbers for a discrepancy.
- **D — PATIENCE precondition: RESOLVED 2026-09-02 (405ef34, M4), branch =
  LIVE ARM.** v1 requoted into dips at 82.2% [79.0, 85.3] of
  requotes-after-fills (n=7,651, G=13); 100.0% of quote births verified at
  the touch (17,032/17,032 — the coded rule held without exception); median
  requote gap 0.0s (same engine cycle). v1 was releasing the patience lever
  constantly, so PATIENCE is a real arm at the measured ~0.8¢/fill target.
  Honest bound, carried into the arm's gate when it registers: no
  quote-stream table exists (`shadow_quote_fills` is the only table
  `core/quote/storage.py` defines; unfilled quote updates were never
  persisted), so the into-dip classification reads the fills' recorded
  births — extrapolation to unrecorded requotes is licensed by the 100%
  at-touch verification of the deterministic coded rule
  (`core/quote/engine.py:6-7`, `:68`). The v2 ledger records the full quote
  stream (schema request with A), so the forward cohort measures this
  directly instead of by rule-plus-verification.
- **B — CONGESTION precondition: UNMET AS DRAFTED (refutation of record,
  2026-09-02).** The pointer "B's measured wall-clock congestion windows"
  fails rule 11 by REIFICATION, not paraphrase: B's pinned artifact
  (`analysis/cross_market_census.py`, congestion_clustering) is a
  retrospective clustering STATISTIC — long-lag episode start times bunch
  (nearest-neighbor ≤30s share vs a uniform-shuffle null) — not a window
  list. No pinned (start,end) windows, no inside/outside classifier, and no
  causal detector: an episode's lag is knowable only after its trigger, and
  clustering only after neighboring episodes occur. A suppression arm needs
  an online rule; the pinned instrument cannot be one. What clears the
  precondition: a NEW self-clocked causal detector registered as its own
  object — defined over the quoter's own observation stream with its own
  stamps, never a cross-process join against recorder timestamps — with
  constants ADOPTED from B's in-sample analysis (not optimized) and a
  causal-replay mutation test (windows computable with no future
  information; a lookahead mutation must fail). B is writing that spec as
  the instrument's author. B's 55–70%-vs-7–12% clustering result is
  in-sample evidence FOR the mechanism and never part of the gate.

---

## REGISTRATION TEXT (research agent's draft, verbatim; amendments land dated
beneath it)

**PREMISE, measured.** The maker's opportunity is the taker's toll map: every
THERE-BUT-TOLLED-OUT family (C1 12¢ windows, B1 5¢ family, the 4.70¢
concession) is revenue collected by whoever stands on the book. v1 stood
blind and paid −1.60¢/fill (17,032 fills / 13 games, ledgered FAIL on
registered terms; reproduced exactly by #211 under rule 16). Decomposition
(#211, in-sample, 13-game clustered): ~0.8¢/fill transient micro-reversion;
the remainder concentrated by lateness/state (Q4 collects the fattest
half-spreads, 2.2–2.3¢, and posts the worst nets, −2.6 to −3.3); congestion
moderate (−1.74 vs −1.44); revert character FLAT at fill
(−1.70/−1.57/−1.52). v2 exists to quote where tolls are collected and refuse
where adverse selection concentrates.

**SEQUENCING RULE (outranks everything below).** Quoting policy FROZEN at the
running engine's commit until A1's gate reads (floors ≈3–4 slate days from
Sept 17; accrual rate cited from the research agent's production read,
2026-09-02 15:25Z: ~1,310 in-game fills/game). A policy change during accrual
kills A1's non-revert comparison leg. Build proceeds off the live path. If A1
hits FAIL-BY-EXHAUSTION or DEPLOYMENT HOLD instead of reading, the freeze
lifts only by a dated amendment naming which arm proceeds without the A1
input and what that costs.

**ARM INVENTORY (declared now; gates register per-arm at precondition):**

— **STATE/LATENESS (primary).** Precondition: A1's gate read. WIDTH IS FOLDED
IN with the identifiability note: v1's width was state-driven, so no
observational read of the v1 tape can identify a width effect separate from
state; a future width arm requires exogenous within-state width variation,
pre-declared (v2.1 design, never a v1 measurement).

— **CONGESTION (second).** Precondition: B confirms the pinned window
definition ports to the quoter's clock. Quote suppression inside B's measured
wall-clock congestion windows vs the accruing always-on control.

— **PATIENCE (third, conditional).** Precondition: the requote-baseline
measurement — v1's actual re-centering behavior after adverse micro-moves,
from the tape. If v1 meaningfully requoted into dips, the arm is live with
the measured ~0.8¢/fill target; if not, the lever was never released and the
finding lands as a measurement-horizon note (true maker loss = the +2m
markout), NOT an arm. A lever already pulled cannot be an arm.

— **GUARDS (build list, named trigger).** Return as arms when the v2 build
carries fv and exact-clock quality inline on the fills.

— NEVER a bundled arm. Levers enter singly or factorially, pre-declared.

**INTERPRETATION MATRIX (standing section, meanings fixed before either
instrument reads).** A1 trip-economics × at-fill capture: PASS×flat → revert
edge lives in roll economics; v2-STATE quotes for the trip, not spread
capture. PASS×discriminates → full state-conditional maker. FAIL×flat →
classifier dead for making; program falls to CONGESTION/PATIENCE.
FAIL×discriminates → capture-basis quoting only. No cell's meaning may be
authored after its number exists.

**SCORING STANDARD (all arms).** Per-fill markout at pre-named horizons
+30s/+2m/+10m AND round-trip inventory P&L; game-clustered; maker θ=0;
capture basis with the settlement basis printed beside it (#211's inversion
is why both). Coverage counted, never dropped (the 4/13-game markout gap
pattern). Every scorer passes rule 16 before its first live read: reproduce
the ledgered −1.60 on the v1 pin. Timing-sensitive instruments carry the
jitter-null per the census standard.

**SCOPE.** Basketball only for gate one: WNBA from Sept 17, NBA added at
launch. Non-basketball DEFERRED with named revival: a v2 arm PASS on
basketball triggers a porting proposal, which then owes its own rule-10
coverage work (feeds, constants, venue facts — none exist today). Operator's
words preserved in the registry: "doesn't have to be strictly basketball" —
answered in daylight, scheduled not shelved.

**O4.** A quoter fires continuously; per-arm suppression rates (congestion
windows, state gates) stated in each arm's own registration.

**CLOSURE.** The program closes when every declared arm has read or been
closed at its precondition; no catch-all NO DATA — each arm carries its own
exhaustion clause at registration. The program itself cannot PASS or FAIL;
only arms can. Shadow-only, credential-free (the overlay mounts no
POLYMARKET_* vars; the absence is load-bearing and cited).

**CAPITAL.** No in-sample result justifies capital. The forward test is the
evidence. A passing arm earns the operator conversation; it does not earn
size.

---

*Author's standing flag for the window: the accrual-rate citation reuses an
Aug-era fills/game figure under late-season slate composition — a fresher
basis once Sept 17 fills exist is a welcome, cheap amendment.*
