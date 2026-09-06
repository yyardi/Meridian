# Every interval I computed in scratch today was too narrow

Found by chasing a residue rather than by anyone catching it: my reproduction
of a published figure matched its point estimate exactly (+4.761pp) but gave a
half-width of **5.900** against the published **6.216**.

## The cause, identified exactly

The ratio 6.216 / 5.900 = **1.0536** decomposes into two standard corrections
my ad-hoc estimator omitted and the published one applies:

| | factor at G = 34 |
|---|---:|
| t critical value at df = G−1 (2.0345) instead of z = 1.960 | 1.0380 |
| CR1 finite-sample correction √(G/(G−1)) on the variance | 1.0150 |
| **product** | **1.0536** |

Reconstructed half-width **6.216** against published 6.216 — agreement to
0.0005. Not a guess at the cause; the cause.

## The repo's own estimator is correct — this is mine only

`core/quote/adverse_selection.py:294`'s `clustered_mean` applies **both**:
`correction = n_clusters / (n_clusters - 1)` on the variance and
`df = n_clusters - 1` on the critical value, with a docstring that says so.
So every figure produced through it is soundly constructed. The defect is in
the estimator I wrote inline in scratch scripts today and nowhere else.

**The size of the error grows as clusters shrink** — exactly where it is most
dangerous:

| G | factor | |
|---:|---:|---|
| 34 | 1.054 | most of today's work |
| 21 | 1.091 | the edge-quintile buckets |
| 10 | **1.216** | the >5-contract size bucket |

## Re-issued, and no verdict changes

| claim | as reported | corrected |
|---|---|---|
| entry markout per leg | −1.541 [−1.701, −1.381] | −1.541 [−1.709, −1.372] |
| entry markout per contract | −1.825 [−2.109, −1.541] | −1.825 [−2.124, −1.526] |
| pre-fill drift per leg | −4.545 [−4.199, −4.891] | −4.545 [−4.910, −4.181] |
| **drift / half-spread** (null −1.0) | −1.809 [−1.896, −1.721] | **−1.809 [−1.901, −1.716]** |
| **withdrawn mid move** (≤120s) | +3.713 [+2.608, +4.818] | **+3.713 [+2.547, +4.879]** |

Point estimates unchanged throughout. The two load-bearing claims survive:
the drift ratio still excludes the mechanical null of −1.0, and the withdrawn
arm's favourable mid move still excludes zero.

The `withdrawn − filled` paired difference is unaffected by CR1 — it is
already a game-level mean, so n = G — but should use t(32) = 2.037 rather than
1.96, widening +52.206pp [+10.461, +93.952] to roughly **[+8.8, +95.6]**.
Still excludes zero.

## Why this is worth a page

Nothing flipped, so the temptation is to fix it silently. But the error was
**systematic and one-directional** — every interval too narrow, never too
wide — and it scaled up precisely as the cluster count fell, which is the
regime where the intervals are already doing the most work. A defect that
never changes a verdict *this time* and always points the same way is the kind
that eventually changes one.

It was also invisible to every check I ran. The point estimates were right,
the identity closed, the reproduction matched to three decimals. Only a
**disagreement with someone else's interval on the same data** exposed it —
which is an argument for reproducing others' figures including their error
bars, not just their means.
