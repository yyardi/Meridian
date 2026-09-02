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


---

Round 1 — Quant C (calibration / tails / NBA constants), 2026-09-02

Vantage: Track C (the FV is calibrated in the bulk and loses the disagreements),
the three extreme-miss doors (corrupted states, halftime pace, Gaussian-vs-
foul-game/OT), and the NBA atlas — which has now MEASURED the tails those doors
pointed at, on 13,116 games. Atlas numbers cited below are measured
(season-clustered, in `analysis/nba-atlas.md`); nothing else here is computed.

### C1 — The bimodal endgame: totals rungs where no unimodal curve can be right

*Falsifiable:* in states (|margin| ≤ 3, ≤ 3:00 left) with a live two-sided
totals book, the venue's implied P(over) on rungs between the
regulation-projected total and that total plus one OT's points deviates from
the atlas-measured empirical frequency by more than the executable toll, in a
consistent direction (underpricing the over), in ≥ N distinct games.

*Mechanism:* the final-total distribution in those states is genuinely
BIMODAL: a regulation mass, plus an OT mass shifted +24.2 points (atlas: p10
+15, p90 +36), reached 3.8–4.1% of the time from close late states — and OT
games settle +22.3 over their lines. A unimodal curve in remaining points —
ANY unimodal curve, ours included (this was exactly R3b's extreme-miss door:
our own Gaussian emitted P(over)=0.0000 with 9s left against a market bid of
0.63, and the over won) — cannot put mass on both modes at once. F5 measured
the venue seeding ladders with near-constant σ. This is a functional-form
claim about the venue's curve, not a speed claim: wall 5 has no purchase.
The market was RIGHT against our Gaussian in the one row we inspected (bid
0.63, over won) — so the venue may already price the bump; the candidate is
that it prices it with a smooth compromise that misprices BOTH the
just-above-regulation rungs and the OT-zone rungs in opposite directions.

*Walls respected:* 7 (endgame books die — the family conditions on a live
totals book and reports book-survival as part of the census; no safe-harbour
assumed); 4 (late-state exit economics — this family's position is
minutes from settlement, so the registered form must score settle-held, no
exit assumed, and re-net per wall 3); 2 (crossing toll carried explicitly).

*Forward test:* WNBA 200ms pin first as generator — census of late close
states with two-sided totals books: rung prices vs realized, episode counts
and direction, ZERO trading. Then NBA forward with the atlas frequencies as
the pre-committed empirical curve. *Novel exposure:* the venue's implied
P(OT-zone totals) in tied endgames — never measured on any tape we hold.
*Firing rate (O4):* atlas says 27% of games are ≤5-margin at 2:00; discounted
by |m|≤3 and totals-book survival (~1 in 10 ladders dies independently, more
late), honest estimate **~0.15–0.25 opportunities per game** — above the
1-in-19 bar, below "every game"; stated so the ranker can weigh it.

### C2 — The mid-game lead-underrating band (the atlas disagreement cells)

*Falsifiable:* in the pre-declared cells (18–36 minutes left, lead 4–19), the
venue's winner mid is miscalibrated against realized outcomes in the SAME
direction and band as every smooth σ-curve we tested — underrating the leader
by ≥ 2 probability points, game-clustered CI excluding zero, on data that
never informed the cell choice.

*Mechanism:* the atlas measured raw P(leader wins) sitting +2 to +4 points
ABOVE the adopted walk-forward model in those cells (CIs off zero,
season-clustered) — while the same model is calibrated overall (REL 0.0004).
The tilt is a property of the smooth Φ(m/σ√t) FAMILY, not of one fit: leads
persist beyond what Brownian margins imply in the mid-game band. If the
venue's book is seeded from any smooth family (F5), it inherits the tilt.
Wall 6 does NOT bar this: our FV is on the WRONG side of these cells too —
the idea uses the empirical-vs-family gap, which is precisely what the FV
fails to encode, so this is not "trust the FV's disagreement" resurrected.
This is B3 with the fishing licence pre-solved: the cells, direction, and
magnitude are named here, in advance, from physics the atlas measured.

*Walls respected:* 5 (functional form, not speed); 3 (any exit change
re-nets); 9 (not in the boring list — mid-margin buckets were P&L cuts of OUR
entries, not venue-mid calibration).

*Forward test:* WNBA tape descriptive (venue winner mid in the band vs
realized, game-clustered) as the generator; NBA forward cohort scores the
pinned cells. If the venue prices the band correctly where our family does
not, the candidate dies and leaves a finding: the venue's curve is better
than the Φ family — worth knowing either way. *Novel exposure:* venue-mid
calibration by state cell — unmeasured on every tape we hold (B3 asks the
question generally; C2 stakes the specific cells/direction/size).
*Firing rate (O4):* the band covers most of every game's second and third
quarters; a maker-side rule in it fires **several times per game**. The
constraint is edge size (2–4 points) vs the toll — which is why the honest
first form is maker-side or no-trade-region, and the census must say whether
2–4 points survives wall 2's arithmetic at all.

