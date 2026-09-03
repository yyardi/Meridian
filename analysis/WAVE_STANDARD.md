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

17. **The precondition citation duty (corollary to rule 10): a floor is a
   claim about data; a PRECONDITION is a claim about an artifact. Both carry
   the citation duty** — name the file/function/commit that satisfies it, or
   state explicitly "to be built and registered." An uncited precondition is
   where reifications breed. The type specimen (2026-09-02, the QUOTE v2
   congestion arm): a draft cited "measured wall-clock congestion windows,"
   which reified a retrospective bunching statistic into a deployable window
   list; the bad pointer then propagated — a builder's scaffold cited a third
   object matching neither the phantom nor the real artifact. Three pointers,
   one nonexistent object, caught only because the instrument's author checked
   the pointer against their own code before anything was built on it.
   (Proposed by the research agent; elevated by the manager same day.)

   *Corollary — EVIDENTIARY LOAD (D's formulation, 2026-09-03): standards
   scale with what a number is asked to CARRY. A live unpinned read is
   SUFFICIENT TO STOP a claim and INSUFFICIENT TO FOUND one.* This resolves
   the standing tension between "verify against the venue" and "pin
   everything," which have read as competing duties: they are not, once the
   standard is indexed to the claim's load. **Specimen, 2026-09-03: a live
   prod read killed its own author's founding premise, and would not have
   been permitted to establish one.** Declining to build needs less
   provenance than building.

   *Corollary — ASK THE SYSTEM, DON'T RECONSTRUCT FROM ITS EXHAUST (found
   by the manager and Quant A, 2026-09-03):* **when the system you are
   measuring can answer your question directly, ask it before
   reconstructing the answer from the traces it leaves.** Where rule 20
   says count the phenomenon on the substrate before building the fix,
   this says: **if the substrate reports the phenomenon itself, read that
   report first** — a reconstruction is not merely extra work, it is
   fragile in ways the direct answer is not.

   *SCOPE, because both cases occur:* reconstruction is legitimate and
   sometimes forced — when the system does not report the quantity at all.
   **State which case you are in before you build.** And a direct report is
   authoritative about what IT measures; confirm it answers your question
   rather than an adjacent one.

   **Specimens, and the pair is the point.** *The answer existed and was
   not asked for:* request dispatch reconstructed from DB row-write stamps
   read 60 req/s against a 12/s cap, while the venue's own HTTP 429 count
   sat at ZERO across every recorder's life — the reconstruction inferred
   dispatch from COMPLETION stamps, so concurrent completions in one second
   read as simultaneous sends. **A completion-time stamp is never a
   dispatch clock.** *The answer does not exist and reconstruction is
   forced:* the venue emits nothing for a zero-fill cancel and offers no
   order-status endpoint, so P(fill) is unobtainable by asking and the
   operator's own written log becomes the instrument. **Same night,
   opposite world, and the difference is entirely whether the system
   reports the quantity.**

   **The symmetry note, which is the sharpest part:** the ALARM (a sum of
   configured per-process caps) and the INSTRUMENT built to check it (a
   count of write completions) were **the same category error from
   opposite sides** — neither a sum of caps nor a count of completions is a
   dispatch claim.

   *Cross-reference with the matched-bases corollary above: both are the
   same disease — an instrument whose shape does not match the question —
   approached from different directions. One compares two numbers that
   measure different things; the other builds a number when the right one
   was available. A reader who finds either should be pointed at the
   other.* And the generalisation (A's): **"verify against the venue, not
   adjacent sources" was written about documentation and extends to
   measurement — the venue is authoritative about the venue, including
   about how it is treating us.**

18. **The synthetic plant: every mutation suite carries at least one
   SYNTHETIC PLANT asserting an exact expected value — a boundary instant, a
   known coefficient, a planted count — never only recovery-on-real-data.** A
   bug that distorts the measurement and the expectation identically passes
   every real-data test with confident wrong numbers. Type specimen: the
   congestion detector's datetime64[us] unit bug — a silent ~1000× duration
   rescale under which real-data causal replay "passed" with a wrong window
   count, caught only by a planted episode asserting the window opens at
   exactly t0+5s (congestion_detector.py @ d1fb6de). The load-bearing phrase
   is the author's: "distorts the measurement and the expectation
   identically." (B's entry, research-endorsed; the R5 harness complied
   before the rule existed — generator plants asserting exact injected
   values — which is the pleasant way to discover a rule was already
   necessary.) *Cross-ref, and they AGE TOGETHER: rule 20 is this rule's
   COUNTERWEIGHT, not merely rule 16's complement — a plant without a count
   may be a real mechanism that fires on nothing; a count without a plant
   may be a broken query returning a comfortable zero. Rule 18 was one day
   old when it manufactured the sensation rule 20 exists to puncture.
   Amendments to either must notice the other.*

