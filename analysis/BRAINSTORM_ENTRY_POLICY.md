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


---

## Round 1 — Quant D (execution microstructure), 2026-09-02

Three candidates, one instrument note, one engagement with the round-3 seed
queue. Every number cited below is in-sample and inherits the fill-model
caveats of its source doc.

### D1 — Rest where nobody is informed: the pregame concession window

*Real resting-order concession, measured on the quote engine's own fills, is
≤ 0 in dead pregame windows (≥ N hours before tip, N pinned before reading),
and the measured +4.70¢ in-game adverse concession is concentrated in the
in-play/near-tip window.*

**Mechanism.** Adverse selection needs informed aggressors; informed
aggressors need information arrival. F8's 36-second feed-lag bound (wall #5)
is an IN-PLAY mechanism — during a dead pregame afternoon there is no play to
be 36 seconds behind. The measured concession numbers we quote everywhere
(2.11¢ pregame, 4.70¢ in-game) are already a 2× window split in this
direction; the candidate says the gradient continues inside pregame, and
somewhere out on it the maker side of the book stops paying and starts
collecting. If true, "be the resting flow" (seed 5) is a WINDOW property, not
a flow-family property — and it composes with the pregame 35–65¢ depth fact
(wall, seed 1) rather than fighting the in-play wall.

**Forward test.** No new plumbing: the quote shadow engine accrues real
resting fills with `mid_at_quote`/`mid_at_fill` already. Pin a window
partition (hours-to-tip buckets) before the next read; score per-window
concession, game-clustered, floors per regime as already registered. The
in-tape descriptive first pass (my post-fill drift by window on the decision
tape) is cheap but carries the fill-rule artifact — the quote engine's real
fills are the evidence-grade instrument.

**Wall respected:** #2 not assumed (this is maker-side, no crossing); #5
respected (mechanism is absence-of-information, not "venue is slow"); #4
untouched (pregame, not late).

### D2 — The halftime re-anchor

*Across the halftime boundary, ladders reopen at prices that then drift
systematically (> spread + fee) toward the live-FV computed from first-half
state — the reopen is anchored to a stale pregame/early shape, and the drift
is harvestable in a window where F8 does not bind.*

**Mechanism.** Halftime is the one in-game moment where repricing is
wholesale re-anchoring rather than event reaction: no clock is running,
nothing races our 36-second feed. The venue seeds ladders with near-constant
σ (F5, 362 ladders) — a seeding-error family already measured once. If the
halftime reopen re-seeds from a stale anchor, the first minutes of Q3 carry a
predictable drift toward state-updated fair value, and a HALFTIME-WINDOW
entry (rest or cross, priced either way) collects it without touching the
late-game exit hazard (wall #4, #7 — halftime books are the healthiest
in-game books we hold).

**Forward test.** Descriptive first, from the pin we already hold: 34 games
× (last two-sided Q2 mid, first two-sided Q3 mid, mid at Q3+5m) per market,
vs halftime-state FV — one script, no new data. If the drift exists and
exceeds spread+fee in a direction knowable AT the reopen, register a
halftime-window companion with the entry rule pinned. If the reopen is
already fully state-priced, the candidate dies by measurement and seed 4
loses its most testable member.

**Wall respected:** #5's F8 clause explicitly does not bind (break window);
#6 is the risk — if the FV is uninformative where it disagrees, the drift
must be measured toward *state-updated market self-consistency* (the venue's
own Q3 pricing minutes later), not toward our FV alone; the descriptive pass
scores BOTH targets so the candidate can die honestly.

### D3 — Momentum-toward-FV as the crossing discriminator

*Among forward intents, those where the mid had moved toward the model's
fair value over the prior T seconds (T pinned before reading) outperform
those where it had not, scored at the far touch per the registered formula —
direction of convergence, not level of disagreement, is what selects the
never-reachable winners.*

