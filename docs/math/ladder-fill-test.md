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
* **Leg 2 — SELL YES on the harder line ℓ_lo at its bid B_lo.**

Settlement is 0, +1, or 0 across the three margin regions; it is never
negative. Entry receives E per contract. Size = min(displayed ask at ℓ_hi,
displayed bid at ℓ_lo), and the test uses far less than that.

**Order of legs.** Take the *stale* side first — the one the maker has not
re-quoted (usually the mid-rung resting order) — because it is the one that
disappears when the maker wakes up. The other side is normal liquidity.

## Sizes and stops (registered before any episode is seen)

| | |
|---|---|
| test size | **50 contracts** (≈ $10–35 of notional per leg) |
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