19. **Every registered checker DECLARES ITS BLIND SPOTS — at least one
   class of defect it structurally cannot catch, stated where the checker
   registers.** Precedent: the deployed guards' own coverage statement
   (31/44 caught, 13 unreachable by any state-only check — stated, not
   hidden). Rule 18 covers the bug that distorts measurement and
   expectation identically; this covers the checker BUILT so both legs
   share a source: reconciliation proves consistency, never correctness,
   and a checker whose legs both derive from one origin inherits that
   origin's defects invisibly. Type specimen (2026-09-02,
   wrong-but-consistent, findings B14): the recording binary stamped
   observed_at from the forbidden cross-process clock, and the
   recording-integrity scorer — plants passing, shown able to fail —
   still could not see it, because replay and record shared the stamp.
   A checker with no stated blind spot has not been asked what it cannot
   see — and the asking is where the catch lives: the scorer's author
   found the bug by auditing their own instrument's structure, hours
   before any data existed to be corrupted. (Research proposed; manager
   elevated same day.)

20. **Substrate-count duty (complement to rule 16). Before building anything
   whose value depends on a condition, COUNT that condition on the substrate
   it will run against.** A planted-case reproduction proves a mechanism CAN
   produce the symptom; only a substrate count shows it is what fires on real
   data — and a passing planted test produces the sensation of having
   checked, which is exactly when the count gets skipped. A zero count does
   not always forbid building: it forbids the CLAIM. It sets the label
   (bugfix vs defensive hardening), and "fires on nothing today, guards a
   silent failure tomorrow" is a legitimate label — stated in the code, not
   only the PR. Rule 16: reproduce the known answer before reading live.
   This: measure that the condition exists before asserting your code
   addresses it. (D and A's rule, body verbatim; c7's name on the two
   additions below.)

   *Addition — the counterweight, and the general lesson (c7):* rule 20 is
   rule 18's counterweight and they age together (see rule 18's cross-ref).
   The lesson generalises beyond this pair: **registering a rule that creates
   a hazard obliges us to register its counterweight beside it** — every
   future rule should be asked, at adoption, what false confidence it
   manufactures.

   *Addition — the deferred-count clause (c7):* when the substrate does not
   yet exist the count CANNOT run, so it is DEFERRED AND NAMED IN THE CODE,
   and every claim the artifact makes is PROVISIONAL until it runs on first
   data — the first-data count a required deliverable, not a good intention.
   In an unmeasured domain, plants carry everything AND every substrate count
   is deferred, therefore every claim is provisional until first data.
   (Landed in GRIDIRON's registration, b4d4505, the program this was written
   for.)

   *Precedent, four agents, one species — which is what makes it a practice
   rather than anyone's penance:* research's attrition misattribution (three
   causes named, none run); A's NULL-timestamp diagnosis (disproven by a
   production count: 15,254,061 depth rows, zero unstamped); the manager's
   top-N-levels hypothesis; and the manager's "two different questions"
   reading, flagged unverified pending its funnel. Each a mechanism reasoned
   to and never counted. **A fourth hypothesis is not a diagnosis** — the
   correction pattern is A's: after three failed hypotheses they shipped an
   instrumented funnel and handed the measurement over rather than producing
   a fourth guess.

   *Corollary — MATCHED BASES (c7, 2026-09-03, proposed as a corollary
   rather than a new rule because the registry needs this where a reader
   would look, not another number):* **no cross-population comparison
   without matched bases; state each number's basis in the same sentence
   that compares them.** Already a practice in this record without a name —
   capture-vs-settlement, drop-vs-relinked linking policy, the census
   commit pin. **Fifth instance of the night's signature species, and the
   one that nearly became a program's founding claim:** WNBA depth at our
   quote price in-play compared against NFL top-of-book pregame at T-7,
   two axes differing at once. The others: depth read as capacity, a
   crossing read as a trade, a status name read as a mechanism, patient
   limit orders compared to touch-joining quotes. **Every one was two
   numbers measuring different things placed on the same axis.**

