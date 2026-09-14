# The scan programme — pre-registration, written before the first scan

2026-09-14. Registers the decision procedure for a ~50-strategy-per-week,
400–600-cell scan (league × market type × price decile × side) **before any cell
is scored**, so that what counts as a result is fixed in advance.

---

## 0. The finding that has to come first

**Slicing does not create information. It divides a fixed amount of it and adds
a multiplicity bill on top.**

CFB produces about **45 game-clusters a week**. Eight weeks is ~360. The
game-clustered interval is governed by G, not by rows, so:

| what is tested | G at 8 weeks | minimum detectable effect |
|---|---:|---:|
| CFB, all rungs pooled | 360 | **7.40¢** |
| CFB, one decile × side | 238 | 9.10¢ |
| CFB, decile × side × 3 market types | 79 | **15.79¢** |

Against a measured cost hurdle of **~2.1¢**. **The 500-cell design is the
bottom row.** This is not an argument against breadth — it is the reason the
scan must be a **screen**, and the reason its primary output must be the
**distributional** test, which pools what the cells divide.

### What a conclusive negative would require

A family is **conclusive** when its minimum detectable effect drops **below the
cost hurdle** — then anything undetectable is also untradeable and a null is a
real answer rather than an absence of evidence.

| family | cell G / week | G needed | weeks |
|---|---:|---:|---:|
| CFB spread | 30 | 4,467 | **150** |
| NFL spread | 11 | 4,467 | 423 |
| MLB winner | 10 | 4,467 | 425 |
| TT winner | 109 | 3,461 | **32** |

**No family reaches a conclusive negative inside a season at the per-cell
level.** And table tennis, the only one close, is **dyadic**: its effective
sample caps at `P/(2ρ)`, giving a best-ever MDE of **4.1¢ at ρ=0.05 and 10.1¢ at
ρ=0.30 — never below its 2.72¢ hurdle** unless the player pool grows.

> **This must be stated in every write-up: after eight weeks the programme can
> rule out edges above roughly 5–15¢ depending on family. It cannot rule out
> edges between the hurdle and that bound. "We found nothing" and "nothing is
> there" are different sentences and only the first will be true.**

---

## 1. The family, and the decision procedure

**The scan is a SCREEN. It never decides anything.** It may only nominate
families for a pre-registered held-out read; the held-out read carries the small
family and makes the decision.

### Why the split is worth having

| m | Bonferroni \|z\| |
|---:|---:|
| 500 (the scan) | **3.89** |
| 10 (nominations) | **2.81** |
| 1 | 1.96 |

**The split buys 1.08σ**, which at fixed G is the difference between a 9¢ and a
6¢ detectable effect. It is the single highest-leverage design choice available.

### What the null already produces, so nobody is impressed by it

**In a 500-cell scan with NO edge present, the best cell shows |t| ≈ 2.9**, and
**P(some cell exceeds |t|=3) = 0.74**. A "we found a 3-sigma cell" headline is
the *modal output of pure noise* at this m. Every scan report must print the
expected null maximum beside the observed maximum.

### FDR versus a hard threshold — what q buys, and what it does not

BH at q compares the k-th smallest p to `k·q/m`. **Its first rejection is no
easier than Bonferroni** (q=0.10, m=500 → |z| 3.72 vs 3.89); it only relaxes
when several cells are real at once (10th rejection → |z| 3.09).

> **Registered: use BH at q = 0.10 for NOMINATION only.** FDR is the right
> shape for a screen because it changes the guarantee from "probably no false
> positives" to "about one in ten nominations is spurious" — and stage 2 is what
> kills that one. **FDR must never be used to license a decision**, because a
> 10% false-discovery rate is not a standard anything gets traded on.

**Nomination cap: 10.** More nominations raise the stage-2 threshold (m=20 →
3.02) against finite held-out data. If BH returns more than 10, take the 10
smallest p and record how many were dropped.

### Stage 2 rules

- **Disjoint data, by time.** A nominated cell is read on weeks strictly after
  the week that nominated it. Never re-read the nominating tape.
- **Fixed horizon, read ONCE.** Each nomination gets a pre-declared number of
  weeks and is read at the end. **No peeking** — a sequentially-monitored cell
  carries its own multiplicity and none of the thresholds here apply to it.
- **Power for the TRUE effect, not the observed one.** A cell nominated for
  having the largest t among 500 is inflated by selection. **Stage 2 must be
  powered against half the nominating effect size**, and the write-up must state
  the nominating estimate and the held-out estimate side by side.

---

## 2. The distributional test — the primary output

**This is where the programme has real power**, because it pools across cells
what the per-cell tests divide.

Under "a fraction ε of cells carry non-centrality μ", `Var(t) = 1 + ε·μ²`:

| real cells (of 500) | μ=2 | μ=3 | μ=4 |
|---:|---:|---:|---:|
| 5 | 1.040 | 1.090 | 1.160 |
| **10** | 1.080 | **1.180** | 1.320 |
| 25 | 1.200 | 1.450 | 1.800 |

> **Ten cells at μ=3 give Var(t)=1.18 — detectable — while not one of those
> cells clears the m=500 bar of 3.89. The pool sees what the parts cannot.**

### The statistic

Report **three**, because they answer different alternatives:

1. **Var(t) across cells** — powerful against a *dense* alternative (many small
   effects).
