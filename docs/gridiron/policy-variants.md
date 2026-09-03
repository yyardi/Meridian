# GRIDIRON — parallel policy variants (REGISTRATION)

**Research agent, 2026-09-03. Landed by the manager; this commit is the
cutoff, read from git `%ct`. Written because the operator asked what had
changed from the failing quoter and the honest answer was NOTHING.**

## Why this is not another data collector

**Every prior deployment measured the MARKET. This measures our own POLICIES
against each other.** Four engines, same games, same second, same book,
different rules — the first experiment in this program whose output is
*"which rule is better"* rather than *"what does the venue do."* Shadow
costs nothing and nothing can trade, so the only price is CPU.

## Cohort

GRIDIRON, league-filtered at the observation query, every row stamped with
engine identity — four engines share tables, so identity is what makes the
cohort legible. **Touches neither A1's cohort nor the basketball freeze**;
authorised by amendment 12, which places GRIDIRON's binaries outside the
freeze by construction.

## Arms — one lever off a common base, each difference pre-declared

- **BASE** — frozen v1 policy, byte-identical. The control; every other arm
  is interpretable only against it.
- **PATIENCE(N=30s)** — after a fill, do not requote to the touch for N
  seconds. *Basis: v1 requoted into the dip 82.2% of the time at 0.0s median
  gap; dips revert +0.76→+0.90¢.*
- **LATE-SUPPRESS** — no quoting in the final period. *Basis: Q4 collected
  the fattest half-spreads (2.2–2.3¢) and posted the worst nets (−2.6 to
  −3.3¢).*
- **WIDTH-FLOOR** — **self-calibrating, no imported constant:** quote only
  when the current spread is at or above the **60th percentile of that same
  market's own spread over the trailing 30 minutes.** A literal >10¢ floor
  quotes nothing on 5–6¢ NFL cells; a percentile rule adapts to whatever the
  board turns out to be and is fixed before any NFL data exists. **Percentile
  and window are pinned here and may not be tuned after a read.**

## ★ THE INSTRUMENT-BIAS CLAUSE — the one that must not be dropped ★

**All four arms use the mid-cross fill rule, which is optimistic in a way
that scales with QUOTING FREQUENCY:** it books ~1.5¢/leg and the mid then
reverts ~1.8¢ favourably, so **the model pays a bonus for every additional
quote.** PATIENCE, LATE-SUPPRESS and WIDTH-FLOOR all quote LESS than BASE
by construction.

**Therefore the instrument systematically handicaps exactly the levers under
test, and a slate in which every variant loses to BASE on TOTAL P&L is the
EXPECTED OUTPUT OF THE BIAS, not evidence against the levers.**

Registered consequences:
- **PRIMARY METRIC IS PER-FILL CAPTURE, not total P&L.**
- **Fill COUNT per arm is reported beside every number**, so the volume
  difference is visible rather than buried.
- Total P&L is secondary and read only with the bias named in the same
  sentence.
- **A variant that beats BASE on per-fill capture is STRONGER evidence than
  its number suggests, because it did so carrying the handicap.**

## Scoring

Both fill arms (optimistic and measured-concession), game-clustered CIs,
per-arm fill counts, per-arm inventory path. **Rule 16 before any read:
BASE must reproduce v1's policy byte-identically on the pinned replay — if
the control is not the control, nothing downstream means anything.**

## Contention clause (amendment 12's residual channel, now +4 processes)

Per-engine cycle-time telemetry printed every slate, and a pre-declared
equivalence check: **if arms' median cycle times differ materially, the
comparison is confounded by TIMING rather than policy and the slate reads
NO DATA.** Four engines contending on one m7i.large is a real mechanism for
exactly that.

## Schedule — dress rehearsal, then cohort

- **Sept 9–10, single game: HARNESS VERIFICATION ONLY, never a read.** All
  four engines running, identity stamps landing, cycle times equivalent,
  BASE reproducing v1. The unrepeatable-night discipline: prove the
  instrument on the cheap game.
- **Sept 13, ~12 games: first real cohort.** One slate gives an INDICATIVE
  read at G≈12 clustering. No gate.
- **GATE at 3 slates (~Sept 27) or ≥2,000 fills per arm across ≥24 games,
  whichever is later.** Below that: NO DATA, accrue.

## Pre-declared expectations — magnitudes, so the read can surprise us

- **PATIENCE:** improves per-fill capture on the affected subset by some
  fraction of the measured 0.8¢ dip; diluted across all fills, expect
  **+0.2 to +0.5¢/fill.** Below +0.1¢: the dip does not transfer to football.
