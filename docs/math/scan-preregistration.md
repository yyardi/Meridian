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

**Rate is not stock.** The 109 cell-G/week for table tennis is an **accrual
rate**; the **settled stock is ~35**, because 91–100% of listed TT markets have
not started at any moment. **A scan run this week gets the stock, not the rate.**
Weight the grid on settled counts, never on a projection.

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

### ⚠ Var(t) has NO fixed null baseline — the baseline is a function of G

**A cluster-robust t is referenced to t(G−1), whose variance under the pure null
is `(G−1)/(G−3)`, not 1.** At the cell sizes this scan actually produces:

| G | null Var(t) |
|---:|---:|
| 10 | **1.286** |
| 12 | 1.222 |
| 25 | 1.091 |
| 30 | **1.074** |
| 79 | 1.026 |

**Week-one cell G is CFB spread 30, NFL spread 11, MLB winner 10** (§0). So a
scan with **no edge anywhere** produces Var(t) ≈ **1.07–1.29** depending on the
family mix. An uncorrected reading of "Var = 1.18 means ten real cells" is
**indistinguishable from the null's own output.**

> **REGISTERED: Var(t) is never reported alone. It is always printed beside
> `baseline = mean over cells of (G−1)/(G−3)`, and only the EXCESS
> `Var(t) − baseline` is interpretable.** The increments below are excesses over
> that baseline, not absolute values.

| real cells (of 500) | μ=2 | μ=3 | μ=4 |
|---:|---:|---:|---:|
| 5 | +0.040 | +0.090 | +0.160 |
| **10** | +0.080 | **+0.180** | +0.320 |
| 25 | +0.200 | +0.450 | +0.800 |

> **Ten cells at μ=3 give an excess of +0.18 — detectable — while not one of
> those cells clears the m=500 bar of 3.89. The pool sees what the parts
> cannot.** That claim survives the correction; only its baseline moves.

### Two further consequences of the same fact

**Var(t) is undefined below G=6.** The sampling variance of a variance needs a
finite fourth moment, and t(ν) has one only for **ν > 4**. A cell with **G ≤ 5
makes the statistic infinite-variance, not merely noisy** — so the G floor of §3
is required by the *distributional* statistic, not only by per-cell power.

**And its SE is inflated by t's heavy tails**, by `√((κ−1)/2)` — **1.26× at
G=10**, 1.06× at G=30. Another reason the permutation null, not theory, sets the
reference.

> **Because of all this, HIGHER CRITICISM is promoted to the PRIMARY statistic
> and Var(t) demoted to secondary.** HC operates on p-values, which are uniform
> under the null **regardless of G** provided each cell's p is computed against
> its own t(G−1). **HC is automatically calibrated across a ragged-G scan where
> Var(t) is not.**

### The HC promotion is CONDITIONAL — a validity check that can fail

HC has **two demonstrated failure modes that look identical in a summary table**:
unclamped it divides by `√(p(1−p))` and returned p99 **2,864** / max **10,626**
on pure null data; the textbook HC+ restriction then made it **identically 0.00
across 400 null replicates and the observed value** — dead rather than
conservative. A denominator-clamped version measured a null range of
**1.06–1.08 at m=29**, nearly saturated.

**A reference implementation does not reproduce that saturation.** Denominator-
clamped, 600 replicates:

| m | null p50 | null p95 | IQR | distinct values |
|---:|---:|---:|---:|---:|
| 29 | 0.550 | 1.683 | **1.130** | 600 / 600 |
| 250 | 1.218 | **3.103** | 1.132 | 599 / 600 |
| 500 | 1.303 | 3.165 | 1.228 | 600 / 600 |

and it is **responsive at m=29** (98–100% power against 5–25 planted cells at
μ=3). **So saturation to a 0.02-wide range is a property of an implementation,
not of HC at small m** — it should be diagnosed, not accepted.

**Note the m that matters is `m_eff ≈ 250`, not 500**, after the side-axis
collapse. At m=250 HC retains full spread and **97.3% power against 10 cells at
μ=3**.

> **REGISTERED — run on the permutation replicates at the real m, BEFORE the
> observed HC is read:**
>
> **(a) Spread.** Null IQR ≥ 0.5 HC units over ≥400 replicates, and ≥100
> distinct values. *(Reference: 1.13.)*
> **(b) No boundary pile-up.** <5% of null replicates at the extreme value the
> clamp can produce.
> **(c) Responsiveness — decisive.** Plant 10 cells at μ=3 into permuted data;
> **HC must exceed its own null p95 in ≥80% of planted replicates.**
> *(Reference 97.3%; a dead statistic gives ~5%.)*
> **(d)** The observed HC must not equal a clamp boundary.