21. **The profit-mechanism audit. Any measured or simulated result showing a
   GAIN must name the counterparty and the reason they lose, and that
   mechanism must be the one under test.** A result whose profit arrives by a
   different mechanism than the one being studied is measuring something
   else, however real that something is.

   The asymmetry it corrects: **we scrutinise losses because they feel like
   bugs and accept gains because they feel like findings.** Every other rule
   here polices measurement generally; this one polices the direction we are
   least motivated to police.

   Type specimens, both from one evening's flattening simulator, both
   profitable, both wrong: (a) it sold BELOW THE BEST BID — a counterparty
   the venue's post-only rejects outright, so the profit came from a trade
   that cannot exist (+$10,313 on a −$182 book); (b) it leaned its ask
   UNCONDITIONALLY, which is "quote to get short" rather than flattening — a
   real counterparty, the wrong experiment (+$1,928).

   And the audit applies to the audit: the story then told about where (b)'s
   money came from — "far rungs mostly expire worthless" — was itself
   unverified, and when measured (`analysis/rung_calibration.py`) the board
   showed no such bias in either direction. **Naming a counterparty is a
   hypothesis, not an answer; the rule is discharged when the mechanism is
   measured, not when it is plausible.**

   Magnitude is not a substitute. Both bugs were caught only because their
   numbers were absurd; a subtler version returning a plausible +$300 would
   have shipped. *"Where does this money come from, and who pays it?"*
   catches both in one question, before magnitude enters. (D's rule, in
   their words.)