- **LATE-SUPPRESS:** removes fills averaging ~1¢/fill worse than the book;
  at ~25% late share expect **≈+0.25¢/fill**, partly offset by forgoing the
  fattest half-spreads. **A NEGATIVE result here is informative** — it would
  mean football's late-game structure differs from basketball's, which is a
  real finding about the sport.
- **WIDTH-FLOOR:** **no prior on NFL. Genuinely open**, and the only arm
  with no expected magnitude — stated as such rather than dressed with one.
- **OVERALL: we do NOT expect positive capture on the first slate. We expect
  the levers to move −1.60¢ toward zero and to tell us which ones transfer
  from basketball to football.** Anything better is a surprise, and
  surprises that arrive unpredicted are worth more than promises that arrive
  on schedule.

## Capital

Shadow-only, credential-free, nothing trades. **No in-sample or first-slate
result justifies capital; the gate is the evidence.**

---

# FIFTH ARM + THE BRANCH TREE (2026-09-03, dated BEFORE the first slate)

**Added because the operator pushed: "make sure u are innovating on the
losses, be prepared for the downside case if it doesnt work or gets worse
too cuz otherwise ur just gonna be doing some stupid shit and not fixing a
broken algo approach."** They were right on both counts, and fixing it
exposed a false claim of the manager's, corrected below.

## ★ FLATTEN(k=1¢) — the fifth arm, and the manager was wrong to defer it ★

The manager wrote that flattening "needs an exit mechanism the engine
lacks." **It does not.** The engine already quotes both sides every cycle,
and flattening is **inventory-conditional quote PLACEMENT**: when net long
in a market, lean the ask 1¢ toward the mid; when short, lean the bid. Same
class of change as PATIENCE — both modify quoting as a function of the
engine's own recent history — not an architectural addition. The engine
writes its own fills, so its position is derivable in-process.

**And it is the best-motivated arm we own.** Round trips were available at
up to 27–42% within 30s; +1.44¢ on the flattened subset; +$76 whole-book at
k=1¢, direction consistent, decaying with k, negative by 5¢, CI spanning
zero only for lack of power. **k=1¢ is pre-declared from that curve and may
not be tuned.**

**Why it matters for the design: without it, ALL arms are "quote less" and
the program's headline finding — that v1 never closes a round trip — goes
untested on the first real slate.** With it, four arms are "quote less" and
one is "quote DIFFERENTLY," which is the family balance the criticism asked
for.

## The branch tree — every outcome names what gets built next

**(a) ALL ARMS ≈ BASE.** The basketball levers do not transfer; adverse
selection in football is not concentrated where basketball's was.
**Next: flattening becomes the whole program** — "quote less" was the wrong
family and "close the round trip" is the untested one.

**(b) ALL ARMS WORSE than BASE on per-fill capture** (total P&L is covered
by the instrument-bias clause and cannot trigger this). Our model of where
the loss lives is wrong, not mistuned. **Next: stop adding levers and
re-derive from the fills. A wrong map is not fixed by walking faster.**

**(c) BEST ARM STILL DEEPLY NEGATIVE (worse than −1¢).** The levers work,
the level does not — pointing at the structural story: **we are always
behind the queue with no speed or priority advantage, so we systematically
receive the informed side of the flow the spread exists to compensate.**
*ITS DISCRIMINATOR, registered so this is a diagnosis and not a story told
when things go badly:* the claim predicts that **fill events cluster with
subsequent adverse price movement, and more so for fills arriving after
larger queue clearance.** Measurable on the variants' own fills and on the
operator's probe log. Confirmed or refuted, never asserted.