### If HC fails the check, this is primary instead — declared now

Measured at m=250, power against the null p95 of each statistic:

| scenario | HC | count(p<.01) | max\|t\| |
|---|---:|---:|---:|
| 5 cells at μ=3 | 65.8% | 53.8% | **79.3%** |
| 10 cells at μ=3 | **97.3%** | 96.2% | 96.2% |
| 10 cells at μ=2.5 | **84.5%** | 73.7% | 72.0% |
| 25 cells at μ=2.5 | 100% | 100% | 96.7% |
| 50 cells at μ=2.0 | 100% | 100% | 90.0% |

**HC is the best all-rounder; max|t| wins at extreme sparsity; the count is
never best but never bad — and it cannot break** (no division by a small
number, bounded, no moment requirement, exact under permutation).

> **REGISTERED: if HC fails (a)–(d), `count(p < 0.01)` becomes primary with
> `max|t|` reported beside it. All three are reported every week regardless, so
> a disagreement between them is visible rather than resolved by choice.**
> **No statistic may be selected after its value is seen.**

### Correcting my own over-statement

I wrote that Var(t) "is not usable across a ragged-G scan". **Too strong.** Read
against the **permutation** null it is perfectly valid — the permutation
reproduces each cell's realized G, so the `(G−1)/(G−3)` inflation is embedded in
the reference distribution automatically. **My objection was to reading it
against a THEORETICAL baseline of 1**, which is an interpretability defect in the
printed number, not a validity defect in the test. **The G ≥ 6 floor still
stands, but for POWER** — small-ν cells have heavy tails and dominate the
variance — **not for validity.**

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

1. **Exact complement — and this collapses the SIDE AXIS of the whole grid.**
   `net_YES = y − a − f(a)` and `net_NO = b − y − f(b)`, so
   **`net_NO = −net_YES + c`** with `c = −(spread + both fees)`, a per-market
   constant. A YES cell and its NO cell are **the same markets**, so
   **`t_NO ≈ −t_YES`**, every deviation is counted twice, and Higher Criticism
   sees each real cell as a matched `p` and `1−p`.

   > **REGISTERED: score ONE side per (market, bucket); print the twin by
   > identity. `m_eff ≈ 250`, not 500, which hands back 0.17σ on the threshold
   > for free.**

   The count-excluding-zero null band widens by **√2, not 2**: 250 pairs each
   contributing 0 or 2 gives sd **6.89** against the naive **4.87**
   (95%: 25 ± 13.5 versus 25 ± 9.6). **√2 is an upper bound** — the constant `c`
   shifts `t_NO` off exactly `−t_YES`, so some pairs split one-and-one and the
   real inflation is less. One more reason to read the band off the permutation
   null rather than a formula.

   **This is the third appearance of one property in a day** — five complement
   pairs in the paper-book registry, ten-distinct-of-twenty printed cells in the
   decomposition grid, and now the scan's side axis. **It is a structural
   property of this venue's two-sided markets, not three coincidences.** Any new
   grid must be checked for it before m is counted: probe the rules over a price
   grid and compare selected row sets — a complement is invisible in source and
   obvious in its selection.
2. **Twin-is-the-same-rows.** Any grid printing a cell once as a "main" and once
   as a mirror's "twin" — count **distinct statistics**, never printed cells.
   (The decomposition grid prints 20 and computes 10.)
3. **Below the G floor.** Two binding constraints, neither arbitrary:
   **(a) G ≥ 6 absolutely** — below that `t(G−1)` has no finite fourth moment and
   the Var(t) statistic has infinite sampling variance;
   **(b)** the G at which the cell *could* clear its nomination threshold at a
   plausible effect size. A cell that cannot produce a nomination under any
   achievable outcome only adds to m.
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

---

## AMENDMENT 1 — 2026-09-14: the primary score becomes the binomial win count

**This is a change to the registered statistic, not a patch to the harness.** It
was made after the first pass was scored and before any cell was nominated; the
figures that prompted it are below so the amendment can be judged, not trusted.

### What happened

Two implementations of this grid — written independently, no shared code — were
run against the same tape. Both produced an apparently enormous global effect:

| | manager's pass | quant-b's pass |
|---|---:|---:|
| max \|t\| | 30.01 | 31.543 |
| Var(t) | 17.282 | 18.637 |
| cells excluding zero | 54 of 324 | 62 of 324 |

