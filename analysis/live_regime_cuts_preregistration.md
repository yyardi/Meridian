# Pre-registration: does the live model's tie hide a winning regime?

Committed before any point estimate is computed. Cuts fixed here on **power**,
not on results — the half-widths below were measured with the point estimates
suppressed.

Substrate: `pulse_decisions_20260906T174104Z.csv.gz`, entered branch, joined to
`resolved_outcomes` (d5 validated at 1.0000 agreement, zero disagreements).
**2,974 rows, 34 games.** Statistic: `Brier(market) − Brier(model)`, positive =
model wins. Row-weighted cluster-robust sandwich, t at df = G−1, clusters are
games. Basis: entered branch only, all rows (no dedupe), so weights are rows.

## ★ POWER FIRST — measured, point estimates not computed

Pooled half-width **0.0154**. Effects this programme has ever measured are
**0.010–0.018**, so the pooled test is already at the edge.

| cell | n | G | half-width | resolves 0.010–0.018? |
|---|---:|---:|---:|---|
| minutes_left 0–10 | 379 | 26 | 0.0141 | yes |
| minutes_left 10–20 | 532 | 30 | 0.0398 | **no** |
| minutes_left 20–30 | 803 | 29 | 0.0208 | marginal |
| minutes_left 30–41 | 1,260 | 31 | 0.0132 | yes |
| \|margin\| 0–4 | 1,149 | 31 | 0.0099 | yes |
| \|margin\| 4–10 | 902 | 34 | 0.0197 | marginal |
| \|margin\| 10–99 | 923 | 30 | 0.0275 | marginal |
| **late(<10m) AND close(\|m\|<4)** | **48** | **5** | **0.0416** | **no** |
| \|fv−mid\| 0–0.05 | 1,298 | 33 | 0.0021 | yes |
| \|fv−mid\| 0.05–0.10 | 899 | 33 | 0.0079 | yes |
| \|fv−mid\| 0.10–1 | 777 | 32 | 0.0555 | **no** |

**The interaction cell — "late and close", the obvious place to look — has 48
rows across 5 games and cannot resolve anything.** Its half-width is 2.7× the
largest effect ever measured here. **It is registered as underpowered now, and
whatever it shows will be reported as underpowered**, including if it shows a
large positive.

## ★ MULTIPLICITY, DECLARED BEFORE THE COUNT

**Eleven cells will be inspected.** At 95% that is an expected 0.55 false
positives, so **one cell clearing zero is the null's ordinary behaviour.**

Bonferroni at 11 tests widens every interval by ≈1.45×. Applying that to the
table above, only **three** cells can still resolve a 0.010–0.018 effect:
`|margin| 0–4`, `|fv−mid| 0–0.05`, `|fv−mid| 0.05–0.10`.

## ★ THE DECISION RULE

A regime counts as found only if **either**:

* **(A)** a cell's interval excludes zero at the **Bonferroni-corrected** level
  (11 tests), **or**
* **(B)** a cut family shows a **monotone ordering across all its bands** with
  the two extreme cells' uncorrected intervals disjoint from each other.

Anything else — including one or two uncorrected cells clearing zero — is
reported as **no regime found**, with the cell values shown and labelled as
not meeting the rule.

**If no cell can resolve an effect of the size we have measured, the exercise
is reported as underpowered and the cell results are not interpreted.** That
branch is live: five of eleven cells already fail the uncorrected threshold.

## What is fixed and cannot change after this commit

The eleven cells, the statistic, the basis (entered branch, all rows,
row-weighted), the clustering, the 11-test multiplicity count, and the two-part
decision rule. No cell may be added, split, or re-bounded after the numbers
exist. If a band looks interesting at a boundary, that is not a reason to move
the boundary.

---

## RESULT — decision rule applied, 2026-09-06

Pooled −0.00370 [−0.01910, +0.01170].

| cell | n | G | diff | 95% CI | Bonferroni CI |
|---|---:|---:|---:|---|---|
| minutes_left 0–10 | 379 | 26 | −0.01626 | [−0.0304, −0.0021] * | [−0.0376, +0.0051] |
| minutes_left 10–20 | 532 | 30 | −0.01835 | [−0.0582, +0.0215] | [−0.0783, +0.0416] |
| minutes_left 20–30 | 803 | 29 | +0.00246 | [−0.0183, +0.0232] | [−0.0288, +0.0338] |
| minutes_left 30–41 | 1,260 | 31 | +0.00233 | [−0.0108, +0.0155] | [−0.0174, +0.0221] |
| \|margin\| 0–4 | 1,149 | 31 | +0.00426 | [−0.0057, +0.0142] | [−0.0107, +0.0192] |
| \|margin\| 4–10 | 902 | 34 | −0.00462 | [−0.0244, +0.0151] | [−0.0342, +0.0249] |
| \|margin\| 10–99 | 923 | 30 | −0.01272 | [−0.0402, +0.0147] | [−0.0540, +0.0286] |
| late AND close **[underpowered]** | 48 | 5 | +0.00011 | [−0.0415, +0.0417] | [−0.0860, +0.0862] |
| \|fv−mid\| 0–0.05 | 1,298 | 33 | +0.00050 | [−0.0016, +0.0026] | [−0.0027, +0.0037] |
| \|fv−mid\| 0.05–0.10 | 899 | 33 | −0.00125 | [−0.0092, +0.0067] | [−0.0131, +0.0106] |
| \|fv−mid\| 0.10–1 | 777 | 32 | −0.01356 | [−0.0690, +0.0419] | [−0.0968, +0.0697] |

**NO REGIME FOUND.** Neither branch of the rule is met.

* **(A)** Zero of eleven cells clear zero at the Bonferroni level.
* **(B)** `minutes_left` is not monotone (−0.016, −0.018, +0.002, +0.002).
  `|margin|` and `|fv−mid|` are both monotone decreasing, but neither family's
  extreme intervals are disjoint — they overlap heavily.

**One cell cleared uncorrected** (`minutes_left 0–10`, −0.01626), against 0.55
expected by chance over eleven cells. It is also **negative**: the model is
worse in the last ten minutes, not better. It does not meet the rule and is not
a finding.

The interaction cell resolved to +0.00011 with a ±0.042 interval, exactly as
registered — underpowered, and reported as underpowered rather than as a null.

**Direction not meeting the bar, recorded as direction only:** both `|margin|`
and `|fv−mid|` order the same way — the model does relatively worse the further
it is from the market and the more lopsided the game. Consistent with a large
model–market gap being evidence of a stale model rather than an edge, which is
what the pregame gate analysis also showed. Neither family clears the rule.