**(d) THE CROSS-VENUE PIVOT — SUBSTRATE CORRECTED, AND ITS PRIOR DEATH
CITED.** *The manager claimed "we record BOTH Kalshi and Polymarket on the
same NFL games, starting now." **That is false.** Verified at prod:
`kalshi_contracts` is 771 KXWNBASP + 684 KXWNBATO + 152 KXWNBAGA —
**WNBA only, zero NFL**, across 530,061 snapshots.* Cross-venue NFL would
require extending the Kalshi recorder to NFL series: a build with a Sept 9
deadline, not a free query.
**AND THE THESIS ALREADY FAILED ONCE:** venue-gap was this project's
FOUNDING thesis and was killed — **V23, pregame resolution, 36 games,
median gap 0.0000.** Reviving it unnamed is how a dead idea returns wearing
new clothes, which a branch tree exists to prevent.
**SALVAGED FORM, better than proposed and free:** we hold 530k Kalshi WNBA
snapshots beside Polymarket WNBA ticks, so **cross-venue IN-PLAY gap is
measurable on the historical tape today.** That differs from V23 in the one
dimension that could matter — V23 tested PREGAME, where prices have hours
to converge; in-play they may not. **Scored NET OF BOTH VENUES' SPREADS AND
FEES** (Kalshi ~1¢ + Polymarket 5–6¢ ⇒ a tradeable gap must exceed ~6–7¢
against a pregame median of 0.0000), with a pre-declared bar and a null
clause. If it survives on WNBA, extending Kalshi to NFL becomes justified
rather than speculative.

**(e) ONE OR MORE ARMS BEATS BASE on per-fill capture, CI excluding zero.**
The lever transfers. **It does NOT authorise capital and does NOT end the
experiment** — it authorises the pre-declared composition arms (pairs,
single-lever-additive) and continued accrual to the 3-slate gate. **A
winning arm on one slate is a regime observation, not a result.**

**(f) MIXED — some better, some worse. The most likely actual outcome.**
Rule, fixed now: **each arm reads independently against BASE; no composite
verdict.** A family-level conclusion ("quote-less levers transfer") requires
consistency across all three; its absence means the mechanism is
arm-specific rather than familial.

**And the framing that makes a null a diagnosis rather than a shrug:**
market making has three failure modes — adverse selection, inventory risk,
and never being filled. **Our quote-less levers address only the first.** A
null would be evidence the loss lives in the other two, and both are already
measured: inventory shows an 18× variance fan-out across peak position, and
queue depth runs ~1,000 contracts ahead of us at our own price.


---

# AMENDMENT — TWO ENGINES, THREE CUTS (2026-09-03, BEFORE the first slate)

**Registered before any CFB game has kicked off and before any arm has run.**
The five-arm design above is superseded. Nothing here is fitted to a result
from the slate it governs; every number cited comes from the WNBA tape, and the
mechanism that forced the change (phantom fills, WAVE_STANDARD rule 24) was
discovered today and is documented at `docs/math/adverse-selection-measured.md`.

## Why the design changed

**63.9% of our shadow fills could not have occurred.** The simulator rests an
order against a recorded book that does not contain it, so the recorded bid can
fall below our own price and drag the mid onto it while nobody was offering
anywhere near us. Separated, on 17,339 fills at 100% classification and 100%
settlement coverage:

| population | n | settlement P&L / fill |
|---|---:|---:|
| phantom | 11,084 | **+0.951¢** |
| real | 6,255 | **−3.376¢**, game-clustered **[−5.06, −1.78]**, 12 of 13 games losing |

Two independent instruments agree: manager's fills-table read **−3.38¢**, D's
whole-book replay **−3.62¢**.

## THE STRUCTURAL RULING — engines for PRICES, cuts for SELECTIONS

**Per-fill capture is a market fact at the fill instant. It does not depend on
the engine's inventory or history.** Therefore a policy that only changes WHICH
observed fills you keep is recoverable as a **cut on BASE's own fills** — no
engine, no slot, and read on *all* of BASE's fills rather than a fifth of the
slate. A policy that changes the PRICES QUOTED is not recoverable: you cannot
ask a tape "what if we had offered a cent tighter" when we never did.

**WIDTH, LATE-SUPPRESS and PATIENCE are selections → CUTS.
FLATTEN is a price counterfactual → ENGINE.**

Stated honestly: a cut answers *"would these fills have been better?"*; an arm
answers *"would this policy have been better?"*, including path and inventory
effects a cut cannot see. For the primary metric they are near-equivalent and
the cut has ~5× the sample. **This dissolves the power constraint that made
WIDTH-FLOOR the binding arm.**

## The registered shape

**ENGINES (2):**
- **BASE** — v1 unchanged. On NFL/CFB its job is to answer *does football behave
  differently from WNBA at all*, because on WNBA touch-joining is dead (below).
- **FLATTEN(k=1¢)** — the only arm that leaves the losing family rather than
  partitioning it. **k=1¢ re-derived by BOOK INSERTION and RETAINED** (see the correction
  below — exclusion was not enough).