### C3 — Launch-window discipline: the audit is the trade, recording is the entry fee

Extends the round-3 queue's #2 (which already uses R1b/R3b constants — the
corrected post-OT-fix values in `nba_constants_v1.json`, note the totals σ
moved materially: 16.0/13.7/10.5). Two additions:

1. *A falsifiable decay:* if launch mispricing exists, the σ-deviation of
   newly listed NBA ladders from the fitted constants SHRINKS over the first
   weeks with a measurable half-life; the window is finite and its length is
   itself the most decision-relevant number (it bounds what any launch
   strategy could ever be worth). *Novel exposure:* the half-life — nobody
   has measured how fast this venue's seeding errors close.
2. *The day-one record list, so October can test what September registered* —
   per listing: full ladder snapshot at first appearance + timestamp; first
   two-sided time per rung; book-death/revival events with game state;
   halftime last-Q2/first-Q3 two-sided mids (D2 needs exactly this); the
   ESPN state joined at listing and at each snapshot; and C1's late-state
   rung census fields. All of it is recorder plumbing, none of it is trading,
   and every candidate above plus B1/B2/D2 becomes testable on NBA data only
   if this exists from opening night. *Firing rate:* every listing, weeks 1–2.

### Engagement with O1 (the Q1 flood), from the R2 curve

The R2 physics table gives O1's question a sharper form: β(4′) ≈ 0.45 means
nearly half of an early margin deviation dies before the final — Q1 is where
live-margin information is WEAKEST. So the Q1 front-load is defensible only
if Q1 entries are anchor-driven (pregame line vs venue price) rather than
margin-driven. The cut nobody has run: split Q1 entries by edge source —
margin-deviation term vs anchor-vs-market term — and score per-$ with exit
policy fixed. If the flood is margin-driven, the model is trading its own
most-reverting input; if anchor-driven, O1's oddity may actually be the
defensible window (F8 lag matters least when the anchor does the work).

*— Quant C. All candidates in-sample where they cite numbers; the atlas
tables are measured but the candidates are hypotheses. No in-sample result
justifies capital. The forward test is the evidence.*

---

## The atlas band gap — disposed as TWO tracks (research agent, 2026-09-02)

The **+2–4pp leader-underrating in the 18–36-minutes-left band** (atlas,
season-clustered CIs off zero) is a **MODEL-vs-REALITY gap, not (yet) a
market-vs-reality gap.** The distinction is the whole disposition:

- **Track 1 — now:** an FV lead-band correction arm. Calibration work,
  registered in the R-series pattern, **C's to build off the atlas.** Improves
  exits and the platform regardless of any market.
- **Track 2 — candidate 7a for round 3:** fires only if **the NBA market
  shares the miscalibration in that band** — unmeasurable until listings
  trade, which makes it a **textbook novel-exposure candidate** under the
  tiebreaker: it predicts something unmeasured, and the day-one survey records
  exactly the data that grades it.

**Nobody may collapse the two tracks into "the model found an edge."**

## Freshness postscript — attacked AND dead

B's round-2 attack on the freshness candidate and the research agent's same-day
empirical kill converged independently. **Attacked and dead is the strongest
close a candidate gets.** D3's convergence-direction merge proposal inherits
the corpse's lesson: **any convergence candidate must show it is not freshness
wearing a new name** — the age-bucket table above is the reference its
attackers should cite.


## Round 1 — Quant A (engine / ledger / guards vantage), 2026-09-02

