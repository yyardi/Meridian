# The hundred-dollar memo — arithmetic, no hope

**Research agent, 2026-09-02/03, landed by the manager (author's
message-of-record text verbatim; calendar substitution flagged as in the
program registration: "Thursday" → the first NFL slate, first game
2026-09-09, event governs). Instruments now registered against this memo:
the paper-wallet scoreboard and the lever-replay wave (2ab891c) — the bar
has a daily scoreboard and the levers have a ranking protocol; neither is
evidence.** **Ratified by the author, with the error given its true shape (research agent, 2026-09-03): "Thursday" was an INHERITED calendar claim — asserted in a relay, repeated by the author into registration text without verification, caught by B at the venue (gameStartTime 2026-09-10 00:20Z). The author carries two memory scars named verify-against-the-venue and verify-clock-and-timezone, and still landed a relayed date into signed text on the day the whole registry learned to cut pointers into artifacts. The event-governs form was always the correct drafting; this flag says the author needed teaching twice.**

## THE FRAME (D, 2026-09-03 — read this before the arithmetic)

**v1 is not a market maker; it is a passive position accumulator with
slightly better entry prices than mid.** It quotes two-sided, realises
one-sided flow, and has NO MECHANISM TO CLOSE. Every other measurement is a
consequence: it accumulates (time-weighted |q| 7.24) without that ordering
the per-fill mean; the accumulation orders the TAIL (per-market settlement
SD 0.35 → 6.45 across peak |q|); round trips were AVAILABLE and refused (up
to 27–42% at a 1¢ lean, +1.44¢ round trip against −15.09¢ rides); and the
un-closed positions aggregate to a ~$702 arithmetic worst case against a
$1,000 wallet at unit size.

**The one missing capability — FLATTENING — answers all three:** it converts
high-variance rides into tight scalps, shrinks the inventory that orders the
tail, and frees the wallet capacity that permits size.

Recorded with equal prominence so no later reader revives them: the
inventory CAP as a P&L lever is DEAD (game-clustered null, and no
calendar — not even a full NFL season — can resolve it), and no reading of
the tail supports "remove the tail and we have a business" (no peak-|q|
bucket has a positive mean).

**The bar: $100/month = $3.29/day = $23.03/week.**

**EVERY CAPTURE FIGURE BELOW IS CONDITIONAL ON A MODELLED FILL.** The
−1.60¢ baseline, the +0.11¢ target, the flattening deltas — none are wrong,
all sit above a fill model with **two known optimisms and one unmeasured
magnitude**: (a) the mid-cross rule books ~1.5¢/leg then the mid reverts,
against +4.70¢ measured adverse selection on real resting orders; (b) queue
position — median 1,000 contracts rest at our own quote price, holding time
priority, so a crossing event cannot distinguish TRADE-THROUGH (queue
consumed, we might have been reached) from CANCEL-THROUGH (queue evaporated,
no trade happened at all), and depth favours the second. The quote engine is
credential-free and has never placed an order: **`shadow_quote_fills` rows
are the mid-cross rule's output, not venue executions.**

**The real-fill count, run rather than assumed (rule 20 applied to the claim
"we have none"): FIVE real resting limit orders exist** (`orders`, Aug 5–7,
all `would_rest=true`, all at the touch): **3 EXPIRED unfilled, 2 FILLED IN
FULL.** So the honest statement is "n=5, two-fifths filled completely" —
statistically worth nothing on its own, and **mild evidence the queue was
NOT binding at these sizes**, which is the OPPOSITE direction from the
caveat above. The caveat stands on the modelling argument alone and never
needed this; these five orders are not evidence for it.

*Correction, and it is the specimen the clause below is named for
(2026-09-03, manager's error, caught by the research agent):* the first
version of this paragraph called both fills PARTIAL and cited them as
direct evidence of the queue mechanism. **They fill 2.4700/2.4778 and
1.4600/1.4645 — 99.69% each. Order quantities carry 4 decimals and the
venue reports fills at 2, so the residuals are DECIMAL TRUNCATION, not
queue truncation**, and the `fill_status` column said FILLED all along. The
error was reading a numerator without its denominator and letting a
quantity outvote the status field beside it.

**AND THE CORRECTION'S OWN CORRECTION (same evening, D's ratios): the five
were an unrepresentative sample, and the queue caveat DOES have real
supporting evidence — from a different population.** Run over ALL 129 real
passive executions in the operator's venue history, filled÷requested is
**BIMODAL**: 68/129 (52.7%) sit at ≥99% — the decimal-dust artifact, which
is all the five contained — but **59/129 (45.7%) are genuinely partial, 22
of them filled under a tenth of what was asked, the smallest at 0.15%.**