**PRE-DECLARED CUTS on BASE's fills (3), fixed here before data:**
- **WIDTH** — buckets ≤1.5 / 1.5–2.5 / 2.5–3.5 / 3.5–5.5 / >5.5¢ of quoted spread.
- **LATENESS** — by `event_period`, late window versus the rest.
- **PATIENCE** — fills arriving within 30s of a prior fill in the same market
  versus the rest.

## Metric ruling

- **PRIMARY: settlement P&L.** Stated limit: on a binary held to expiry it is
  dominated by directional variance, so **the effective sample is games, not
  fills** — all CIs game-clustered.
- **SECONDARY: markout at pre-named horizons.** Lower variance, real power at
  this n, and it exhibits the mechanism directly.
- **RETIRED: capture versus mid-at-fill.** Wrong for a maker in both
  directions. The manager's "~61% of the loss is mechanical half-spread, true
  loss ≈ −0.90¢" decomposition is **withdrawn** as a flattering heuristic.
- **PHANTOM FLAG on every arm and every cut**, always reported.
- **RULE 25 COMPLIANCE, binding on every comparison here:** the arms differ in
  activity by construction, so **no composite may be reported alone.** Fill
  count, opportunity count and per-event mean travel together, and every
  ranking is checked at both degenerate extremes (never act / act always). A
  metric that either extreme wins is ranking activity, not policy.

## FLATTEN is scored on DISPERSION AND TAIL, not mean

Its registered premise is inventory RISK — *"we accumulate and wear it"* — which
a per-fill mean structurally cannot address. **The other version of the premise
is already dead:** on real fills, capture by position before the fill is flat
(0 → −2.305¢, 1–2 → −2.334¢, 3–5 → −2.340¢, 6–10 → −2.530¢, >10 → −1.791¢) and
fills that ADD to a position (−2.310¢) are indistinguishable from those that
REDUCE it (−2.293¢). **Inventory does not degrade fill quality.** What remains
is the 18× dispersion fan-out by peak inventory, and that is what FLATTEN is
for. Scoring it on mean would test a hypothesis nobody registered.

**And the caveat that outranks the parameter: every cell is negative at every k.**
Best on the board is wide-band k=1¢ at **−1.13¢/fill**. **Flattening improves a
losing book; it does not make a winning one.** The aggregate +$17.55 at k=1¢ is
a fill-count and mix effect, **not a per-fill positive.** *"FLATTEN leaves the
losing family"* means **by being less negative** — it must not harden into
*"FLATTEN wins."*

## Why WIDTH is a cut and not a lever

Its original hypothesis (*wide is better*) was a phantom artifact: the phantom
share rises with spread (43.6% → 78.9%) and phantoms are less bad, manufacturing
a spurious gradient. Cleaned, capture runs the other way monotonically
(−1.666¢ → −3.800¢). **But the restraint travels with the number: "wide is best"
is REFUTED; "wide is worst" is NOT ESTABLISHED** — n=483 and n=129 real fills in
the wide bands, CIs spanning zero. **Width leaves the lever list because the
evidence that it was good is gone, not because the wide end is bad.**

## CORRECTION — exclusion cleans the scoring, not the policy

**Filtering phantoms out of the P&L is NOT the same operation as putting our
order into the book, and the difference bites whenever inventory steers
quotes.** In the flattening simulator the inventory `q` is incremented by
*every* model fill, phantoms included — it classifies them and still counts
them — and `q` is the input to the inventory-conditional lean. **A phantom bid
fill makes the sim "long", which leans the ask in, which changes every later
quote and therefore every later fill.** Excluding those fills from the score
afterwards cannot undo a quote path they chose.