22. **SILENT ABSENCE — a zero is the least self-validating result there is.**
   A system reporting zero has two explanations it cannot distinguish:
   **the world is empty, or the instrument is.** A non-zero result partially
   validates its own instrument — something was found, so the thing was
   looking. **A zero validates nothing, and is therefore the result that
   most requires provenance and habitually receives the least.** Before a
   zero counts as evidence of absence, establish that the instrument is
   running the code you believe it is running, against the substrate you
   believe it is reading.

   *SYMMETRY — added after the rule's own author broke it in the OPPOSITE
   direction, hours later.* **An unprovenanced zero supports NO conclusion
   in EITHER direction. Believing it and disbelieving it are the same
   error**, because the zero carries no information about which explanation
   holds and the reader supplies one either way. The manager read a CORRECT
   zero (`discovered=0` meaning "no NEW games since last discovery") as a
   stale-image failure and spent real time hunting a phantom; the earlier
   specimens read broken zeros as quiet venues. Both readings were the
   READER's contribution, not the data's. **The elegance is that one test
   resolves both directions** — the positive control below separated
   instrument-empty from world-empty in three of three cases, including one
   where the answer was genuinely the world (Kalshi's WNBA season gap).

23. **A NAME IS A CLAIM, NOT A MEASUREMENT.**
   A configured or well-named value asserts its own meaning, and that
   assertion goes unchecked because **it does not look like a claim**. We
   verify values and trust names — but the name is where the meaning lives,
   and the meaning is what gets acted on.

   *AGGRAVATING FACTOR — the better the name, the less it is checked.*
   Nobody audits a field called `occurrence_datetime` on a clock question,
   or an env var called `INTERVAL` on a cadence question. **Plausible naming
   buys immunity from the only check that would catch it, which inverts the
   usual relation between quality and scrutiny.**

   *THE TEST — verify a name against a source that CANNOT INHERIT THE
   ASSUMPTION.* ESPN's clock does not know what Kalshi calls its field; a
   loop's observed period does not know what its env var is named. **A
   second source that shares the naming shares the error — which is why
   reading the docs is not a check.**

   *SCOPE, deliberately small because "verify every constant" is
   unaffordable and would simply be ignored:* **(a) values that reach an
   operator's eyes**, because those become the shared mental model and
   propagate into every decision taken on them; **(b) values that gate
   whether data is captured at all**, because those failures are
   UNRECOVERABLE — you cannot re-record last night.

   *RELATION TO 22.* Rule 22 concerns ABSENCE — a zero that cannot
   distinguish an empty world from an empty instrument. This concerns
   PRESENCE — a value that is confidently, specifically, plausibly wrong.
   **A zero announces itself as nothing; a named value announces itself as
   a fact.** Shared parent: a reading whose interpretation is supplied by
   the reader rather than by the data. The rules are cut apart because
   their TESTS differ — 22's remedy is a positive control on the same
   substrate, 23's is an independent source that cannot inherit the
   assumption.

   *SPECIMENS — five, in one night, across five subsystems, found by four
   people.* (1) `occurrence_datetime` carried a kickoff+3h END stamp under a
   name that says start; storing it as a start would have opened every
   recording window three hours late and forfeited the whole pregame tape,
   with nothing anywhere reporting an error. (2) `KALSHI_INTERVAL=60`
   produced a ~124s period at 106 games, because the loop sleeps the
   interval AFTER the cycle rather than sampling on it — no cliff, no
   overrun, no alarm; the tape simply thins. (3) The healthcheck **printed
   the configured interval under the label "cycle"** — **a checker that had
   absorbed the error it exists to detect**, confirming the wrong model back
   to the humans reading it (simultaneously a rule-19 failure: an undeclared
   blind spot, namely that it cannot detect drift in the very quantity it
   displays). (4) `ORDER_STATE_PARTIALLY_FILLED` read as queue truncation
   when the values were 99.69% — decimal dust; recorded at the time as *"a
   field's name asserts a mechanism; only its values evidence one,"* which
   was this rule in embryo and was under-registered as a one-off. (5)
   `n_zero` counting something adjacent to its name.

   **A pattern found five times in one night by four people is not a rule
   anyone needs persuading of — it is a description of how this codebase
   fails.** (B's formulation and the manager's framing; the precedent line
   and the cut are the research agent's.)

   *OPERATIONAL TEST, concrete enough to build:* a zero is evidence only
   when the instrument has demonstrated it can return non-zero ON THIS
   SUBSTRATE — a positive control. **Every zero-reporting monitor should
   carry its LAST-NON-ZERO timestamp and count.** A recorder that has never
   once found an NFL contract tells you nothing by reporting none; one that
   found fifty yesterday and zero today is reporting news.

   *RELATION TO ITS NEIGHBOURS:* rule 20 says count the condition before
   claiming your code addresses it; **this is the inverse case — the count
   ran and returned zero because the INSTRUMENT was empty, not the world.**
   And it pairs with rule 21 (gains must name their counterparty): **21
   guards results we WANT; 22 guards results that RELIEVE us. Both express
   one principle — scrutiny should scale with how much a result comforts
   you, and by default it scales the opposite way.**

   *Specimens, 2026-09-03, all in one night:* Kalshi NFL logging
   `discovered=0` indistinguishably from a quiet venue (stale image, found
   by accident while verifying an unrelated branch — **detection was luck,
   not process**); venue-timing code on main and absent from six running
   containers; `analysis/` never COPY'd into any image; the wallet's
   `n_zero` counting something adjacent to its name; the scorer's empty read
   as a false all-clear. (Research agent's rule; the operator asked for the
   night's failures to be audited systematically rather than patched.)

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
