# Alpha is anchored on the fill mid — so the pessimistic rule charges the same move twice

> **The two intervals below are ~5% too narrow** (inline estimator, z = 1.96,
> no finite-sample correction; correct is CR1 √(G/(G−1)) with t at df = G−1).
> Point estimates and every dollar total are unaffected, and the load-bearing
> results here are identities and totals rather than intervals, so **nothing
> changes**. The ride/trip comparison was already reported as underpowered and
> widening reinforces that. See
> [my-clustered-intervals-were-narrow](my-clustered-intervals-were-narrow.md).

**Question:** should the +3.004¢/leg of spread that resting at the touch earns
be netted against the execution charge?

**Answer: no — and the reason exposes a larger defect.**

## Alpha is mid-anchored, on the FILL mid

`analysis/pulse_execution_decomposition.py:144`:

```python
legs = legs.rename(columns={"limit_price": "L_e", "mid_at_fill": "m_e"})
```

`m_e` **is** `mid_at_fill`, and the docstring says so: *"m_e, m_x are the
engine's mid at entry/exit fill"*. So:

```
c_e     = s·(L_e − m_e)        fill-anchored, and exactly −(markout at fill)
alpha   = s·(m_x − m_e)        starts from the FILL mid
pnl     = alpha − c_e − c_x    identity, residual $0.0000000000 on 1,944 legs
```

The **decision** mid appears nowhere. The identity closes exactly without it,
so netting a decision-anchored spread credit would import a term from an
anchor this decomposition does not use — and would break an exact identity.
Measured on the pin, `c_e ≥ 0` on **100%** of legs and `c_x ≥ 0` on 100% of
trips, so the ">= 0 by rule" comment is empirically true, not aspirational.

`c_e` per leg is **+1.541¢**, per contract **+1.825¢** — the same numbers as
the markout study, negated, as they must be.

## The anchor is bookkeeping and cannot change P&L

Re-anchor on the decision mid and every term moves, but the total does not:

| term | fill-anchored | decision-anchored |
|---|---:|---:|
| entry concession | +1.541¢ (cost) | **−3.004¢** (credit) |
| entry contribution to alpha | 0 | **−4.545¢** |
| net | −1.541¢ | −1.541¢ |

`alpha_dec = alpha_fill + drift` and `c_e_dec = c_e − static`, and the two
changes cancel identically. **Any anchor gives the same P&L.** This is the
constraint that decides the question.

## So the pessimistic rule is not conservative, it is inconsistent

Wave rule 2 replaces `c_e + c_x` with `4.70¢ × Σ contract-legs` **while
leaving alpha fill-anchored**. That is not a re-anchoring; it is one term
swapped for a quantity measured from a different origin.

| | charge | PULSE total |
|---|---:|---:|
| engine rule (`c_e + c_x`) | $85.34 | **+$23.65** |
| pessimistic (4.70¢ × 4,699.6 legs) | $220.88 | **−$111.90** |
| ratio | **2.59×** | sign flips |

**The whole sign of the headline rests on this substitution.**

The quantity it substitutes in is the **pre-fill mid travel**. PULSE's own is
**4.545¢ [4.199, 4.891]** per leg; QUOTE's constant is **4.70¢**, inside the
interval. Under the fill anchor that travel is **not a cost at all** — it is
the movement that *caused* the fill, and it is correctly absent from the
identity, which closes to the cent without it. Charging it converts a non-cost
into a $220.88 line.

I earlier called this a double charge. That is right only under one reading —
that 4.70¢ stands in for adverse selection, whose *continuing* effect does
flow through alpha (a fill selected by the mid falling through us tends to
have a worse `m_x` too). Under a strict accounting reading it is not a second
charge but a first charge on something that was never a cost. **Either way the
$135.54 is not realised execution cost**, but the two readings are not the
same claim and I should not have collapsed them.

## What the rule was actually for — verified, and it is neither

`analysis/WAVE_STANDARD.md` rule 2, in full:

> **Money at price, fees explicit, gross/net labelled.** Fills are not
> decisions: anything fill-dependent scores under the pessimistic rule with
> the measured concessions (**2.11¢ pregame, 4.70¢ in-game**). **46% of
> intents never filled** historically.

The stated concern is **selection**: fills are a filtered subset of decisions,
so scoring fills does not score the strategy. Not an opportunity-cost
counterfactual, and not arbitrary conservatism.

