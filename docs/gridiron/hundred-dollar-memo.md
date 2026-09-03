# The hundred-dollar memo — arithmetic, no hope

**Research agent, 2026-09-02/03, landed by the manager (author's
message-of-record text verbatim; calendar substitution flagged as in the
program registration: "Thursday" → the first NFL slate, first game
2026-09-09, event governs). Instruments now registered against this memo:
the paper-wallet scoreboard and the lever-replay wave (2ab891c) — the bar
has a daily scoreboard and the levers have a ranking protocol; neither is
evidence.** **Ratified by the author, with the error given its true shape (research agent, 2026-09-03): "Thursday" was an INHERITED calendar claim — asserted in a relay, repeated by the author into registration text without verification, caught by B at the venue (gameStartTime 2026-09-10 00:20Z). The author carries two memory scars named verify-against-the-venue and verify-clock-and-timezone, and still landed a relayed date into signed text on the day the whole registry learned to cut pointers into artifacts. The event-governs form was always the correct drafting; this flag says the author needed teaching twice.**

**The bar: $100/month = $3.29/day = $23.03/week.**

**(a) GRIDIRON maker capture — the ONLY candidate whose ceiling clears the
bar on the 2026 calendar.** The arithmetic: at +0.5¢/contract-fill net,
the bar is **≈4,600 net-positive contract-fills/week** (2,300 at +1.0¢).
Supply side: WNBA shadow density ran ~1,310 fills/game; 16 NFL games/week
at comparable density ≈ 21k shadow fills/week — but shadow fills carry the
documented fill-model haircut, so the honest planning number is a QUARTER
of that, ≈5,200/week at 1 contract. **The bar is approximately the first
plausible operating point — TIGHT, not comfortable.** It requires ALL
THREE: capture actually positive (+0.5¢ is UNPROVEN — v1 measured
−1.60¢/fill; the entire v2/GRIDIRON program exists to flip that sign via
selectivity), real-fill volume near a quarter of shadow density, and NFL
book depth supporting ≥1-contract quotes across the day — the last one is
measurable ON THE FIRST SLATE and is the day-one survey's first
deliverable. Kill line, stated now: **if the first slate's depth/spread
survey shows NFL cannot support ~5k fills/week at plausibly-positive
capture, the $100 bar is unreachable on this venue's sports ladders and
this memo says so** — that is a findable, falsifiable fact, not a mood.
(This condition and the program registration's fail-fast clause are the
SAME fact stated twice, cited to each other, so neither text can outlive
the other's verdict silently.)

**(b) A1 + WNBA: the epistemic engine, NOT the cash register.** Even a
full PASS (+4.35%/$ with concessions cut to c*) cannot pay $100/month on
WNBA's remaining calendar — ~4 thinning weeks from Sept 17, then darkness
until May. Its value is deciding WHAT GRIDIRON QUOTES (state-conditional
vs unconditional) with basketball evidence before NFL capital-relevant
decisions. Fund it with attention, not expectations.

**(c) PATIENCE's 0.8¢/fill: a MULTIPLIER, never a source.** Reducing a
loss is not income; composing +0.8¢ onto near-breakeven quoting is what
pushes across zero. It rides on (a); it cannot be ranked beside it.

**CANNOT CLEAR THE BAR — attention stops here:** every taker strategy on
measured spreads (the wave's whole verdict: tolls exceed alpha,
priced-or-tolled-out everywhere checked); the FV model as a signal
business (Brier worse than the market on every slice with real n);
anything confined to the WNBA calendar; MLB; CFB/EPL.

**TIMELINE HONESTY, because the operator reads for hope:** real dollars
require operator-confirmed execution — autonomous orders are barred by our
own safety architecture (the DB CHECK constraint is the algo's oath, not
an obstacle). So "pays for itself" operationally means: the shadow book at
MEASURED concessions clears $100/month, then the operator lifts it to real
with confirmations. Earliest credible sequence: first-slate survey → first
capture descriptives inside 2 weeks (3 NFL slates) → first gate read ~end
of September → IF it passes, an operator-executed pilot in October →
**November is the first month that could realistically show $100 REAL.
Anything sooner is hope, and this memo doesn't sell hope.** What we can
promise instead: by end of September the operator will know — with
pre-registered numbers — whether this venue's NFL board can pay the bar,
and if it can't, they'll know that too, in time to decide what ceases and
what pivots.

---

## ADDENDUM (2026-09-03) — CAPITAL CAPACITY: the constraint nobody had computed

The memo priced the EDGE and never priced the BALANCE SHEET. D measured it
(51c252e), and on a binary venue it is arithmetic rather than statistics:
per-contract loss is BOUNDED (a long at p loses at most p, a short at most
1−p, so at most $1/contract at settlement), therefore **peak total open
contracts IS the worst-case dollar exposure.**

**Measured on the August WNBA tape, AT UNIT SIZE: peak 702 contracts across
91 concurrent non-flat markets (~$702 against a $1,000 wallet); time-weighted
262 contracts across 38.6 markets.** v1 was already near the wallet's
arithmetic capacity while quoting ONE contract, on a SMALL slate.

Consequences the memo now carries:

1. **The AGGREGATE limit binds, not the per-market cap.** A per-market K
   bounds one market; ruin comes from the sum across concurrent markets. Any
   K chosen without the aggregate number bounds the wrong object.
2. **The arithmetic is linear in size: at 2 contracts/quote the peak worst
   case is ~$1,404 — more than the wallet exists.** So $1,000 supports unit
   size and no more on a WNBA-sized slate.
3. **NFL is WORSE, not better.** A Sunday lists ~12 concurrent games against
   WNBA's ~4–5, so unit-size peak exposure plausibly runs $1,400–$2,100 —
   **above the wallet at ONE contract per quote.** Re-measurement on the NFL
   board is required before this sizes anything; the WNBA figure does not
   transfer.
4. **This does not break the wallet — it INSTRUMENTS it.** The reservation
   rule already refuses fills beyond available balance, so the wallet clips
   rather than blows up, and **the capital-clip rate IS the measurement of
   how much bankroll the strategy actually requires.** The scoreboard answers
   the capital question by running, not by arguing.

Conservatism stated so the number stays usable: the bound assumes every open
contract settles against us at once, while this tape's whole cumulative
settled P&L was about −$133. **The bound is the RUIN object (what cannot be
exceeded); the realised distribution is the P&L object.** A wallet sizes on
the first and forecasts on the second. Lower-bound caveats in the artifact:
unit size, 4 games absent from the tick pin, exposure past the pin uncounted.
