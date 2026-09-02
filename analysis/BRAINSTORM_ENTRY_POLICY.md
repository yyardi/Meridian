# Joint brainstorm — entry policy (2026-09-02)

**Convened on the operator's directive: when a strategy dies, the team thinks
TOGETHER and builds the next idea — no giving up without basis, no solo dead
ends.** This page is the shared design-space map every participant works from.
Ideas land as PRs against this file; attacks land as review comments or
follow-up commits. The research agent synthesizes and ranks; survivors get
registrations.

## The question

**The resting-maker book as constituted loses. Exit hygiene does not rescue it.
What ENTRY policy could produce positive expectancy on this venue?**

## The wall — measured facts every idea must respect (cite or refute, never ignore)

1. **Resting is adversely selected by construction.** You are filled exactly
   when the market comes to disagree with you; the never-reachable 32.2% OF
   UNFILLED intents (of 1,019 — not of all intents) was worth +33¢/ct at the
   resting price you never got (#126).
2. **Crossing pays spread + fee**: 4–7¢ early / 8–10¢ late medians, plus
   0.06·p(1−p). The registered crossing arms test whether selective crossing
   clears that toll — accruing now, verdict unknown. Ideas may not assume its
   answer.
3. **Detectable risk is compensated in this book** — but ENGINE-mediated (the
   5¢ target over cheap costs), not a market law. Any idea that changes exits
   must re-net (#157/#158).
4. **The model's in-game alpha is +3.47¢/ct optimistic, and late-state exit
   risk alone (3.5–3.8¢/ct) exceeds it. Late entries are uneconomic at measured concessions** — the 4.70¢ figure; both sides of the inequality are measured, and the concession side carries its name. (#154)
5. **TWO deaths by the market's sword** — in-game reversion (#18) and ESPN win
   probability (F9). A third apparent instance (ride-risk compensation) was
   **WITHDRAWN as substantially ENGINE-mediated** (#157/#158); it rejoins only
   if re-established exit-invariantly. **Do not count it.** An idea whose mechanism is "the market is slow to X" needs a
   reason THIS venue is slow that survived F8's feed-lag bound (price move
   100% complete by our feed time — event-reaction is structurally dead).
6. **The FV is calibrated in the bulk and uninformative where it disagrees with
   the mid** (Track C). Where the model would trade, the market has been right.
7. **Endgame books die**: 9/22 bookless endgames; winner books die in decided
   games, ladders die independently ~1 in 10. No safe-harbour market type.
8. **Unfilled intents are two DIFFERENT REGIMES, not a trend: 46% on the
   pregame-maker shadow record (C13 era, ANCHOR entries); 34.6% on the in-game
   engine tape.** Computing an "improvement" between them is a regime
   confusion, not a measurement.
9. **Boring list (do not re-mine):** entry spread, side, cheap contracts,
   mid-margin buckets, if-ridden counterfactual, v1-only positives, book-state
   flags at intent (+0.000 AUC), edge_net ordering (dead in every big cell).

## Directions deliberately NOT yet tried (seed list — attack or extend)

- **Pregame / near-tip entries.** All measurement is in-game. The 35–65¢
  pregame band has depth (V1) and no F8 lag problem, and the model's pregame
  anchor is the venue's own line. Is there any pregame mispricing family left
  untested? (#16/#17 killed two — but both were in-game reversion shapes.)
- **Cross-market structure within a game — NARROWED 2026-09-02**:
  totals-adjacent-rung monotonicity is now MEASURED AND DEAD (1 sub-cent 20s
  episode / 34 games / 4.69M rows net of fees — candidate 3's closure below;
  do not re-derive). Still unmeasured: **CROSS-TYPE coherence** — winner vs
  spread vs total triplets, which share state through different books — and
  spread-rung monotonicity. The surviving question is the cross-type one.
- **Liquidity provision where WE are the informed side**: the one region where
  C found the FV informative is... nowhere yet. But C's NBA atlas may find
  state pockets where empirical frequencies diverge from any smooth curve
  (foul-game, OT tails) — the market must price those with SOME curve.
- **Event-window entries the venue must reprice slowly**: halftime (books
  reopen), starting-lineup news, injury scratches — pregame or break windows
  where F8's in-play bound does not apply.
- **The other side of adverse selection: BE the resting flow that picks off
  stale quotes.** D measured that our modelled fills buy dips of mid noise
  (−1.8 to −2.3¢ favourable drift). Whose quotes are we hitting, and is there
  a family where resting is selection FOR us?
- **NBA-specific structure at launch**: opening weeks of a new listing are the
  most mispriced any book will ever be (no history, thin flow). What entry
  discipline exploits early-season NBA specifically, and what data must be
  recorded from day one to test it later?

## Protocol

Round 1 (divergent): every agent posts ≥3 candidates from their own vantage —
one falsifiable sentence + mechanism + what forward data tests it. Building on
the seed list or demolishing it both count.
Round 2 (adversarial): every agent attacks at least one OTHER agent's
candidate in writing, citing the wall. An idea nobody attacked is not ready.
Round 3: research agent ranks by mechanism plausibility × testability;
survivors get registrations before anything computes.

**No idea dies by assumption. It dies by citation of the wall, or it gets a
forward test.**

**Round-3 tiebreaker (enforceable):** *An idea that fits every fact on the wall
was probably reverse-engineered from it. To rank, each surviving candidate must
name ONE testable prediction about something NOT YET MEASURED — its novel
exposure — and that prediction enters its registration as a stated check. An
idea with no novel exposure is a summary of the wall wearing a strategy's
clothes.*

---

## Round 3 seed — the research agent's ranked queue (2026-09-02)

Filed before A–D's round-1 posts so it can be attacked alongside them; being
first in does not privilege it.

1. **Disagreement freshness.** *Intents whose edge first appeared within the
   last X seconds outperform intents whose edge has persisted longer, per-$,
   game-clustered.* Mechanism: F8 — the market reprices state in seconds, so a
   PERSISTENT disagreement is more likely our error than theirs; the
   never-reachable third were, by construction, fresh disagreements the market
   chased away from us. Test: edge-age from the decision tape (descriptive
   first), then a crossing-arms companion keyed to an age threshold pinned
   pre-read.
2. **Venue ladder-shape audit vs fitted σ — the NBA day-one candidate.**
   *Newly-listed NBA totals ladders are shaped with a σ deviating from the
   fitted walk-forward σ by more than the WNBA board's measured dispersion
   (±1.4), in a persistent direction.* Mechanism: the venue seeds ladders with
   near-constant σ (F5, 362 ladders); a NEW board is where seeding errors
   live, and we hold validated NBA constants the venue must match **or
   mispricing exists structurally — no game forecast required.** Test: pregame
   listings from day one; F5's machinery with R1b/R3b constants; zero trading
   needed. **The highest-value use of the first two NBA weeks.**
3. **Intra-venue ladder coherence — CLOSED, negative** (see below).
4. **Price-band restriction.** *Under identical edge buckets, 35–65¢ entries
   outperform tail entries per-$.* Confound named in advance: the
   engine-mediated compensation means the naive cut is structured by the
   profit target — the descriptive pass must hold exit policy fixed and
   bucket by edge.
5–6. **The registered pair** (crossing arms; Q4∪blowout mask) — accruing.
7. **Atlas-dependent NBA masks** — forms follow C's atlas within a day of its
   landing.

### Candidate 3: CLOSED — the venue's ladders are coherent

Across **4,693,964 two-sided totals rows / 34 events / 306 rungs / 23,743
ten-second grid instants**: persistent executable violations found — **1**
(ind-dal 08-20, rungs 174.5/177.5, ~20s, max net edge **0.7¢** after both
taker fees). One sub-cent episode per 34 games is unharvestable before F8's
racing bar even applies. **Intra-venue structure arbitrage is dead as an
entry-policy candidate. No registration warranted.**

Scope printed with the negative: the pin is live rows only, so **pregame**
coherence is unassessed; **spread-rung** coherence deferred for team-frame
subtleties — stated, not skipped. Reproduction: `survey/ladder_coherence.py`
against the 19:52:02Z tick pin.

**Salvage:** coherence is a measured invariant of the venue's engine — the
same script becomes a standing venue-health check, folded into the NBA
day-one quality survey per the launch policy.