Re-run with the order actually inserted into the book (rule 24's real remedy):

| k | excl. P&L | inserted P&L | ins. per-fill | ins. per-game (clustered) |
|---:|---:|---:|---:|---|
| 0¢ | −156.35 | −156.35 | −3.62¢ | +0.00 [+0.00, +0.00] |
| **1¢** | −138.80 | **−125.92** | **−2.33¢** | **+3.38 [−3.28, +10.05]** |
| 2¢ | −195.33 | −139.45 | −2.34¢ | +1.88 [−5.67, +9.43] |
| 3¢ | −194.18 | −147.81 | −2.39¢ | +0.95 [−6.93, +8.82] |
| 5¢ | −207.20 | −163.84 | −2.57¢ | −0.83 [−8.80, +7.14] |

**SUPERSEDED — see the FINAL k-curve below; the +$30.43 figure came from a
substrate missing 25% of the board.**

### FINAL k-curve — insertion basis, FULL substrate (209/209 markets)

**This is the third value recorded tonight and the only one with both fixes on
complete coverage. The sequence is part of the record:**

| | method | substrate | improvement over k=0 | positive region |
|---|---|---|---:|---|
| 1st | exclusion | partial (147/209) | +$17.55 | {1¢} |
| 2nd | insertion | partial (147/209) | +$30.43 | {1¢, 2¢, 3¢} |
| **3rd** | **insertion** | **full (209/209)** | **+$10.10** | **{1¢}** |

| k | fills | P&L | per-fill | per-game (clustered) |
|---:|---:|---:|---:|---|
| 0¢ | 6,403 | −188.06 | −2.94¢ | +0.00 [+0.00, +0.00] |
| **1¢** | 8,071 | **−177.96** | **−2.20¢** | **+0.78 [−3.77, +5.33]** |
| 2¢ | 8,899 | −204.95 | −2.30¢ | −1.30 [−6.69, +4.10] |
| 3¢ | 9,244 | −215.94 | −2.34¢ | −2.14 [−7.85, +3.56] |
| 5¢ | 9,501 | −235.97 | −2.48¢ | −3.69 [−9.47, +2.10] |

**THE COVERAGE HOLE:** the tick source used for the first two runs covered
**147 of the 209 markets that have fills** — 62 markets and 4,412 fills, 25% of
the population, absent entirely. Classifying on the union of all four tick
sources reproduces the manager's independent count **to the row** (17,339
classified, 63.9% phantom, 6,255 real), and the phantom share is stable across
the two substrates (62.6% vs 63.9%), so **the headline was never at risk** — but
the k-curve was, because it is a difference between policies and the missing
quarter was not missing at random.

**CONVERGENCE IMPROVED once coverage was right:** D's replay yields 6,403 fills
at −2.94¢ against the manager's 6,255 at −3.38¢ — **population within 2%,
per-fill economics within half a cent**, from two independently written
instruments.

**k=0 known-answer identity still holds exactly at full coverage: 6,403 fills,
−$188.06, both methods, to the penny.** Coverage is now asserted and printed on
every run, so a grid that silently omits markets cannot answer a different
question again.

**DISPOSITION: k=1¢ retained — structurally justified, statistically
unresolved, deferred to NFL volume.** The case is WEAKER than either earlier
number: **+$10.10 not +$30.43**, per-game **+0.78 [−3.77, +5.33]** spanning
zero, **every cell negative per fill at every k, best −2.20¢.**

**A second, smaller defect found on the way, with no effect on any published
number:** an ASOF join negated timestamps to work around DuckDB's direction and
landed on `captured_at >= filled_at` — **a forward join whose one-sided age
filter admitted unbounded lookahead**, worst case a book from 25 hours *after*
the fill. 123 fills on the partial substrate; zero on the union substrate, where
every fill has a tick at its own timestamp. Fixed with an assert.

**The "propagated across several scripts" claim is WITHDRAWN — checked and
false.** The negated-timestamp ASOF pattern appears in four other committed
scripts (`exit_option_value`, `halftime_reanchor`,
`pulse_execution_decomposition`, `quote_v2_markout`) and is **correct in all
four**: they are markout joins, where forward IS the intended direction by
definition, and in every case the derived gap is non-negative by construction
and capped above. The defect was in exactly one place.

**AND THE BUG IS NOT "A NEGATED ASOF JOIN" — the negation is fine and often
necessary.** It is a **MISMATCH between the join's DIRECTION and the SIGN
CONVENTION of the quantity you then filter on**, which turns a one-sided cap
into a vacuous one. `age <= 5` reads like a freshness gate and was admitting
books from 25 hours in the *future*. **The generalisable guard is one line:
assert the age quantity is non-negative before applying any cap to it.** If the
assert fires, the join points the other way from what the filter assumes.

**★ THE PROCESS LESSON, which is worth more than the parameter ★**
The first answer was **right for the wrong reason**. The retraction **fixed the
reason and, on incomplete data, produced a wrong conclusion — and arrived with
MORE confidence than the first, because it had a better derivation.**
**Fixing defects one at a time and broadcasting after each fix manufactures a
sequence of confident wrong numbers, each better-derived than the last.** After
finding the insertion defect, the right move was to ask *what else is wrong*
before reporting. **And the manager compounded it by publishing to main inside a
twenty-minute window twice, on a single unreplicated report each time** — speed
of correction is not a substitute for waiting until a correction is complete.


