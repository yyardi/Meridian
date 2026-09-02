# The Q1 edge-source split — Quant B, 2026-09-02 (speed-1 item 1)

**Artifact:** `analysis/q1_edge_source_split.py` (self-test: engine-built
on-script rows decompose to margin_share 0.0000, pure-margin rows to
1.0000). **Pins:** `20260901T195202Z`. Decomposition is exact from the
engine's own formulas (drift inverted per row for winner/spread; the
totals anchor recovered through the module's own b/share functions —
least sensitive exactly in Q1, where this diagnostic looks).
**Instrument checks printed:** totals round-trip max err 0.00089;
winner/spread per-event recovered-drift range median 0.016 pts (the
anchor is pinned per event, and the inversion recovers it consistently);
**212 rows excluded** (6 drift-inconsistent events, p90 range 7.7 pts —
plausibly v4's flag-widened σ, which the tape does not carry).
**19 clustered intervals**, in-sample, correlated with the loss map's
197+. Exit policy fixed throughout. Descriptive — this reprices priors,
it registers nothing.

**No in-sample result justifies capital. The forward test is the evidence.**

## The answer to O1

**The Q1 flood is not anchor-driven. It is an even three-way split** —
262 anchor-driven / 249 mixed / 238 margin-driven (mean margin_share
0.46) — so roughly a third of the tip-time flood trades the model's
most-reverting input (β(4′)≈0.45, R2), and another third trades pure
anchor-vs-market disagreement. Composition nuance: Q1 has the HIGHEST
anchor-driven share of any period (later periods are almost all mixed,
as margin information accumulates into every estimate) — the flood is
*more* anchor-grounded than the rest of the tape, just not mostly so.

## The prior's prediction fails: source does not order outcomes

| Q1 class | n | games | per-$ optimistic | per-$ pessimistic |
|---|---|---|---|---|
| anchor-driven | 262 | 26 | +0.8 [−4.3, +5.9] | −31.4 [−37.8, −25.0] ◄ |
| mixed | 249 | 27 | +3.2 [−1.3, +7.6] | −23.2 [−29.0, −17.4] ◄ |
| margin-driven | 238 | 24 | +2.6 [−3.3, +8.5] | −20.7 [−26.5, −15.0] ◄ |

β(4′)≈0.45 predicted margin-driven Q1 entries underperform. In this
sample they do not — every class is flat optimistically with heavily
overlapping CIs, and under the measured concession the ORDERING is the
reverse of the prediction (anchor-driven worst). **Edge source does not
order Q1 outcomes**, which coheres with the wave's central result twice
over: claimed edge size doesn't order outcomes (Track C), and trip P&L
is decoupled from belief correctness (the coupling result) — so it is
decoupled from belief *source* too. The roll's payoff comes from
oscillation and exit availability, not from why the model thought it
had an edge.

One cell of nineteen shows a ▷ (Q1 mixed, edge ≥10¢: +11.7 [+7.2,
+16.3], 76 fills/18 games) — at 19 intervals on re-mined data, noted
and left alone.

## What this reprices (per the synthesis's framing)

* **O1's oddity is neither vindicated nor damning**: the flood is not
  the model naively chasing early margins (source mix is even, and the
  margin-driven third performs no worse), but neither is Q1 a
  distinguished anchor window (anchor-driven Q1 is the WORST class
  under the pessimistic arm).
* **A1's interpretation**: ordering claims about early entries cannot
  lean on "margin-driven = suspect" — the suspect class isn't
  differentially bad in realized per-$. Whatever A1's oscillation
  ordering finds, it is not explained by edge source.
* **The crossing family's priors**: no support here for
  source-conditioned crossing (e.g., "cross only anchor-driven
  disagreements") — in-sample, the sources are indistinguishable on
  outcome.

**No in-sample result justifies capital. The forward test is the evidence.**
