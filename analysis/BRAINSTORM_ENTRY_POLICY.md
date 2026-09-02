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
