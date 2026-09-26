# The ladder fill test — pre-registered, 2026-09-18

**Question.** On Polymarket US, when a live-game spread ladder contradicts itself
(STATUS 0bu/0bv), does an order at the *displayed* size on the mispriced rung
actually fill? Everything else in the chain is measured; this is the one link
that is not, and no amount of observation can measure it.

**Who places it.** The operator, by hand. Meridian places nothing; the sampler
only pushes the two legs.

## The trade

For lines ℓ_lo < ℓ_hi on the same team (YES = away), with taker fee
f(p) = 0.06·p·(1−p):

    E = B_lo − A_hi − f(A_hi) − f(B_lo)        violation iff E > 0

* **Leg 1 — BUY YES on the easier line ℓ_hi at its ask A_hi.**
* **Leg 2 — BUY NO on the harder line ℓ_lo at (1 − B_lo).** This is the UI's
  form of "sell YES at B_lo" and is the identical position.

Why it cannot lose, in the buy-NO form. The pair costs A_hi + (1 − B_lo) per
contract and pays at settlement:

| margin region | YES(ℓ_hi) | NO(ℓ_lo) | paid |
|---|---:|---:|---:|
| harder line covers | 1 | 0 | 1 |
| only the easier covers | 1 | 1 | **2** |
| neither | 0 | 1 | 1 |

Paid is ≥ 1 in every region; cost is 1 − (B_lo − A_hi). So the guaranteed
profit is B_lo − A_hi − fees = E > 0, with a bonus of +1 if the margin lands
between the lines. **The only ways to lose money:** (a) leg 1 fills and leg 2
does not — you then hold a small directional bet worth at most what you paid
for it; (b) clicking the wrong side. The alert names the button.

**Funding.** At the $189-shape prices (YES 0.22, NO 0.735) 15 contracts each
cost about $14.30 and pay $15.00 plus $15 more if the margin lands between the
lines. **$15 funds one attempt of ~15 contracts.** The registered 5-attempt
rule at 50 contracts needs roughly $50–100 depending on prices. One attempt
still answers the binary question — *does displayed size fill at all* — which
is the question; five attempts answer *how reliably*.

**Order of legs.** Take the *stale* side first — the one the maker has not
re-quoted (usually the mid-rung resting order) — because it is the one that
disappears when the maker wakes up. The other side is normal liquidity.

## Sizes and stops (registered before any episode is seen)

| | |
|---|---|
| test size | **15 contracts** with the current $15 balance (≈ $14 for both legs); 50 once funded |
| alert floor | episodes with E × min-size ≥ **$25** |
| rung filter | prefer mid-ladder pairs (+3.5 … +20.5) — where 0bv found the money and the minutes |
| if leg 1 fills and leg 2 does not within 60s | do NOT chase; you hold 50 YES on ℓ_hi — record it, let it settle or close at market |
| if leg 1 does not fill | stop; record; that is a result |

## What to record per attempt

time (UTC); pair; A_hi and B_lo as alerted; displayed sizes; size placed;
for each leg: filled? how many? at what price? seconds to fill; the alert's E.

## Decision rule (registered)

Over the first **5 attempts**:

* **≥ 3 attempts with both legs filled ≥ 80% of size at alerted prices** →
  displayed size is real; the per-game figure in 0bv is a valid floor and the
  next build is the multi-game scheduler.
* **≥ 3 attempts where leg 1 does not fill at all** → resting size is phantom;
  the ladder lead closes on executability, like the wide book (0bi/0bj).
* anything else → NOT YET; extend to 10 attempts before reading it.

**What would make me withdraw the whole finding:** the *same* rung showing
displayed size that vanishes on contact in ≥ 3 of 5 attempts. That is the
quote-stuffing explanation and it is the only one left that fits the tape.

## Amendment 2026-09-18 — Placement via the dashboard (operator's instruction 2026-09-18)

**What changes.** Legs may now be sent from the ARB tab's SEND (`/arb`, `POST /api/arb/send`)
instead of by hand at the venue's screen. The path is: the operator's order token in the
page, a first click on the ticket's SEND, a confirmation ticket that spells every term in
words (row, button, side, price, quantity, pair cost, guaranteed amount, stake), an explicit
acknowledgement, and a second click on a different element. Meridian never sends without
that second human click; there is no path from a sampler, an executor or a poll to the venue.

