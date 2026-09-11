# Meridian — state as of 2026-09-06

## THE SHORT VERSION

**Market making: CLOSED.** Break-even needs **49.7%–57.8%** benign fills depending on
H's population — the verdict is invariant across the range; the measured
ceiling is 23.7%, **upper bound 31.4%** (was quoted as 35.8%; see below). It closes structurally, not on an
assumption: break-even needs **H = 3.57¢**, i.e. benign fills concentrated above a
**7.14¢ quoted spread** — the widest **8.9%** of what we actually quote. A passive
maker cannot earn more than the spread it quotes.

> **★★★ THE FLOOR IS A RANGE, AND "MATCH |A|'s POPULATION" IS THE WRONG PRINCIPLE.**
> Break-even is `r·H = (1−r)·|A|`, where **r** is the benign share, **H** is what a
> BENIGN fill earns and **|A|** is what an ADVERSE fill loses. **Those are disjoint
> populations by construction** — so H and |A| should *not* be measured on the same
> rows, and the population-matching argument that restored 57.8% is unsound even
> though it produced an internally consistent pair.
>
> `real ⟺ ask ≤ B` is an ADVERSE condition (the ask came down to us), so |A| on real
> fills is right. A **benign** fill is `ask > B` — a seller crossing to our resting
> bid while the ask holds — which is the **phantom** bucket (`probe.py:81`: the
> simulator "cannot distinguish a true phantom from a real benign fill"). So H
> belongs there:
>
>       H on guarded REAL     1.193¢ → 57.8%   ← published; the ADVERSE population,
>                                                where a benign fill cannot occur
>       H on guarded PHANTOM  1.653¢ → 49.7%   ← where benign fills actually live,
>                                                contaminated by true phantoms
>       H on guarded BOTH     1.482¢ → 52.4%
>
> **Every one clears the 31.4% ceiling by 18–26 points** (57.8% → +26.4, 52.4% →
> +21.0, 49.7% → +18.3). **And the close breaks only if H > 3.569¢ — 2.16× the
> phantom bucket's own mean and 2.41× the pooled mean [c7].** Benign fills would
> have to concentrate at more than double the quoted half-spread of the bucket they
> live in, **and the incentive runs the other way**: a wider quoted spread means a
> counterparty gives up more to cross, so benign crosses should be *rarer* there.
> That converts "invariant across the range" into "and here is how far outside it
> would have to go."
>
> **★ AND THE RANGE IS DIRECTIONAL, NOT MERELY WIDE [A, c7]: `H = s_q/2` is a
> CEILING on benign earnings**, because it is geometry-classified (what we quoted)
> rather than informedness-classified (what a benign counterparty actually left us).
> True H ≤ measured H, so **true floor ≥ the range** — 49.7–57.8% is a *lower bound*
> and the close can only get stronger from better measurement. Every correction
> tonight moved the margin; this one fixes its **sign** permanently.
>
> **Full spread, restored as a range too [A]:** 2H = 2.386–3.305¢ → r\* 40.6% down
> to 33.1%, **+9.2 to +1.7 points** over the ceiling. It clears everywhere, but it
> is *thin* at the full-spread/phantom corner. The earlier "+9.2 only" overstated
> it — a claim withdrawn once for the wrong reason and restored at the strongest
> reading.
>
> **The close is invariant and the exact floor is not identifiable** — the phantom bucket mixes true phantoms
> with real benign fills and the simulator cannot separate them at any sampling
> rate. That is the permanent measurement gap the probe exists for.
>
> **Quote the range, not a point.** This number has moved three times today
> (57.8 → 51.0 → 57.8) because each move argued for a different single population,
> and the honest answer is that no single population is correct.
>
> **★★ 57.8% RESTORED — MY "CORRECTION" TO 51.0% WAS THE ERROR [c7 + Debugger].**
> I withdrew H = 1.193¢ as unsourceable and replaced it with **1.569¢, the
> all-fills mean quoted half-spread**, giving 51.0%. **1.193¢ was never
> unsourceable: it is `mean(s_q)/2` over the SAME 22,062 guarded real fills that
> produce |A| = 1.634¢.** Verified:
>
>       H over all 73,964 fills           1.569¢  →  floor 51.0%   ← what I published
>       H over the 22,062 guarded real    1.193¢  →  floor 57.8%   ← population-matched
>
> **The original 57.8% was internally consistent — numerator and denominator on the
> same subset. My fix paired a GUARDED |A| with an ALL-FILLS H**, which is the exact
> population mismatch I spent the night catching in other people's work. Third
> movement of this number today: 57.8 → 51.0 → 57.8.
>
> **What was actually wrong was never the source — it was that NEITHER figure stated
> its aggregation or its subset.** 1.193¢ moves from *withdrawn* to **superseded
> by nothing; correct, with its population now stated.** τ's 2.69pp inherited it and
> needs its own population statement rather than an inherited correction — a taker's
> half-spread is not the guarded maker subset, so **3.07pp is not established
> either.** [flagged to A and d5]

> **AND THE CEILING WAS WRONG TOO, in the opposite direction [c7].** 35.8% was an
> *assumed* clustering widening (G≈20, ρ≈0.3, design effect 2.5). **Measured on
> the same 118 events: G=35, ρ≈0, design effect 1.05.** Three independent routes
> agree — naive CI [16.1, 31.4], cluster-robust sandwich [15.9, 31.6], cluster
> bootstrap over games [15.4, 30.7]. **The doc's [11.6, 35.8] is none of them.**
> Honest upper bound **31.4%**, essentially the naive one, because there is almost
> no clustering to correct for. 23.7% reproduces exactly (28/118).
>
> **★ THE GENERAL FORM, which matters more than either number [c7]: a conservative
> unmeasured constant survives audit longer precisely because nobody challenges a
> figure that argues against them.** c7 argued *for* 35.8% over 31.4% that morning
> on honesty grounds, and never checked that anyone had measured it. Same shape as
> 1.193¢, opposite sign — and the sign is what protected it.
>
> **Net: floor 57.8% vs ceiling 31.4% — 26.4 points clear.** The floor returned to
> its published value; only the CEILING correction survived (35.8% → 31.4%), and it
> widens the margin. My floor "correction" was withdrawn as a population mismatch.

**Cross-venue: CLOSED, but NOT on the argument this line used to make.**

