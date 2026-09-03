# Fill-calibration protocol — the operator's 25 orders

**Research agent, 2026-09-03. PRE-REGISTERED: the market-selection rule and
the cancel discipline are fixed HERE, before any order is placed, because
choosing markets by belief or cancelling only the unattractive orders would
reintroduce exactly the selection that voided the hand-trade finding.
Landed by the manager. OPERATOR'S DECISION ENTIRELY — nothing here is a
recommendation to trade, and the autonomous-order bar is untouched: the
engine places nothing, ever.**

## What it measures, and why it is worth more than a markout

**The pitch is the DENOMINATOR, not the markout.** Unfilled resting orders
leave no trace — the venue emits nothing for a zero-fill cancel — so the
program has no record of orders that DIDN'T fill. **A human who writes down
their own placements creates the record the venue refuses to keep.** Twenty
five logged orders produce twenty five denominator rows whether or not any
fill, so the no-fills are data rather than waste.

That yields **P(fill | at the touch, ~45s exposure)** — a quantity this
program owns exactly zero of, and the one the entire fill model assumes.

**The power argument, which is the strong form:** ~25 orders CANNOT pin the
concession's magnitude (SE ≈2¢ against a 7¢ per-fill SD). But **our fill
model assumes P(fill | price touched) ≈ 1**, and 25 orders distinguish
"approximately 1" from "substantially less" decisively — at a true rate of
40% the interval would exclude 1.0 by a wide margin. **So: this experiment
cannot measure the concession, and it CAN decisively test whether the core
assumption underneath every number in the program is approximately right or
badly wrong.**

## When — the first NFL slate (2026-09-09/10), not WNBA's return

Sooner by a week, on the board where the revenue question lives, and NFL
recording is already capturing at 0.5s so the tape exists to score against.
**A zero-fill outcome is NOT a failed experiment — it is the flow answer the
memo's kill line needs:** 25 touch-joining orders that never fill says the
NFL board does not trade, which is precisely what the day-one survey was
built to ask. Repeat on WNBA from Sept 17 if markout power is wanted, where
narrower books make fills likelier.

## The protocol — 25 orders, ~$15 exposure, one evening

1. **When:** during a live recorded game.
2. **Market selection — PRE-DECLARED, never by belief.** Fix the rule in
   advance and follow it mechanically (e.g. *"the spread market of the game
   being recorded, the rung nearest the current mid"*). Choosing markets
   where you believe there is an edge reintroduces the population mismatch
   that killed the hand-trade finding.
3. **Placement:** minimum size, **JOIN the touch** — best bid to buy, best
   ask to sell. **Never cross.**
4. **Duration:** cancel at **~45 seconds BY THE CLOCK**, honoured even when
   the order looks good. **Cancelling only the unattractive ones is
   selection on outcome and contaminates the sample.** This discipline is
   what the whole experiment depends on.
5. **Alternate sides** so no directional position accumulates.
6. **LOG EVERY ORDER — the log IS the instrument:** time placed, market,
   side, your price, the best bid AND ask at that instant, time
   cancelled-or-filled, filled yes/no, quantity filled.

## Limits, stated up front so the result is not over-read

It matches the engine on **placement discipline** (at the touch, brief
exposure) but **not on market selection or timing distribution**, so it
calibrates the **SIGN and order of magnitude** rather than replacing the
4.70¢ figure. It needs no engine credentials, no relaxation of the
autonomous-order bar, and no new code — the operator, a clock, and a
spreadsheet.

**No in-sample result justifies capital. The forward test is the evidence.**
