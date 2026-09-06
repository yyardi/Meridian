# Alpha is anchored on the fill mid — so the pessimistic rule charges the same move twice

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

And it charges the adverse move twice. Alpha *starts* at `m_e`, the fill mid —
which is already worse than the decision mid by the measured drift of
**4.545¢ per leg**. Beginning the alpha clock at an already-penalised price
absorbs that travel implicitly. Adding 4.70¢ on top charges the same
mid-movement a second time, explicitly.

The two figures are the same quantity: PULSE's own pre-fill travel is
**4.545¢ [4.199, 4.891]** per leg, and QUOTE's constant is **4.70¢** — inside
the interval. The rule is not importing a harsher assumption; it is
re-charging a move already reflected in where alpha begins.

## What a consistent pessimistic rule would look like

Charge the travel at the **decision** anchor, where it belongs, and re-anchor
alpha with it. Then the substitution replaces PULSE's measured 4.545¢ with
QUOTE's 4.70¢ — a difference of 0.155¢ per leg, well inside the interval, and
worth roughly $7 rather than $135.54.

**The conservative rule, applied consistently, changes almost nothing.**
Nearly the entire $135.54 gap between "PULSE makes $23.65" and "PULSE loses
$111.90" is the double charge, not conservatism.

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
