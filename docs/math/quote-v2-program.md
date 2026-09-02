# QUOTE v2 — Program Registration (REGISTERED)

**STATUS: REGISTERED — this commit is the registration cutoff, being the
post-window final text landing and saying so. Window record: C signed end to
end (five attacks, amendments 4–7); D's premise checks resolved (amendments
1, 8); B's detector delivered at d1fb6de, pending its own registration
window as the CONGESTION precondition's cited artifact. Arm-gate cutoff
instants per amendment 4 read from git hereafter. Author: research agent.
Structure note carried from the author: this registers the PROGRAM — frame,
arm inventory, sequencing, standing clauses. Each arm's GATE registers
separately when its precondition clears, because three of four arm designs
depend on results not yet read; registering their gates now would mean
writing floors for cohorts whose shape we don't know, which is how gates
that cannot close get born.**

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
- **D — premise item 4 CORRECTED 2026-09-02 (supersedes the check above for
  that item only):** B's census determinism fix (c78432d — canonical sort
  inside lags_for_event/triangle_for_event; order-invariance proven on 221
  real episodes across three row shuffles) moved the congestion cell boundary
  by ~1,200 fills (18× the old jitter): the tie-break rule selects a
  different episode-opener set. Canonical numbers under the fixed instrument,
  verified deterministic by D (two runs byte-identical): **in-congestion
  −1.79 [−1.92, −1.66] on 7,801 fills vs clear −1.43 [−1.52, −1.35] on
  9,231 (G=13)** — the lever's teeth survive and slightly sharpen (gap 0.36¢
  vs 0.30¢). The pre-fix −1.74/−1.44 RETIRES; the premise text's numbers
  await the author's dated amendment, and any consumer must pin the census
  commit beside the numbers — two defensible instruments measured different
  episode sets and their numbers must never be silently mixed. Premise items
  1, 2, 3, 5, 6 are untouched (they don't consume the lag instrument).
- **C — structural review returned 2026-09-02: CONDITIONAL SIGN, five
  rulings.** (1) The congestion precondition rewrite must be a dated
  amendment, never a log entry — the draft's own constitution says only
  amendments amend, and registration text survives into summaries while logs
  don't (SATISFIED by author amendment 3 below). (2) The real structural
  hole: NOTHING BINDS THE DEFERRED ARM GATES TO CUTOFF INSTANTS — gates
  registering after preconditions clear register after accrual starts,
  floors written against partially-visible cohorts, the deferral argument
  inverting into its own defect. Fix: a standing clause — every arm gate
  carries its own git-read registration instant; gated cohorts count only
  data first recorded after it, or disclose-and-justify. (3) Preconditions
  need clocks, else the program can never close. (4) The freeze-lift needs a
  stall path and a named author. (5) The interpretation matrix's cells must
  route to REGISTRATIONS, never to policies — "capture-basis quoting only"
  currently reads as deployment permission conditional on two instrument
  reads. C signs with 1–3 as dated amendments and 4–5 as wording; items 2–5
  await the author's second amendment batch.
- **C — the two new numbers in amendments 5–6 checked 2026-09-02:** the
  review instant CONFIRMED with the event-governs wording (adopted); the
  single-trigger stall path ATTACKED on reachability and replaced by the
  dual trigger (adopted). With amendments 4–8 landed below, **C's sign-off
  is END TO END** (message of record: "everything queued has my sign-off
  end to end").
- **B — CONGESTION precondition artifact DELIVERED 2026-09-02:**
  `analysis/congestion_detector.py` (landed from B's d1fb6de) — self-clocked
  pure function of the consumer's own stream, venue-level pooling, constants
  adopted-not-optimized, clustering result outside the gate, causal-replay +
  lookahead-must-fail mutations both passing. The planted-boundary mutation
  caught a datetime-unit bug (µs-vs-ns inference rescaling durations ~1000×)
  that real-data replay alone had masked — the mutation suite earning its
  keep before first use. The detector's own REGISTRATION (the object
  amendment 3 requires) gets research's window next; the census report
  carries the version note retiring pre-canonical consumer numbers
  (8dde1f6). A is warned: a scaffold predicate keyed at trigger time is the
  lookahead bug — key at confirm time (t0+5s).
- **A — ledger seam closed and the CONGESTION substrate mismatch caught
  2026-09-02 (PR #212 → fe45ccc):** fed the recorder tape, the registered
  detector marked 90.6% of fills congested vs the 46% lag-statistic; A
  FAIL-CLOSED the gate flag rather than shipping the proxy as truth — the
  standard working unprompted, and the trigger for amendment 9.
- **B — the revision bar's provenance, verbatim in the log because it is
  the sharpest statement of the laundering trap on record:** every
  alternative bar B could derive comes off the RECORDER clock, the very
  feed the registration rules non-compliant, so deriving the revision bar
  from it would launder the wrong instrument's measurements into the judge
  of the right one — "worse provenance wearing better clothes." An agent
  checking their own candidate numbers and ruling AGAINST their own
  provenance is the property this record is built to produce.
- **The thread's last word (B's):** a validated proxy is the one honest
  way a refused input ever earns partial readmission.
- **A — the proof-1 substrate gap caught and refused 2026-09-02:** no
  existing pin cleanly carried the full 13-game window (the eval pin ends
  Aug 20 22:25; the since-0820 pin lacks game_id), and A asked for a
  ruling instead of stitching a substitute that provably wasn't what the
  prod quoter read. Manager cut the true object from prod same hour (the
  dated line under amendment 10 carries its identity). Third
  under-specified pointer cut into an artifact today, third different
  hand; the fail-close habit is now the house norm, not the exception.
- **Substrate epoch INSTANTIATED 2026-09-02:** the observation migration
  (amendment 10's cohort-epoch ruling) landed at merge commit 322397c —
  epoch by command, never prose:
  `TZ=UTC git log -1 --format=%ct 322397c`. Field set signed by B, D,
  manager, and research (condition met: the three deploy proofs are spec
  requirements). The v2 quoter recording path + proofs are in build (A);
  the freeze remains bound to 7a3a217 until the proofs land per
  amendment 10 stage 2.

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

---

## DATED AUTHOR AMENDMENTS (research agent, 2026-09-02; numbering from the
landed text)

**Amendment 1 (precision, D's).** The premise's game count reads: "13 games
with fills (12 settled at the v1 verdict)" — both numbers true, one clause,
so quote-shadow.md's 12 never reads as a discrepancy.

**Amendment 2 — PATIENCE resolves to LIVE ARM; the precondition discriminated
exactly as designed.** Measured (405ef34): v1 requoted into dips at 82.2%
[79.0, 85.3] (n=7,651, G=13), 100.0% of quote births at the touch, median
requote gap 0.0s — the lever was not merely released, it was held down
continuously. The ~0.8¢/fill transient is a live target. Substrate bound
DISCLOSED in the arm text: v1 has no quote-stream table (`shadow_quote_fills`
is the only object storage defines), so the classification reads births
recorded on fills, licensed by the 100% at-touch verification of the
deterministic coded rule. Forward requirement PINNED now: A's v2 ledger
records the full quote stream (births, moves, cancels), and PATIENCE's
eventual GATE reads the stream, never the fills' shadow of it — the v1-tape
bound travels into that gate's registration as a named limitation, not a
footnote.

**Amendment 3 — CONGESTION's precondition is REWRITTEN; the defect was the
author's: the draft cited an object that does not exist.** "B's measured
wall-clock congestion windows" reified a retrospective bunching statistic
(NN ≤30s share vs shuffle null) into a deployable window list — no such list
exists, no causal detector exists, and episode lag is knowable only
post-trigger. The reification propagated exactly as bad pointers do: A's
scaffold came to cite a THIRD object ("≥5s lag / 30s window, from D's
calibrated cut") matching neither the author's phantom nor B's actual
artifact — three pointers, one nonexistent object. Corrected precondition,
per B's own refutation terms: a NEW self-clocked causal detector, registered
as its own object, running over the quoter's own stream (never a
cross-process join on recorder timestamps), constants ADOPTED from the
in-sample analysis rather than optimized, carrying a causal-replay mutation
test in which a lookahead mutation MUST fail. A's predicate is HELD until
that registration lands. The lineage of all three divergent pointers is
recorded here so the record shows how a reification breeds. (This day's
chain is the type specimen of WAVE_STANDARD rule 17, the precondition
citation duty, elevated same day.)

**Amendment 4 — THE CUTOFF-INSTANT CLAUSE (C's, folded verbatim; this was a
real hole).** The deferral of arm gates meant a gate could register three
slate-days into accrual and write its floors against visible partial
results — the deferral argument inverting into its own defect. Standing
clause binding ALL arm gates: every arm gate carries its own registration
instant read from git; its gated cohort counts only data first recorded
after that instant, OR the gate discloses-and-justifies any included prior
accrual with the cohort's interim results unread by the gate's author,
attested. The R-series convention, imported to where it was silently
missing. (A1's gate already satisfies it — registered before any accrual
existed.)

**Amendment 5 — PRECONDITION CLOCKS.** One program-wide review instant: NBA
opening night, currently expected 2026-10-20; THE EVENT GOVERNS if the
schedule moves (C's wording — a bare date goes ambiguous the moment the
league moves a game, and nothing pinned in the repo verifies the date). Any
arm whose precondition is uncleared at that instant converts to CLOSED-UNMET
by dated note, revivable only by fresh registration. Per-arm:
STATE/LATENESS inherits A1's own clocks (exhaustion at 2× floors, DEPLOYMENT
HOLD) — cited, not duplicated; CONGESTION = B's detector registration
landing; PATIENCE's gate = the v2 stream ledger shipping; GUARDS = fv +
exact-clock inline on fills. The program can no longer pend forever on an
arm that never clears.

**DATED LINE under amendment 5 (2026-09-02, author's):** the fv-waits
decision creates the program's tightest clock, named here so it is CHOSEN
rather than discovered at the review instant. GUARDS' precondition (fv +
exact-clock inline) cannot clear before the post-A1 deploy: exact-clock
ships pre-tip, fv only after A1 reads (amendment 10's no-mid-accrual
rule), and the post-A1 deploy owes its own equivalence proofs. Feasible
path: A1 reads ~Sept 26–30 → post-A1 build with proofs → deploy → GUARDS
registers before NBA opening night (event-governed). Slack ≈ three weeks,
contingent on A1 reading promptly and the post-A1 deploy not slipping.
PRE-ACCEPTED OUTCOME: if the chain slips, GUARDS converts to CLOSED-UNMET
at the review instant exactly as amendment 5 provides — the review
instant does NOT bend for a tight chain; bending clocks for tight chains
is what review instants exist to prevent. The cost is bounded and was
chosen twice over: the state guards themselves remain deployed on the
decision side regardless of this arm's fate; only guard-gated QUOTING
closes; revival is a fresh registration citing an already-written design.
This line reopens neither the fv-waits decision nor the no-mid-accrual
rule — it prices their interaction, in advance, in the voice that
authored both.

**Amendment 6 — FREEZE-LIFT COMPLETED.** (a) Stall path, DUAL-TRIGGERED
(C's reachability catch — the gate-that-cannot-fire species applied to the
author's own clause: nothing pinned verifies twelve more 2026 WNBA
slate-days exist, so a single trigger could leave the clause uninvokable
while the freeze holds silently into NBA launch): the stall path opens at
12 WNBA slate-days post-resumption OR the program review instant, whichever
comes first. (b) Authorship named: any freeze-lift amendment is authored by
the research agent with the standard peer window applying — a lift can
never arrive as a relay.

**Amendment 7 — MATRIX CELLS ROUTE TO REGISTRATIONS.** One clause across all
four cells: each cell names what may REGISTER next, never what deploys —
"full state-conditional maker" and "capture-basis quoting only" are
registration licenses, not deployment permissions. Qualifier on PASS×flat:
the roll-economics reading holds per A1's instrument checks.

**Amendment 8 — the premise paragraph's congestion citation moves to the
fixed instrument.** Replace −1.74 vs −1.44 with the canonical numbers:
**−1.79 [−1.92, −1.66] on 7,801 congested fills vs −1.43 [−1.52, −1.35] on
9,231 clear, G=13, census commit c78432d pinned beside them.** D's
version-pin sentence carried verbatim: two defensible instruments measured
different episode sets; their numbers must never be silently mixed. (The
log holding the canonical numbers while the registered text held the
retired ones is exactly why the constitution says the log cannot amend —
this closes the gap the right way.)

**Amendment 9 (2026-09-02): CONGESTION's in-sample read was STRUCTURALLY
IMPOSSIBLE, and the arm's gate gains a second named dependency.** The
registered detector is defined over the consumer's OWN observation stream
and stamps at cadence ≪ LONG_S; v1 recorded no such stream and observed at
~5s, where the response test DEGENERATES — a sibling's response is first
observed at the next cycle, landing at or past the 5s deadline by
construction, so every trigger confirms and the instrument measures the
consumer's cadence, not the venue (the registration's append A carries the
mechanism). Fed the 200ms recorder tape — right cadence, FORBIDDEN clock —
it marks 90.6% of in-game fills / 75% of game time congested against the
46% lag-statistic: the divergence is the substrate mismatch being
MATERIAL, and the detector's own-stream constraint is what made the wrong
read detectable rather than quietly believed. The gate flag (`congested`)
is ABSENT in-sample and the arm FAIL-CLOSES; only a labelled
`congested_recorder_proxy` exists, diagnostics-only, PERMANENTLY barred
from gates. The arm's gate dependencies are now: (i) the detector
registration — met, cec9453 / epoch 1788366953
(`docs/math/congestion-detector-registration.md`); (ii) the v2 quoter
recording its own observation stream (A's forward schema, fe45ccc lineage)
— cohort FORWARD-ONLY per amendment 4's cutoff clause. NO READER may
conclude an in-sample congestion read was available and skipped: it was
not available, and this amendment is the proof it was checked. Two arms
(CONGESTION, GUARDS) now share this substrate dependency — the forward
schema is the single highest-leverage build item in the program,
unblocking two of four arms simultaneously; it should ship once, complete,
rather than fast.

**The proxy ruling (author's, B's pre-exclusion folded verbatim into the
lock):** forward-only is the only registrable path for the GATE, full
stop — validating a downsample proxy requires the truth stream v1 never
recorded; an unvalidated proxy is a free parameter wearing a measurement's
name. The door and its lock, written now so it is not relitigated
quarterly: once the forward stream accrues, a proxy-validation study
(proxy vs truth on the overlapping forward period, agreement
pre-registered) MAY register as its own instrument question — and a proxy
that passes could thereafter INFORM retrospective descriptive work, never
gate anything. The lock: "candidate proxies must satisfy the detector's
cadence requirement (observation cadence ≪ LONG_S); feeds that fail it are
excluded BY DEFINITION, not by study." Full disposition, one line each:
the 5s downsample — dead by definition (append A's degeneracy is the
proof); the 200ms recorder tape — right cadence, wrong clock, eligible for
a future pre-registered overlap study, descriptive-only forever; the
gate — forward-only on the quoter's own stream, always.

**Amendment 10 (2026-09-02) — the freeze's purpose over its letter, by its
author.** The freeze exists for A1's cohort integrity: one engine, one
policy, uncontaminated comparison legs. A recording-only deploy that
PROVES policy equivalence serves that purpose; refusing it would trade two
arms' substrate for a letter protecting nothing additional. Authorized in
two stages: **(1)** this amendment authorizes a pre-first-tip deploy of
the observation schema (A's #214 lineage) CONDITIONAL on three proofs
attached at landing: REPLAY EQUIVALENCE — the new binary replayed on the
pinned Aug tape produces byte-identical quoting decisions to 7a3a217; AST
EXTENSION — the credential/venue-client import ban verified on the writer
path; OFF-DECISION-PATH — the observation writer is async off the quote
loop, with quoter loop-time telemetry printed pre/post on the first slate
night (the tripwire pattern applied to the very process being modified — a
recording-only change that slowed the loop would be a policy change
wearing a recording costume). **(2)** The freeze re-binds to the NEW
commit in a dated line under this amendment at the instant the proofs
land — never before. **HARD CONSEQUENCE:** if the build misses the first
Sept 17 tip, it does NOT deploy mid-accrual — recording waits for A1's
read, and the CONGESTION/GUARDS substrate delay is the recorded price of
the slip. One-commit-per-cohort outranks parallel accrual, explicitly
rather than by accident.

**Cohort-epoch ruling (CONGESTION / GUARDS / PATIENCE), riding under
amendment 10:** substrate epoch = the observation migration's landing
commit — when compliant data begins existing. Arm gates register when
their designs CAN exist; skeleton cutoffs now would recreate the exact
deferred-design problem the two-layer structure solved (CONGESTION's gate
cannot even name which detector version it cites until the saturation read
selects one). Each gate takes amendment 4's disclose-and-justify path: its
cohort may count the full compliant stream from the substrate epoch, WITH
the disclosure that the stream was written by a frozen,
mechanically-recording binary whose recording rule predates all data and
which the gate's author does not shape — interim results unread, attested.
Structural support so the attestation isn't bare: **the forward
observation table is EMBARGOED from analytical reads until a consuming
gate registers; any pre-registration read is named in that gate's
disclosure.** The ONE pre-registered reader is exempt and named to prevent
text collision: the detector registration's append B saturation
diagnostic — bar, median, and definitions all pinned blind; it reads
coverage only, and its outcome selects the detector version the gates
cite.

**DATED LINE under amendment 10 (2026-09-02):** proof 1's replay substrate
is `backups/exports/market_snapshots_quote_replay_20260902T173700Z.csv.gz`
— prod market_snapshots verbatim, 2026-08-17 12:00 → 2026-08-23 00:00 UTC,
5,319,984 rows, game_id on all, md5
`b740d2fb6dcd5f325877cf8281a97c42`, one named exclusion (`raw`, the venue
blob — nothing in the observation path reads it). The amendment's original
phrase "the pinned Aug tape" named no artifact — an under-specified
pointer of the rule-17 species, the author's own (research agent); A's
refusal to stitch a substitute substrate and the manager's cut of the true
object are the correction. Proof 1 = A's replay runner over THIS pin, both
engines, byte-for-byte, with reproduction of the ~17,032-fill ledger
population as the substrate-integrity check (rule 16 built into the
proof). The freeze-rebind line will cite this same pin and md5.

**FREEZE-REBIND dated line under amendment 10, stage 2 (2026-09-02,
manager).** Written once before and refused twice on its own discipline:
the first draft was permission-paused unpushed, and in the pause A found
findings B14 (the recording binary stamped `observed_at` from the
recorder's forbidden cross-process clock — a defect #217's reconciliation
scorer structurally cannot see; rule 19 is its residue), so that draft
was marked never-ship and THIS line is rebuilt on the FIXED binary
(#218 → merge b50390f: own-stamp `observed_at`; B's canonical
(observed_at, market_slug) feed sort per the detector's registered input
contract; `source_captured_at` carried as provenance-never-input, giving
the wrong-clock regression an assertable signature; scorer check 3
cross-clock validity with plants, closing the declared blind spot).

The three proofs, each verified by the manager's own runs on the fixed
tree, not the relay:

— **Proof 1 (registered form,** `analysis/quote_v2_replay_proof.py`**):**
EQUIVALENCE — v1==v2 byte-identical `_standing` + fills across all 14,861
replay cycles on the pin named in the dated line above (md5-gated read).
INTEGRITY COMPANION (completeness form; the withdrawn attribution form
and its history are in the log): all 17,032 ledgered in-game fills'
producing observations present and matching — zero holes in all four
categories; rule-18 plants pass. The cadence-bounded reproduction count
(16,400 on a 5s grid) prints as a labelled non-gating diagnostic.

— **Proof 2:** the AST no-order/no-credential ban verified on the writer
path (engine_v2 selftest, re-run by the manager on the fixed tree).

— **Proof 3:** recording is off the decision path — structurally (v2
overrides no quoting method, asserted in code) and behaviourally
(equivalence holds with recording interleaved; `record_cycle` perturbs
neither `_standing` nor fills; manager re-ran the selftest against an
ephemeral postgres with the full migration chain through e1a7c3f60d94
applied). The quoter loop-time telemetry prints pre/post on the first
slate night per this amendment.

**THE FREEZE RE-BINDS TO THE COMMIT CARRYING THIS LINE**, which also
switches the quote overlay's command to the v2 recording engine
(`docker-compose.quote.yml` → `core.quote.engine_v2`); the pre-tip deploy
runs exactly this commit, and the running engine's quoting policy remains
v1's, byte-identical, per proof 1. **fv-WAITS is the named fork of
record:** `fair_value` records NULL until the post-A1 deploy; guard-2's
cohort hole is counted and disclosed per the scoring standard; the clock
consequence for GUARDS is priced in the dated line under amendment 5.
Recording — and with it the compliant observation stream for the
CONGESTION / GUARDS / PATIENCE substrate — begins when this commit
deploys; the embargo on analytical reads stands, with the recording-
integrity scorer's checks running as recording-integrity, never
analytics.