**How the legs go.** Both legs are `IMMEDIATE_OR_CANCEL` synchronous limit orders at the
ticket's prices (one tick of slack, no re-pricing), not the post-only GTC every prior order
used. Leg 1 (the stale side) is sent first and alone. Leg 2 is sent only for the quantity
leg 1 filled, and not at all if leg 1 filled nothing. An IOC rests nothing, so "leg 1 fills
and leg 2 does not" is the same first-class outcome as in the hand protocol, with the same
rule: record it, let it settle or UNWIND at the touch; do not chase.

**What is recorded.** Fills come from the venue's synchronous response (state, cumulative
quantity, average price), written to the orders table per leg and to `ladder_attempts.jsonl`
as a `recorded` attempt, so the tally below counts a dashboard send exactly as it counts a
hand-placed one. A `recorded` attempt is written **only when every sent leg's fill was
observed**: the venue accepted the leg and either filled something or ended the order in a
terminal state. A venue refusal, an unreadable reply, a zero fill in a pending state
(`PENDING_NEW`, `NEW`: no `maxBlockTime` is sent, so whether the venue blocks until an IOC is
terminal is unobserved) or a leg-2 transport error is protocol noise, not a fill observation;
it is written as `placed` with the outcome named, and the operator records the real fill by
hand once the fill watcher has reconciled the rows. The tally's "leg 1 filled nothing" count
therefore cannot contain a 401. The record carries the quantity actually sent per leg
(`l1_sent`, `l2_sent`) and the tally's 80 % is measured against that, not the ticket, when a
send went for less than the ticket. The decision rule above is **unchanged**: the same five
attempts, the same 80 % / zero-fill thresholds, the same withdrawal condition.

**Sizes and caps.** Quantity is at most the ticket's (any size from the venue minimum up to
it; never above it unless the operator has set `MERIDIAN_ARB_ALLOW_SIZE_UP=1`, and then never
above displayed size); each leg's stake is under the per-order cap (`MERIDIAN_MAX_ORDER_STAKE_USD`)
as well; the pair stake is capped at `MERIDIAN_ARB_MAX_PAIR_USD` (default $25) or the
last-read account balance when one is available, whichever is smaller (an unreadable balance
falls back to the configured cap, a stated policy, never to a guessed bankroll); the pair's
cost plus the scanner's taker fees must be under $1.00 after any one-tick nudge, or the send
is refused as a locked loss; spread rungs only; a LOCKED desk refuses the send. UNWIND is
deliberately exempt from the lock: it is the operator's way out of a half-filled pair, and
locking the desk must not lock them in. It still needs the token, the literal and the
acknowledge flag, never sells more than the venue reported filled, and prices "at market" only
from a ladder sample younger than two sample intervals.

**Not yet exercised live.** The synchronous reply shape (`executions[].order.state`,
`cumQuantity`, `avgPx`) is the create-order document's and had not been observed on a real
order when this was written. The first live send is the first observation of it: the whole
reply body is logged for both legs (the `arb_send` event) and returned to the page; the row
keeps the refusal body on a rejection. Where a reply carries several priced executions the
VWAP of `lastPx × lastShares` is the recorded average and a disagreement with the reported
`avgPx` is logged, because the document does not say whether a per-execution `avgPx` is
cumulative.

## Amendment 2026-09-26 — the ticket gate is sized to the attempt, not to the display

The operator, testing with about $20: *"idk why u have the $25 limit, it dont
gotta be that high."* Right. The $25 alert floor above is **edge × the FULL
displayed size** — a statistic about what the venue showed, never about
anyone's bankroll — and it stood between a $20 test and every crossing whose
thin leg showed twenty-odd contracts at a good edge but whose full size was
small. From today the ticket gate is the operator's (`core/ladder/intent.py`):

- **attempt** = `MERIDIAN_ARB_ATTEMPT_USD`, default **$20**; a ticket is sized
  to it (`qty = attempt ÷ pair cost`, ~21–23 contracts of a $0.85–0.95 pair),
  never above the thin leg;
- a crossing is a **ticket** when the thin leg displays at least that many
  contracts **and** the net edge is ≥ **2c** per contract (rounded to a
  hundredth of a cent first);
- the desk's `candidate` flag, both executors and the planner's launch line
  carry the same number; the pair cap `MERIDIAN_ARB_MAX_PAIR_USD` ($25) still
  bounds a send.

The $25 floor stays as the **ledger's statistic** (`>= $25` columns), and the
ledger gains `tkt@$20 / profit / life`: how many crossings a $20 attempt could
have ticketed, what twenty contracts of each would have netted, and how long
they stood. The decision rule (five attempts, 80 % / zero-fill) is unchanged;
its **size** is now the attempt's contracts rather than the 15 registered on
a $15 balance.