> **CORRECTED 2026-09-06 [c7 refused M's edit].** "Maximum gap of one tick across
> 620 cells" is the **single-snapshot** row, which `docs/math/cross-venue-status.md`
> **supersedes**. Its own preferred measurement — instant-matched, ≤10s lag — finds
> **5 instants at ≥2¢ and a maximum of 5.00¢** across 558, two at sub-second lag and
> explicitly *not* staleness artifacts. On that row the close is **coefficient-
> sensitive**: the best genuine instant is 4.0¢ gross at 0.4s lag, netting **+0.75¢**
> at Kalshi 0.070 but **+1.25¢ at 0.050** — over a tick, i.e. profitable.
> **I instructed c7 to write the room argument in; they stopped and checked. It
> would have retired the wrong question permanently and looked more rigorous doing
> it.**

**The honest ground is concentration, not room:** the close rests on **one game
(UAB/Illinois), five instants, 0.9% of 558** — which the doc already says "cannot
be generalised and is not an edge claim." That survives the coefficient being wrong
because it never depended on it; it depends on n=1 game. Dead on fees in the middle
and on 22–26¢ spreads in the tails, both unaffected.

**Directional vs ESPN: LOST, cleanly.** B's CFB win-probability model scores
**−0.01119 [−0.043, +0.021], G=28** against ESPN's published number, and **0 of 5
pre-declared subsets clear zero with every point estimate negative** — worst in
the late-game cut (−0.09277), exactly where a live model would have to earn. Not
an edge the pooled test missed. **We do not beat the public model.**

**★★ AND ESPN HAS NO PREGAME PRIOR — the finding of the day, and it redirects the
programme.** ESPN opens **every** CFB game between 52% and 66% for the home team
(33 games, sd 0.0222, **zero** with a strong prior; c7 replicates on 23 games at
sd 0.0176). The venue prices ~half its board as strong favourites or dogs
(sd 0.2663, 53% strong). **12–15× dispersion.** So:

- **"Trade ESPN against the venue" is CLOSED** — ESPN is not better-informed, it
  has no prior; that route would systematically fade favourites. I proposed it
  this afternoon as the only one left. It lasted four hours.
- **B's tie with ESPN reads differently:** two models sharing a blind spot agree.
  Their result is "no edge from game state alone", not "no edge".
- **The market anchor is the missing information**, not a nice-to-have — which is
  what nflfastR's per-game constant has been all along.

**Live proposal (c7):** venue as prior, ESPN's *delta* as the update. Falsifiable
on Saturday's settled cohort. **09-12 gates every date.**

**Directional in money (PULSE):** filled P&L +4.761pp [−1.455, +10.978], spanning
zero; **58 games** settles it, not the 15,400 the accuracy statistic needs.

**The probe: recommended AGAINST arming.** $278 buys a confirmation we no longer
need at 17 points clear. It remains the only instrument that can separate a true
phantom from a real benign fill — a permanent measurement gap — but that is a
different claim from being worth the money.

**Infrastructure:** the CFB venue recorder died 09-05 22:08Z from a compose
collision and was restored 09-06 20:43Z; verified dense at a 2.27s mean gap.
Tonight's tape is the first that is dense AND moving. Two monitoring instruments
are designed and neither is built. **Eleven PRs are unreviewed**, `STATUS.md`
itself is untracked — a fresh clone sees only the August version — and the
`cfb_game_map` rebuild (73 matches vs 55 stored, dry run clean) is a prod write
blocked by permissions.

**★ THE NIGHT OF 09-06/07 — first healthy football slate, and what it settled.**

- **THE VENUE'S FRAME IS CONFIRMED.** 38 scoring events across two settled games,
  bidirectional. Accuracy rises monotonically with move size and **clears c7's 91.7%
  gate from p75 of the drift distribution upward**; strongest cell **21/22,
  p=5.5e-06**. *An inverted frame would produce the opposite slope, so the curve is
  the test rather than a robustness check.* Unfiltered: 24/28 = 85.7%.
- **σ's LINE DEPENDENCE IS REFUTED WITH POWER** (9.7× signal-to-scatter). Shipped as
  **σ ≈ 15.9, flat**. Three cohorts, all flatter than the original, which was the
  only one from a known-bad selector.
- **B's PRE-FLIGHT IS VALIDATED END TO END** — all three conditions now seen both
  passing and failing. Coverage **100.0% (120/120 minutes)** on an explicit window,
  and **`UNTESTED` + FAIL when unwindowed** on the same file. *It refuses to claim a
  pass it cannot justify.*
- **THE FIRST COMPLETE GAMES EXIST.** Three caught at `P1 0-0` with pregame *and*
  live quotes; two settled. The 22:08:57Z boundary that blocked five measurements all
  week is gone.
- **`scoring_play` IS RETIRED AS AN EVENT DETECTOR** — misses **39.1%** of score
  changes (284 of 726, **56 whole touchdowns**).
- **CONSTANTS AUDIT: 3 of 5 reproduce**, 1 withdrawn (assumed clustering), 1
  unverifiable from the venue (Kalshi 0.07, three endpoints, no fee field).

**Still gating everything: both recorders up before kickoff on 09-12.** The
readiness check covers T−30 only; **both of this week's failures began mid-slate**,
and COLLAPSED/NOT_WRITING are built, tested and **not deployed**.

**Method note.** Roughly a dozen instruments returned confident wrong answers
today — tests that could not fail, a guard whose own definition had drifted, a
coverage check blind to the truncation it existed to catch, intervals
systematically too narrow. Nearly all were caught by their own authors after
applying the same scrutiny to a peer's work. **The detail below is long because
the corrections are the product.**

---


Written by the run manager, 2026-09-06. Every figure carries **who measured it
and on what** — a number without provenance in this file is a defect.

*Market-making section: the adverse anchor, floor and H inversion are* [A];
*the benign ceiling and its caveats are* [c7]; *the commensurability argument is*
[A + c7, joint]; *the selection close is* [B]; *probe sizing is* [A].
*Football and infrastructure: recorder and compose findings are* [Debugger + d5];
*liveness and venue-payload findings are* [a1]; *the 09-12 registration is* [B].

> ⚠ **This supersedes `docs/STATUS.md`, which is dated 2026-08-04 and is stale.**
> That file still describes making as unbuilt, quotes ROI −2.33% and a 52.4%
> breakeven. It is committed, so it is not mine to delete — it should be stubbed
> or removed by its owner. Until then, "read STATUS.md" is ambiguous.

**Not everything here is a measurement.** Marked inline: [M] measured,
[A] algebra on measured inputs, [P] power calculation, [E] estimate or
projection. Claims are stronger than measurements only where marked.

## The two strategies

**Market making — CLOSED against our own break-even floor.** (Against the
independently-registered 10% kill line the same evidence does NOT close it —
the verdict flips on which line is named, so the line is named every time.)

> **CORRECTION.** Every figure below that includes a "maker rebate" is wrong and
> too optimistic by ~0.28¢/fill. **There is no maker rebate.** `docs/findings.md`
> C7 was RESOLVED 2026-08-25: the advertised rebate has never been observed in
> this account across its entire history, and the credits that looked like one
> were a 50%-of-own-taker-fees promo that ran 2026-03-29 → 05-10 and ended.
> V9: no maker fee field exists. The code defaults θ_maker = 0 and
> `--assume-maker-rebate` is a sensitivity arm for a credit never seen.
> The manager reintroduced the retracted claim from a web search. Correcting
> the numbers makes making's verdict **worse**, so the close holds a fortiori.
- **Rebate-free** (recomputed per fill, not by subtracting a mean), fills-weighted
  cluster-robust sandwich:

      headline, real, no guard     CFB −2.080 [−3.633, −0.526]  G_eff 20.5/35
                                  WNBA −3.376 [−4.746, −2.007]  G_eff 11.8/13
                                pooled −2.400 [−3.592, −1.208]  G_eff 30.4/48

      guarded anchor, real+guard   CFB −1.357 [−2.754, +0.041]  G_eff 19.9/35
                                  WNBA −2.462 [−3.551, −1.372]  G_eff 11.2/13
                                pooled −1.634 [−2.694, −0.573]  G_eff 29.5/48

- **Break-even needs ≥57.8% benign fills** [51.0% withdrawn — it mismatched populations] —
  removing the phantom rebate raised the floor from 48%. Measured ceiling **23.7%**;
  **upper bound 31.4%** — the naive CI, which is also what the sandwich [15.9, 31.6]
  and the game bootstrap [15.4, 30.7] give. ~~clustering-widened 35.8%~~
  **WITHDRAWN 2026-09-06 [c7]: the widening was assumed (deff 2.5), measured deff
  is 1.05 — there is almost no clustering to correct for.**

- **AND THE CLOSE IS STRUCTURAL, NOT AN ASSUMPTION ABOUT EARNINGS.** Inverting
  r\* = |A|/(H+|A|) for H — how much a benign fill would have to earn:

      H = 0.60¢                    r* = 73%
      H = 1.193¢  (guarded real fills — POPULATION-MATCHED to |A|)  r* = 57.8%  ← use this
      H = 1.569¢  (all fills — mismatched population)               r* = 51.0%
      H = 2.386¢  (FULL spread)    r* = 40.6%
      H = 5.26¢                    r* = 23.7%   ← ceiling, POINT estimate
      H = 3.57¢                    r* = 31.4%   ← ceiling, MEASURED upper bound
      H = 2.93¢   ── the 35.8% row is WITHDRAWN (assumed clustering) ──

  > **★ THE 35.8% IN THIS TABLE IS WITHDRAWN [c7, 2026-09-06].** The clustering
  > widening was **assumed** (G≈20, ρ≈0.3, deff 2.5), not measured. Measured on the
  > same 118 events: **G=35, ρ≈0, deff 1.05**, and three routes agree on an upper
  > bound of **~31.4%**. The `r* = 35.8%` row below therefore corresponds to no
  > real bound. **The binding comparison is floor 51.0% vs ceiling 31.4%.**

  **Even at the full spread — all edge, zero post-fill drift — the floor is
  40.6%, above the 23.7% point AND above the measured upper bound of 31.4%.**
  Break-even needs **H = 5.26¢ = 2.2× the full spread** at the ceiling's POINT
  estimate. **Quote the 2.2×** — the 1.23× figure was computed against the
  withdrawn 35.8% bound. The conclusion
  survives either way — a passive maker resting at the touch cannot earn more
  than the spread it quotes — but the margin is ~80% smaller than the more
  quotable number suggests. [defect found by c7's audit; the 35.8% amendment had
  reached three places and missed the H table in both documents]

  So the close is not "the rate is too low given our half-spread assumption" —
  it is "the rate is too low unless a passive fill earns more than twice the
  full spread, which is structurally impossible.

### ★ THE CLOSE WAS CHALLENGED AND SURVIVED — but the challenge was right about the structure [C7 / M / A]

**c7, 2026-09-06:** `pop` is mechanically confounded with spread. `real` is
*defined* as ask ≤ B — the ask came down to our bid — **which requires a narrow
spread**. A benign fill is by definition ask > B (a seller crosses to our resting
bid while the ask holds). So **benign fills live in the phantom bucket**, and
`probe.py:81` says so in the code: the simulator *"cannot distinguish a true
phantom from a real benign fill."* Measuring H on `real` fills measures the
half-spread in the one regime where a benign fill **cannot happen**.

All three of those claims are correct and they stand. c7 then measured spread at
fill on each bucket and concluded the close reverses:

      real     n=25,332   book full med 2.00   mean  3.04  ->  H 1.522  r* 51.8%  CLOSES
      phantom  n=48,632   book full med 8.00   mean 10.98  ->  H 5.491  r* 22.9%  FAILS

**Reproduced to the digit off the pin. The arithmetic is not in question.**

**★ THE INFERENCE FAILS ON THE CHOICE OF COLUMN, AND THE DATA SHOWS WHY.**
`ba−bb` is the book's spread **at the fill moment**. It is not what we earn.

      pop        s_q (WE quoted)   ba−bb (book at fill)   widened
      phantom          2.0¢               8.0¢            +5.0¢
      real             1.0¢               2.0¢             0.0¢

      book WIDER at fill than the spread we quoted:  phantom 92.1%   real 65.4%
      median quote age at fill:                      phantom 15.2s   real 17.4s

**For 92% of phantom fills the book gapped open between our quote and the booked
fill.** That IS the phantom mechanism — the bid goes stale, the market widens
away from it, the mid falls to the stale bid, the engine books a fill nobody
took. `ba−bb` on phantom rows measures **the size of the gap that created the
artifact**, a property of the failure, not of our edge.

**H is not an unobservable.** We rest at `qp` with quoted spread `s_q`, so
`qp = m_q − s_q/2`. A seller crossing to our bid sells us at `qp` against fair
value `m_q`; we earn `m_q − qp = s_q/2` **by construction**. So **H = s_q/2**,
observable on every row. Only the benign *rate* is unobservable — which is what
the probe was for.

      H = s_q/2       phantom  H_mean 1.750¢  r* 48.3%
                      real     H_mean 1.223¢  r* 57.2%
                      ALL      H_mean 1.569¢  r* 51.0%   ← all-fills; MISMATCHED to a guarded |A|
      GUARDED  H_mean 1.193¢  r* 57.8%   ← population-matched, and the published floor

**Every one is above the 35.8% clustering-widened ceiling, including on c7's own
population.** Measured on earnings rather than on the gap, the wide-spread bucket
makes the close *stronger*: 48.3% against a 35.8% bar. **[Ceiling since corrected to 31.4% and H's population shown to be unidentifiable — the current statement is the 49.7–57.8% range clearing by 18–26 pts. This paragraph is the contemporaneous argument, not the current figure.]**

**To break it you need H > 3.570¢** — benign fills concentrated above a **7.14¢
quoted** spread, the widest **8.9%** of our own quoting. So the break needs benign
fills ~10× over-concentrated in the widest tenth of what we quote.

> Both halves of this moved today. Against the *old* 35.8% ceiling the bar was
> H > 2.930¢ = a 5.86¢ quoted spread = the widest **16.3%** — I first wrote "top
> decile" and c7 corrected it to 16.3%, a *weaker* requirement than I had stated.
> **c7 then withdrew the 35.8% ceiling itself** (assumed clustering, measured deff
> 1.05), which moves the bar to 3.570¢ and the share back to 8.9%. The requirement
> ends up near where I first guessed, **by two corrections rather than by being
> right** — worth saying, because the intermediate number was the honest one at
> each step and neither correction was mine.

**★ AND THE INCENTIVE RUNS THE SAFE WAY, which turns "nothing suggests it" into an
argument [c7].** A wider *quoted* spread means a counterparty crossing to us gives
up more. So benign crosses should be **rarer** at wide `s_q`, not concentrated
there — H on benign fills is plausibly **below** the all-fills mean, pushing r\*
**up** and widening the margin. The concentration the break requires runs against
the counterparty's incentive.

**The identity is exact, not approximate [c7]:** `qp = m_q − s_q/2` holds with
residual max |·| = **0.000000000 on 100.0% of 36,759 bid fills**. H = s_q/2 is an
identity, so the "H is unobservable" framing was wrong on both sides — the right
column was in the file the whole time.

**A reached the same place independently:** the engine quotes only mid ∈ [0.2,0.8]
and spread ∈ [1,15¢] (`adverse_selection.py:133-140`), so the deep rungs behind
the whole-board mean are never quoted. **Max observed `s_q` in the pin is exactly
15.00¢** — the band confirmed empirically.

**THE LESSON, and it is not "c7 was wrong":** three correct structural claims
produced a reversed verdict because the statistic attached to them described the
wrong event. The confound is real; the population argument is real; `ba−bb` is
the spread of a market that had already moved away from us. **Name the column,
not just the population.**"

- **Market selection is also closed.** The one surviving route — quoting
  benign-rich markets rather than the whole board — cannot be tested on this
  tape and cannot work. A subgroup's CI *lower* bound must clear 0.48; at a
  subgroup of 50+ markets that needs **31+ benign events when only 28 exist**.
  Arithmetically impossible, not merely underpowered. And n=118 ignores
  clustering — at G=20, rho=0.3 the tape-wide rate alone spans 0.12 to 0.36.
  Computed before splitting; no split was run.
- **Making is closed without residual.**
- Probe sizing, measured over 446,010 touch observations (median depth 272):
  at $278 the probe is the DOMINANT order at the touch in 53–79% of
  observations depending on price. p25 = 36 contracts leaves it buried in 75%
  — that is the genuine passive-joining test.
- Verdict depends on which line is named: against the independently-registered
  10% kill line the same 23.7% does NOT kill it. Always name the line.

**Directional (PULSE) — MEASURED THROUGH THE WRONG INSTRUMENT.**

The tie does not mean the model has no edge. It means Brier could never have
told us either way.

*Everything in this section: threshold, e² identity and the G-ladder are* [d5];
*the fill split and the accrual ladder are* [B]; *the 58/260 reconciliation is*
[B + d5, one version]; *the convention table is* [d5].

For a market at p and a calibrated model at q = p + e:
**Brier(mkt) − Brier(model) = e², exactly, independent of p** — though the
general form is e_k² − e_m², which collapses to e² only under exact calibration,
so it is an upper bound [B].

The squaring is the whole problem. A tradeable edge of **3.07pp** [CORRECTED from 2.69pp — it inherited the withdrawn
1.193¢; 1.569¢ + 1.50¢ fee. **+0.38pp HARDER**, running against us] (the taker
threshold: one spread **1.569¢** [was 1.193¢, withdrawn] plus 0.06·p(1−p), no exit leg since binaries
settle) appears as a Brier improvement of **0.00072**.

Our G=34 interval has half-width ~0.018, so the smallest edge it can resolve is
√0.018 = **13.4pp** — five times the edge that would pay, twenty-five times in
Brier terms. And e² assumes perfect calibration, so it is an upper bound; Brier
also averages over markets where the model is silent, diluting further.

    G=34      today                detectable edge 13.4pp
    G=272     full NFL season                       8.0pp
    G=600     NFL + CFB                             6.5pp
    G=21,039  required for 2.69pp                   2.7pp

> **2.69pp is ILLUSTRATIVE here, not the taker bar** — it was built on a maker-side
> H and is withdrawn as a threshold. τ is measured on the venue book per type at the
> traded price and is of order 1–3.5pp. **The conclusion is insensitive to which
> value in that range you take**, which is the point of the table.

**A whole season moves 13.4pp to 8.0pp against a ~2.7pp threshold. No amount of
football closes it.** The accrual plan is not aimed at an unreachable target —
it is aimed through an unusable instrument.

**Fix: measure money, not accuracy.** Money is LINEAR in edge where Brier is
quadratic, so edge resolution scales 1/G^(1/4): **79 games against Brier's
15,400.** That makes the directional question answerable in roughly one season
rather than never.

**But the threshold to compare against is the MAKER one, not the taker one.**
PULSE never crosses — `limit_price == market_bid` on 100.0% of 1,342 yes-side
entries and `== market_ask` on 100.0% of 1,632 no-side entries. It joins the
touch on both arms. So PULSE faces the same maker economics we closed this
afternoon (23.7% benign against a **57.8%** floor), not the taker bar.

**And the money statistic does not clear zero on real fills:**

    ALL entries    +6.880pp [ +2.774, +10.985]   excludes zero
    FILLED only    +4.761pp [ −1.455, +10.978]   SPANS ZERO
    WITHDRAWN     +10.857pp (n=1,019, `withdrawn_at.notna()`) — retracted arm,
                  and the correct predicate [D, 5d335e9]

Scoring unfilled orders counts P&L that does not exist — 34.3% of entries never
traded. **The withdrawn orders carry more than twice the P&L of the filled
ones.** The bets we wanted are the ones nobody would take: adverse selection
showing up in P&L rather than in fill rates.

**λ\* is convention-dependent and cannot support a "close to paying" reading.**
Measured on one tape, the dedupe choice alone moves it across the bar:

    earliest row per market   λ* +0.364 [-0.110, +0.929]  edge 2.96pp  CLEARS
    all rows, no dedupe       λ* +0.219 [-0.045, +0.796]  edge 1.70pp  below
    entries, all rows         λ* +0.217 [-0.061, +0.753]  edge 1.74pp  below

The required λ* of 0.337 sits *between* them, **every interval contains zero**,
and more games cannot help: while the point estimate sits below target,
tightening moves the interval toward the point and away from clearing. At
λ* ≈ 0.28 the accrual can only ever confirm **failure**, and needs ~2,200 games
to do it.

So the λ* route is dead. **The money route is the live one, and it is cheap.**

PULSE joins the touch, so it pays neither the half-spread nor the taker fee.
There is **no maker rebate** (see the correction above), so break-even is
**exactly 0.00pp** at every price level. The question is "is filled P&L > 0",
not "does it clear 2.69pp". **[2.69pp is withdrawn as a taker bar — it was built on
a maker-side H. A's venue-book per-type τ at the traded price is the taker bar.]**

Source: `analysis/pulse_money_scorer.py`, 32bc6d9 — committed only after an
audit could not find it. `pnl = y − limit_price` (bought YES at the bid) or
`limit_price − y` (sold at the ask): **a signed price difference, never a squared
error.** The file carries the discriminating check on the same rows —
Brier(mkt) − Brier(model) = **−0.00481** (dimensionless) against money per
contract = **+0.04761** (price units). Different quantities, different units,
different scaling laws, so the linear-vs-quadratic argument holds.

**CORRECTED.** I reported the figures existed only in chat messages. Wrong — and
the way I got it wrong is the point. `analysis/pulse_money_and_the_taker_join.md`
carries 4.761 seven times at commit `3dbe88a`, on branches
`quant-b/live-regime-cuts` and `builder-d/joint-money-fix`. My `grep -rn
analysis/` searched the **working tree**, which is checked out to `main`, so it
searched one branch and I reported a repo-wide negative. Same class as an
audit truncated at `head -50` earlier today: **a confident negative from an
instrument that could see a fraction of the corpus.**

**But the auditor's experience was real, and it indicts the merge queue rather
than the author.** A read `pulse_branch_scoring.py`, correctly identified it as a
Brier scorer whose differences run ~0.002–0.003, and had no way to reach the
money computation — because it is on an unmerged branch and they were on main.
**Nine PRs deep, a figure can be committed, reproduced and still unauditable by
anyone standing on `main`.**

[D reproduced both figures independently from the pinned export at
`s·(S − limit_price)·100`, game-clustered: filled **+4.761pp**, withdrawn
**+10.857pp**, exact to three decimals. So the statistic is settled by
reproduction, not by label adjudication.]

**Predicate settled on substance** [D]: the 11 rows separating the two
definitions all carry `binding_constraint = max_open_per_event` — blocked by a
position limit before ever being placed, from one event in a nine-minute window
on 2026-08-23. Nothing rested in the market, so there was no fill to miss.
`filled_at.isna()` merges *"posted and the price left"* with *"never posted"*,
and the mechanism is entirely about the first. Use `withdrawn_at.notna()`, which
is what the published figure already used.

**And that independently confirmed the interval fix.** Recomputing the withdrawn
arm with CR1 + t(G−1) returns **[+7.554, +14.160]** — the published interval
exactly, on a figure whose half-width had never been reconciled. The CR1+t
diagnosis was derived from the *filled* arm; this is it holding on a second,
independent figure, which moves it from a fitted explanation to a confirmed one.

**And the interval discrepancy decomposes exactly** [B]: t(df=33)/z = 1.0380,
× √(G/(G−1)) at G=34 = 1.0150, product **1.0536** against the observed
6.216/5.900 = **1.0536** — match to 0.00009. B's `clustered_mean` uses t at
df=G−1 *and* the cluster small-sample correction; D's uses z and neither. B's is
preferred at G=34 (not asymptotic, and omitting t understates by 3.8%), and the
ladder moves 58 → 52 under D's convention — inside the range the conventions
already span. **"Game-clustered" named the clustering and left t-vs-z and the
finite-sample correction implicit, so two correct implementations differed by 5%
with identical point estimates.** The label should read: cluster-robust sandwich,
t at df=G−1, with the G/(G−1) correction.

**Blast radius bounded, and it is narrow** [D, 43fa4bb]. `core/quote/
adverse_selection.py:294` applies both corrections with a docstring saying so —
**the repo's estimator is correct and everything computed through
`clustered_mean` is sound.** The defect was in an inline estimator written in
today's scratch scripts, so it touches today's ad-hoc numbers only, not the
published corpus.

**And it grows as clusters shrink**, which is where intervals do the most work:
×1.054 at G=34, ×1.091 at G=21, **×1.216 at G=10**. D re-issued every affected
claim; point estimates unchanged and **no verdict moves**:

    drift / half-spread (null −1.0)   −1.809 [−1.901, −1.716]  still excludes −1.0
    withdrawn mid move                +3.713 [+2.547, +4.879]  still excludes 0
    markout per contract              −1.825 [−2.124, −1.526]
    pre-fill drift per leg            −4.545 [−4.910, −4.181]
    withdrawn − filled (t(32), CR1 n/a) +52.206pp ≈ [+8.8, +95.6]  still excludes 0

**Why it was written up rather than fixed quietly** [D]: the error was
**systematic and one-directional** — every interval too narrow, never too wide —
and it scaled up exactly as G fell. Nothing flipped this time, but *a defect that
always points the same way and grows in the thin-data regime is the kind that
eventually flips something.*

**And it was invisible to every check that was run.** Point estimates right,
identity closed, reproduction exact to three decimals. The only thing that
exposed it was **disagreeing with a peer's interval on the same data** — which
argues for reproducing peers' ERROR BARS, not just their means.

Games needed, from the measured half-width of 6.216pp at G=34 (1,944 fills),
row-weighted; **260 game-weighted** — the estimand moves the answer 4.5x and
must be named:

    +4.76pp  measured point estimate        58   ← one to two CFB Saturdays
     2.69pp                                182   ← illustrative; 2.69pp is withdrawn
     2.00pp                                328      as a taker bar (maker-side H).
     1.00pp                              1,314      The table spans the plausible τ.

No row for break-even itself: **a break-even of exactly zero is not a target a
finite sample resolves — a null is bounded, never proven.**

**Unlike λ\*, the point estimate sits ABOVE the bar, so accrual here CAN
confirm success** — that asymmetry is why this line is fundable and the λ\* line
is not.

Robustness: leave-one-game-out range +3.259 to +6.152pp, largest single-game
influence 32%, **zero sign flips**.

Fragility, and it conditions the whole result: **games with ≤20 bets average
−10.97pp; games with ≥80 bets average +2.67pp.** So the 58 holds only if the
bet-allocation pattern holds. A slate that produces many thin games looks
nothing like one that produces few fat ones. (A "top 3 games as share of net" measure was
discarded as unstable — net P&L is a small difference of large offsetting sums,
+173.3 against −80.8, and two analysts got −9% and +65.7% from it.)

Convention sensitivity is real and worse than λ*'s: the point estimate runs
**−3.294 to +4.761pp across six dedupe conventions and changes sign**, with
games-at-point from 27 to 5,622. Unlike λ* there is a principled tiebreak —
money is earned per fill, so deduping discards realised P&L. All-filled-rows is
correct, and the shared outcome belongs in the clustering.

**Two bounds that must travel with this.** 58 games resolves the POINT ESTIMATE
from zero, not any particular bar — at a true 1pp effect it is a full season.
And the ~54 games/week CFB rate is the 94% WNBA capture applied to football, an
upper estimate. **The 09-12 slate is upstream of this entire table**, so every
date is contingent on Saturday.

Prior measurements, all through the coarse instrument:
- Pregame model **loses** to the market: −0.0070 [−0.0122, −0.0018] Brier, G=83.
- Live model **ties**: −0.0048 [−0.0231, +0.0135], G=34. Every branch ties.
- λ* on the live model: +0.283 [−0.149, +0.716]. Contains zero; interval is 2×
  the effect that would matter. Direction differs from pregame (−0.022).
- No regime found: 0 of 11 pre-registered cells clear correction.

## What we cannot measure, and why it matters

1. **Our simulator cannot record a winning fill.** The fill rule books a trade
   only when `mid <= bid`, which with a positive spread requires the book to
   move *down through us*. The profitable case — a seller crossing to our
   resting bid while the ask holds — produces no row at all. Every making
   number is measured on the adverse half of the population.
2. **Queue position is not supplied by the venue** at any sampling rate. Book
   levels carry price and aggregate quantity only — no order count. This cannot
   be fixed by recording harder.
3. **Trade data is sampled at 1.2% of snapshots.** [M] Median per-market gap
   265.85s in the joined export; the tail reaches p10 28.66s with 225
   transitions at ≤10s, so "never below 283s" (an earlier claim of mine from one
   window) is wrong. Still far too sparse to attribute a 2-second transition
   at usable n. Fixable going
   forward by writing trade stats on every snapshot; not fixable historically.

The resting-order probe addresses (1) directly and (2) only in its consequence:
a resting order EXPERIENCES queue position, it does not measure it. What it
resolves is whether we fill, which is the quantity the decision needs. It is
now a CONFIRMATION of a negative, not an open experiment.

**The probe is mis-sized for the question.** $278 = 556 contracts at 50¢ =
**204% of median touch depth** (511% at 20¢). As specified it would BE the
level, not join the queue — testing a different strategy from the one we mean.
To test passive joining, size against p25–p50 depth (36–272 contracts), not a
round dollar figure.

## Cross-venue (Kalshi vs Polymarket) — CLOSED on cost

- Kalshi coverage is good (500k+ CFB rows, top-of-book both sides with sizes)
  but it is **level 1 only**, and per-market cadence is **162.9s against
  Polymarket's 3.4s — a 48× mismatch**.
- A previous measurement found a "7¢ arbitrage" that was an artifact of
  time-bucketing: averaging the fast venue against the slow venue's stale
  reading. Instant-matched at 3.3s lag it collapsed to **max 5¢, with 5 of 558
  observations over 2¢ and all of those in one game**.
- **Kalshi charges makers** (`quadratic_with_maker_fees`) where Polymarket pays
  them. Our fee formula is Polymarket's and does not transfer.
- Any bucketed cross-venue result is refuted by construction.

**The close is on cost, not on gaps.** An arb crosses both venues as taker:
Kalshi 0.07·p(1−p) + Polymarket 0.06·p(1−p) = **0.13·p(1−p) = 3.25¢ at p=0.5**.
That is below one tick only for p < 0.084 or p > 0.916 — and those rungs carry
measured **22–26¢ spreads and do not trade**. Dead on fees in the middle, dead
on spread in the tails.

Stated as a requirement: a profitable gap needs **4+ ticks**. Measured maximum
across 620 cells / 72 games is **one tick**, with **zero cells reaching two**.
  > **This is the SINGLE-SNAPSHOT row and `cross-venue-status.md` supersedes it
  > [c7].** Instant-matched at ≤10s lag: **5 instants ≥2¢, max 5.00¢ across 558.**
  > Do not quote the one-tick figure as the close's basis.
Re-opening this should require showing a 4-tick gap first — measuring how often
an unprofitable event occurs measures nothing.

## Football

### ★ THE DIRECTIONAL TEST RAN AND LOST — and it reframes what is left [B, M]

**2026-09-06.** B built and fitted a CFB win-probability model on
`espn_cfb_live_plays` (commit `ded4f01`) and scored it against ESPN's published
win probability on ESPN's own data.

      Brier model 0.08061   ESPN 0.06942
      difference  −0.01119  [−0.04316, +0.02077]   G=28
      INDISTINGUISHABLE, point estimate favouring ESPN

**Then five subsets, DECLARED IN A COMMIT BEFORE RUNNING** (`13736f7`, run at
`aa7e3d9`) — the standard d5 set with their pre-registration the same night:

      subset                 n    G      diff            95% CI            hw     proj
      4th down             387   28  −0.02015  [−0.0556, +0.0153]      0.0355   0.0320
      red zone             473   27  −0.02184  [−0.0663, +0.0226]      0.0445   0.0320
      two-score, 2nd half  917   14  −0.03898  [−0.1003, +0.0224]      0.0613   0.0437
      3rd and long         315   28  −0.01196  [−0.0477, +0.0238]      0.0358   0.0320
      late (≤5 min)        395   25  −0.09277  [−0.2107, +0.0252]      0.1179   0.0339

**0 of 5 clear zero, and EVERY point estimate is negative.** So this is not an
edge hiding where the pooled test lacked power. **The worst cell is the late-game
one — precisely where a live model would have to earn.**

**★ THE STRUCTURAL RESULT, which retires a class of proposals [B]:** the outcome
varies only at the GAME level, so a within-game subset keeps G almost unchanged —
every game has 4th downs, so that cut still carries 28 games and the *same 28
outcome draws* — while shedding 92% of its rows. **Subsetting by play type cannot
buy independent information, only spend it.** Knowable before any run.

**And B's named assumption failed in the pessimistic direction**, which is the
half worth keeping: they projected on constant between-game variance and flagged
that a subset could come in *tighter*. **Every subset came in WIDER, the late cut
by 3.5×** (0.1179 vs 0.0339 projected). Between-game variance RISES under
within-game subsetting, because late-game plays are where games diverge — rows
fall and dispersion rises together. **A within-game subset's interval widens
faster than √n predicts.**

### ★★ ESPN'S CFB WIN PROBABILITY HAS NO PREGAME PRIOR — the finding of 2026-09-06 [M, replicated by c7]

**Measured two ways, independently, on different subsets:**

                                        games/boards   mean     sd      range        strong prior
      ESPN first in-game WP     [M]          33       0.5925  0.0222  0.521..0.656   0 of 33  (0.0%)
      ESPN first in-game WP    [c7]          23       0.5935  0.0176  0.572..0.623   0 of 23  (0.0%)
      Venue pregame moneyline   [M]          47       0.2847  0.2663  0.007..0.942  25 of 47 (53.2%)
      Venue first winner mid   [c7]          93       0.2865  0.2635  0.007..0.943  45 of 93 (48.4%)

      dispersion ratio:  12× [M]   14.9× [c7]
      "strong prior" = >0.80 or <0.20

**ESPN opens EVERY college football game between 52% and 66% for the home team.**
That is home-field advantage and nothing else. The venue prices roughly half its
board as strong favourites or underdogs. On tonight's game ESPN opened at **0.55**
against a market at **0.92**, and was still 12pp below the market at 10-0 in Q2.

**★ THIS CLOSES "TRADE ESPN AGAINST THE VENUE".** ESPN is not a better-informed
public forecaster we can borrow — it is a game-state model with no prior. Trading
it against the venue would systematically fade heavy favourites. **I proposed that
route earlier today as the only one left; it is closed.**

**★ AND IT REFRAMES B's NEGATIVE RESULT.** Their model tying ESPN (−0.01119) is a
much weaker signal than it read: **two models sharing the same blind spot agree
with each other.** Their corr(model, ESPN) = +0.728 with ESPN WP never a feature is
consistent with shared game state *and* shared absence of the prior. The honest
reading of their five negative subsets is **"no edge available from game state
alone"** — narrower and more useful than "no edge available".

**★ AND IT VINDICATES d5's ARCHITECTURE BY MEASUREMENT.** nflfastR puts a per-game
constant in the feature set; **that constant is the prior, and a pure play-state
model has none.** The anchor is not one feature among many — it is the whole of the
missing information, with a 12–15× dispersion signature.

**THE LIVE PROPOSAL [c7]:** venue as prior, ESPN's *movement* as the update —
`logit(p̂) = logit(venue_pregame) + [logit(ESPN_live) − logit(ESPN_at_kickoff)]`.
ESPN's *level* is uninformative; its *delta* is where its game-state model lives.
Falsifiable on Saturday's settled cohort.

> **Lead-lag, run tonight because it needs no settlement — SUGGESTIVE AGAINST, and
> confounded.** corr(ESPN Δ_t, venue Δ_{t+k}) peaks at **k=−1 (+0.465)** — venue
> first, ESPN following — against **+0.157** for ESPN-leads. **But ESPN gave 74
> updates to the venue's 2,425**: its WP is play-triggered and polled, the venue
> tape is continuous, so a one-minute lag is what an instantaneous ESPN model with
> slow *publication* would also produce. **Cannot separate model lag from ingestion
> lag.** Fix for Saturday: **align on GAME time (play_id/clock), not wall-clock** —
> a wall-clock difference inherits the ingestion asymmetry and makes ESPN look
> stale regardless of its information content. 63 increments, G=1: a design input,
> not a result.

**Frame verification, better than the registered rule [M, adopted by c7]:** the
venue home-win probability rose monotonically across four scoring events
(0.9175 at 0-0 → 0.9426 at 9-0 → 0.9608 at 10-0 → 0.9792). **Response-to-score
confirms the frame during a live game**, where the registered 11-of-12
settled-price check is unavailable — which is exactly when you need it.

### ★ AND THE ANCHOR OUTPERFORMS SEVEN GAME-STATE FEATURES [B, 2026-09-06]

**`live_spread` is already in `espn_cfb_game_state` — ESPN-keyed, so it needs no
`cfb_game_map` at all.** Present on **50 of 50** games, constant within a game in
46 of 50 — *which is what makes it an anchor*. sd 15.62 points → implied P(home)
sd **0.1879 against ESPN's 0.0176 = 10.7×**, independently matching the 12× and
14.9× measured from the venue side.

      out-of-fold Brier, B's 28-game settled cohort
      game state only (7 features)   0.08061      vs ESPN  −0.01119
      anchor only (1 parameter)      0.07413      vs ESPN  −0.00472
      state + constrained anchor     0.10443      vs ESPN  −0.03502
      ESPN                           0.06942
                                                  (all three tie ESPN)

**A single logistic parameter on the pregame spread beats a seven-feature model of
down, distance, field position, clock and score.** B had *deleted* this feature
that afternoon precisely because it was constant within a game — the property that
makes it the prior was read as the defect that disqualified it.

**★ THE COMBINATION MEMORISES, AND IT IS NOT AN INFORMATION PROBLEM [B]:**

      in-sample / out-of-fold      base   0.03239 / 0.07443   gap 0.042
                                 anchor   0.00307 / 0.10940   gap 0.106   ← 2.5×

**22 distinct anchor values across 28 outcome draws is a near-unique game key**, so
a GBM fits the game-level points essentially perfectly and does not generalise.
**GroupKFold REVEALS this; it does not prevent it.**

> **CORRECTION TO MY OWN ARGUMENT [B corrected M].** I told B that a game-level
> feature *buys* independent information where a within-game subset can only
> *spend* it. **True of the information, false of the fitting.** At G=28 a
> game-level feature is also a near-unique key. Constrained to one parameter it
> helps; handed to a GBM it destroys the model. **The fix is constraint or more
> games, not a better feature** — a second reason 09-12 gates everything.

**THE TEST THAT RESOLVES BOTH THREADS:** c7's identity has **zero fitted
parameters**, so it *cannot* memorise 22 anchor values —
`logit(p̂) = logit(anchor) + [logit(ESPN_live) − logit(ESPN_at_kickoff)]`.
B's overfitting problem and c7's proposal are the same problem and its solution,
reached from opposite directions the same evening. **Runnable on the settled 28
tonight; needs no map.**

**Caveats, carried:** the venue boards are not the same games as the ESPN cohort,
so this is **NOT paired** — the dispersion contrast is the robust part and does not
depend on pairing. ESPN's "first WP" is the first recorded play, at 0-0 in Q1:
pregame in substance, not literally.

### ★★ MEASURED: our entire advantage over ESPN IS SPREAD KNOWLEDGE [a1, E2]

      conditional on outcome, vs ESPN:
        favourite WON  (49 games)   −0.0320  [−0.0435, −0.0204]   excludes zero
        favourite LOST  (4 games)   +0.2088
        pooled                                                     spans zero

**ESPN is nearly line-blind; we are not; and the market knows the line too.** So the
model's apparent advantage appears exactly when the favourite wins — which is what
the line predicts — and reverses hard on the four games where it does not.

> **This is the quantitative form of "ESPN is the wrong opponent": beating ESPN was
> never evidence of edge, because the thing we beat it WITH is the thing the market
> already prices.** It closes the ESPN-benchmark question rather than qualifying it.
> *(Sign convention a1's; n=4 on the losing arm, so the +0.2088 is directional.)*

**Also refuted [a1, E2]:** the OT / garbage-time / data-error hypothesis. Garbage-Q4
**60% of losers vs 56% of winners**, blowout **60% vs 53%**, close final **10% vs
12%**. **None separate.**

### Polymarket CFB winner spread — tighter than Kalshi, DIRECTIONAL ONLY [a1]

      Polymarket CFB winner, IN-GAME, n=115,041 snapshots, 09-03..09-06
        mean 0.60¢   median 0.50¢       vs Kalshi's 1.0¢ near-event

**Not a clean comparison and not offered as one:** the Polymarket figure is at game
time, and Kalshi's only game-time cell is `<3d, n=2`. The load-bearing Kalshi cell
(6–10d, n=238) is a **different horizon**. *"Polymarket is the tighter venue for CFB
winners" needs a same-horizon Kalshi sample to stand.*

**If it survives that check it matters for cross-venue, and it cuts AGAINST room
rather than for it — room is bounded by the tighter book.**

### ★ BUT ESPN IS THE WRONG OPPONENT [M]

**We never trade against ESPN.** ESPN's win probability is a free, public,
well-built model, and beating it is a hard bar that is not the bar that pays. We
trade against the **VENUE PRICE**.

**The open question, and it is now the only live route:** is the venue's implied
probability worse than ESPN's win probability, in-game, by more than τ? If it is,
**the strategy needs no model of ours at all** — take the public number and trade
it against the venue when they disagree past the bar. B's result says *we* cannot
beat ESPN. It says nothing about whether *the venue* can.

**Both blockers cleared 2026-09-06:**
- **The tape.** First in-game CFB tape that is neither frozen nor collapsed:
  21:00Z, 143 markets, **705.9 rows/market, 81.8% moved, 0.0% single-row**,
  against a healthy median of 84.2%.
- **The map.** B found `espn_cfb_live_plays` and `espn_cfb_game_state` are BOTH
  ESPN-keyed — **49 of 50 games join with no `cfb_game_map` at all.**

Routed to c7 (owns ESPN-vs-mid), with A measuring τ on the same tape. **Tonight is
one game deep; Saturday 09-12 is the volume.**


- We already hold **114,549 NFL rows across all 32 games**, every one with a
  kickoff time, through 2026-09-22. The venue sends `startTime`; we store it.
- `kalshi_games` is not populated from it — a backfill join, not acquisition.
  **This does NOT block week 1.** `board.py market_state()` reads
  `game_start_time` from **`market_snapshots`**, not `kalshi_games`, and it is
  populated on all 114,549 NFL rows / 32 games. Nothing in `core/quote/`,
  `core/board.py` or `core/pulse/` references `kalshi_games` at all. The missing
  rows feed the Kalshi cross-venue join — an analysis already closed on cost.
  Normal fix, not a Thursday emergency.
- No `nfl_game_map` exists. **Eight team codes collide** between WNBA and NFL
  (ATL CHI DAL IND LV MIN SEA WSH) and today resolve to the WNBA team, so
  enabling NFL mapping via the ESPN-pair key before fixing that writes wrong ids
  that look valid. **Avoidable entirely**: key the backfill on date + unordered
  normalised name pair from both venues' own payloads, which never touches the
  team map — the approach already proven on CFB, over-determined with zero
  conflicts in both directions. Then backfill and map-fix are independent.
- Downstream pipeline is **48/48 lossless** on football.
- Whether the live model can see football game state is **UNTESTED** — the two
  recorders have never run concurrently. **2026-09-12 settles it in one slate**,
  pre-registered: PASS ≥80% capture, MARGINAL 50–79%, FAIL <50%; uptime derived
  from the recorder's own row gaps, never a status signal; under 50% uptime the
  slate does not settle the question at all.
- `cfb_game_map` is **55/55 correct on inspection** [M, B] — but all 55 were
  matched by one method at confidence ≥0.746, so **nothing observed says what a
  0.00 floor would admit.** Correctness on the games it contains cannot license
  lowering the gate that decides what it contains. Earlier recommendation to use
  floor 0.00 is withdrawn as unsupported.

## ✅ RESOLVED 2026-09-06 22:30Z — the SAME failure with the sides swapped [a1, M]

**CFB ESPN recorder wrote ZERO rows from 21:37:25Z to 22:30:25Z — 53 minutes, two
live games, unrecoverable.** The venue price tape recorded perfectly throughout
(133 markets, 248 rows/market, 66.9% moved). **Every instrument we have called the
slate healthy.**

      every 20s:  espn_cycle league=cfb live_games=2 plays_attempted=0 state_rows=0
      every 20s:  warning cfb_summary_failed error='Unconsumed column names: league'

**CAUSE [a1, correcting M].** Not image skew — that was **my** guess, broadcast as
though it were a finding. a1's patch added `league` to three SQLAlchemy classes
using **identical anchor strings**; both replacements landed on the first class, so
`CfbLivePlay` got TWO and `CfbWinProbability` got NONE. The DB was correct all
along. **What I had established was that the schema was eliminated; I reported a
replacement hypothesis instead of the elimination.**

**★ THE VERIFICATION LESSON [a1].** They checked by COUNTING OCCURRENCES. It
returned **3** — the expected number — and printed *"league column added to 3
tables."* **Two-in-one-class plus one is indistinguishable from one-each.** The
count was right and the distribution was wrong. Correct check iterates the classes
and asserts exactly one per table. *Whenever a count is the verification, ask what
else produces that count.*

**★ "VISIBILITY WITHOUT AN EVALUATOR IS NOT DETECTION" [a1].** The honest counter
a1 added that afternoon made `plays_attempted=0` visible in the log — and it sat
there beside `live_games=2` **on the same line** for 19 more minutes. Nothing
compared the two numbers.

**THE THIRD MONITOR SHAPE**, distinct from FROZEN (values static) and COLLAPSED
(rate degraded): **zero rows, process healthy, work identified.** No rate can see
it — the denominator is zero. **The discriminator is expected-vs-observed from
inside the process**, and both numbers are already logged. D spec'd it (`692bb20`)
as a **disjunction of two invariants**, measured, because each is blind to a real
failure the other catches:

      failure                  state_rows  plays  `state<live`  `plays==0`
      3 of 5 games throw          2/5        40      FIRES        blind
      parse returns empty         5/5         0      blind        FIRES

> **Tested against every retained cycle [M]: 18 CFB + 2 NFL, 100% equality, zero
> mismatches — but the log spans SIX MINUTES, all post-fix.** No game started or
> ended inside it, so the transition cases the invariant is most likely to
> false-fire on are untested. Exact equality is the strongest available claim;
> a game moving to 'post' mid-cycle would break it at every game's end.

**★ AND D'S PARSE TESTS WOULD NOT HAVE CAUGHT IT [D, self-corrected].** They test
`parse_plays`/`parse_game_state` as **pure functions and never touch the write
path**, so they stay green straight through a total write failure. D had told me
those tests were what protected Saturday. **They protect the parse. The write path
had no test and still has none.**

## ✅ KALSHI DEPTH — MEASURED for the first time; both leagues liquid near the event [a1]

**The old probe read `volume` and `yes_bid`. Those fields do not exist** — Kalshi uses
`volume_fp`, `yes_bid_dollars`, `yes_bid_size_fp`. **Control: zero markets anywhere
showed volume, so the probe could never have returned yes on any board.** Board
liveness was never the issue; the "empty book" result was an instrument artifact.

      KXNCAAFGAME (480 open markets, full pagination), by days to close:
        <3d      n=  2   spread  1.0¢   vol 516,212           ← directional only
        3-6d     n=  2   spread  1.0¢   vol 229,101           ← directional only
        **6-10d  n=238   spread  1.0¢   vol   1,263   224/238 traded  ← LOAD-BEARING**
        10-20d   n=238   spread 54.0¢   vol       0           ← horizon effect at scale

      KXNFLGAME (64):
        3-6d     n=  4   spread  1.0¢   vol 454,395
        6-10d    n= 28   spread  1.0¢   vol  55,460
        10-20d   n= 32   spread  2.0¢   vol   1,948

**Kalshi CFB and NFL are BOTH ~1.0¢ near the event and both wide beyond 10 days.**
The claim rests on the **6-10d cell at n=238**; the <3d and 3-6d cells are n=2 each
and **the "CFB out-trades NFL" volume comparison must not be quoted.**

> **★ THIS ENTRY REVERSED TWICE IN ONE HOUR, BOTH SELF-CAUGHT [a1].** First reported
> as *"Kalshi CFB has no book"* (62¢ median). **`limit=200` returned a DATE-ORDERED
> page of a 480-market series, so only the far-dated half was measured.** Second
> version, *"near kickoff: not measured"*, was stale within minutes. **M escalated the
> first version to the operator as a cross-venue invalidation and had to retract it
> twice.**
>
> **THE LESSON, and it is the one check nobody else ran tonight:** *"I checked whether
> my INSTRUMENT could return yes, and did not check whether my SAMPLE was the
> population. **A page is not a sample when the endpoint orders it.**"*
>
> **And the original 62¢ was never wrong — only its population label.** Same defect as
> the estimator-in-the-label problem, on the **population** axis instead of the
> **estimator** axis.

**CONSEQUENCES, all negations:** the cross-venue CFB invalidation is **dead**; the
reopened-NFL point **loses its exclusivity** (CFB qualifies on the same measure); and
**c7's concentration argument is untouched** — the cross-venue close stands or falls
on *one game, five instants, 0.9% of 558*, alone.

## CONSTANTS AUDIT COMPLETE — 3 of 5 reproduce [c7; −1.634¢ closed by M]

      23.7%        REPRODUCES exactly (28/118)
      2.69pp       REPRODUCES, but inherited 1.193¢ -> corrected 3.07pp
      35.8%        DOES NOT REPRODUCE -- assumed clustering, WITHDRAWN
      −1.634¢      ✅ REPRODUCES — guard found at sandbox.py:97 (was "cannot be located")
      0.13·p(1−p)  half verified, half UNVERIFIABLE FROM OUR DATA

### ✅ −1.634¢: RESOLVED — the guard was under an unexpected name [M, closing c7]

**FOUND AND REPRODUCED to three decimals.** `scripts/sandbox.py`, strategy
`"quote-guarded"`: **`onesided < 0.65 OR n < 4`**, per `(game_id, market_slug)`,
ratio computed over **REAL fills only**. Docstring: *"withdraws a side once fills
go >=65% one-way."*

                              computed   published
      real+guard pooled        −1.634     −1.634   ✓
      real+guard cfb           −1.357     −1.357   ✓
      real+guard wnba          −2.462     −2.462   ✓
      real unguarded pooled    −2.400     −2.400   ✓

      25,332 fills before the guard, 22,062 after, 3,270 withdrawn as one-sided
      |A| = 1.634¢ → floor **51.0%**, exactly as published

**The published floor stands at 51.0%. The 60.5% alternative is WITHDRAWN.**
Audit tally improves to **3 of 5 reproduce**, 1 withdrawn, 1 unverifiable.

> **★★ AND THE SCRIPT DOES NOT EMIT −1.634. IT EMITS −2.626 [c7, correcting M].**
> `sandbox.py:99-103` is `per_game AS (SELECT game_id, avg(pnl) m ...)` then
> `avg(m)` — **the average of per-game means, not the fills-weighted mean.**
> Verified on the same 22,062 guarded fills across 48 games:
>
>       fills-weighted mean           −1.634¢   <- published, and CORRECT for the formula
>       equal-weight per-game mean    −2.626¢   <- what sandbox.py actually emits
>       gap                            0.993¢
>       floors:  51.0%  vs  62.6%     — eleven points
      [both computed pre-range; the point is the ELEVEN-POINT GAP between two
       aggregations of one predicate, which stands whatever H's population]
>
> **The published number is the right one**: `r* = |A|/(H+|A|)` is per-fill on both
> sides, since `H = s_q/2` is per-fill, so `|A|` must be fills-weighted. But **anyone
> re-running the located script concludes the published figure is wrong**, and c7
> spent a query believing their own reproduction had failed.
>
> **SO MY "FOUND THE GUARD" WAS HALF A CITATION.** c7 searched `circuit`/`breaker`
> and missed `onesided`; then found `onesided` and still got −2.626. **A predicate
> under an unexpected name is indistinguishable from one that does not exist — and a
> predicate found under its right name still does not reproduce the number, because
> the AGGREGATION is the other half.** The citation needs both: *"one-sided guard
> (`sandbox.py:97`), **fills-weighted**."*
>
> That is Debugger's gate doing real work — dataset, column, **population predicate
> AND aggregation**, n. And it is [[estimator-not-named-in-the-label]] again: I
> walked into it while closing an audit finding about citations.
>
> **And it is sharper than "no production code computes our anchor": NO CODE
> ANYWHERE computes it.** `sandbox.py` carries the predicate and emits a
> neighbouring statistic. That is appropriate for a research finding, and
> it is still true that the number setting our floor comes from a strategy flag in
> an analysis tool.

### Original finding, kept for the record: the computation is right, the SUBSET is undefined

      dataset  backups/exports/quote_fills_classified_20260906T024500Z.csv
      column   pnl   predicate  pop == 'real'   n = 25,332
                                        computed    published
        real, cfb                        −2.080      −2.080  ✓
        real, wnba                       −3.376      −3.376  ✓
        real, pooled                     −2.400      −2.400  ✓
        real, GUARDED pooled            (target)     −1.634  ✗

Three unguarded figures reproduce to three decimals; the guarded pooled does not,
because **the guard exists nowhere reachable** — no `circuit`/`breaker` definition
in `core/`, `analysis/` or `scripts/`, and **no guard column in the pinned export.**
A predicate that exists in no tracked file is not a stricter measurement, it is an
unrepeatable one.

**★ AND THE REPRODUCIBLE NUMBER MAKES THE CLOSE STRONGER BY NINE POINTS:**

      |A| = 2.400  (reproduces)    floor 60.5%   margin over the 31.4% ceiling  29.1 pts
      |A| = 1.634  (unlocatable)   floor 51.0%   margin                         19.6 pts

**The unlocatable figure is the conservative one.** Third time today the
unverifiable number was the one arguing against us — 1.193¢, 35.8%, now this — and
each time for c7's reason: *nobody challenges a figure that costs them.*

> **NOT switching the published floor.** The guarded subset may be the right
> population and the guard may sit in unpushed work — the tracked tree is not the
> whole world tonight (Debugger: **4 registered constants of 204**). STATUS carries
> ~~**51.0% as published, 60.5% as the reproducible alternative**, and the difference
> is a predicate nobody can produce.~~ **SUPERSEDED — the guard WAS found
> (`sandbox.py:97`, `onesided < 0.65 OR n < 4`), it reproduces to three decimals, and
> 60.5% is withdrawn. The floor is the 49.7–57.8% range. This block is the
> contemporaneous reasoning, retained only to show what the audit concluded before
> the guard turned up.**

### 0.13·p(1−p): restate the close on the room, not the coefficient

`Polymarket 0.06` **VERIFIED** (findings V9, `fee_coefficient` across 874,267 rows /
241 markets). `Kalshi 0.07` **NOT IN OUR CAPTURE** — no `maker_fee`, `taker_fee`,
`fee_type` or `fee_rate` key anywhere in the Kalshi export. c7 declined to
substitute a docs page, correctly: *this project took two wrong venue facts from
adjacent sources in one day, and I reintroduced a retracted maker rebate from a web
search.*

**★ AND MY PROPOSED FIX WAS WRONG — c7 STOPPED BEFORE MAKING IT.** I told them to
restate the close on "the room": max gap one tick against a 3.25¢ bar, zero cells
at two ticks across 620. **That is the single-snapshot row the document supersedes.**
Its preferred instant-matched (≤10s lag) row finds **5 instants ≥2¢, max 5.00¢**
across 558. On that row halving the coefficient **flips the best instant from closed
to profitable** (+0.75¢ → +1.25¢ on 4.0¢ gross at 0.4s lag). The room argument is
true of the superseded row and false of the current one.

**The honest ground is CONCENTRATION:** the close rests on **one game, five
instants, 0.9% of 558** — a sample too concentrated to support either verdict, which
the doc already states. That is coefficient-independent because it never depended on
the coefficient.

## ★ THE DECISION: the CFB winner market is 0.90% of the board [B, A, d5]

**Derived independently by B from the slug substrate, reproducing d5 and A:**

      asc  8,088 slugs  55.23%   spread        81 markets per game
      tsc  6,425 slugs  43.87%   total         64 markets per game
      aec    132 slugs   0.90%   WINNER         1 market  per game

**One winner market per game.** A's per-game tape agrees: winner 1.3, spread 45.5,
total 36.5. *(Unexplained: B counts 132 winner slugs against d5's 70 — flagged, not
smoothed.)*

**★ AND SPREAD/TOTAL HAVE EVERYTHING THE WINNER ROUTE LACKS [A]:** 34× and 28× the
coverage, sitting near **p=0.5 (median mid 0.46–0.51)** so τ pairs with the p=0.5
fee cleanly with no blowout gap — CFB spread ~2.0pp / total ~3.5pp (G=1), WNBA
~3.5pp proper. **`Brier(venue)` IS computable there** — the baseline that blocked
A's conversion at leg 1 and that c7 could only produce inadmissibly on winners.

**THE FORK, and it is the operator's:**
  **(a) re-site to CFB spread/total** — coverage and bar ready; the open question is
      whether the identity *transfers* (a win-prob model gives P(home wins);
      spread needs a MARGIN distribution — a different model, not a re-label). **With d5.**
  **(b) take the winner identity to NFL** — where the winner market is the liquid
      one. Opener **2026-09-10 00:20Z**.

A's conditional ceiling survives both: **22.6pp RMS clears ~1.9pp τ** even after a
large RMS→mean discount. **Re-site, do not abandon.**

> **B's summary is the honest one:** the identity is *not falsified and not
> confirmed against the market* — it is **untested against the market for a
> structural reason.**

### Corrections to this section

- **"Empty by arithmetic" overstates it [B, correcting c7].** At the ESPN recorder
  start 22:08:57Z: at-start games were identity-defined **False 16 / True 1**;
  later-seen games **False 2 / True 31**. So **16 of 17, not 17 of 17** — one game
  is both. The empty intersection is a fact about *this vintage's* price coverage,
  not a theorem, and a wider price vintage could marginally help.
- **c7's `Brier(venue)` = 0.12454 [−0.01603, +0.26510] is INADMISSIBLE, not merely
  wide.** A Brier score cannot be negative, so an interval spanning impossible
  values is proof the normal approximation has broken down at G=14. One game is
  **47%** of it (leave-one-out: 0.1245 → 0.0708), and its base-rate control was
  **fitted in-sample** on the outcomes it scores. *Any figure whose interval spans
  impossible values should be reported as inadmissible, not as wide.*
- **★ THE COHORT CRITERION NOBODY HAD STATED [c7]: a venue baseline needs a SPREAD
  OF OUTCOMES, not just a spread of games.** 13 of 14 one-sided makes Brier
  degenerate however many rows sit underneath — **16,301 observations bought
  nothing.** That is a selection rule for Saturday and it is *not* "more games".
  Spread/total are structurally better here: priced near 0.5 by construction.

> **`is_live` IS TEXT, NOT BOOLEAN [B, and M hit it too].** `d.is_live == True`
> returns **0 live rows of 1,442,602**, putting *"no live price coverage exists"* on
> screen as a clean plausible number. B caught it because 92.2% of a price tape
> being non-live is not a thing — not by checking the dtype. **A wrong result that
> agrees with the right answer** is the most dangerous shape of the night: it would
> have corroborated the correct conclusion for entirely fictitious reasons.

## ✅ THE FRAME IS CONFIRMED — 15 of 15 on every move above the noise band [M, 2026-09-07]

**Both games settled overnight. `401856661` finished 41-38, so the away side scored
35 points after the earlier run — the bidirectional evidence the check had never
had.** 38 events across two games, all three amendments applied (1a UNION guard on
period AND total score, 1b score-diff detection, 1c anchor sweep).

              correct  WRONG  flips  flat
      HOME        13      2      2     3
      AWAY        11      2      1     0
    stable: 24 correct / 4 wrong = 85.7%   (gate 91.7%)

**★ THE AWAY ARM IS NOW GENUINELY TESTED — 11 correct / 2 wrong.** The structural
objection (favourites extending give one-directional evidence) is retired.

**★★ AND SPLITTING BY SCORE SIZE SETTLES IT:**

      points          n   correct  WRONG   accuracy   median |move|
      1-3 (FG/PAT)   17      13      4      76.5%        2.00pp
      6-8 (TD)       11      11      0     100.0%        6.00pp

      median |move| on CORRECT   5.25pp
      median |move| on WRONG     1.13pp
      **events moving >3.5pp:   15 of 15 correct — 100%**

**Every touchdown is correct. Every event moving more than 3.5pp is correct.** All
four failures are 1- or 3-point scores whose largest move is ≤3.5pp — **inside the
measured drift band** (~25% up / ~25% down, modal flat).

**So the frame is CONFIRMED and 85.7% fails the gate for a reason that is not the
frame: the check counts noise-sized moves as evidence.** A 1-point PAT moving
−0.0100 is the market not responding, scored as a vote against.

### The threshold objection, retired by reporting the whole curve

My 3.5pp was **post-hoc — chosen after seeing the results.** c7 derived the drift
distribution from the control instead (n=6,742 non-scoring 60s windows) and
deliberately **did not** check what any percentile gave on the event set, to avoid
selecting a threshold by which one flattered the result. So I picked none:

      percentile   floor    n admitted   correct  wrong   accuracy
        none      0.00pp        28          24      4      85.7%
        p50       0.50pp        28          24      4      85.7%
        **p75     1.50pp        22          21      1      95.5%**  ← clears the 91.7% gate
        p90       3.50pp        15          15      0     100.0%
        p95       4.75pp        13          13      0     100.0%
        p97.5     6.00pp        11          11      0     100.0%
        p99       8.50pp         6           6      0     100.0%

      unfiltered, always reported alongside:  24/28 = 85.7%

**★ THE RESULT IS NOT THRESHOLD-DEPENDENT.** Accuracy is **monotone** in the floor
and clears the gate at p75 — a floor admitting a quarter of all drift windows. No
post-hoc choice does any work: every principled cut from p75 up passes, and the only
failures are at p50 and none, where the check knowingly counts noise as votes.

> **★ READ THE CURVE AT p75, NOT AT THE 100% ROWS [c7].** Accuracy rises partly for
> a *mechanical* reason — raising the floor removes events — so a 100% cell buys
> itself with n. Under a symmetric-drift null:
>
>       floor    n  correct        p
>       none    28       24    9.0e-05
>       **p75   22       21    5.5e-06**   ← STRONGEST
>       p90     15       15    3.1e-05
>       p95     13       13    1.2e-04
>       p97.5   11       11    4.9e-04
>       p99      6        6    1.6e-02   ← 100% and nearly uninformative
>
> **p99's perfection is six coin flips.** Read where accuracy and n are jointly high.
>
> **★★ AND THE CURVE'S SHAPE IS THE TEST, NOT A ROBUSTNESS CHECK ON IT [c7].** Under
> an **inverted** frame the large moves would be unanimously WRONG — accuracy would
> fall as the floor rose. **A correct frame predicts monotone-RISING; an inverted one
> predicts monotone-FALLING.** So conditioning on magnitude is *informative* precisely
> because its two directions are diagnostic — which answers c7's own objection that
> 1d conditions on magnitude and correctness together. **The curve points one way at
> every cut.**
>
> **c7 has withdrawn the refusal they placed on the frame**, noting it stood for the
> right reason for as long as the evidence was thin.

**And 3.5pp is p90**, so the 15/15 was achieved *with* drift-sized moves admitted at
one window in ten — stricter cuts can only remove marginal events, not manufacture
the unanimity. **c7's even-handedness precondition for 1d is met by construction:
the filtered number is not a claim, the curve is.**

**Away scores move home probability down 9–19pp on touchdowns; home scores move it
up 11–13pp. The large moves are unanimous.** c7's refusal to publish a Brier was
correct at the time, and the reason is now measured rather than suspected.

> **`401856661` has NO `post` row despite finishing 41-38** — the recorder stopped at
> 03:38Z in the fourth quarter. **A strict `has_post` predicate excludes a completed
> game**, which is the strict-vs-loose cohort distinction arriving in the data.

### Superseded: the earlier 6/2 reading, kept for the trail [M]

> **★★ WITHDRAWN 2026-09-07. The 4/4 below came from a DEFECTIVE EVENT DETECTOR and a
> SINGLE ANCHOR.** Applying c7's amendments together — **1b** (detect by score diff,
> not `scoring_play`) and **1c** (sweep the anchor over 30/60/120/180s) — finds
> **ELEVEN events, not six.** Five were invisible to the flag, *including both that
> now read wrong.*
>
>       game scorer  change         Δhome_wp 30/60/120/180s          verdict
>       661  AWAY    0-0→0-3        +0.0000 +0.0000 +0.0000 -0.0200  stable correct (weak: 3 of 4 zero)
>       661  HOME    0-3→3-3        +0.0150 +0.0150 +0.0050 +0.0150  stable correct
>       661  HOME    3-3→9-3        +0.0000 +0.0000 +0.0000 +0.0000  all-flat, no evidence
>       661  HOME    9-3→10-3       +0.0100 +0.0100 +0.0100 +0.0100  stable correct
>       661  HOME    0-3→10-3       +0.0000 +0.0000 +0.0000 +0.0000  ★ ARTIFACT — 1a
>       438  AWAY    0-0→0-3        +0.0300 +0.0300 +0.0350 +0.0350  **stable WRONG**
>       438  HOME    0-3→3-3        -0.0100 +0.0000 +0.0050 +0.0050  **FLIPS — cut by 1c**
>       438  HOME    3-3→9-3        +0.0100 +0.0100 +0.0100 +0.0150  stable correct
>       438  HOME    9-3→10-3       +0.0150 +0.0150 +0.0150 +0.0150  stable correct
>       438  AWAY    10-3→10-10     -0.0450 -0.0450 -0.0450 -0.0450  stable correct
>       438  HOME    10-10→13-10    -0.0100 -0.0100 -0.0100 -0.0100  **stable WRONG**
>
> **6 correct, 2 WRONG on stable events = 75%, against c7's registered 91.7% gate.
> The frame is REFUSED, not refuted** — 75% against a 91.7% bar declines to certify
> the frame; two stable-wrong events on two games do not establish that the venue's
> frame is wrong. **Unestablished in BOTH directions** [c7's phrasing, adopted over
> my "the frame FAILS"].
>
> **★★ AND 6/2 IS PROVISIONAL — A SECOND ROUTE REPRODUCES EVERY VALUE AND NOT THE
> EVENT SET.** A SQL version of the same sweep, run on prod against the pandas run on
> the local export: **every value matches to four decimals** (−0.0450; +0.0150/−0.0100;
> +0.0000/+0.0100; +0.0100/+0.0150). **It found 7 events; pandas found 10.** One gap
> is explained (`HOME 10-10→13-10` postdates the query). **Two are not — both
> `AWAY 0-0→0-3`, one of which carries a stable-WRONG verdict.**
>
> **So the arithmetic is corroborated and the POPULATION is not**, and the
> discrepancy lands on the away arm, which was already the thin part. *Not re-run to
> a clean answer — the honest state is an unexplained event-set disagreement.*
>
> **The cause is an omission of mine: `game_id` was left out of the SQL SELECT**, so
> its rows are unlabelled and cannot be matched game-by-game. **A comparison you
> cannot align row-to-row can confirm values and can never confirm populations** —
> which is the half that matters. *Print the KEY with the value, or the second route
> can only ever agree with you.*
>
> **★ AMENDMENT 1a HAS SINCE BEEN APPLIED AND THE TALLY IS UNCHANGED.** Guard =
> drop plays rows whose TOTAL score falls below the running max; 1 row dropped from
> 661, 0 from 438. **The spurious `0-3→10-3` was ALL-FLAT, so it contributed nothing
> — 6/2 now stands on an event set with all three amendments applied.** One wrong event is on the HOME arm — home kicks a field goal
> and home_wp falls 0.0100 at every window.
>
> **★ 1c IS EVEN-HANDED — it cuts a HOME event** (`438 0-3→3-3` flips sign and is
> excluded). c7 stated *before* seeing the sweep that they would rather it cost the
> 4/4 than stand unexamined. The rule removed evidence from the arm that was winning.
>
> **★ AND `661 0-3→10-3` WAS AMENDMENT 1a INSIDE MY OWN DETECTOR** — it appeared
> *after* `9-3→10-3`, so the score went backward then forward and the diff
> manufactured an event. **The monotonicity guard must run BEFORE the diff.**
>
> **★★ AND 1a MUST BE SCOPED TO THE PLAYS AXIS ONLY [c7] — the same guard on STATE
> would cause real damage:**
>
>       STATE  18,775 rows / 50 games   22 backward score steps / 18 games  ← ESPN UN-POSTING, REAL
>       PLAYS   8,633 rows / 50 games   38 backward score steps / 17 games  ← wall_clock sort artifact
>
> **Same symptom, opposite correct response.** On plays the guard removes an
> artifact; on state it would **silently keep a retracted score and hide the
> retraction that flips one winner in 29.** As written, 1a said "order by wall_clock
> with a monotonicity guard" and someone would have applied it to state rows.
> **★ AND THE GUARD VARIABLE IS NEITHER — IT IS THE UNION [c7, measured]:**
>
>       plays ordered by wall_clock, 8,633 rows / 50 games
>         below running-max PERIOD only          5
>         below running-max TOTAL SCORE only   205
>         below both                            35
>         period guard alone catches            40
>         score  guard alone catches           240
>         **UNION                              245**
>
> **Neither variable catches the other's misses.** Period-only misses a
> within-period reversal; score-only misses an out-of-order row that did not change
> the score. *My re-run used total-score alone — right for those two games, and it
> would have left 5 rows on the full export.*
>
> **1a as first written — "order by `wall_clock` with a monotonicity guard" — named
> neither the SCOPE nor the VARIABLE, and three people adopted it.** It now carries
> both, with the counts behind each.
>
> **What survives: the drift control.** Up/flat/down near-symmetric at a ~25%
> baseline, so the moves that exist are not noise. **What does not: the direction.**
>
> **c7 refused to publish a Brier on exactly this basis three hours earlier. I then
> spent two hours producing a number saying the frame was fine.**

### The withdrawn result, kept for the trail [M, re-derived by c7]

Ran c7's frame check with **Amendment 1 applied** (event time from `plays.wall_clock`,
not `first_seen_at`) and **zero movement scored as NO EVIDENCE, never as failure** —
their two named defects, avoided.

      scorer  score   home_wp before → after            verdict
      AWAY    0-3     0.6475 → 0.6475    0.0000         no evidence
      HOME    3-3     0.6400 → 0.6675   +0.0275         correct
      HOME    9-3     0.7925 → 0.8025   +0.0100         correct
      AWAY    0-3     0.8525 → 0.8525    0.0000         no evidence
      HOME    3-3     0.8325 → 0.8475   +0.0150         correct
      HOME    9-3     0.9175 → 0.9275   +0.0100         correct

**★ THE CONTROL IS WHAT MAKES IT A RESULT.** c7's stated worry was that a venue
drifting up confirms "home probability rises" for free. Over ~2,500 random
non-scoring windows on the same markets:

                    UP      FLAT    DOWN
      M   16453   23.0%    56.8%   20.2%      c7 re-derived:  22.3% / 47.8% / 29.9%
      M   16488   28.5%    45.6%   25.9%                      24.8% / 38.2% / 36.9%

**Up and down are near-symmetric; FLAT is modal. The market is not drifting.** 4-of-4
up on home scores against a ~25% baseline is **p ≈ 0.004 (M) / 0.003 (c7,
independently).** Drift is dead.

**It also vindicates the second defect fix:** flat is 38–57% of *all* windows, so a
flat response is the **modal outcome** — the two away zeros are uninformative, not
contradicting. c7's first pass had scored the modal state as failure.

> **THE CONTROLS AGREE ON THE UP RATE AND ARE NOT THE SAME MEASUREMENT [c7].** The
> flat/down split differs ~10 points **in the same direction in both markets** —
> systematic, most likely c7's 60s-step-with-300s-exclusion against M's 30–180s
> window. **Corroborating on the up rate only; do not quote them as agreeing on the
> flat rate.** c7 also could re-derive only 3 of 4 informative events (their price
> export ends 00:31Z) and said so.

**★ WHAT IS NOT ESTABLISHED: THE AWAY ARM.** Both away events produced exactly
0.0000, so all four informative events point one way, in two games where **home is
favoured (0.65, 0.85) and extending.** *A frame inverted on the away arm would be
indistinguishable from this result.* The bidirectional requirement in c7's
registration is **unmet, and unmet structurally** — favourites extending produce
one-directional evidence. **Confirmed for home-scoring events; unverified for away.**

## ⚠ THREE SUBSTRATE DEFECTS IN `espn_cfb_live_plays` — one lands on the axis we all adopted [M]

**1. `wall_clock` DOES NOT GUARANTEE GAME ORDER.** Ordering plays by it, **period goes
BACKWARD on 27 plays across 9 of 53 games** — including 4→1 jumps, one of them a
touchdown (`401868170`, 13:58:53, period 4→1, "Rushing Touchdown"). So the fix
everyone converged on tonight is right about *which clock* and **still needs a
monotonicity guard** — the same `cummin` d5 prescribed for `reg_left`. *A
scoring-play-only filter is not sufficient protection, since one of the out-of-order
rows is a scoring play.* (The frame check above is unaffected — its six events were
verified in correct game order rather than assumed.)

**2. THE EXTRA POINT IS NOT FLAGGED AS A SCORING PLAY.** The touchdown row reads 9-3;
the score reaches 10-3 on the *following* `Kickoff` row with `scoring_play = f`.
**Summing `scoring_play` rows undercounts by one per touchdown.**

**3. `score_value` IS NULL ON EVERY ROW**, touchdowns included.

**Safe rule: read the score from `home_score`/`away_score` on the play row. Never
reconstruct it from `scoring_play` or `score_value`.**

## ⛔ "SETTLED PRICE" DOES NOT EXIST ON THIS VENUE — the frame is unverifiable by either registered method [c7, M]

**ZERO of 119 markets on game 401858437 carry any quote after the whistle.** Not the
winner market, not one of the other 118. The most liquid market on the game —
`aec-cfb-washst-wash`, n=4,653 — **stopped quoting at 23:29:31Z, eleven minutes
before the 23:40:52Z result.**

**This is structural, not sampling.** c7's pre-registration named settled-price
agreement as the FALLBACK frame check. **On this venue it has no data to run on by
construction — a fallback that cannot execute.**

**And the PRIMARY check is the one reported broken three hours earlier** (wrong
event-time axis, absence scored as failure, no bidirectional scoring events). **So
the frame is currently unverifiable on this venue by either registered method.** That
is worse than "one check failed" and it is a Saturday blocker, not a caveat.

**THE FIX, and it is the night's recurring correction one more time:** resolution
must come from the **ESPN outcome**, never from a price. A frame check comparing the
venue's final *live* price to the realised outcome — accepting that "final" means
~11 minutes early — is testable, and **needs a stated STALENESS TOLERANCE rather than
a price threshold.** *The condition, not a proxy for it.*

> **What the map/convention clearing DID establish, by outcome rather than
> inspection:** ESPN final 24-10 HOME; slug `washst-wash` so first team = `washst` =
> away = the loser; **YES priced 4.75%.** So **YES = first slug team = away, confirmed
> on this tape**, and the 0.86 fuzzy map row is correct. Two of c7's three candidates
> eliminated; the residual is the extremity proxy they had diagnosed from the inside.
>
> **It does not touch the refusal** — 80% is still 80%, and G=1 on 59 markets sharing
> one margin is still one outcome draw.

**Open for Saturday:** if either remaining game finishes close, the monotonic check
finally gets bidirectional scoring events — **but it will still be on the wrong time
axis until it reads `plays.wall_clock`** (c7's own Amendment 1, registered four hours
ago and still unapplied to the check they hand-rolled).

## ✅ 2026-09-06/07 — THE FIRST COMPLETE GAME, AND THE σ SLOPE REFUTED

**The cohort that blocked five measurements all week stopped being empty.** Three
games caught at **`period 1, 0-0`** with pregame *and* live venue quotes on the same
game — the first time the two boundaries have coincided:

      espn        venue  conf   kickoff (P1,0-0)   pregame rows   live rows   closing ladder ≤15min
      401856661   16453  1.00   23:45:38Z             18,013        58,593           60
      401858437   16486  0.86   20:08:46Z              4,403       234,573           42
      401858438   16488  0.96   23:52:29Z             21,069        51,274          415

**The map was the only obstacle and it was never a prod write** — zero of the three
were in the DB table; the builder matches all three at 0.86–1.00, emitted read-only
to `backups/exports/cfb_game_map_20260907T0030Z.csv`. *Third time tonight the
blocked action and the needed artifact were different things.*

**`401858437` SETTLED 24-10**, and the final was verified against tonight's own
hazard rather than trusted: **one `post` row with the recorder then stopping** — the
configuration that conceals an un-post — but the eight preceding `in` rows all read
24-10. **The first game in the programme's history with kickoff gate, closing
ladder, live tape and a verified outcome.**

### ★ σ's LINE DEPENDENCE IS REFUTED — level holds [d5]

      fitted slope        −0.0105     (shipped +0.1182)
      predicted rise       1.87 pts    observed 0.00
      residual scatter     0.193 pts   →  signal-to-scatter 9.7×
      mean |err|:  flat 15.86 → 0.16 pts  |  shipped relation → 0.70

**Shipped description is now σ ≈ 15.9 with no supported line dependence.** Not
refitted on n=3 — coefficients unchanged so the trail stays legible, `MarginScale.flat()`
added and preferred, docstring says the relation is unsupported.

> **★ THE CORROBORATION IS WEAKER THAN I FIRST WROTE, and d5 downgraded their own
> result [correcting M].** B independently refuted the slope by a two-point
> difference (+0.0003 ± 0.0303, excluding the shipped +0.1182). I called that "two
> cohorts and two statistics." **It is one measurement and two inferences** — B's and
> d5's σ values are *identical* (15.98 / 15.98 / 15.61) on identical rung counts
> (34 / 25 / 23), the same computation on the same three ladders. **By B's own
> standard the σ could not have disagreed.**
>
> **The refutation stands on the POWER CHECK** — 9.7× signal-to-scatter, a property
> of the one measurement — **not on two independent routes.** Hold it at that
> strength.
>
> The three slope *estimates* (0.1182 / 0.0623 / −0.0105) do come from different
> cohorts, and all three are flatter than the shipped one, which was the only one
> from a known-bad selector. **G=3, with one game at |line| 8.1 against two
> near-coincident at 22.5 and 23.9** — one low point against effectively one high
> point.
>
> **★ NARROWED AGAIN [B], applying c7's own defect to their ladders — "closing" was
> doing work the data does not support on two of three:**
>
>       venue   interior rungs   mids that CHANGED in the 15-min window   last-quote age
>       16453        34                1/34   ( 3%)                          0.2 min
>       16486        25                0/25   ( 0%)                          9.7 min  ← one
>                                                                    sweep, all rungs
>                                                                    share a timestamp
>       16488        23               20/23   (87%)                          0.1 min
>
> **Only 16488 is genuinely closing AND active.** B's original headline contrast was
> 16453 vs 16486 — *both static*. Re-run against the active ladder: gap 14.4 pts,
> observed Δσ −0.37, implied slope −0.026, **shipped +0.1182 predicts +1.70 and is
> still excluded.** So the refutation does not depend on the static ladders — but the
> **low-line end is still static**, so the contrast is one static against one active
> and cannot be made two active on this cohort.
>
> **THE PRECISE FORM: the shipped slope is unsupported WITH POWER on three gated
> pregame ladders, of which ONE is genuinely quoting at the close and two are
> static.** Third narrowing of this claim tonight — mine, then d5's, then B's — each
> weaker and more accurate than the last.

> **★★ HOW THE BAD SLOPE SURVIVED, and it is the finding [d5]: a CONTROL COMPUTED ON
> THE CONTAMINATED DATA CANNOT EXONERATE THE CONTAMINATION.** d5 *had* tested the
> suspected mechanism — lopsided games carry more one-sided rungs, and a tail-only
> probit fit inflates σ — with a symmetric-window control that argued the slope was
> real. **It ran on the same 14 contaminated ladders, so it never had power to clear
> itself.**
>
> **And power was checked BEFORE the refutation was claimed**, explicitly because B
> had just watched their own flat-σ result collapse for want of it. 9.7× is what
> makes "could have seen it and did not" a finding rather than an absence.
>
> **A distinction not to conflate [d5]:** σ is **cross-sectional** over ~30 rungs at
> one instant, so it needs a *ladder*, not a *moving* one. B's σ-stable-over-time
> test needed movement and lacked it. *"The board was frozen" disqualified three
> measurements tonight and is NOT a disqualifier here.*

**WITHDRAWN before it travelled [B]:** "d5's surface passed out of sample" tested the
**level**, not the slope — **every slope from 0.0 to 0.1182 passes ±10%, and a FLAT σ
fits better**, because the slope's whole contribution across the line range is 1.62
points, inside the band at both ends. **A criterion that admits the entire hypothesis
space rejects only a level wrong by ~13%.** d5 caught it by running B's own
achievable-image check against rival surfaces.

**Concrete Saturday cohort requirement, better than "more games":** the slope needs
**two games at |line| ≥ 35 with quoting boards**, where it predicts ~17.4 against a
flat 15.4 — a 13% gap that clears the band. Tonight's 8.1 / 22.5 / 23.9 cannot.

## ⛔ THE WINNER-MARKET ROUTE IS BLOCKED BY VENUE COVERAGE, NOT BY EDGE [c7, A, d5, B]

**The identity is a winner-market model and the venue barely runs a CFB winner
market.** c7's feasibility on B's cohort:

      31 games -> 19 in the game map -> 3 with live winner prices -> **7 price rows**

**Not a cohort accident.** d5 measured the CFB board at **70 moneyline markets
against 8,088 spread and 6,425 total**; tonight's live game carried **one** `aec`
market against 72 spread and 46 total. The instrument and the market do not
overlap, and ESPN-side abundance (~466 poll rows/game) cannot fix it. B's own
diagnosis: *selected on the abundant side.*

**★ AND IT BLOCKS THE MONEY CONVERSION AT LEG 1 [A].** Brier improvement = edge²
**only when the baseline is the MARKET.** B's +0.02456 is against ESPN and
+0.02043 against an anchor — neither is what the model trades against. So
√0.02456 = 15.7pp is the **RMS distance to ESPN, not an edge over the venue**:
*two models can differ by 16pp and both lose to the venue.* Beating ESPN
(sd 0.0222) is not beating the venue (sd 0.2663) — a category difference, not a
caveat. A's requirement (1), `Brier(in-game venue)`, is the number that settles
everything and **cannot be computed on this data**.

**Options, and it is a design question:** a different market type (spread/total —
a different instrument), a different league, or **NFL, where the winner market is
the liquid one** — opener 2026-09-10 00:20Z.

**A's conditional ceiling survives and says re-site rather than abandon:** IF the
edge is against the venue AND early AND real, **22.6pp RMS clears ~1.9pp τ** even
after a large RMS→mean discount.

## ⚠ `state == 'post'` IS NOT FINAL — ESPN UN-POSTS, AND A WINNER FLIPS [d5, M, B, c7]

      game 401858428
        02:54:26Z  post   7-12    ESPN calls it final, AWAY ahead
        02:54:52Z  in    13-12    reverts to live, HOME scores
        02:55:43Z  post  13-12    final again, the OTHER TEAM won

      games with a post row              29
      margin changes after first post     2
      **WINNER changes                    1**   (1 game in 29)
      games that un-post                  2

**Taking the FIRST `post` row names the wrong team.** Verified independently by M
(prod), B and c7. **Nobody was affected** — B uses `.last()` on time-sorted rows and
c7 used `tail(1)` filtered to `last_state == 'post'` — but *both by accident*:
`.last()` was chosen because it reads as "final score", not because anyone knew
ESPN un-posts. Another [[a-rescue-you-did-not-design]].

> **★ THE CITATION NEEDS A THIRD FIELD: PREDICATE, AGGREGATION, ROW SELECTOR.** The
> cohort predicate says which GAMES; the row selector says which OUTCOME; and only
> the first was ever written down. Same shape as `|A|` needing predicate *and*
> aggregation. B: *"same predicate, opposite label — the labels were never wrong,
> the description was, and the description is what someone reimplements from."*
>
> **At G=11 one inverted label flips a whole ladder of ~48 rungs**, since every rung
> in a game resolves from the same margin [c7].
>
> **Pinned by asserting the DISAGREEMENT, not the value** [B]: a test that first-post
> and last-row *differ on game 401858428, by name*, fails a mutant that hardcodes
> today's labels and fires if a future export stops exercising the hazard.

**TWO HAZARDS, DIFFERENT GUARDS:** the P4-`0:00` branch (7 games continue past such
a row; now explicitly guarded) and the un-post (handled **only** by `tail(1)`, which
is why it is in the docstring — the guard is a one-word choice that looks arbitrary
without the reason).

> **★ AND d5's SELF-CORRECTION MATTERS MORE THAN THE HAZARD.** They first diagnosed
> this as the P4-`0:00` clock branch. The clock rows on that game are a clean 7-12
> throughout — **their script compared the first P4-`0:00` row to the LAST row and
> charged the whole difference to the predicate under test.** Right phenomenon,
> wrong mechanism, and *worse than missing it because it was actionable and someone
> acted*: B had already written the game into a 3-game cohort with the clock
> mechanism attached, and would have fixed a clock predicate on Saturday while
> leaving outcome selection untouched.
>
> **General form [B]: a difference between two endpoints attributes to whatever you
> were looking at, not to whatever happened.** Third instance in this project —
> with the "monotone" three-bucket series and the "non-early" bucket that
> manufactured a decline.

## ⚠ ESPN POSTS SCORES THEN RETRACTS THEM — and the win probability follows [M, B]

      backward score steps   23, across 19 of 52 games (36.5%)
      every step exactly −3 or −6      (field goal / touchdown reversals)
      inflated score stands   mean 62.3s | min 22.1s | max 204.0s | 6 of 23 over 60s
      ESPN home_win_pct at the revert:  mean |jump| 6.47pp, **max 41.6pp**, 7 of 23 > 5pp

**A 41.6pp WP swing on a score that never happened.** B measured the impact on the
identity: 395 rows, 2.73%, across 16 of 31 games — **aggregate untouched**
(+0.02455 → +0.02496 vs ESPN), but per-row |identity − ESPN| reaches **41.01pp** on
phantom rows.

> **The cleanest example of the day of why "does it change the number" is the wrong
> test on its own [B]:** for a pooled Brier it changes nothing; for a per-row price
> comparison it *manufactures exactly the signal being hunted.* Same data, same
> defect, opposite significance. Shipped as a `score_reverted_window` column, not
> as prose — *a described caveat has no test.*
>
> **And B had already measured it and walked past it.** Their check printed
> `score DECREASES: 23 across 18 games` beside a comment reading
> `0 == scoreboard is trustworthy`. **The comment stated the conclusion the check
> existed to test, so the output read as confirmation.** It fails safe — a phantom
> can only make a P1-and-0-0 kickoff gate reject a good row — but that was not
> known when it was leaned on.

**It also breaks the frame check I proposed:** a retracted score produces a real WP
move against a score that vanishes, reading as an inversion that is not one. Run
monotonic-response on non-phantom rows only.

## ✅ PRE-SLATE READINESS CHECK — built, rescoped, handed to a1 [D]

One command, run at T−30, exits non-zero if the slate will not record. No daemon,
no deploy, no thresholds — which is why it can exist by Saturday when nothing else
D built is deployed.

**★ RESCOPED TO THE VENUE BOARD, and the measurement forced it [M, D].** Widening
the ESPN window moved events **132 → 180 while the venue stayed 119 both times.**
The board and the schedule are **different populations and the board is the
smaller fixed one**, so an ESPN-scheduled game the venue never lists is not a
coverage failure. Schedule-scoped, the check was permanently red; board-scoped it
passes and can legitimately reach zero:

      BOARD  19 games listed by the venue (the tradeable set)
      MAP    OK 19/19 joinable | VENUE OK 19/19 | ESPN OK 19/19

**Four lines, never one green/red** — both of this week's outages were one-sided,
and both times the healthy side is what everything measured.

> **Correction to my own escalation:** "31 of 50 unjoinable" counts against ESPN's
> *schedule*; the board-scoped number is the operational one. The 34/50 map
> improvement stands as the reason to rebuild; the residual is partly games the
> venue never offered.
>
> **Usage caveat [D]:** comparing two pinned exports **cut at different times
> manufactures gaps** — a first run showed ESPN missing 18 of 37, and game-by-game
> it was 18 kicked off before the ESPN export opened, 3 after it closed, **0
> genuinely absent.** Production reads live tables so it cannot arise there;
> anyone testing against pins must window-match first.

## ⚠ THE MONITOR WAS SILENCED BY THE FAILURE IT EXISTS TO CATCH [c7, D]

D's COLLAPSED spec read `espn_cfb_game_state` to decide which games were live.
**That table is written by the recorder the monitor watches.** During the 53-minute
outage `live_games` would return 0 and the monitor would conclude there was nothing
to check.

**D's account of the error is the transferable part:** they argued the source was
independent *because a different container writes it*, and never asked whether that
container's output survives the failures the monitor detects. **Different writer is
not independent. Independent means the signal still exists when the monitored thing
is broken.**

      derived from the monitored system   -- dies with it        (as specced)
      OR with the venue side              -- survives an ESPN failure, dies with
                                             a DB or host failure  (c7's amendment)
      fetch ESPN's schedule directly      -- survives all of it    (D, verified live)

**Build the fetch; keep the venue OR as the fallback**, not the reverse.

> **The independent source imports the same trap one level up [M]:** a failed fetch
> returns no games, indistinguishable from no games scheduled. An ESPN outage, a
> rate limit or a bad parameter would all silence it. **The external call needs a
> loud-failure state that is never folded into zero** — *"no games are live"* and
> *"I cannot tell"* must not share a code path.
>
> Already concrete: `groups=80` returns 1 live game, `groups=81` returns 1, **the
> union returns 2.** A monitor calling the default sees half the slate and reports
> a clean number — a1's FCS gate, now on the monitor.

**D's exact-equality invariant SURVIVES transitions, tested rather than assumed:**
28 games carry both `in` and `post` rows, zero breaks; `parse_game_state` returns
None only when `header.competitions` is missing, and a completed game still has one
(41 `post` rows, 2 `pre`). My false-fire concern is withdrawn.

## ⚠ τ IS A SURFACE, NOT A SCALAR — and the pooled number hid a factor of seven [A, c7, d5]

**τ(p) = half-spread + 0.06·p(1−p) varies by MARKET TYPE and by PRICE.** On
tonight's CFB tape:

      winner (aec)   0.25¢ half @ mid 0.04   → τ ≈ 0.5pp   (100% at extreme prices —
                                                            blowout, so p=0.5 UNMEASURED)
      spread (asc)   0.50¢ half @ mid 0.47   → τ ≈ 2.0pp
      total  (tsc)   2.00¢ half @ mid 0.46   → τ ≈ 3.5pp

**The pooled 2.5–3.5pp was totals-dominated.** A also corrected a 1.75pp winner
figure that paired a p≈0.04 half-spread with a p=0.5 fee — at the actual price it
is 0.47pp. **The fee term alone ranges 7× across the price axis**, so each trade's
edge must be compared against τ at its own price and type.

**★ AND IT COSTS A VERDICT [d5].** λ\* = 0.15 buys **1.20pp** — which **clears** a
0.5pp winner bar and **fails** a 3.5pp totals bar. Opposite conclusions inside one
pooled number.

> **FENCED, and the fence is the point [d5].** **1.20pp is WNBA, from PULSE's live
> entered decisions. 0.5pp is A's CFB tape.** A WNBA λ\* against a CFB τ shares no
> population — the splice this project keeps getting caught on. What the arithmetic
> establishes is that **the pooled bar hid a factor of seven between types.** It
> does **NOT** establish that any market clears. Status: *the winner-market case is
> no longer closed by that page* — **not** reopened.

**What closes it:** per-type τ on the **same league and cohort as the λ\***, i.e.
WNBA, on tape already held (`delta_market_snapshots`, 07-31..08-20). Routed to A;
d5 explicitly not running it, because two people measuring adjacent quantities on
different tapes is how the splice appears.

**★ 3.07pp IS ITSELF A TYPE-MIXTURE WHOSE BLEND WAS NEVER RECORDED [d5].**
`s = 1.569¢` was measured over some mix of winner/spread/total and nobody wrote
down which. **That is 1.193¢ one level up — a number without a population, in the
document that opened by documenting exactly that failure.**

## ✅ THE ASSERTION I PROPOSED WAS THE WRONG FIX [d5 corrected M]

I proposed asserting the away-first convention at the settlement boundary. **d5
refused and was right.** Those four sites do not *depend* on away-first, they
**measure** it: `quoted_is_home = home.team_abbrev == parsed.first_espn` compares
ESPN against the slug, so a flipped venue returns True and is **still correct**.
Verified by running `implied_settlement` with home/away logs swapped — same answer
in every case, and `resolution.py:118` documents the convention then declines to
rely on it.

**My error, in d5's words:** the structural distinction was doing more work than
the verdict I drew from it — I had already identified these as two independent
sources, reachable in principle, *which is exactly why they need no guard*. The
assertion would have raised on a game the functions already handle correctly.

**What shipped instead: `tests/test_slug_orientation_invariant.py`** — 11 tests,
each running BOTH orientations and demanding the same answer. Mutation-tested:
`!=` kills 4 of 11; **`quoted_is_home = False` (hardcoding the venue's current
behaviour) kills 3 of 11** — and that second mutant is **correct on every row of
real data**, wrong only on a home-first game. A fixture drawn from the real
convention cannot kill it. Totals survive both, correctly.

## ✅ DEAD BRANCHES: `first_is_home` is constant across 701 observations [d5, M]

d5's moneyline anchor was **inverted in every game** — away's probability labelled
home. The tell: `home_is_first` was **True on 1,451,379 of 1,451,379 rows across
5,754 slugs.** A conditional with no reachable else is a constant wearing an
orientation test's clothes. Confirmed by `corr(spread anchor, moneyline anchor) =
−0.929` on 12 overlapping games, having disagreed in **sign** before the fix.

**Swept the sibling sites on prod, which d5 could not reach.**

> **CORRECTION [d5, self-reported]: "four sites" was a truncated count.** It came
> from `grep | head -20` over a population of **49 hits across 14 files** (d5 said
> 54/18; my count on the tracked tree is 49/14 — same order, and neither of us
> printed a count at the time). **The 14 files include the whole `core/kalshi/`
> tree**, a different venue where nothing requires our naming convention to hold.
> d5 has since read all of them: **none carries the orientation defect.** The two
> genuine orientation decisions among the previously-unseen files are sound, and
> sound for the reason the broken one was not — **both are POSITIONAL and neither
> infers home/away from slug order** (`kalshi/analysis.py:337`,
> `audit/wnba_trade_sheet.py:148`). *The finding was fine; the epistemics were not,
> and the conclusion was only available after looking.*

      WNBA, slugs joined to team_game_logs on date + both abbrevs:
        resolvable games 648 | first IS home 0 | first IS away 648
      CFB, over the computed map [d5]:        away 53 | home 0

**701 observations, zero Trues.** But **these are NOT defects** — d5's compared two
encodings of one ordering (unreachable in principle, and wrong); these compare an
ESPN abbrev to a slug abbrev (**genuinely two sources, and empirically correct** —
an inverted `resolution.py:130` would resolve every settlement against the wrong
team and we would have noticed). **A dependency on an unstated invariant with no
test.** Fix is one assertion at the boundary, not a refactor.

## ✅ RESOLVED 2026-09-06 20:43Z — CFB venue recording is back

Both containers now run their own job and the fix is deployed, not just
committed. **Verified on prod at 20:46Z: 5,530 rows / 73 distinct stamps /
166 markets in 10 minutes, mean inter-stamp gap 2.46s** — against 4,736 rows
across **one** stamp in the preceding hour.

    meridian-cfb-live-recorder   core.live_recorder --interval 1.0   ← venue tape
    meridian-cfb-espn-recorder   core.feeds.espn_cfb_recorder        ← ESPN state

Tonight's 23:30Z FBS slate and the 09-12 measurement both have price tape.

**And the pre-flight was exercised on it immediately — finding two bugs in
itself** [B, 928060d]. First time any condition had been observed PASSING rather
than failing:

    CADENCE     1.63s   PASS
    CONTINUITY 12.26s   PASS   ← on a recorder restarted 6 minutes earlier,
                                 against a 60s ceiling. The restart did NOT
                                 spike it, so the ceiling is not too tight for
                                 real operation.
    COVERAGE   140.0%   impossible

**Bug 1** was arithmetic: an `elapsed // 60` denominator against a numerator
counting distinct minute buckets.

**Bug 2 is the one that matters.** With no `--start`/`--end` the window is
**data-defined** — min(stamp) to max(stamp). So **a recorder that ran six
minutes of an eight-hour slate scores ~100% coverage over its own span.** The
condition cannot see a truncated start or end, *which is the exact failure it
was added to catch.* The same data against the real slate window gives **1.5%**.

Fixed: coverage now reports **UNTESTED** when no window is given, and an
untested condition cannot contribute to a PASS.

**And the pre-declaration is what exposed it.** Both of us predicted coverage
would FAIL here by construction. **It passed — the prediction was right and the
code was wrong**, and that is only visible because the prediction was written
down first. Without it, a 140% reading is a green line nobody reads twice.

Two of three conditions are now validated in both directions. Coverage is fixed
but **still unobserved in a passing state against a real window** — tonight's
slate closes it, and it must be invoked with an explicit
`--start 2026-09-06 23:30 --end 2026-09-07 01:30` or the condition is inert.

*(Near-miss during the fix, flagged by a1: the merge was blocked by untracked
files on prod, and `run_vs_espn.py` THERE was newer than the committed version —
it carried the magnitude analysis. Thirteen files were byte-identical; that one
was not. Diffed before removing rather than clearing the blocker wholesale.)*

## ⚠ The original diagnosis, kept for the record

**CFB venue live recording died 2026-09-05 22:08Z and has not run since.**
No container currently runs `core.live_recorder` for CFB.

**Cause: two compose files claim the same `container_name`.**

    docker-compose.nfl.yml:106      cfb-live-recorder
      container_name: meridian-cfb-live-recorder
      MERIDIAN_LEAGUE: cfb ·  python -m core.live_recorder --interval 1.0   ← venue tape

    docker-compose.cfb-live.yml:18  cfb-live-recorder
      container_name: meridian-cfb-live-recorder
      ESPN_LEAGUE_PATH: ... ·  python -m core.feeds.espn_cfb_recorder        ← ESPN state

**The SERVICE KEY collides too** [M, d5] — both files declare a service named
`cfb-live-recorder`, not just the same `container_name`. **Renaming only the
`container_name` leaves the trap armed.**

**Two mechanisms fit and we cannot tell which fired** [Debugger]:
(a) if both files were passed to one `compose -f … -f …` invocation, compose
**merges** same-named services field-by-field and the second definition silently
overrides the first; (b) `docker-compose.cfb-live.yml`'s own header documents
the command as `-f docker-compose.yml -f docker-compose.cfb-live.yml`, which
does **not** include `nfl.yml` — under that invocation there is no merge, just a
container-name **takeover**: compose creates `meridian-cfb-live-recorder` and
replaces the running container of that name.
Distinguishing them needs shell history we do not have. **Both end in the same
dead recorder and neither changes the fix**, so "silent merge" should not travel
as established fact.

The surviving container was created 2026-09-05T22:22:15Z and runs the ESPN feed;
dense recording stopped at 22:08. [M, Debugger]

**It is the only duplicate — derived twice, independently** [M, d5 and
Debugger]. Across all 7 compose files: 19 distinct container names, 20
definitions; one container name claimed twice and one service key defined twice,
both the CFB case. Nothing running that is undefined. The only thing defined and
not running is `trainer`, whose own header calls it "a ONE-OFF RUNNER, not a
service" with `restart: "no"` — absent is its correct state. **No feed is
silently missing, and Thursday's NFL path is not exposed** (all three NFL
services appear exactly once).

**Recommended direction** [d5]: rename the ESPN half, following the repo's own
convention — feed recorders carry the feed's name (`espn-live-recorder` →
`core.feeds.espn_live_recorder`), venue recorders carry the venue naming
(`live-recorder` → `core.live_recorder`). The ESPN service in `cfb-live.yml` is
the misnamed one — a feed recorder wearing a venue recorder's name — so
renaming it to e.g. `cfb-espn-live-recorder` leaves `meridian-cfb-live-recorder`
pointing at the venue tape and nothing that greps for that name needs changing.
That matters because whatever pre-slate check gets written for Saturday will
reference the venue recorder. Rename BOTH the service key and the container
name; that is correct under either mechanism above and strictly safer than
renaming one.

Measured: at Saturday's peak CFB took 1,193,206 rows/hour across **967 distinct
`captured_at` stamps** — ~3.7s cadence. The sweep produces ONE stamp per
~35-minute cycle. Live rows/hour since: 1.25M (21:00) → 184k → 2,227 → ~650.

**Consequence: 09-12 would be captured at 35-minute sweep cadence, not 1s.**
The pre-registered Saturday measurement assumes a tape that will not exist.

**The fix is not a restart.** Starting the venue recorder destroys the ESPN feed
the same way — they cannot coexist under one service key. Both the service key
and the container name must change, which is a decision plus a deploy.

> **STATUS 2026-09-06 20:16Z — FIXED IN THE REPO, NOT IN PRODUCTION.**
> `edd329b` corrects the compose files in the recommended direction. **Prod is
> unchanged.** `meridian-cfb-live-recorder` is still running
> `core.feeds.espn_cfb_recorder` from a container created 2026-09-05T22:22:01Z;
> `meridian-cfb-espn-live-recorder` does not exist; **`core.live_recorder` runs
> nowhere for CFB** (only WNBA at 0.2s and NFL at 0.5s). Zero CFB rows in the
> preceding 30 minutes. **The container must be recreated.** Until then Saturday
> is still NO-GO. [M, manager]

> **AND THE PRE-FLIGHT AS WRITTEN WOULD NOT HAVE CAUGHT THIS CLASS.** [M, Debugger]
> Tested against known-bad days:
>
>     09-06, dead all day          25 stamps   median gap 2,076s   FAIL ✓
>     09-05, died mid-slate     6,099 gaps     median gap  3.16s   PASS ✗
>
> 09-05 is the day the recorder died at 22:08 with ~110 slate minutes
> unrecorded — 372 of 480 covered, 77.5%. **The outage contributes ONE gap**, and
> a median over 6,099 gaps cannot see three outliers (only 3 exceed 60s; p99 is
> 10s, on the boundary). The "<50% uptime = not measured" clause does not save it
> either, since 77.5% clears 50%. **On the exact day it broke, both criteria
> pass.**
>
> What would have fired from the same data: max inter-stamp gap (2,487s against
> ~4s healthy, 600× separation), minutes with no stamp (108 of 480), or any
> coverage floor above 80%.
>
> **REPLACED, 2202b48** [B]. Three conditions, ALL required, each failing on a
> different shape:
>
>     1. CADENCE     median gap < 10s     distinguishes live tape from the 900s sweep
>     2. CONTINUITY  max gap ≤ 60s        09-05 max 2,487s against ~4s healthy
>     3. COVERAGE    ≥95% of minutes      09-05 was 77.5%
>
> The arithmetic behind why no threshold on a median works: **an outage of any
> length contributes exactly ONE gap.** Among 6,099 slate gaps, three exceeded
> 60s; the median is the 3,050th value. p99 landing at 10s on the original
> boundary was coincidence, not design.
>
> **The apparent disagreement about which rule was tested was neither party
> misreading — BOTH predicates were in the file, 96 lines apart** [B]:
> line 43 gated on `espn_cfb_game_state.first_seen_at` at a 10-MINUTE gap;
> line 139 gated on the venue tape at a 10-SECOND median. A venue pre-flight was
> bolted onto a registration whose denominator still ran on ESPN state, and the
> two were never reconciled. Debugger tested the amendment, so **the
> three-condition replacement keeps its evidence and stands** — the DENOMINATOR
> was the untested half, and it was the dangerous one.
>
> **FIXED, aad20de:** two recorders, two conditions, both required. Condition A
> is the **venue tape**, and the denominator is defined on it because fills come
> from it. Condition B is game state and gates only the join. **If A fails the
> slate is NOT MEASURED and no verdict about the model issues, whatever B
> shows** — pre-committed rather than decided on the night.
>
> Without that fix, 09-12 would have reported ESPN uptime HIGH, venue tape
> absent, capture near zero — which B's own diagnostic tree reads as "cannot see
> football at all, a capability failure." **A dead container reported as a
> verdict about the model.**
>
> **The figures are Debugger's, not B's** — B could not reproduce the test locally (their only
> substrate with `captured_at` had 810 stamps against 13,175, with an existing
> ten-hour gap that swallowed the injected outage). They accept the mechanism,
> which needs no data, and decline to claim the numbers.

> **WEDNESDAY IS A FREE REHEARSAL FOR SATURDAY — and the date is UTC-sensitive.**
> First NFL kickoff is **2026-09-10 00:20Z**, verified at the venue: ticker
> `KXNFLGAME-26SEP09NESEA-NE` carries `occurrence_datetime 2026-09-10T03:20:00Z`
> minus the verified +3h settlement-stamp convention. The ticker date is
> US-local, the UTC date is the 10th. **Rehearsal window 2026-09-10
> 00:00Z–04:00Z.** Third ET/UTC confusion in this programme; every window in the
> registration is now stated in UTC.
> `core.live_recorder` cannot be verified on a quiet day: `meridian-nfl-live-recorder`
> (0.5s) and `meridian-live-recorder` (0.2s) both report `cycles: 0` right now,
> which is CORRECT — NFL week 1 has not started and the WNBA season ended 08-31.
> So the last demonstrable proof the code path works is the 09-05 CFB tape.
>
> **NFL week 1 on Thursday is the first live exercise of that path since.** If
> Thursday produces a dense NFL tape, the path is proven two days before the CFB
> slate needs it. If it does not, there are two days to fix it rather than
> discovering it on Saturday. Worth watching deliberately rather than in
> hindsight — and it costs nothing, because the NFL recorder is already running
> and already correctly configured.

Good news attached: `core/live_recorder.py` contains no MIN_MID/MAX_MID/
MAX_SPREAD reference, so the venue tape was never band-filtered. Restore it and
the **whole slate** is captured, not just the quotable band.

## The freeze alone kills fills — measured, no confound [M, Debugger]

Cut at both boundaries (17:39Z freeze onset, 22:08Z recorder death) so the
middle window has one cause:

    A  pre-freeze   recorder alive, prices moving   14,873 fills / 1.81h  8,217/hr
    B  freeze ONLY  recorder alive, prices FROZEN        65 fills / 3.20h     20/hr
    C  freeze + recorder dead (confounded)                0 fills            —

**The freeze alone removes 99.75% of fills** with the tape flowing at full
cadence — 1.19M rows/hour, 967 distinct stamps at 18:00Z. That confirms a1's
arithmetic empirically: a fill requires the mid to fall through our resting bid,
and a book that does not move cannot produce one. Window C stays unattributed.

**And the 65 survivors are a THIRD selection effect.** They are not noise — they
are the markets that ESCAPED the freeze (0.0% of markets moving at 18:00 and
21:00, but 0.7% at 19:00 and 8.6% at 20:00). So any capture number computed over
a freeze-contaminated window rests on ~0.25% of the normal fill population,
selected on *"was still moving"* rather than at random.

Unlike phantom and censoring, this one applies **only** to freeze-contaminated
windows — which makes it a reason to EXCLUDE those hours, not to widen a caveat.
The pinned export is already clean on this: the 13 all-frozen CFB games carry no
real fills and were removed by the real-fill filter independently.

## The pessimistic execution arm double-charges [M, D]

`pulse_execution_decomposition.py:144` anchors alpha on `mid_at_fill`, so the
entry concession `c_e` is exactly the negated markout and the identity closes
with residual **$0.0000000000** across 1,944 legs. Netting the +3.004¢/leg
spread credit would therefore be **wrong** — it imports a term from an anchor
this decomposition does not use.

**But Wave rule 2 replaces `c_e + c_x` with `4.70¢ × Σ legs` while leaving alpha
fill-anchored.** That is not a re-anchoring; it is one term swapped for a
quantity measured from a different origin. Alpha *starts* at the fill mid, which
is already worse than the decision mid by the measured pre-fill travel of
4.545¢/leg — so the travel is absorbed implicitly, and adding 4.70¢ on top
charges it again.

    engine rule    charge $85.34    PULSE total  +$23.65
    pessimistic    charge $220.88   PULSE total −$111.90

**2.59×, and the sign of the headline flips on it.** PULSE's own pre-fill travel
is 4.545¢ [4.199, 4.891]; QUOTE's constant is 4.70¢, inside that interval. A
*consistent* pessimistic rule charges the travel at the decision anchor and
re-anchors alpha with it — the substitution is then 0.155¢/leg, about **$7, not
$135.54**. Applied consistently, conservatism changes almost nothing.

**Do not read −$111.90 as PULSE's P&L under conservative execution, and do not
read +$23.65 as "PULSE is profitable."** Filled P&L spans zero at G=34. This
changes a sign, not a conclusion. Unverified: whether the rule was *intended* as
an opportunity-cost stress test against a decision-mid counterfactual — if so it
answers a different question, but it still cannot leave alpha fill-anchored
while doing it.

## The freeze alarm would have MISSED the freeze it was built for [M, c7 + manager]

Replayed against 2026-09-05 18:20Z, the alarm returns **OK — 214/3300 moved
(6.48%)**, above its 5% floor. Debugger's 0.0% and this 6.48% do not disagree —
they are one mixture: Debugger's 1,443 markets are a **frozen subset**, and the
other 1,857 were healthy at ~11.5%.

**The cause is POOLING WITHIN A LEAGUE, not the window straddling the onset.**

    frozen  healthy  healthy rate   pooled   verdict
      1443      500         11.5%    2.96%   ALARM
      1443     1857         11.5%    6.47%   MISSED   ← the real 09-05 mixture
      1443     1857         30.0%   16.88%   MISSED
      1443     4000         80.0%   58.79%   MISSED

A totally frozen block of 1,443 markets is invisible in almost every mixture. So
**v5 detects a freeze covering essentially a whole league and MISSES one confined
to the in-play subset — which is the shape 09-05 actually had.** Better than v4,
which missed both. Not sufficient.

c7's own design note 4 reads *"PER-LEAGUE, NOT POOLED. A freeze on one league and
not another is diagnostic and pooling hides it."* The argument was applied at the
league level and not one level down.

**Fix is per-GAME** — markets share a fate by game. The distribution was measured
[M, manager on c7's query]: 216 games kept and **0 dropped** by the 4-market
floor (so the constant would sit on the full population), worst healthy game
still moved 41.5%, and **zero simultaneously-quiet games in any healthy
30-minute bucket**.

**But K CANNOT BE SET FROM THAT, AND THE ZERO IS WHY** [c7]:

    0 quiet-game buckets in n=33
    95% upper bound on P(≥1 quiet game/bucket) = 8.68%  (rule of three)
    K=1 → 375 pages/month at that bound, 0 at the point estimate

33 buckets cannot distinguish *"never happens"* from *"8.7% of windows"*.
Bounding it properly needs 0 events in ~12,940 buckets — about **270 days**.

**And the sample contains no instance of the phenomenon K exists to tolerate.**
Legitimately quiet games must exist (a blowout with nobody trading), so either
the window is too short, the floor and stream guard remove them, or those 33
buckets happened to hold only competitive games. Setting a threshold to
discriminate quiet games from freezes, on a sample containing zero quiet games,
is the same defect as the `near_floor_buckets = 0` run from this morning.

**RESOLUTION: ship the per-game trigger in SHADOW.** Compute it every sweep, log
`games_quiet` and the game ids, never page. **Production becomes the
measurement** — a few weeks of healthy slates supplies the left tail this sample
lacks, including the legitimately-quiet games. The pooled league trigger keeps
paging meanwhile: weak, now precisely quantified, and better than nothing.

That also settles a1's liquidity precondition empirically rather than by
legislation — shadow mode shows whether quiet-but-healthy games actually appear.

**Shadow mode needs the alarm deployed first**: a trigger logging to a cron
nobody runs measures nothing.

**Nothing is deployed** — the alarm was never wired to a cron, so this is a
defect in an instrument we believed we had rather than one that failed in
service.

## Monitoring: two disjoint failures, two instruments, neither built [a1, c7]

**Rows can keep arriving while prices stop, and prices can keep moving while
rows stop.** Those are different failures and no single instrument sees both.

    ARRIVAL — external evaluator     spec `docs/infra/external-evaluator.md` cc58834
      **Floor MEASURED, not guessed** [M, a1, a821456]: healthy 09-05
      18:00–22:00Z, 425 intervals / 32 games, rows per market per 10-min:

          all intervals      p01  8.4   p05 50.9   p50 81.7
          edge (first/last)       2.4        6.6        75.1
          interior               60.7       67.3        82.0

      **The partial-interval effect IS the entire left tail.** Excluding edges
      moves the usable floor from ~8 to ~60 — with edges included, a floor low
      enough to avoid false alarms **would sleep through a 90% outage**. So an
      interval is evaluated only if the game was in progress for all of it;
      edges yield UNKNOWN.

      **And the obvious denominator is disqualified.** Markets-we-recorded is
      structurally blind: if the recorder drops half its markets, numerator and
      denominator both halve and the ratio is unchanged — the exact
      self-reference the evaluator exists to escape, nearly written into it.
      Denominator is `marketCounts.numMarkets` from the venue payload. It
      over-predicts (241 listed against 145.5 recorded, factor 1.66), which is a
      constant to calibrate through rather than a defect.

      **FLOOR = 30 rows per LISTED market per 10-min interval** — below measured
      healthy p01 with ~20% margin. A function of recorder cadence; must be
      recalibrated if that changes.
      ESPN scoreboard, groups 80 ∪ 81, own table, own timer, own process.
      expected>0 AND observed==0 → ALARM; expected==0 → quiet;
      schedule stale → UNKNOWN, never OK. `observed` must be ROW ARRIVAL, not a
      counter the recorder reports about itself.
      Would have caught: the dead container (yes) · the kickoff window
      (probably, needs per-game) · the venue freeze (**NO**) · an ESPN outage
      (must not false-alarm → UNKNOWN).

    MOVEMENT — per-game freeze alarm  `scripts/alarm_v5.py`, defective as written
      Rows kept arriving at 1.17M/hour through the 09-05 freeze; only prices
      stopped. Current pooled-per-league version MISSES that shape (see above).
      Fix is per-game and blocked on a healthy per-game distribution.

**Shipping either as though it covered both would leave a real failure
undetected while looking complete — worse than today, because today nobody
believes they are covered.** [a1]

**The recursion terminates, except at the last link.** The evaluator's own
staleness is detectable from `max(fetched_at)` — data it READS, not a process it
depends on. But **if the evaluator itself dies, nothing reports.** That needs a
dead-man on infrastructure we do not own and **we do not have one.** The spec
states the last link is unwatched rather than claiming the chain is closed.

Neither instrument is built. Both are design-only and both need operator sign-off
(a new production monitor, and a threshold that requires a prod measurement).

## A defect in WAVE_STANDARD rule 2 itself [M, D]

Rule 2 verbatim: *"Fills are not decisions: anything fill-dependent scores under
the pessimistic rule with the measured concessions (2.11¢ pregame, 4.70¢
in-game). 46% of intents never filled historically."*

**The stated concern is SELECTION — which decisions became fills. The remedy is
an execution-cost haircut, and it cannot address that.** A per-fill price charge
makes the observed subset look worse by a constant; it does not reweight it
toward the unfilled one. Correcting for "46% never filled" requires saying what
those intents would have done, which needs the unfilled population — not a
per-contract charge on the filled one.

The rule conflates two different problems. Both are real; the remedy fits only
the second.

**The withdrawn arm really is better, and reweighting toward it would be
WRONG** [M, D]. Paired by game on return-on-cost, with `resolved_outcomes`
joined at 100% coverage and validated at agreement 1.0000 against the native
settlements: **withdrawn − filled = +52.206pp [+10.461, +93.952]**, excluding
zero. (A different P&L definition from the +4.761/+10.857 pair, so only the
*difference* is comparable.)

**But the mechanism is arithmetic, not skill.** A resting order fills when the
market comes TO it and fails when the market moves AWAY, so the arms are sorted
by price direction before anything else enters:

    filled     mid move decision → fill        −4.545¢ [−4.199, −4.891]  against
    withdrawn  mid move decision → withdrawal  +3.713¢ [+2.608, +4.818]  in favour

An 8.3¢ swing, and it GROWS with the window (+4.04¢ at ≤30s to +7.62¢ at ≤300s)
— exactly what "the price ran away" predicts.

So the withdrawn arm's advantage exists only in a counterfactual where the order
filled at its limit, and it did not fill *because the price left that limit*.
**You cannot buy at 0.20 once the market is at 0.24.** Reweighting toward the
unfilled population is not a correction for selection — it is the selection bias
with its sign reversed, flattering the strategy exactly where it captured
nothing.

**AND THE DIRECT TEST CONFIRMS IT IN ONE LINE** [M, B]. If a counterparty were
picking us off, the FILLED arm's OUTCOMES would be worse. They are not:

    FILLED     n 1,944   settlement 40.2%   +4.761pp
    WITHDRAWN  n 1,030   settlement 39.6%  +10.878pp
    (this table uses `filled_at.isna()`, n=1,030. D later settled the correct
     predicate as `withdrawn_at.notna()`, n=1,019, +10.857pp — the 11-row
     difference is orders blocked by a position limit before ever being placed.
     The outcome-rate comparison is unaffected; the predicate is named so the
     two figures do not fork.)

**Near-identical outcome rates against a 6pp gap.** Adverse selection shows up in
outcomes; this shows up only in prices — withdrawn limits sat +3.91pp better than
the decision mid against filled +3.00pp. **The arms differ in where the limit
sat, not in what happened.**

And the withdrawn arm was never admissible: zero withdrawn rows carry a
`filled_at`, by construction. Their P&L is *"what if this had filled at its
limit"* — and it did not fill because the price left that limit. **The arm's
advantage is forced by the rule that defines the arm.**

**It is not that *nobody would take* these bets — the price moved before the
trade could happen.** Queue and latency, not a counterparty picking us off. Those
have OPPOSITE remedies: being picked off says quote wider; being too slow says
reach for the fill. The earlier "adverse selection in P&L" reading — which this
file carried — points at the wrong one, and acting on it would have been
expensive.

Rule 2 is unaffected: "46% of intents never filled" is still real and a per-fill
haircut still does not correct it. The point is only that the unfilled arm cannot
be the counterfactual we reweight toward.

This is a defect in a standing rule, not in any file's use of it, and it is the
rule's owner's to settle. Nobody has patched around it.

## Finding 7 — floor and ceiling sit on different leagues [c7]

The floor (−1.634¢) is measured on the pinned export, **WNBA + CFB**. The
ceiling (23.7%) is measured on the book tape, **WNBA only**. The denominators
were reconciled carefully; the *populations* never were.

**Status: unexamined, and cheaply examinable on 09-12 with cadence-matched
strata.** Not "never" — but not tonight, and not naively.

**Power is not the constraint.** The n=118 cost only ~2 market-HOURS of dense
observation; the three-week window is misleading because only 7,100 of 458,732
transitions qualified at gap ≤2s (1.5%), the export being sparse at an 11s
median. 100 markets for two hours would give ~6,600 events.

**Validity is the constraint, and c7's own sweep is the proof.** The registered
statistic is provably sensitive to sampling gap — **15.6% @1s → 22.1% @5s →
25.0% @10s**, because longer gaps admit moved-and-reverted books. The WNBA
ceiling comes off a 200ms-derived tape; CFB runs at 2.46s. **A CFB-vs-WNBA
difference would confound league with cadence, and cadence alone moves this
statistic by ~10 points — larger than most league differences worth caring
about.**

**Fix is a stratum, not a correction:** compare cadence-matched bands, gap in
[1.0s, 2.0s], the only window both tapes can populate. WNBA has 3,556
transitions there. Same sampling geometry, so a residual difference is a league
difference. **Registered** at `docs/math/cross-league-benign-preregistration.md` before any
CFB rate existed: band gap ∈ [1.0s, 2.0s] on BOTH arms, kickoff restriction,
three-way decision rule with an n≥500 floor per arm and a forbidden-forms list.
All three branches checked reachable before writing.

**★ And the registration caught something not discussed: the existing 23.7% is
NOT the WNBA arm of this test.** It is the ≤2s figure. Comparing a
cadence-matched CFB number against an unmatched WNBA number would reintroduce
the exact confound the band removes — and it is the natural error, because
23.7% is the number everyone has in hand. **Both arms are recomputed inside the
band, together.** That is in the forbidden-forms list explicitly.

**And tonight is disqualified for a second reason:** the CFB recorder returned
at 20:43Z, so tonight's tape begins mid-recovery — the same shape as this
morning's finding, where a recorder starting mid-slate delivered fourth
quarters. Restrict to games observed from kickoff or the CFB arm is the endgame
sample again, and that would look like a league difference too.

## Known-bad, unfixed

- **`plays=-1 wp_rows=-1` on every ESPN CFB cycle — a guard that does not
  guard** [M, Debugger]. `espn_cfb_recorder.py:219` ends
  `return session.execute(stmt).rowcount or 0`. `rowcount` is **−1** when the
  driver cannot report an affected-row count, and **`-1 or 0` evaluates to −1**
  because −1 is truthy. The `or 0` was written to normalise None/0 and passes
  the one value it needed to catch straight through. `state_rows` looks sane
  only because `ns = 1` is set by hand rather than from rowcount.
  **The data is fine** — CFB win probability is recording, 8,514 rows / 50
  games, newest 20:56:29Z; plays 8,599 / 50; state 18,920 / 51. So the
  three-way benchmark has its data.
  **But the counter can now never carry a real number**, so "did this cycle
  write anything" is unanswerable from the log — the instrument reads identically
  on a healthy cycle and on one that wrote nothing. Third instance today of a
  status field whose value does not vary with what it reports, after
  `rows_written: 0` and `cycles: 0`. Harmless to the data, useless as a monitor,
  and it would silently defeat any alarm built on it.
  One-line fix available; production file untouched.
  *(Also: `espn_live_win_probability` is the WNBA table; CFB's is
  `espn_cfb_win_probability`. Counting the wrong one returns the WNBA figure and
  reads as "CFB has nothing" for the wrong reason.)*

- `core/live_recorder.py:319` takes liveness from the venue's own `is_live`
  flag. During the 09-05 freeze that flag went false while games played; the
  recorder stopped, reported healthy, and Saturday's late price tape is gone.
  Per hour, 8,667–11,047 rows were rescuable from `period`, which we received
  and discarded.
- `eventState.ended` is never persisted, so the liveness fix cannot be
  validated retroactively — only from deployment forward.
- **A second, independent recorder defect, observed live on a healthy venue
  2026-09-06.** `live_events()` is `now <= start <= now + window` — it covers
  [start−10min, start] and **closes at the SCHEDULED start**. After that a game
  is covered only if the venue has already set `live=True`. So **any delay
  between scheduled and actual kickoff is an unrecorded gap**, and late
  kickoffs are common. Observed: recorder recording at 19:59Z, dropping at
  20:01Z and 20:04Z, with the game genuinely not yet started (ESPN "pre", venue
  `live=false` — both correct; the recorder was the wrong one).
  The comment on `pre_tipoff_minutes` claims the window covers "the minutes
  EITHER SIDE of tip-off"; the code covers only the minutes before. On a 50-game
  Saturday this loses the kickoff transition on every late-starting game — which
  is the window the comment itself calls "worth having".
- **There is no CI.** 1,478 tests run only by hand. Three tests that could not
  fail shipped and passed review; two critical loaders had no test at all.
- **Eight untested sign/money decisions, all in `core/backtest/engine.py`
  lines 424–452**, found by mutation sweep (20 decisions tested, 12 caught
  elsewhere). Every one feeds a published figure: which side each bet takes,
  which price is paid, the edge sign and magnitude, win/loss, the push-line
  boundary, net ROI, and CLV. `test_backtest.py` has 19 tests that DO call
  `run_backtest` — they assert determinism, point-in-time correctness, config
  hashing and record isolation, and **every one of those holds under any sign
  convention.** Good tests, testing something else. Scoped: one file, a
  morning's work.

## Retracted today

- "The point estimate is POSITIVE for the first time in this programme"
  (+0.061¢). It was an equal-weight mean of game means on a superseded 24-game
  tape whose population was **64% phantom fills**. Corrected in
  `docs/math/the-rebate.md`.
- **−2.74¢ cannot be reproduced.** It ran on a laptop mirror retired at the
  2026-08-20 cutover, which had known 49% gaps. Any re-run is a new
  measurement. It is cited in `core/quote/engine.py:21`.

## Waiting on the operator

EIP/credentials incident · public AWS account id (811 commits) · PR #239 ·
trade-stat + touch-depth collection frequency · the symbol-naming gate (needs a
shared-state hook edit) · liveness predicate · NFL league-keyed team map ·
probe capital (resize to p25–p50 depth, ~36–272 contracts, not $278) ·
SSH allowlist for one session ·
the adverse_selection extraction · all merge and push decisions ·
trade-stat write frequency.