**In both, every one of the top twelve cells was outcome-homogeneous** — every
bet in the cell resolved the same way. When that happens the P&L has no outcome
variance left, so the game-clustered sandwich SE collapses onto the band's price
dispersion and `|t|` explodes. Removing the degenerate cells took the manager's
figures to max |t| 5.87 and Var(t) 1.308.

Against a binomial on the win count of the *same cell*, the t overstates the
evidence by **five to thirty orders of magnitude**:

| cell | n | k | p from t | p binomial |
|---|---:|---:|---:|---:|
| cfb full_game_winner dec 0.2 | 12 | 0 | 3.9e-12 | 6.3e-02 |
| nfl 1q_spread dec 0.0 | 68 | 0 | 7.9e-33 | 6.1e-02 |
| cfb 2q_total dec 0.8 | 46 | **46** | 1.2e-25 | **1.3e-02** |
| tabletennis winner dec 0.7 | 6 | 6 | 6.6e-06 | 3.6e-01 |

> **CORRECTION, same day, at the table rather than below it.** The `k=46` row
> above first read `k=44`, and its binomial p first read 4.7e-02. **I had backed
> the win count out of each cell's mean and price instead of reading `y`** — a
> reconstruction, where a binomial p depends on `k` exactly. Read directly from
> the settlements the cell is **46 of 46**, which also makes it *degenerate* and
> moves it from the scored set into the excluded set.
>
> When the manager corrected me I defended the old number with a second
> reconstruction — inferring the cell's mean ask from the decile midpoint (0.855)
> and arguing a 3.2¢ gap proved a membership difference between our two scans.
> The real mean ask is **0.889**: asks sit near the top of a `[0.8,0.9)` *mid*
> band, not in its middle. **There was no membership difference. It was the same
> reconstructed-not-observed error, twice, the second time deployed to defend the
> first.** This is also the sharpest argument for the Poisson-binomial below: a
> single midpoint-derived break-even is wrong by 3.4¢ on this cell alone.

Those cells are not *wrong*: 12 of 12 losing a 25¢ bet is p=0.03 and is worth
noticing. They are not 1e-12 evidence, and **Var(t) = 18.6 was built almost
entirely out of that gap.**

### The registered change

1. **The primary score is a two-sided exact POISSON-binomial on the cell's win
   count against its own per-market break-even** (`ask_i + fee(ask_i)`). A decile
   spans a 0.1 price band so break-even **varies within the cell**; collapsing it
   to one number mis-states the tail in whichever direction the within-cell price
   distribution leans, and on the cell above that collapse was worth 3.4¢. Exact
   and cheap at these n. It requires no exclusion: a homogeneous cell gets a
   legitimate p rather than an exploded t.
2. **The sandwich becomes secondary** and runs only on cells with genuine
   outcome variation. Every excluded cell prints its reason *and its binomial p*.
3. **Both print for every cell**, so the gap between them stays visible rather
   than being resolved silently.

### The permutation's job is multiplicity, not the per-cell test

**The shuffle holds each cell's marginal win count fixed by construction**, so it
cannot be the reference for "is this cell's win rate above break-even" — that
hypothesis is a claim about the marginal, and the permutation preserves it. Per
cell the Poisson-binomial is exact and needs no permutation. **Across** cells, the
minimum p over ~324 correlated cells is what needs one: recompute every cell's p
inside each replicate and take min-p. That is the multiplicity reference and the
only thing the permutation is for. (Debugger's correction; it sharpens rather
than contradicts the bias note below, which is about Var(t).)

### ★ The permutation null is biased for this failure mode

Shuffling settlements within games **breaks the homogeneity that creates the
degeneracy**. So the null's Var(t) comes out small, the observed excess reads as
signal, and the reference this document registered as *"the only valid one"*
confirms the artifact instead of catching it. **Pre-exclusion and post-exclusion
figures are not comparable and must never be quoted beside each other.**

### Why this is a property of the substrate, not an incident

**Second appearance.** `docs/math/extreme-hold_2026-09-13.md` needed the identical
correction one day earlier: a 7/7 cell reported +1.68 [+1.41, +1.96] — *the
tightest interval on that board, because nothing varied* — whose binomial lower
bound was 65.2% against a 98.3% break-even.

Binary outcomes at the G this programme can reach make outcome-homogeneous cells
**common**, not exceptional. Any statistic built on the dispersion of a P&L will
meet this again. Twice is the point at which it stops being an incident and
becomes something the estimator has to handle by design.