**RETRACTED:** the claim that the positive region *"collapses from {1¢, 2¢, 3¢}
to {1¢} alone"*. That was an artifact of the exclusion method. **Under insertion
all three beat k=0 and the curve is a clean monotone decay from a peak at 1¢,
crossing zero between 3¢ and 5¢.** Exclusion penalised larger leans spuriously:
phantom-inflated `|q|` made the sim lean more often and harder than the policy
ever would, and those extra leaned quotes drew extra real fills that were bad —
**the larger the k, the more inflation, which manufactured a cliff that is not
there.**

**THE LESSON THAT GENERALISES, and it is uncomfortable: the "collapse" was the
more dramatic finding and the one that FELT like rigour** — it cut the positive
region by two thirds. **It was the artifact. The less dramatic version was
closer to right.** Removing data feels conservative; it is not neutral.

*Known-answer check validating the new simulator against the reviewed one:* at
k=0 there is no lean, so inventory cannot steer anything and phantom-driven `q`
is inert — the two methods must select the identical fill set, **and they do to
the penny (4,321 fills, −$156.35 both ways).** The selftest asserts this on a
synthetic volatile walk so a future bug in the insertion path unrelated to
phantoms is still caught.

**Scope note: the BASE measurements elsewhere in this program are unaffected.**
BASE does not lean, so inventory never steers its quotes and exclusion and
insertion coincide exactly — as the k=0 row demonstrates. The contamination
bites only where inventory feeds back into price.

*Two mechanisms were proposed for the k boundary and both were refuted by their
own predictions* (instant-phantom: phantom share is flat in k; through-the-mid:
the boundary does not scale with spread, 3¢/1¢/1¢ across bands). **k=1¢ stands
as an empirical regularity — it improves per-fill P&L in all three spread bands
— not as a mechanism.** Effective lean is `min(k, s − tick)`; the post-only
clamp makes nominal k and effective k differ in tight books.

## ★ FLATTEN's inventory input — a pre-implementation constraint ★

**FLATTEN is the first STATEFUL policy this program has proposed.** Its lean is
a function of inventory, so **inventory stops being a scoreboard and becomes a
controller input.** That is the entire reason phantom exclusion repaired every
v1 analysis and failed on FLATTEN.

**v1 is stateless with respect to fills** — `core/quote/engine.py:200-225`
requotes at `ob.bid`/`ob.ask` unconditionally, and there is no inventory
variable anywhere in `core/quote`. So phantoms can corrupt v1's MEASUREMENT and
cannot corrupt its POLICY. **FLATTEN breaks that immunity**, and if its counter
is fed by the naive fill model **the engine will lean to flatten positions it
does not hold — invisibly, because the shadow fill model and the shadow
inventory agree with each other perfectly. A self-consistent wrong answer, which
is the kind that survives review.** On the WNBA tape the two differ by 63.9%.

**THE RULE: the P&L record and the position counter are DIFFERENT OBJECTS with
different truth conditions.** One is the study's accounting convention; the
other is a claim about what we own. **They must not be fed by a single fill
stream** — the position counter carries its own predicate, and that predicate is
the phantom test, so a fill can be SCORED while failing to MOVE INVENTORY.

- **SHADOW (Saturday):** inventory is fed **only by fills that survive the
  phantom test** — the book-inserted model, never the naive mid-cross one.
- **LIVE (if ever):** inventory comes from **venue order confirmations**, full
  stop.

*Free known-answer test, from D's validation:* at k=0 the lean is inert, so a
book-inserted run and a naive run **must** select an identical fill set — verified
at 4,321 fills and −$156.35 to the penny. Any engine that can run at k=0 gets
that equality as a permanent assertion on the inventory path.

## Recording requirement

`shadow_quote_fills` keeps `mid_at_fill` but discards the ask the engine held at
the same instant, so phantom status is **not computable from the row**. The
variant engines record **the touch at fill (best_bid_at_fill, best_ask_at_fill)
from the same observation the fill was judged against** — not re-joined from the
tape afterwards. Without it, Saturday's phantom classification depends on a
coverage-dependent join.

## Pre-declared expectation

**BASE on football is expected to lose**, in the −2 to −4¢/fill region, if
football behaves like WNBA. **A BASE result near zero or positive is the
surprise**, and would be the single most important read of the slate — it would
say the venue, not the strategy, was the problem. FLATTEN is expected to be
**less negative than BASE on dispersion**, not positive on mean.

**No in-sample result justifies capital. The forward test is the evidence.**
