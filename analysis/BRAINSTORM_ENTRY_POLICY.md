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

---

## Round 1 — Quant B (loss map / coupling vantage)

One seed self-killed before posting, recorded so nobody re-mines it:
**pregame maker flow in the 35–65¢ band** dies twice on the wall — the
ANCHOR pregame entry rule is already measured at −2.33% under the
measured 2.11¢ pregame concession (C13/C14), and the venue-vs-sportsbook
gap is measured at median 0.0000 (V23). A pregame candidate must state a
mispricing family that is neither of those two corpses; I don't have one.

### B1 — The winner↔spread triangle (cross-type consistency)

*Falsifiable:* in-game, the winner mid and the spread-ladder-implied
win probability (the −0.5 rung equivalence: P(m>0) is exactly the
winner, integer margins) diverge by more than the executable toll
(both spreads + fees) in ≥N distinct episodes per game persisting ≥5s,
in a consistent lead direction.
*Mechanism:* the venue's market types are quoted by processes that
measurably live and die INDEPENDENTLY (bookless-endgames' within-game
control: winner book 5 two-sided rows in the window where that same
game's spread carried 3,430). Independent processes desynchronize on
state changes; this is venue-internal sync, so F8's feed-lag bound
(wall 5) does not apply — no race against ESPN, only against the
venue's own other book.
*Why the coherence closure does not cover it:* candidate 3's CLOSED
verdict is totals-rungs-only, on a 10-second sampling grid, live rows
only. Cross-TYPE was never measured, spread-rung coherence was
explicitly deferred, and sub-10s episodes are invisible to a 10s grid
by construction. The 200ms pin can see them.
*Forward test:* descriptive episode census on the existing pin first
(count, duration, net edge after tolls — counts before ratios); if
episodes exist at all, a registered forward gate on episode frequency ×
capturable edge, floors in games. Zero model input — this is
arbitrage-shaped, so walls 5 and 6 have no purchase.

### B2 — Rung-update staleness (who is the flow?)

*Falsifiable:* when a totals/spread ladder reprices on a state change,
rung updates propagate non-simultaneously at 200ms resolution: the
last-updated rung's stale price deviates from its already-updated
neighbours' implied value by more than the toll, in ≥X episodes/game,
capturable by crossing the stale rung.
*Mechanism:* the engine-mediated-compensation lesson inverted (wall 3):
OUR fixed 5¢ target manufactured structure; other participants'
mechanical quoting (ladder engines updating rungs in sequence, fixed
refresh grids) manufactures theirs. D measured our shadow fills buying
noise dips with favourable drift — the real version of that harvest, if
it exists, is picking off the mechanically stale rung, being the
adverse selector instead of the adversely selected (wall 1, other
side).
*Distinct from B1:* B1 is level-inconsistency across types; B2 is
update-LAG within one ladder, temporal, attribution-flavoured (whose
quotes are stale — the same census tells us what the flow structure
is even if the edge doesn't clear the toll).
*Forward test:* update-propagation census on the 200ms pin (latency
histogram between neighbouring-rung updates on the same state change);
then a registered crossing gate conditional on measured lag > toll.
Wall 2 discipline: this is a crossing idea and may not assume the
crossing arms' verdict — it registers only if the census shows lag
episodes whose captured edge would clear spread + 0.06·p(1−p)
independently.

### B3 — Where is the MARKET miscalibrated? (model-free state calibration)

*Falsifiable:* the venue mid, bucketed by a PRE-DECLARED small family
of state cells (period × band × market type — pinned before looking),
is miscalibrated against realized outcomes by ≥X¢ with a game-clustered
CI excluding zero, in some cell, on data the cell choice never saw.
*Mechanism:* every model-side candidate died because OUR beliefs were
worse than the mid (walls 5, 6). The untested direction is the mid
itself: calibration of the market against realized frequencies, no
model anywhere. Wall 3's anchoring trap is structurally avoided —
comparing a price to the realized frequency OF ITS OWN TRADES conditions
on exactly what the price conditions on. C's track showed our FV loses
the disagreement; nobody has yet asked where the mid loses to reality.
*Discipline:* this is a fishing licence if the cell family is not
pinned first — the pre-declared family and the multiplicity bill print
in the artifact before any cell is read (loss-map rules). WNBA pin is
in-sample generator only; the NBA launch (V29: identical structure) is
the forward cohort, and C's atlas is the natural cell-family source.
*Forward test:* cells pinned from WNBA + atlas reasoning; scored on
forward NBA games only; floors in games per cell.

### R2 opening move (the seed invited attack): the freshness candidate

The research agent's #1 (disagreement freshness) has a survivorship
confound the tape cannot escape: OUR withdrawal rule deletes stale
disagreements (the engine pulls when edge dies — the autopsy), so
"persistent edge" on this tape means "edge the engine kept believing",
a survivor-biased population. And its own text notes fresh
disagreements are the never-reachable third — so as an ENTRY policy it
is a crossing policy in disguise, and per wall 2 it may not assume the
crossing arms' answer. It needs (a) an edge-age definition robust to
our own withdrawals, (b) explicit sequencing behind the crossing
verdict. Not dead — but not registrable before those two.

*(B posts; attacks welcome. No number above was computed for this post —
candidates only, in wave-standard language.)*

### R2 outcome on B2 — C's attack ACCEPTED; B2 folds into B1

C's attack (latency): the harvest races the venue's own ladder engine
with a measured ~260ms average detection (158–430ms; write-latency.md,
numbers verified) + 36ms warm RTT + an UNMEASURABLE venue queue — and
the 200ms pin cannot even see sub-poll propagation (ordering two rung
updates needs them in different polls, so the observable population is
the ≳400ms tail; the histogram is censored exactly where software-loop
lags live). All three of C's demands are accepted and carried:
the censoring statement prints in the census; the capturability line is
T_detect + T_order + venue-unknown, never the toll alone; long-lag
episodes get a temporal-clustering check (venue congestion plausibly
slows OUR order exactly when it slows their engine — marginal captures
select against us).

One coincidence worth keeping from the wreck: **the pin's censoring
boundary (~400ms) approximately EQUALS the capturability bar (~300ms +
venue-unknown)** — the census cannot see what the strategy could not
reach anyway. So the observable tail ≈ the actionable tail, and the
folded census is cleanly interpretable rather than fatally biased,
missing only spectator-sport episodes.

**Disposition: B2 is DEMOTED from entry-policy candidate to the
attribution half of B1's instrument.** One census, two outputs: the
within-type update-lag baseline (attribution: what the venue's quoting
structure looks like) and the cross-type desync episodes (B1's
entry-policy claim, which plausibly persists for seconds — a race our
latency can actually run). B1's spec inherits C's three demands.
Narrowed to what the instruments can honestly measure, per the wall's
own standard.

### R2 — B attacks C1 and C2 (the execution bracket)

**C2 (lead-underrating band): the edge is bracketed below the measured
toll on BOTH execution paths, at WNBA-measured numbers.** The claimed
size is 2–4 probability points. My loss map measured in-game winner/
spread books in exactly the mid-game band at **4–7¢ median spread**
(spread_px on 1,944 fills), and the measured maker concession is
**4.70¢** [4.41, 5.00] per filled quote. So: as maker, concession ≥
edge; as taker, spread + 0.06·p(1−p) fee > edge. Even a FULLY REAL
tilt is uncapturable at these numbers — the candidate is economically
alive only if NBA books in the band are materially tighter than WNBA's,
which is unknowable until listing. Demand: the registration carries a
PRE-COMMITTED minimum-book condition (e.g., median band spread ≤ 2¢
measured on the NBA tape before the gate arms), or the forward test
will "confirm" a mispricing nobody can trade — a calibration finding
wearing an entry policy's clothes. (The descriptive calibration pass
is untouched by this attack and worth running regardless — as a
finding. Note E[y − mid | cell] is anchoring-clean per wall 3: the mid
conditions on whatever it wants, cell membership is public.)

**C1 (bimodal endgame): both mispriced legs live in measured deserts.**
The OT-zone over rungs price in the <20¢ band — V1 measured ~$5 at the
touch there, and V3 says cheap contracts resolve their moves less
often; the just-above-regulation side prices >90¢ where wall 7's book
death is worst. The census must therefore price the FILLS, not just
the gaps: per episode, report the mispriced rung's price band, V1-band
depth, and whether a two-sided book survived to settlement — else the
candidate inherits the old model's exact grave (edge concentrated
where nothing could fill, V1–V3). Not dead: the bimodal mechanism is
the most physically-grounded thing in this file; but its tradable form
must be shown to exist on the tape, not assumed from the distribution.
