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
   when the market comes to disagree with you; the unfilled third that ran away
   was worth +33¢/ct at the resting price you never got (#126).
2. **Crossing pays spread + fee**: 4–7¢ early / 8–10¢ late medians, plus
   0.06·p(1−p). The registered crossing arms test whether selective crossing
   clears that toll — accruing now, verdict unknown. Ideas may not assume its
   answer.
3. **Detectable risk is compensated in this book** — but ENGINE-mediated (the
   5¢ target over cheap costs), not a market law. Any idea that changes exits
   must re-net (#157/#158).
4. **The model's in-game alpha is +3.47¢/ct optimistic, and late-state exit
   risk alone (3.5–3.8¢/ct) exceeds it. Late entries are uneconomic.** (#154)
5. **The market already prices**: in-game reversion (#18), ESPN win probability
   (F9), and detectable state risk (partially engine-mediated). Three deaths by
   the same sword. An idea whose mechanism is "the market is slow to X" needs a
   reason THIS venue is slow that survived F8's feed-lag bound (price move
   100% complete by our feed time — event-reaction is structurally dead).
6. **The FV is calibrated in the bulk and uninformative where it disagrees with
   the mid** (Track C). Where the model would trade, the market has been right.
7. **Endgame books die**: 9/22 bookless endgames; winner books die in decided
   games, ladders die independently ~1 in 10. No safe-harbour market type.
8. **46% of intents historically never filled; 34.6% on the current tape.**
9. **Boring list (do not re-mine):** entry spread, side, cheap contracts,
   mid-margin buckets, if-ridden counterfactual, v1-only positives, book-state
   flags at intent (+0.000 AUC), edge_net ordering (dead in every big cell).

## Directions deliberately NOT yet tried (seed list — attack or extend)

- **Pregame / near-tip entries.** All measurement is in-game. The 35–65¢
  pregame band has depth (V1) and no F8 lag problem, and the model's pregame
  anchor is the venue's own line. Is there any pregame mispricing family left
  untested? (#16/#17 killed two — but both were in-game reversion shapes.)
- **Cross-market structure within a game**: winner vs spread vs total carry
  the same state — are they ever mutually inconsistent by more than
  spread+fee? (Never measured here. Mechanism is arbitrage-ish, not
  prediction.)
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