**But the remedy does not address the concern.** Selection is about *which
decisions became fills*; a per-fill price haircut is about *what each fill
cost*. Charging every filled leg 4.70¢ does not reweight the filled subset
toward the unfilled one — it just makes the observed subset look worse by a
constant. A real correction for "46% of intents never filled" has to say
something about what those intents would have done, which needs the unfilled
population, not a per-contract charge on the filled one.

That is a live defect in the rule itself, not only in this script's use of it,
and it is worth raising where the rule is maintained rather than patched here.

## What a consistent pessimistic rule would look like

Charge the travel at the **decision** anchor, where it belongs, and re-anchor
alpha with it. Then the substitution replaces PULSE's measured 4.545¢ with
QUOTE's 4.70¢ — a difference of 0.155¢ per leg, well inside the interval, and
worth roughly $7 rather than $135.54.

**The conservative rule, applied consistently, changes almost nothing.**
Nearly the entire $135.54 gap between "PULSE makes $23.65" and "PULSE loses
$111.90" is the double charge, not conservatism.

## The overcharge is per-file, and it depends on the base's anchor

Quant A's algebra, adopted: a **limit-anchored** base already carries the
spread credit implicitly, since
`per = s·(close − L_e) = s·(close − m_dec) + s·(m_dec − L_e)`. So subtracting
the *gross* 4.70¢ from it lands on the *net*, and is self-consistent.

| base | correct charge |
|---|---|
| limit-anchored (`roundtrip_ledger.py`'s `per`) | **gross 4.70¢** — no overcharge |
| mid-anchored, or a raw gross contract tally | **net** (~1.5–1.7¢/leg) |

`pulse_execution_decomposition.py` is the second kind — alpha is anchored on
the **fill mid** — so the overcharge is real there and only there. My earlier
statement was too broad; the ledger is clean.

## Does the concession belong on held-to-settlement legs? Cannot say

A's hypothesis: for a leg held to settlement, `pnl = s·(S − L_e)` and the
interim mid path washes out, so if adversely-filled positions also *settle*
worse, the selection is already in the outcome and charging an entry markout
double-counts it.

Tested on the information channel only — does pre-fill drift predict the
outcome measured **from the fill mid**, `s·(S − m_e)`, which contains no `L_e`
and so has no mechanical link to the entry price?

| legs | n | corr(drift, outcome) | most-adverse fills | least-adverse |
|---|---:|---:|---|---|
| **rides** (held) | 154 | **−0.033** | −18.10¢ [−23.71, −12.48] | −22.63¢ [−33.75, −11.51] |
| trips (exited) | 1,790 | −0.350 | +7.09¢ [+6.46, +7.73] | +3.86¢ [+3.28, +4.44] |

For rides the correlation is ~zero and the more-adverse bucket did *better*,
with heavily overlapping intervals. **But this does not refute the hypothesis
— it is underpowered.** Ride alpha has sd 27.8¢ at n=154 / 30 games, so the
smallest detectable two-bucket difference is **8.79¢, about 1.9× the 4.70¢
concession under test.** An effect exactly the size of the thing in question
would be invisible here. Recorded as open, not as answered.

**The trips row is a warning, not a result.** A −0.350 correlation says legs
whose mid fell hardest before filling had the *best* subsequent alpha — which
is what anchoring at a transient depressed price produces mechanically
(reversion off a low `m_e` inflates `m_x − m_e`). It vanishes for rides, where
the outcome is a 0/1 settlement that cannot bounce. So **trip alpha measured
from the fill mid is plausibly reversion-inflated**, which would touch the
$108.98 alpha total. That is a separate thread and is not established here.

## Status and limits

- Verified: the anchor (line 144), the identity (residual exactly $0), the
  sign rule (100% of legs), and both totals, on pin `20260901T195202Z`.
- **Not** verified: whether the pessimistic rule was *intended* as an
  opportunity-cost stress test against a decision-mid counterfactual. If so it
  is answering a different question — but it still may not leave alpha
  fill-anchored while doing it, because that combination is not an accounting
  of any trade.
- The recommendation is therefore narrow: **do not net the spread credit**
  (it would break the identity), and **do not read −$111.90 as PULSE's P&L
  under conservative execution**. The engine-rule +$23.65 is itself fragile —
  PULSE's filled P&L spans zero — so this changes a sign, not a conclusion.