So: **state the caveat from the 129 with the ratios, never from the status
field and never from the five.** Five observations manufactured a confident
wrong generalisation in BOTH directions within one hour — first "both fills
were partial, that's queue evidence" (wrong), then "fills complete, the
queue wasn't binding" (right for the five, wrong as a generalisation).

**Three candidate causes for an order that stops short, and only the first
is queue evidence:** queue starvation, operator cancellation, or the price
simply moving off our level. Nothing in the feed separates them.
**"Reached and not completed" is established; "reached and starved" is
not.**

**The one-line summary that survives all of it: we have 129 real
resting-order executions, they show substantial genuine partial fills, and
that is the first evidence from ACTUAL VENUE EXECUTIONS — rather than from
modelling — that the fill assumption is optimistic.**

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

## ADDENDUM 2 (2026-09-03) — the required capture is ~10× smaller than this memo assumed

The concurrency measurement forces a re-read of the memo's own core
arithmetic, and it moves in our favour. At v1's measured fill rate
(17,032 fills / 13 games ≈ 1,310 per game) and NFL's ~69 games/month, the
board offers on the order of **90,000 fills/month at unit size**.
$100 ÷ 90,000 ≈ **0.11¢ per contract** — the memo's +0.5¢ working figure was
conservative by roughly 5×.

**So the honest statement of the whole enterprise is: the VOLUME clears the
bar comfortably; the entire question is the SIGN.** Going from v1's measured
−1.60¢ to +0.11¢ is still a 1.7¢ swing and remains unproven — but the target
the levers must hit is a tenth of a cent, not half of one, and that is a
materially different problem.

Caveated properly: **NFL fill rates are UNKNOWN and plausibly much lower than
WNBA's**, because 30¢-wide books get crossed far less often than 4¢ ones —
which is exactly why the flow measurement ranks first in the day-one survey,
and why the trade tape now records (V31/V32).

**And flattening's strongest justification is now capital efficiency, not
P&L.** Closing positions reduces peak concurrent exposure → frees wallet
capacity → permits larger size → multiplies earnings per fill, on top of the
variance reduction and the tail control. Three independent findings converge
on the one capability the engine does not have. **If this program names a
single build priority, it is flattening — and the reason is no longer "it
might earn more" but "it is what lets the book be sized at all."**

## ADDENDUM 3 (2026-09-03) — FLATTENING'S P&L CLAIM IS UNRESOLVED TOO

Tested at the same standard that killed the inventory cap, and it comes back
the same way. Whole-book policy simulation, game-clustered: **+$76 at a 1¢
lean, decaying through 2¢/3¢, NEGATIVE by 5¢** — direction consistent and
"small-lean-or-nothing" reproduced independently — but **only 5 of 9 games
improve and the per-game CI spans zero at every k** (+8.46 [−12.59, +29.52]
at best).

**The subset test overstated by ~3×.** The +1.44¢/round-trip figure came
from fills selected on having flattened; the whole-book policy earns ≈+0.5¢
per fill. That gap IS the selection effect, now measured rather than
suspected — and it is the correction owed to anyone (the operator included)
who was told the +1.44¢ number without it.

**THE BUILD PRIORITY DOES NOT CHANGE, BUT ITS JUSTIFICATION DOES.**
Flattening remains the top build item **for arithmetic reasons, not P&L
ones**: it frees concurrent capital (the only route past unit size on a
$1,000 wallet) and it shrinks the inventory that orders the tail. Both are
arithmetic and both survive the null — exactly as the risk limit's
justification did. **Its earnings claim is DEFERRED to NFL volume.**

Stated the way it should be repeated: *we tested our favourite lever at the
standard that killed the previous one, it came back unresolved, and we are
building it for the reasons that do not depend on the number.*

## DESCRIPTIVE QUESTION + ITS PROHIBITION (kept physically together, deliberately)

