# Wave Standard v1

Written by the research agent **before any agent computed**, for the 2026-09-01
edge-hunt wave. Every line has a scar behind it. It lives here, not in a message
thread, because a lesson is operative only where the work happens.

## Preamble — the strongest configuration this system has produced

**Two agents whose results are in tension, each carrying the other's objection
inside their own document.** On 2026-09-02 Quant B's predictor implied that
Quant D's exit-risk premium might double-count a risk the price already charges;
**D wrote that objection into their own candidate and blocked it themselves**,
rather than defending it. B, earlier the same night, killed the manager's
framing by building the instrument that would have supported it.

**Trust in either result exists BECAUSE the other's objection is in it.** An
artifact that answers its strongest known objection in its own text is worth
more than two artifacts that agree.

## Deliverable shape — every agent

1. **The artifact**, with a reproduction command and the export instants it ran
   against (the `20260901T195202Z` pins).
2. **Top-3 candidate edges.** Each is ONE falsifiable sentence, plus the
   confound/anchoring check it must carry, plus what forward data would test it.
3. **Top-3 negatives, with the mechanism named.** A wave that returns *"we lose
   money in X, Y and Z and here is why"* is a success.
4. **The boring list** — everything checked and found flat, so nobody re-mines
   it.

## Rules enforced at review — non-negotiable

1. **Every number carries** window, unit, policy (which P&L accounting: venue
   average-cost ex-fee / FIFO / round-trip), n **in games and in rows**, and
   game-clustered intervals. **No CI without clustering.** Counts and
   composition before ratios — on this feed the ratio survives errors that move
   the composition, three documented times.
2. **Money at price, fees explicit, gross/net labelled.** Fills are not
   decisions: anything fill-dependent scores under the pessimistic rule with the
   measured concessions (**2.11¢ pregame, 4.70¢ in-game**). **46% of intents
   never filled** historically.
3. Any pattern of the form *"the market disagrees with a historical frequency"*
   **carries its anchoring check inside the write-up**. A base rate is a
   benchmark only if it conditions on everything the price conditions on.
4. **Instruments are mutation-tested before real data** — each pipeline reads
   ~zero on a synthetic null and recovers a synthetic injected effect. A's
   ledger especially: it is the substrate B/C/D consume, its P&L policy must be
   ONE labelled definition, reconciled against the venue-pinned intent-rule
   ledger (**26/26 WNBA markets to the cent** — that is the ground truth to
   match).
5. **Language is DESCRIPTIVE — HYPOTHESIS-GENERATING, on every page.** No
   PASS/FAIL in this wave. Nothing gates. Promotion path: the research agent
   writes the registration (floors in games, forward cohort only, one input per
   gate, and a **closure clause**), then the forward test is the evidence.
6. **The multiple-comparisons statement prints in every write-up.** Four agents
   across dozens of slices yields several sub-0.05 patterns by chance alone.
   **Ranking is mechanism plausibility + effect size + robustness across slices,
   never p-value.**
7. **The capital line, verbatim, everywhere:** *"No in-sample result justifies
   capital. The forward test is the evidence."* The operator has real money
   ready and will read for hope. The write-ups must not sell it.
8. **Known instrument hazards.** `side`/`outcomeSide` encode book mechanics —
   `intent` is the economics. `outcomePrices` is a JSON-encoded string.
   Quantities are 2dp-rounded. Bookless endgames make exit availability a
   per-market-type-per-game fact with **no safe-harbour type**. FT rows carry
   NULL books. Cohort-tick counts and raw-row counts are different units and
   both true.

9. **A live gate is not relitigated by an exploratory slice.** Where a
   registered test covers a region, its read lands first and the exploratory
   work inherits the answer. If the registered test is unresolved, exploratory
   findings in that region carry an explicit *"the registered test on this
   region is unresolved"* header. Exploration may generate candidates in a
   gated region; it may not quietly supply a verdict there.

## Run from pins, not from a database

Where a run can be executed against frozen CSV exports rather than a live
database, it is. Not for convenience — **it makes the window incapable of
changing.** Every prior at-floor attempt read a database whose contents moved
underneath it, and the source-window rule could only ask the author to *state*
the window. Reading pins removes the failure instead of documenting it, and it
guarantees the registered test and the exploratory wave cannot disagree about
what the data said.

10. **A registration that names a floor must cite, inside itself, the coverage
   table that makes the floor reachable.** And its corollary, learned the same
   way: **an exemption is a claim about dependencies.** And its twin, confirmed twice in
   one day: **inheritance claims are exemptions wearing different clothes** —
   *"same as X"*, *"the same shape as Y"* carry the same citation duty as a
   floor, **and their disproof is usually already printed on the page being
   cited.** *"Unaffected"* and
   *"needs no X"* carry the same citation duty as a floor. R2 was ruled
   "unaffected, all 11 seasons" and briefed onward as "needs no market data"
   — while its estimand names its anchor in its second symbol
   (`dev = margin − E·(elapsed/48)`). The dependency check is reading the
   estimand's own formula, which would have cost ten seconds. An unchecked
   exemption propagates further than an unchecked floor, because nobody
   re-derives a claim that something does *not* matter. Floor feasibility is checked at
   registration time, not discovered at fit time. Two gates were registered on
   2026-09-01 whose anchors did not exist for enough seasons; both could never
   have passed at any effort, and it was caught only because the executing agent
   asked whether the data existed before fitting. A floor is a claim about the
   data, and an unchecked claim about the data is how a gate-that-cannot-pass
   gets written by someone who knows better.

## Multi-topic branches can reintroduce superseded text