**Mechanism.** The withdrawal autopsy split the unfilled: the market coming
back to our price was worth ~0; the market running away (toward our FV) was
worth +33¢/ct we never got. Running away toward our number is the market
AGREEING LATE — we were early, not wrong. A static level-disagreement, per
wall #6, is the regime where the market has been right. So the tradable
signal is the derivative (is the market converging to us NOW), not the level
(how far it is from us) — and crossing is the only execution that captures a
convergence already in motion (resting guarantees we only catch the ones
that come back, worth ~0, wall #1).

**Forward test.** This does NOT assume the crossing gate's answer (wall #2):
it is the natural NEXT companion — one input, the pre-intent drift-toward-FV
sign/threshold from the tick tape, keyed off the parent arm (b) exactly as
the state mask is. Descriptive first on the forward cohort once the parent
resolves; registration only through c7.

**Relation to the round-3 seed #1 (disagreement freshness):** same family,
different derivative — freshness asks WHEN the edge appeared; D3 asks which
way the market is MOVING now. They disagree on a concrete population: an edge
that appeared long ago while the mid converges steadily toward FV is stale
per #1 and prime per D3. Propose measuring both on the same forward
descriptive pass so the family produces ONE registered discriminator, not
two correlated gates.

### Instrument note — the favourable drift is not yet evidence of anything

Seed 5 quotes my −1.8 to −2.3¢ favourable post-fill drift. Before anyone
builds on it: that number is measured under the mid-cross fill rule, which
declares fills at local extremes of mid noise — reversion after a
locally-extreme trigger is partly MECHANICAL, and the same tape's real
resting orders measured +4.70¢ ADVERSE. The in-tape discriminator, if wanted
(cheap, descriptive): decompose modelled fills by which side of the book
moved to trigger the mid-cross (far side tightening toward us = quote-refresh
flavour; near side stepping through = trade-through flavour) and compare
post-fill drift between the two. Until that or the D1 window split says
otherwise, the favourable drift should be cited as a FILL-MODEL ARTIFACT,
never as measured counterparty behaviour.

### Engagement with the round-3 queue

**Queue #4 (price-band restriction) — attack, citing the wall.** The wall's
own boring list (#9) retires edge_net ordering and cheap contracts; my
decomposition's band table shows per-band P&L positive in EVERY band under
the optimistic rule with alpha and concessions scaling together — no band
flips sign, nothing concentrates. The 35–65¢ band's virtue is DEPTH (it can
absorb size), which is a sizing input, not an entry filter: restricting
entries to it forfeits bands that are currently additive in-sample without
buying any measured improvement. Unless the confound-controlled cut named in
the queue shows a per-$ gradient the raw table hides, this candidate should
rank below the registered pair, and its registrable form is "size scales
with band depth", not "enter only in band".

**Queue #1 (freshness) — merge proposal, not attack:** see D3. One
descriptive pass, both features, one discriminator survives.

*— Quant D. No in-sample result justifies capital. The forward test is the
evidence.*

---

## Round 1 — THE OPERATOR (relayed by the manager, checked against the tape)

The operator's direct observations, each verified before filing. **They watch
the dashboard live; treat these as a participant's candidates, not noise.**

**O1 — "It acts very odd pregame, taking so many positions."** CHECKED, and the
tape sharpens it: PULSE has **zero pregame entries** (phase=in_play on all
2,974) — but it **front-loads Q1 massively: 829 of 1,944 filled entries (43%)
land in Q1**, versus 229 in Q4. What the operator sees at tip is a flood.
*Open question for the room: is Q1 the model's best window (pregame anchor
still fresh, F8 lag least harmful) or its most overconfident (least in-game
information, the anchor doing all the work)? Nobody has cut per-$ by period
with exit policy held fixed.*

**O2 — "Pulse really likes the spread bets."** CHECKED, half-right and the
right half is interesting: intents are **56.7% totals / 37.5% spreads / 5.9%
winner** — but **spreads earn the most per dollar (+3.8%/$ vs totals +2.1%,
winner −1.1%, maker arm)**. The model *prefers* totals; it *performs* on
spreads. If that gap survives clustering and an edge-bucket control, the mix is
mis-allocated.

**O3 — "Don't hold losing positions too long; take the small loss."** CHECKED
and the tape agrees with the operator, monotonically:

```
losing trips by holding time (dollar-weighted per-$):
  <2m    -18.3%     10-30m  -34.6%
  2-10m  -19.9%     >30m    -38.9%
winning trips: median hold 1.0 min · losing trips: median hold 5.2 min
```

Winners resolve in a minute; losers are held five times longer and the longer
held, the worse. **Confound named before anyone runs at it:** holding time is
not chosen — it is what happens when the exit doesn't fill, so "held longer"
partly MEANS "price moved away." The testable form is a **loss-cap /
time-stop counterfactual on the tick pin**: exit at mid when down k¢ for m
minutes, scored net of the crossing toll, k and m pinned pre-read. This is
adjacent to the registered repricing arm but is a distinct policy (cap vs
re-target) and would need its own registration.

**O4 — the frequency requirement, now a standing term:** *"don't find niche
garbage that works 1 in every 19 games."* **Every surviving candidate states
its expected FIRING RATE (opportunities per game) beside its novel exposure.**
A true edge that fires once a month cannot be distinguished from luck inside a
season, and the operator has said plainly it is not worth their capital.

---

## Candidate 1 (disagreement freshness): CLOSED — descriptive negative, mechanism refuted

Research agent's pass on the pins (`survey/edge_freshness.py`; 2,974 entries /
34 games; buckets declared pre-compute; **B's round-2 attack on this candidate
is hereby vindicated before round 2 formally closed**):

```
age <=5s    2,272 (76%)  fill 67.5%   maker -0.044 [-0.133,+0.045]   pess -0.384
5-30s         148        fill 70.9%         -0.066                   pess -0.266
30-120s       152        fill 59.2%         +0.045 [-0.001,+0.091]   pess -0.180
>120s         402        fill 53.7%         +0.041 [+0.004,+0.078]   pess -0.199
```

**Three readings, all against the candidate:**
1. **The mechanism's prediction is INVERTED.** Fresh edges fill MORE and do
   WORSE — the opposite of "good ideas run away." The running-away in #126
   operates at the **price** level (the limit never reached), not the **time**
   level at engine cadence. Freshness is not the lever.
2. **The stale-positive is substantially game composition** — the shuffle
   control earned its keep: within-game age permutation still reads +0.029
   [−0.014, +0.071] against the real +0.041, so most of the apparent stale
   edge is *which games* contribute stale entries. Entry-level residue ~+0.01
   and noise.
3. **Pessimistic fills are negative in every bucket** (−0.18 to −0.38).

**Composition caveat, printed so nobody misreads:** 76% of entries are ≤5s
because the engine enters on first cycle **by design** — the stale buckets are
re-entries and previously-blocked states, a selected subset. **The buckets are
not exchangeable populations**, which is exactly what the shuffle control
formalized.

First cross-agent artifact reuse on the record: A's ledger consumed as the
substrate, cleanly. **The wall gains two same-day corpses with mechanisms
named (candidates 1 and 3). That is what walls are for.**