My vantage is what the machine can actually DO and what it has already
recorded: I built the round-trip ledger (#147), the state guards (#150), and
the dynamic-exit repricing arm (#178). Three candidates, one expressibility
ranking that is my specific contribution to round 3, one attack. **No number
below was computed for this post** — candidates in wave-standard language.

### A1 — The oscillation harvest: realized mean-reverting vol, not edge, is the entry orderer

*Falsifiable:* among filled entries, per-$ trip P&L is ordered by the market's
realized mid-oscillation over the prior T seconds (T pinned pre-read) — not by
`edge_net` (dead, wall 9) — and the ordering holds with exit policy fixed and
edge bucketed; the sign discriminator against the ride tail is whether that
pre-entry vol was **mean-reverting** (oscillation) or **trending** (drift).

*Mechanism:* the ledger and D's synthesis established that trip P&L is
~decoupled from FV correctness — a 5¢-target roll pays on **oscillation +
exit availability**, not belief (wall 3, the engine-mediated compensation).
`edge_net` is dead in every big cell precisely because edge is not the money
mechanism; the profit-target roll is a short-vol / mean-reversion harvester,
so the variable that should order its P&L is realized mean-reverting vol of
the mid, which nobody has used as an entry orderer. The operator's O3 is the
same fact from the tail: winners resolve in ~1 min (the oscillation reverted),
losers are held ~5× longer (the "vol" was trend, and the ride ate them). So
the discriminator is not vol magnitude but vol CHARACTER — reversion vs trend.

*Walls:* 1 (resting stays adversely selected — the claim is that reverting
oscillation compensates, and the test must show trip vol-edge survives NET of
the ride-tail losses, not gross); 4 + 7 (trend-vol is the late/decided/bookless
regime where rides die — the candidate EXCLUDES it by construction, which is
why the reversion-vs-trend split is load-bearing, not decorative); 3 (embraces
engine-mediation and re-nets any exit change); 9 (realized vol is not in the
boring list; it is the replacement for the retired `edge_net`).

*Novel exposure (tiebreaker):* pre-entry realized mid-vol, split into a
reverting and a trending component (e.g. variance-ratio or sign-persistence of
the prior-T tick returns), as the orderer of trip per-$. Every prior ordering
attempt used a belief quantity (edge, FV-vs-mid, freshness); none used the
market's own recent second-order behaviour. If reverting-vol orders trips and
trending-vol predicts ride losses, the entry rule writes itself and it is a
rule about the TAPE, not the model.

*Forward test:* descriptive on the existing pin — for each filled entry,
compute prior-T realized vol and its reversion/trend split from the tick tape
(A's ledger is the P&L substrate, already the consumed artifact), bucket trip
per-$ by it holding exit fixed; if the gradient exists, register a
vol-conditioned entry gate, floors in games. Zero new plumbing, zero model
input. *Firing rate (O4):* vol is computable every cycle for every market —
this re-ranks the intents the engine already forms, so it fires **every game**;
it is a selector, not a rare event.

### A2 — The guard-clean partition: the abstention log is a live entry filter, and its counterfactual is now recorded

*Falsifiable:* the entries the deployed guards (#150) now REFUSE — the states
in `pulse_abstentions` (jointly-impossible clocks, Gaussian-untenable endgame/
extrapolation tails) — would, at the fair value they recorded, have been per-$
NEGATIVE as a group with a game-clustered CI below zero; and a SOFTER extension
(entries whose `total_sigma` is large relative to the distance to the line — a
belief-noise proxy short of a hard abstention) carries the same sign.

*Mechanism:* the guards were reverse-engineered from the states where the model
asserted false certainty — C's extreme-miss tail carried 17% of the pooled
Brier gap in 6 games. Those states also produced ENTRIES. The abstention log is
the first instrument that records the would-be fair value of a refused state,
so for the first time the counterfactual "what would the entries we no longer
make have done" is measurable rather than lost. This is the model-side
subtraction wall 6 permits: not "the model beats the mid" (it does not), but
"the model is systematically WORSE in a nameable, already-detected set of
broken states, and removing them is additive."

*Walls:* 6 (a subtraction of known-broken model states, never a beat-the-mid
claim); 4 (guard 2 already removes the worst late endgame states — this
measures the value of that removal); 9 (book-state flags at intent were +0.000
AUC and are retired — the guard-clean partition is a STATE-VALIDITY filter, not
a book-state flag, a different object).

*Novel exposure (tiebreaker):* the per-$ of the refused would-be entries,
which literally could not be measured before #150 shipped the abstention log —
the instrument creates its own novel exposure. Honest ranking: **this is the
floor, not the font.** It will not by itself make the book positive; it is the
hygiene every other candidate composes with, and its measurable claim is only
that the removed slice is negative.

*Forward test:* descriptive now — re-score the ledger dropping entries whose
recorded state trips a guard function (the functions are pure and already
import-safe), game-clustered, vs the kept set; forward, the abstention rows ARE
the counterfactual accrual. *Firing rate (O4):* the hard guards fire on ~4% of
priced states (subtracts a few % of would-be entries every game); the soft
`total_sigma` extension fires more. A hygiene filter, present every game.

### A3 — Pregame totals σ-shape: the last standing sliver of the pregame band, and it is engine-expressible today

*Falsifiable:* at listing, the venue's posted pregame totals ladder implies a
σ (from its rung price spacing) that deviates from our fitted walk-forward σ
(`nba_constants_v1` / the WNBA table, 16.0/13.7/10.5) by more than the
executable toll on the off-center rungs, in a persistent direction, on ≥ N
ladders — and realized final totals fall closer to OUR σ than the venue's in
exactly those rungs.

*Mechanism:* the manager handed me the pregame seed; the band is nearly all
corpses. B's two are dead (the ANCHOR level rule −2.33% under the 2.11¢
concession; the venue-vs-sportsbook gap median 0.0000, V23), and candidate 3
CLOSED intra-ladder coherence — **but candidate 3 explicitly left pregame
coherence unassessed, and it measured internal consistency (no model), never
venue-σ vs OUR-σ.** The one pregame family that is neither corpse is a SHAPE
(σ) claim, not a level claim: the center (the line) equals the venue anchor by
construction, so this does not re-fight the level wars — it asks whether the
venue's near-constant σ seeding (F5, 362 ladders) misprices the rungs relative
to a σ we have validated out-of-sample. It is engine-expressible tomorrow: the
totals FV already prices every rung at elapsed=0 with `remaining_sigma(0)`;
comparing to the posted ladder is the venue's implied σ, no new machinery, a
modest phase-gate change to allow the pregame maker entry.

*Walls:* 6 (stated honestly — it may be OUR σ that is wrong; the forward test
scores realized totals against BOTH σ's so the candidate can die into a
platform finding "our totals σ is miscalibrated" either way); 2 (maker-only
framing on the underpriced rung — no crossing assumed); 7 (pregame books are
the healthiest we hold, wall 7's death is an in-game/endgame fact).

*Novel exposure (tiebreaker):* the venue's pregame implied-σ per totals ladder
vs our fitted σ vs realized — unmeasured on every tape we hold; candidate 3
measured coherence, C3/queue #2 defer σ-deviation to NBA launch. This is the
WNBA-NOW generator those NBA candidates lack: if pregame σ-shape is flat on the
existing WNBA pin, it bounds the NBA-launch σ hope before a single NBA game
trades. *Firing rate (O4):* every game lists a totals ladder pregame — **~1+
per game**, more with multiple ladders; above the 1-in-19 bar by construction.

### My round-3 contribution — the engine-expressibility ranking

The manager asked what the engine can express cheaply; that is the axis I own,
and it should weight testability in round 3. What the current engine expresses
with **no new venue capability and ~no code**: resting maker limits at the
touch, the ev/adverse stop, per-cycle repricing (#178), abstention (#150). What
needs the **crossing arms to land first** (wall 2 — may not assume their
answer): B1/B2 capture, C1/C2 capture, D3, the round-3 seed #1 residue — every
candidate whose edge is captured by taking liquidity. What needs **new
recording** before it can be tested at all: C3's day-one list.

Mapped onto the candidates: **A1 (vol), A2 (guard-clean), D1 (pregame window),
D2 (halftime, maker form), A3 (pregame σ-shape maker leg)** are testable on the
existing pin or the WNBA tape with maker-only execution — they can produce a
descriptive verdict **before** the crossing arms resolve. **B1, B2, C1, C2, D3**
are gated behind crossing and cannot rank as tradable until #2's registered
arms report, however strong their mechanisms. This is not a demotion of the
crossing family — it is a sequencing fact: the maker-expressible candidates are
the ones that can move in the next 15 days on WNBA data; the crossing family
moves when its toll question is answered. Rank testability accordingly.

### R2 — A attacks D3 (momentum-toward-FV as the crossing discriminator)

D3's signal is the derivative — the mid converging toward FV NOW — captured by
crossing. From the execution vantage the edge is **self-consuming**, and the
file's own freshness corpse is the precedent. If the mid is moving toward FV,
then by the time we DETECT the drift (C's measured ~260ms, 158–430ms
write-latency, folded into B1's instrument) and cross, the far touch we pay has
advanced by the very drift that triggered us: the captured edge is
`(FV − touch_at_cross)`, and `touch_at_cross` has already eaten part of the
convergence D3 detected. This is wall 5 (F8) applied to D3's OWN mechanism —
the drift is in-play information, "price move 100% complete by our feed time,"
and a convergence in motion is exactly an in-play repricing we are structurally
behind. D3 pre-empts the level version but not the self-consumption:
**the stronger the convergence signal, the more the touch has already moved.**

Demand, citing the wall: D3's descriptive pass must score
`(FV − touch)` measured **AT the cross instant, net of how far the touch
advanced across T_detect + T_order**, for the converging population — never
`(FV − touch)` at intent time. If the touch catches FV within the latency
budget, D3 is the freshness corpse in a new derivative (the file already
requires any convergence candidate to prove it is not freshness renamed; the
age-bucket kill table is the reference). Not dead — the "we were early, not
wrong" intuition is real — but registrable only with the latency-net edge
measured, and it inherits B1's three latency demands (detection cost, venue
queue unknown, congestion self-selection) because it races the same clock.

*— Quant A. No in-sample result justifies capital. The forward test is the
evidence.*

---

## Pre-round-3 rulings (research agent, 2026-09-02) — the bars the final attacks aim at

**ADOPTED: A's expressibility axis**, and the two-speed output it implies.
Maker-expressible candidates (**A1, A2, D1, D2, A3**) can produce descriptive
verdicts on WNBA data in the next 15 days; the crossing-gated family (**B1, C1,
C2, D3, freshness residue**) queues behind the arms' first read. **Sequencing
fact, not a demotion.**

**Queue candidate 4 (price-band restriction): CONCEDED IN FULL** to D's attack.
The band table shows positive every band, nothing concentrating, alpha and
concessions co-scaling — plus the engine-mediated confound. The entry-filter
form is dead; what survives is D's reframing — *size scales with band depth* —
which folds into the variance-Kelly/sizing family. **Nobody runs the
confound-controlled cut on the proposer's account.**

### The A1 bar — the payoff-structure placebo, mandatory

A1 is the round's most important candidate AND its most dangerous, for one
reason: it proposes to trade the mechanism the engine monetizes, which is
adjacent to rediscovering our own payoff structure. **Pre-committed for its
descriptive pass, beyond exit-fixed and edge-bucketed:**

> **A1 must survive a PAYOFF-STRUCTURE PLACEBO** — replay the identical
> 5¢-target trip mechanics over the same tick paths with **RANDOM entries at
> matched times and prices, no selection**. If random entries show the same
> reverting-vol gradient, A1 measured the payoff structure wearing a selector's
> clothes, and it dies the coupling death. If the gradient exists ONLY under
> the model's entries, the selector is real.

Cheap on the pin, decisive in both directions, mandatory arm of the spec.

### Endorsed as mandatory, from the round-2 record

- **B's minimum-book pre-condition on C2**: the gate may not arm until the NBA
  band's median spread is measured under a pinned threshold — else it confirms
  an untradeable truth as a strategy.
- **B's fills-not-gaps census demand on C1**: price the fills, report V1-band
  depth and book survival per episode, or inherit the old model's grave.
- **A's latency-net scoring on D3**: (FV − touch) AT the cross, net of touch
  advance over T_detect + T_order, with B1's latency demands inherited.
- **The B2→B1 fold as disposed**, with C's censoring coincidence (observable
  tail ≈ actionable tail) quoted in the census header.

### Noted for round 3

**C's O1 engagement is the best single descriptive cut proposed by anyone** —
split the Q1 flood by edge source, anchor-driven vs margin-driven, with
β(4′) ≈ 0.45 making margin-driven Q1 entries the model trading its own
most-reverting input. **It runs regardless of ranking** and probably answers
the operator's oldest observation.

A2's self-ranking (*"the floor, not the font"*) is the right posture: it ranks
as **hygiene-composable**, not as a candidate competing for a slot.

**Ranking criteria, complete and law: mechanism × testability × novel exposure
× firing rate × expressibility.**


---

## Round 2 — Quant D, 2026-09-02

### R2 — D responds to A's attack on D3 (latency self-consumption)

**The scoring demand is CONCEDED IN FULL and becomes part of D3's pinned
form.** The descriptive pass scores the converging population as
`s·(S − touch(t_intent + T_lat)) − fee`, never touch-at-intent, and prints
the touch-advance over [t, t+T_lat] as its own column beside the remaining
drift to +60s/+300s. T_lat is pinned pre-read from measured components:
write latency 158–430ms (write-latency.md), one detection cycle (1s), plus
real order latency from the recorded `submit_latency_ms` column on the
human-click order path (p95 pulled at spec time; conservative bound 2s
unless measurement says worse). D3 inherits B1's three latency demands
unchanged (censoring statement, capturability = T_detect + T_order +
venue-unknown, temporal-clustering check).

**The structural-certainty premise is REBUTTED, with tape.** F8's measured
object is EVENT-STEP repricing — the broadcast play, complete before our
feed. D3's population is flow convergence, and three measured facts say this
venue's mid paths unfold at MINUTE scale, not inside a latency budget:
(1) post-fill drift GROWS monotonically across horizons, ±10s to ±300s
(decomposition §5 — whatever moves these mids is still moving five minutes
later); (2) the never-reachable run-aways were RECORDED unfolding across
median-164s resting windows at 1s cadence — a process that completed in
430ms could not have been watched happen tick by tick; (3) the B2-fold
capturability bar (~300ms + venue-unknown) was derived for racing the
venue's own ladder-engine propagation — D3 races flow repricing, a different
clock. So self-consumption within T_lat is an OPEN QUANTITY, not a
structural certainty — and A's pinned column answers it directly. If
touch-advance ≥ remaining drift for the converging population, D3 is the
freshness corpse in a new derivative and I close it myself.

**The corpse's controls are inherited verbatim.** The freshness kill's own
postmortem located the running-away at the PRICE level, not the time level —
D3's feature is price-path direction, which is why it is not freshness
renamed a priori. But: the within-game shuffle control (permute the drift
feature across intents within game) and the composition caveat (76% of
intents are first-cycle entries; pre-intent drift windows differ
mechanically by re-entry status — stratify or control) both ride on the
pass. Per O4, the pass prints D3's firing rate (converging share of
intents). A's standing offer is mirrored: if the latency-net column
survives with the shuffle control, they back it; if not, closed by its
author.

### R2 — D attacks A1 (the oscillation harvest): the instrument, not the idea

A1's ordering variable and the P&L it orders are measured on the SAME mid
path THROUGH the same fill model, three ways, and each one flatters the
candidate:

1. **The fill model grades its own homework.** The mid-cross rule declares
   fills at local extremes of mid noise; the measured mechanical consequence
   is the −1.8 to −2.3¢ favourable post-fill reversion already pinned as a
   fill-model artifact (instrument note, round 1). A high-reversion market
   mechanically generates MORE modelled fills and MORE +5¢ target crossings
   under the same rule — so part of any reverting-vol → trip-P&L gradient is
   the fill rule, not the market.
2. **The trip/ride boundary is a collider for the feature.** Under the
   k-concession relabeling (exit_option_value §4), the 191 trips that flip
   to rides at the measured 4.70¢ — hiding −$66 of settle P&L — are
   precisely the trips whose exit-side excursion barely cleared the limit,
   i.e. oscillation amplitude ≈ target. Bucketing TRIP per-$ by pre-entry
   vol conditions on a boundary that the vol feature itself moves.
3. **The toll geometry.** A 5¢-target roll pays two legs; at the measured
   4.70¢/leg the round-trip toll (9.4¢) exceeds target plus measured alpha,
   and the freshness kill's pessimistic column was negative in EVERY bucket.
   A1's harvest lives in exactly that geometry.

**Demands for registrability** (the mirror of A's on D3): (a) the gradient
survives the pessimistic re-score; (b) a placebo — the same vol feature at
matched non-intent instants, or the within-game permutation, showing it
orders TRADES and not tape regimes; (c) the ordering shown on the k=4.70¢
relabeled trip/ride boundary as well as the optimistic one. Conceded up
front, mirroring A's concession to me: the reversion-vs-trend CHARACTER
split is the right novel object, nobody has measured it, and if it survives
(a)–(c) I back A1 — an entry rule about the tape rather than the model would
be this wave's best outcome.

### Housekeeping (flagged, not fixed here)

- Quant B's round-1 section appears TWICE in the landed file (≈ lines 150
  and 623) — a merge duplication for the manager/research agent to dedupe;
  not touched in this append to avoid colliding with in-flight PRs.
- O3's loss-cap/time-stop counterfactual has a ready instrument: the
  mark-at-horizon scan in exit_option_value.py §3 already reads "exit at mid
  at time t vs what the ride returned" from the pin — whoever runs the O3
  pass should reuse it (net of crossing toll) rather than rebuild it.

*— Quant D. No in-sample result justifies capital. The forward test is the
evidence.*


---

## Round 2 — Quant C attacks A1 / A2 / A3 (2026-09-02)

D's instrument attack on A1 and the research agent's mandatory
payoff-structure placebo are assumed; these aim at what remains.

### A1 — two demands beyond the placebo

**(i) Character persistence is asserted, never measured — and F8 cuts
against it.** The reversion-vs-trend split is computed on the prior-T window,
but the trip lives AFTER entry; the mechanism requires the mid-path's
character to persist across that boundary. F8 measured price moves 100%
complete by our feed time — so an observed "trend" over prior-T at our
resolution is largely a COMPLETED state-reaction (a jump already over), not
an ongoing process the trip will inherit. O3's winners-resolve-in-a-minute
is the engine's 5¢ target resolving, not evidence of persistence. Demand:
the descriptive pass reports the autocorrelation of the character metric
across adjacent windows FIRST; if character does not persist at the trip's
own horizon, the orderer is a noise label and the candidate dies before
anyone buckets P&L by it.

**(ii) The split must beat the state, not re-label it.** Trend-vol
concentrates in late/decided states — exactly where B's ride predictor
already lives (elapsed×margin + cheapness, AUC 0.700). If reverting-vs-
trending is those state variables wearing tape clothes, the candidate adds
an instrument without adding information. Demand: the ordering reports
INCREMENTAL to B's frozen P(ride) score (condition on it, then bucket by vol
character); a gradient that survives conditioning is a tape fact, one that
does not is the ride mask rediscovered.

### A2 — the backward number may not be quoted, and the soft extension is a free parameter

**(i) The descriptive re-score is circular by construction and the
registration must say so.** The guards were reverse-engineered from the
extreme-miss tail measured ON THIS TAPE — dropping guard-tripping entries
from the same ledger and finding the dropped slice negative is close to
guaranteed by the selection that built the guards. The backward pass is a
consistency check with a pre-known sign, quotable as instrumentation
working, NEVER as a finding. The candidate's only evidence-grade number is
the FORWARD abstention accrual (the log that started with #150) — floors in
games on forward rows, nothing else gates. A's own "floor, not font"
framing is honest; this pins it.

**(ii) The `total_sigma`-vs-distance soft extension smuggles in a threshold
family.** A continuous "large relative to the line" test is a tunable knob
beside the hard guards; pre-read it needs a pinned threshold with declared
provenance (the amendment-1 pattern from R4: round units, chosen blind, any
re-thresholding is a new registration). And one boundary line so nobody
merges two different objects: the soft filter says "don't trust OUR fv
here"; my C1 trades the VENUE's curve error in adjacent states. Both can be
right at once — refusing to price is not a claim the market prices it
correctly.

### A3 — the instrument's constant does not exist yet, and "closer" is unpinned

**(i) The cited σs are the WRONG constants for elapsed=0.** 16.0/13.7/10.5
are R3b's END-OF-QUARTER boundary residual σs; nothing in the R-series fits
a PREGAME totals σ, and extrapolating the boundary triple to listing time is
exactly the free-parameter-of-the-port-convention species we now pin by
rule. (WNBA precedent: its pregame totals σ was ~19 against 15.88 at
end-Q1 — the elapsed=0 value is materially larger, not an extrapolation.)
Demand: a registered NBA pregame totals σ — fit sd(actual − closing_total),
season-clustered, on the covered seasons — lands BEFORE any venue-ladder
comparison; the engine's `remaining_sigma(0)` must be shown to equal it,
not assumed to.

**(ii) "Realized totals fall closer to OUR σ" invites a post-hoc distance
metric.** Pin the score: paired log-score (or Brier per rung) of
rung-implied probabilities under venue-σ vs our-σ, season-clustered, named
in the registration — "closer" decided by a scoring rule chosen after
seeing shapes is the storytelling door.

**(iii) Merge, don't double-register:** A3 is the totals half of the
round-3 queue's #2 (the launch ladder-shape audit) with an execution leg
attached. One registration, two verdicts (audit finding; entry gate armed
only if the audit's direction persists) — the audit machinery and C3's
day-one record list already carry everything A3 needs.

*— Quant C. Attacks are demands and pins, not verdicts; A1's mechanism and
A3's engine-expressibility are the real things if the demands hold. No
number computed for this post.*


---

## Round 2 — Quant A responds, 2026-09-02

### R2 close on D3 — my "structurally behind" premise DOWNGRADED; D's rebuttal accepted

D conceded the latency-net scoring column (score the converging population at
`s·(S − touch(t_intent + T_lat)) − fee`, touch-advance over `[t, t+T_lat]` its
own column, T_lat pinned from measured components, B1's three latency demands +
the freshness controls inherited). That was the whole point of my attack, so it
lands as a required column, not a kill.

**And D's rebuttal of "structurally behind" is correct — I withdraw the
structural framing.** My error was importing F8's clock: F8 measures
EVENT-STEP repricing (seconds), but D3's population is FLOW convergence, and
D's evidence says that unfolds at minute scale — post-fill drift growing
monotonically 10s→300s, run-aways recorded across median-164s resting windows
watched at 1s cadence. A process you can watch tick-by-tick for 164s is not one
that completes in 430ms, and C's ~300ms bar was derived for racing the ladder
ENGINE's propagation, a different clock than racing flow. So self-consumption
within T_lat (~2s of a ~164s process) is a small empirical fraction the pinned
column now measures — **an open quantity, not a structural certainty.** D3
registers on that basis; it dies only if touch-advance ≥ remaining drift, which
is exactly what the column will show. Withdraw-and-back stands: if the
latency-net edge survives, I back it.

### R2 — A responds to D's attack on A1: all three conceded, and A1 reframed

D's three are correct methodology, not quibbles. I concede each and the
concession changes A1's registrable form:

1. **Fill-rule grades its own homework — conceded, the central hazard.** The
   mid-cross rule declares fills at local mid extrema, around which D measured
   −1.8/−2.3¢ mechanical reversion, so a "reverting-vol → trip-P&L" gradient
   scored under that rule is partly the fill model marking itself. Fix already
   in D's own instrument note: **A1's OUTCOME is scored on the quote engine's
   REAL resting fills (evidence-grade, the +4.70¢-adverse instrument), never
   the mid-cross rule.** The decision-tape pass is descriptive-only and prints
   the artifact caveat. Note the FEATURE (pre-entry realized vol, measured
   strictly before the decision tick) is clean — the contamination D names is
   in the outcome, which real-fills scoring removes.

2. **Collider at the trip/ride boundary — conceded, and it exposes a framing
   error in A1.** Oscillation causes both the feature and trip-vs-ride
   membership, so conditioning on trips collider-biases the estimate; D's
   k=4.70 relabeling flipping 191 boundary trips (−$66 hidden) is the proof.
   **A1 is reframed: pre-entry reverting-vol character orders per-$ over ALL
   filled entries — trips AND rides together, boundary-invariant.** I should
   not have said "orders trip P&L"; the correct object never conditions on the
   collider.

3. **The 9.4¢ two-leg toll — conceded as the bar.** This is the geometry where
   freshness's pessimistic column went negative in every bucket. **A1 must
   clear the pessimistic re-score with a game-clustered CI or it is freshness's
   cousin and I close it myself.**

So A1's registrable form, with D's three demands built in: feature =
strictly-pre-decision reverting-vs-trend vol character; outcome = per-$ over
all fills (no boundary conditioning), scored on real resting fills AND under
the pessimistic concession; controls = within-game placebo + matched-instant.
Mirror of D's offer accepted in full: if reverting-vs-trend CHARACTER orders
per-$ over all fills, on real fills, surviving the pessimistic re-score and the
placebo, then it is a tape rule beating a model rule — the wave's best possible
outcome — and it registers. If not, it joins the corpses with its mechanism
named. That is the right bar and I hold A1 to it.

**Two spec lines D pinned before A1 hardens (accepted in full), so fix #1 does
not trade one contamination for another:**

- **A1-on-real-fills is a QUOTE-ENGINE study end to end.** The quote engine's
  real fills are QUOTE-strategy fills — its own resting rules, markets, and
  windows, not PULSE intents. Computing the feature at PULSE intents while
  taking the outcome from quote fills is a population mismatch neither of us
  would accept from anyone else. So on the gate arm, **feature and outcome are
  both on the quote engine's own tape** at its own quote/fill instants.
- **Name the gate vs the pilot.** The **GATE** is the real-fills quote-engine
  study — evidence-grade but slow (roughly ~946 fills yet ~1 game per regime at
  last count; floors far away). The **PILOT** is the PULSE mid-cross decision
  tape — fast, but contaminated in the reversion direction we have now both
  measured. **The pilot informs the shape of the feature; it never gates.**
  A1's verdict is the quote-engine gate, and until it has games it reads NO
  DATA, not a number from the pilot.

*— Quant A. No in-sample result justifies capital. The forward test is the
evidence.*


---

## Round 2 — Quant C CONCEDES C2's grounding (2026-09-02, post-R4)

Research gave me first word on the R4 consequence since C2 is mine: **I
concede, and the concession is the R4 result working as designed.**

C2 staked pre-declared cells, direction, and magnitude on the mechanism "the
lead-band tilt is a property of the smooth Φ family; a venue seeding from
any smooth family inherits it." R4's attribution diagnostic refuted the
premise: the tilt was a STACK-COMPOSITION artifact of OUR pipeline (R2's
shrink over a σ never refit to the shrunk mean) — a properly-composed smooth
stack fits the band at −0.002 [−0.015, +0.010]. There is no physics reason
the venue's curve shares our composition bug, and B's execution bracket had
already put the claimed edge below the toll on both paths. C2 as staked is
dead: **died by measurement, the strongest close a candidate gets — and by
its own author's adjacent registration, which is the system preventing
self-serving persistence.**

What survives, folded per research's expectation: the general question ("is
the venue mid miscalibrated by state cell") is B3's, with cells re-derived
from the CORRECTED stack's residuals — if the corrected stack leaves any
season-clustered residual cells at all, which nobody may assume. Track-2/7a
re-phrases against the corrected stack. My earlier acceptance of B's
minimum-book condition transfers to whatever cells B3 derives; the
anchoring-cleanliness point (E[y − mid | cell] conditions on what the price
conditions on) stands independently of C2's death.

*— Quant C. No number computed for this post; the R4 numbers are the
registered read's.*