An honest merge of a branch that carries published-report text alongside new
code can **silently restore a version main has already corrected**. It happened
on 2026-09-02: a gate harness arrived on a branch that also carried its author's
earlier report commits, which main had superseded with a confound correction —
merging would have republished the confounded text under a PR titled for the
harness. GitHub flagged it only because the files happened to conflict; a
non-conflicting case would have merged clean.

**Practice:** gate code lands **harness-only**, as a single file where possible.
Any branch carrying published-report text is **diffed against main's corrections
before merge**, and the merge is refused if it would revert one.

11. **Verify the landed text on main before reading, never the relay.** On
   2026-09-02 a relayed exemption — *"R2 needs no anchor"* — propagated through
   three people while the formula that refuted it sat in the registration the
   whole time. **The relay is a pointer; the artifact is the claim.** An
   executing agent reads the registration on main, not the dispatch that cites
   it.

12. **A pin declared in prose and not enforced in code is not a pin.** Every
   registered pin carries either an **enforcing assertion** (the harness
   refuses) or a **printed-composition line** (the reader can refuse). The R3b
   defect is the type specimen: a registration declared 23 games unusable, the
   fold builder admitted them anyway, the gate was invariant and the physics
   table was contaminated five-fold in one CI — **caught only because the
   harness prints its own composition.** Composition-before-ratios is an
   **output requirement**, not a review habit.

13. **Feed-quality filters are subject to the same registered-term audit as
   gates.** A QC rule can silently unregister a term: on 2026-09-02 a
   cross-frame margin comparison (regulation-end vs OT-inclusive) deleted a
   registered population — 537 of 701 OT games — from every gate read. The
   catch came from printed composition, the third time that requirement has
   paid. The audit question is one line: **"does any filter's predicate
   reference a frame the registration excludes?"**

14. **Every candidate registration states its expected FIRING RATE** (per game
   and per slate) from the descriptive data that motivated it, **and the
   verdict reports the realized rate beside it.** An edge that cannot fire
   often enough to matter at the operator's capital is a finding, not a
   strategy — the operator's words, now the registry's words.

15. **A census whose selftest can't produce a fake episode hasn't tested its
   episode detector.** B's first cross-market census shipped three headline
   numbers that were ALL instrument artifacts — unbounded stale fills,
   wide-bracket interpolation, a lag rule measuring jitter — surviving a green
   selftest because the suite never perturbed timing. **Mutation suites for any
   timing-sensitive instrument must include a jitter-null, and one top episode
   gets hand-verified before any census is believed.**

16. **The known-answer duty: any new instrument touching a measured domain must
   reproduce the measured value on the pinned substrate BEFORE its first live
   read.** It complements the mutation suite exactly — mutation proves the
   needle can move; the known answer proves it points at truth on real data.
   The type specimen: the day-one survey's coherence module first reported
   6,963 violations against a measured invariant of ~1 — a dominance-direction
   sign error masked by two vacuous selftest cases, caught only because the
   boring list held a measured value to disagree with. **A closed negative is a
   calibration standard for every future instrument in its domain.** The night
   we can't re-run is exactly the night the instrument must already be proven.
   *Cross-ref: the ffill-staleness hazard entry is the habit form of this duty —
   one discipline at two strengths; amendments to either must notice the other.*

## Hazard entry, appended 2026-09-02 (D + B; research-endorsed) — unbounded ffill fakes liquidity in dying books

**The trap:** joining or pivoting a tick tape and forward-filling quotes
without a staleness bound treats an absent quote as the last one repeated.
On a board where books thin and die (this venue's defining late-game fact),
that manufactures simultaneity that never existed: a stale side held
against a fresh one produces phantom crossings, phantom lags, phantom
liquidity.

**Hit twice, independently, same tape, same day.** D's coherence module
first read **6,963 "persistent executable violations" against a measured
invariant of ~1** — raw-tick ffill held stale quotes against fresh ones
(compounded by a dominance-direction error the discrepancy then exposed).
B's cross-market census: an unbounded as-of forward-fill let rungs whose
books had died keep quoting into the winner↔spread triangle, manufacturing
fake incoherence precisely in decided games — a 2s staleness tolerance on
the join collapsed 1,462 fake persistent >10¢ episodes to 101 (a separate
interpolation-bracket guard took the rest to 1). The attribution split is
part of the record: the ffill trap accounts for 1,462→101; 101→1 was a
DIFFERENT trap (wide-bracket interpolation), and crediting it to this rule
would overstate what a staleness bound buys.

**The rule:** any cross-series comparison on a tick tape must bound
staleness explicitly and state the bound in the artifact — compliant
patterns: c7's 10s-fresh grid (both series must quote within the same
bucket; the coherence instruments), B's 2s as-of tolerance on the 200ms
native grid (`cross_market_census.py`). An absent quote is ABSENT, not the
previous value; and per the recorder's own book_tier principle, distinguish
*no resting size* from *we did not look*. A joined number whose staleness
bound is unstated is unreviewable.

**The tell that catches it:** compare the instrument's first read against
any known invariant or closed count before trusting it — the 6,963-vs-1
discrepancy is what surfaced this trap, twice. This tell is the HABIT form
of **rule 16, the known-answer duty**, which is its mandatory-gate form:
one discipline at two strengths — an amendment to either should notice the
other. (Same family as "break a new check on purpose before trusting it".)

## Priority hint

The price bands where size actually exists (**35–65¢**) have never been sliced
for edge. V1–V3 says the old model's edge lived where nothing could fill. Where
our decisions land on that axis is the first thing to look at.

## The registered test runs first

#20's at-floor sequence uses the **same pins** as this wave, so the registered
test and the exploratory wave read one window and cannot disagree about what the
data said. It should resolve **before** Q4-adjacent exploratory slices land, so
those inherit its answer instead of rediscovering it.
