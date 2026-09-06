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