**ANSWERED — NULL (D, 2026-09-03, `analysis/rung_calibration.py` @ dc3b6fc).**
608 markets / 34 events, price at each rung's first two-sided live tick
against realised settlement, event-clustered: **no band's CI excludes its
own price — the board is not measurably miscalibrated anywhere.** The low
tail runs OPPOSITE to the classic bias (rungs priced 6.2% settled 11.5%),
which would make selling them a LOSING proposition rather than an edge. The
only suggestive cell is the middle (0.35–0.65 priced 0.503, settled 0.391)
and its CI still contains the price. **So the mechanism the bug appeared to
exploit is not in the data; the +$1,928 was a directional accident of 34
games.** The question below is kept with its answer and its prohibition
because the sequence — profitable bug → plausible story → measured null —
is the type specimen for rule 21.

**The question as it was asked, testable on data we own:** do far rungs on
this venue expire worthless often enough to be systematically overpriced —
the favourite-longshot bias? It surfaced as a *profitable simulator bug*
("quote to get short prints money"), which is the most suspicious possible
origin for an idea.

**Prohibition, in the same paragraph so it can never be quoted without it:
selling far rungs is the most ruin-prone strategy available to us, and a
$1,000 wallet with a stated survival condition cannot carry it.** Per-contract
loss is bounded at $1, but a naked short-tail book concentrates that bound
across many positions that all resolve the same way on the day the tail
lands. If the calibration says far rungs are overpriced, the legitimate uses
are **correcting our fair value** or **adjusting quotes inside an
inventory-bounded book** — never a naked short-tail position.

## ADDENDUM 4 (2026-09-03) — DEPTH IS THE QUEUE AHEAD OF US, NOT CAPACITY (D)

Measured while diagnosing a wallet sizing bug: depth at the quote price on
the WNBA tape runs **median 1,000 contracts, p90 5,993, max 26,540.** The
natural reading is "capacity." **The true reading is the opposite: recorded
depth at our exact price is OTHERS' resting size, and it holds time
priority.** A maker joining a price where 1,000 contracts already rest is
1,001st in line and is reached only after every one of them trades.

**Three consequences, all sharpening the picture unpleasantly:**

1. **THE FILL-OPTIMISM BOUND WIDENS.** Fill optimism has been stated as the
   mid-cross artifact (the rule books ~1.5¢/leg then the mid reverts, against
   +4.70¢ measured adverse selection on real resting orders). **Queue
   position is a SECOND, independent source of the same bias and it is in
   none of our numbers.** Every fill-dependent result — capture, markout, the
   flattening policy sim — inherits it.
2. **FLATTENING GETS BETTER-MOTIVATED, NOT WORSE.** Leaning inside the touch
   is precisely how a maker BUYS QUEUE POSITION: a price nobody else rests at
   has no queue. So this measurement strengthens the structural case for the
   lean while weakening the fill rates the sim assumed at the touch. The two
   move in opposite directions and **no instrument currently nets them.**
3. **THE GRIDIRON CELL BECOMES THREE-WAY.** Deep books at tight spreads are
   the worst combination available to a maker: no width to earn, long queues
   to wait in. So the cross-tab is not wide × traded but **WIDE × TRADED ×
   SHALLOW.**

**And the NFL board already has that cross-tab, from the T-7 hand read
(one game, all 18 types) — top-of-book size beside spread and volume:**

| market type | spread | bid×ask size | traded |
|---|---|---|---|
| full_game_winner | 0.5¢ | **14,852 × 15,111** | $919k |
| full_game_spread | 5¢ | **87 × 90** | $11.5k |
| full_game_total | 6¢ | **278 × 620** | $7.7k |
| quarter/half rungs | 19–32¢ | 1–45 | **never traded** |

**The moneyline is the trap the three-way frame predicts** — half a cent of
width behind fifteen thousand contracts of queue. **The never-traded rungs
are wide and shallow but have no counterparty.** The only cells that are
simultaneously wide enough to earn, shallow enough to reach, and actually
traded are the **main spread and total** — 5–6¢ wide, 87–620 deep, five
figures of notional. That is one game and pregame, so it is a candidate and
not a finding; but it is the first cell on the NFL board that survives all
three constraints at once, and it is where the first slate's measurement
should look first.
