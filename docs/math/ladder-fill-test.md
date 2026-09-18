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