2. **Higher Criticism**, `max_i √m·(i/m − p_(i))/√(p_(i)(1−p_(i)))` over the
   smallest ~10% of p-values — the standard statistic for a *sparse* mixture,
   and the sharpest tool for "a few cells are real among many".
3. **max |t| against the permutation null's max |t|** — directly answers "is the
   best cell better than the best cell of noise".

### The permutation null is not optional, and the naive SE is wrong in the dangerous direction

Cells share games, so their t's are **positively correlated** and the textbook
`SE(Var) = √(2/m) = 0.063` is **too small**. Using it would manufacture
significance. **The permutation null — settlements shuffled within games —
reproduces the dependence and is the only valid reference.** Every distributional
statistic is read against its permutation distribution, never against theory.

### The planted-edge control must be able to fail

A control that cannot fail tests nothing. **Registered:**
- Plant an edge **at the MDE**: the harness must recover it **≈50%** of the time.
- Plant at **2× MDE**: must recover **≈95%**.
- **Recovery materially above those rates means the harness is leaking** —
  look-ahead, reused tape, or a shuffle that failed to break the link.

The control is run on the same pipeline as the real scan, with no branch that
distinguishes them.

### What "the distribution is too wide" licenses — and does not

> **It licenses exactly one thing: nominating cells for a held-out read.**

It does **not** license a decision, an effect size, or any claim about a
particular cell. **A significant distributional statistic is not evidence for
the top cell** — the top cell's inflation is part of what the statistic is
detecting.

**The more valuable direction is the negative.** If the observed distribution
matches the permutation null, that is a *strong, global* statement about the
venue at our resolution — and it is available in **week one**, because it pools
all 500 cells. **That is the programme's fastest real result and it should be
reported first every week.**

---

## 3. Ineligibility — decided before scoring, not argued afterwards

A cell is **reported** but **not scored, not counted in m, and not eligible for
nomination** if any of the following holds.

1. **Exact complement.** Its row set is identical to another cell's with the
   opposite side. `pnl_A + pnl_B = −(spread + both fees)`, a constant, so the
   pair is one statistic. **Five such pairs are already labelled.** Detect by
   probing the rules over a price grid and comparing selected row sets — a
   complement is invisible in source and obvious in its selection.
2. **Twin-is-the-same-rows.** Any grid printing a cell once as a "main" and once
   as a mirror's "twin" — count **distinct statistics**, never printed cells.
   (The decomposition grid prints 20 and computes 10.)
3. **Below the G floor.** The floor is **not arbitrary**: it is the G at which
   the cell *could* clear its nomination threshold at a plausible effect size.
   A cell that cannot produce a nomination under any outcome only adds to m.
4. **Sampling shares a cause with the hypothesis.** Anything on hand-swept tape
   where capture probability and the tested effect have a common driver — e.g.
   within-day sequence effects on a board where schedule slippage governs both
   capture and fatigue.
5. **Bucket assigned from a stale or noisy price.** If the price used to assign
   the decile carries error comparable to the decile width, assignment is
   regression to the mean. Ineligible unless price freshness is small relative
   to bucket width; report `mins_before` per cell.
6. **Wrong cluster.** Dyadic families (two participants per event) need
   two-way dyadic-robust intervals; a game-clustered interval there is wrong.
   Ineligible until the correct estimator is used, with `deff` and `n_eff`
   printed beside the cell.
7. **In-sample.** A cell on the tape that generated its own hypothesis is
   screen-only, permanently. It can never be a stage-2 read.
8. **Dead decision rule.** If no achievable outcome changes the cell's verdict,
   it is ineligible. Project the rule onto the outcome range before scoring.

**Every excluded cell is listed with its reason in the weekly output.** Silent
exclusion is how a family shrinks without anyone deciding to shrink it.

---

## 4. The stopping rule, and the sentence written in advance

**Horizon: 8 weeks.** Read at the end; nominations made weekly, stage-2 reads on
strictly later weeks.

### The pre-committed conclusion

> **If eight weeks of screening produce no cell that survives a pre-registered
> held-out read, we conclude that no edge LARGER THAN THE BOUND WE ACHIEVED
> exists in the markets scanned, at our cost structure — and we state that bound
> explicitly, by family, rather than reporting "nothing found". On current
> accrual that bound is approximately 7¢ for CFB, 15¢ for NFL and MLB, and 5¢
> for table tennis. Edges between the ~2¢ hurdle and those bounds are NOT ruled
> out and the programme will not have addressed them.**

### And the second sentence, which matters as much

> **If the distributional test also matches the permutation null in every one of
> the eight weeks, that is a stronger and more useful result than any individual
> cell would have been: it says the venue's prices carry no exploitable
> structure at the resolution we can measure. That finding would justify
> stopping the scan and redirecting the effort — to families where G accrues
> faster, or to reducing the cost hurdle, which moves the bar for every cell at
> once.**

### What would justify continuing past 8 weeks

Exactly one thing, declared now: **a distributional statistic outside its
permutation null in at least two separate weeks, with the excess not attributable
to a single family.** One week is a look; two independent weeks is a pattern.
Anything else — a striking cell, a near-miss, a plausible story — is not grounds,
and if it is argued for after the fact that argument must be **written down and
dated before it is acted on**.
