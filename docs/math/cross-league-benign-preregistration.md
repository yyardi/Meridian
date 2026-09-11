# Does the benign rate transport across leagues? — pre-registration

**Registered 2026-09-06, before ANY CFB benign rate exists anywhere.** That is
the whole point of writing it tonight rather than Saturday morning: the band
below is chosen on sampling geometry, not on an outcome. Once a CFB number
exists in any session, choosing this band would be a free parameter on the
figure that decides whether the market-making close needs a population caveat —
and registration after the fact is not registration.

## The question, and why it is open

Finding 7 of the market-making-close audit: **the floor and the ceiling sit on
different league mixes.** The floor (r\* ≥ 57.8%) comes from the pinned shadow
fills, **WNBA + CFB**. The ceiling (23.7%) comes from the book tape, **WNBA
only, 2026-07-31..08-20**. The close reconciles the two *denominators* carefully
and says nothing about the *populations*. Probably harmless; unexamined.

**If CFB's benign rate differs materially from WNBA's, the floor-versus-ceiling
comparison is mixing populations and the close needs a caveat. If it does not,
finding 7 resolves and the close is stronger for having been checked.**

## ★ The registered band: consecutive-snapshot gap ∈ [1.0s, 2.0s], BOTH arms

**Why a band at all — the statistic is provably sensitive to sampling gap.** My
own sweep on the WNBA tape: **15.6% @1s → 22.1% @5s → 25.0% @10s**, because
longer gaps admit books that moved and reverted unobserved. The WNBA ceiling is
derived from a **200ms** tape; the CFB recorder returned 2026-09-06 20:43Z at a
**2.46s mean gap**. **A naive comparison would confound league with cadence by
~10 points — larger than any league difference worth caring about**, and would
produce a number that looks like an answer to finding 7 and is not one.

**Why [1.0s, 2.0s] specifically — it is the only window both tapes populate.**
WNBA's dense bursts reach well below it (1,912 transitions ≤0.5s) and CFB's mean
sits above it, so 1–2s is the overlap. WNBA supplies **3,556 transitions** there
(7,100 at ≤2s minus 3,544 at ≤1s). CFB at a 2.46s mean clears ≤2s on roughly 56%
of transitions and will populate 1–2s heavily.

**Both arms are recomputed inside the band. The existing 23.7% is the ≤2s
figure and is NOT the WNBA arm of this test** — comparing a matched CFB number
against an unmatched WNBA number would reintroduce the confound this band exists
to remove. Compute both together.

## ★ The kickoff restriction

**CFB games must be observed from kickoff.** Tonight's tape begins mid-recovery
at 20:43Z. Earlier today the ESPN recorder started mid-slate and delivered games
already in periods 2–4 — I read that as "static games" until I checked the
period and score columns and found it was *fourth quarters*, a property of the
observation window rather than of the games. **The same artefact here would
present as a league difference.** A game enters the CFB arm only if its first
observed snapshot precedes its kickoff.

## Filters — identical to `benign-fill-predeclaration.md` in every other respect

600s stream-running guard (the `is_live` flag never clears, so dead streams
otherwise read as quoted-and-still); benign = **ask stays put** (the ask-held
column, both bid outcomes); freeze excluded at **17:38Z**; per-market
consecutive snapshots. Any divergence measures a different quantity.

## Decision rule, registered before computing

Let W and C be the matched-band benign shares with game-clustered intervals.

| outcome | reading |
|---|---|
| **C's interval overlaps W's** | **Transport holds. Finding 7 resolves**; the close stands unqualified. |
| **Disjoint, C's point < 40.6%** | **Close holds, population caveat REQUIRED** — the ceiling is league-specific and must be stated per league wherever it is quoted. |
| **C's interval lower bound > 40.6%** | **Close does not hold for CFB.** 40.6% is r\* at the FULL spread — the most optimistic earnings a passive maker can structurally reach. Restate the close per league. |

**Minimum n: 500 matched-band transitions per arm.** Below that the arm is
reported as UNDERPOWERED and no reading is taken — the interval, not the point,
decides every row above.

**Forbidden forms — any of these voids the result rather than qualifying it:**
widening or moving the band after seeing either rate; comparing a matched arm
against the unmatched 23.7%; admitting CFB games not observed from kickoff;
pooling the two leagues into one figure (that is the confound, not the answer).

## Status

**Finding 7 stands as: unexamined, cheaply examinable on 2026-09-12 with
cadence-matched strata.** Tonight's tape is worth collecting and worth a
coverage check. **It is not worth a rate.**
