# The live model, both branches — one method, one document

Joint write-up: Quant B (entered branch) and builder-d5 (declined branch),
scored with **the same function** — `analysis/pulse_branch_scoring.py` — rather
than with two implementations agreed in prose. First measurement of
`pulse_decisions` in the programme's history.

Substrate: 19,333 in-play decisions, 480 markets, **34 games**, 2026-08-18 to
08-31. Outcomes from `resolved_outcomes_20260901T195202Z.csv` joined on
`market_slug`.

---

## ★ THE HEADLINE IS THE POWER, NOT THE ORDERING

**At 34 games this comparison cannot separate the branches.** Every branch ties,
and the entered-versus-declined difference is 0.002–0.003 Brier against
intervals ten times that width.

| branch | n (dedup) | G | Brier(mkt) − Brier(model) | |
|---|---:|---:|---|---|
| enter | 480 | 34 | −0.00511 [−0.0235, +0.0133] | tie |
| hold | 373 | 33 | −0.00774 [−0.0331, +0.0176] | tie |
| exit | 398 | 34 | −0.00709 [−0.0264, +0.0123] | tie |
| declined | 398 | 34 | −0.00709 [−0.0264, +0.0123] | tie |
| all | 480 | 34 | −0.00468 [−0.0231, +0.0137] | tie |

Positive would mean the model beats the market. **Nothing here is
distinguishable from zero or from anything else here.** The pregame model's
gate finding was already borderline at G=79; this table has less than half that.

**If the ordering leads, the ordering gets read.** The ordering is not evidence.

Levels, for reconciliation: model **0.19959** / market **0.19448** on entered,
earliest-row-per-market **with the deterministic `(decided_at, id)` tie-break**.
Before that tie-break landed the model leg ranged 0.19916–0.19969 depending on
input order; the market leg was 0.19448 throughout. The entered row above moved
−0.00479 → −0.00511 when the sort was pinned — a shift far inside the interval,
recorded so the change is not mistaken for a new measurement.

---

## THREE LAYERS OF SELECTION, AND THEY ARE NOT THE SAME KIND

**1 and 2 are about the trade** (d5). The entered branch is selected twice — the
model chose to enter *and* the book chose to fill — while the declined branch is
selected once. A difference between the halves therefore confounds *what the
gate declined* with *what the book let us have*.

**3 is about the comparison** (B). The entry rule gives the model–market
disagreement a **fixed sign on each arm, by construction**:

    side=yes   n 1,342   fv > mid on 100.0%   mean(fv − mid)  +0.0727
    side=no    n 1,632   fv > mid on   0.0%   mean(fv − mid)  −0.0870

The engine enters YES only when it judges yes underpriced, NO only when
overpriced. **So the Brier test is not run on a neutral sample — it is run on
the sample of maximal disagreement.**

**Which way this cuts, stated explicitly so it is not read as a weakening:**
maximal disagreement is the arrangement **least favourable** to a noisy model, so
a tie there is a harder test survived than a tie on a neutral sample would be.
It does **not** license any claim about the model's skill in general — only
about its skill *where it acts*, which is the only place it costs money.

---

## THE COUNTERFACTUAL EXISTS, AND IT IS NOT SELECTED

*(builder-d5)* The declined branch had never been scored because `settlement` is
native to **enter rows only** — and only **65.4%** of those (1,944 of 2,974).
Holds and exits carry none.

Joining `resolved_outcomes_20260901T195202Z.csv` on `market_slug` closes it
completely: **100% of rows on every action** — 2,974 enters, 2,679 exits, 13,680
holds, all 480 markets, with no selectivity by action or market type.

**The join is validated rather than assumed.** On the 1,944 rows that already
carry a native settlement, the joined value agrees **1.0000, with zero
disagreements.** That check ran *before* any score, because a counterfactual
computed on "whatever happened to settle" would be an instance of the selection
disease the exercise exists to diagnose — and if the agreement had not been
exact, nothing downstream would have been usable.

**It also superseded the entered figure**, which is why that number moved: the
natively-settled 1,944 are **not a neutral subset** — spread markets are 40.7%
of them against 31.4% of the rest, and mean `minutes_left` differs by 1.9.

## `edge_net` IS ABSENT FROM THE DECLINED BRANCH

*(builder-d5)* The pregame model's gate finding — mean |edge| **0.0715**
declined against **0.0360** actionable, i.e. the gate declines the model's
*largest* disagreements, which reads as evidence of a stale model rather than an
edge — **cannot be reproduced on this table as stated.** `edge_net` is populated
on **2,974 of 2,974 enters and 0 of 15,367 declined rows.**

The computable analogue is |`fair_value` − mid|:

| enter | hold | exit |
|---:|---:|---:|
| 0.0815 | 0.0879 | 0.1009 |

**Same direction, and weaker.** A gap of ~0.02 here against ~0.036 there, with
no interval attached. It is a description, not a finding, and should not be
quoted as confirming the pregame result — only as failing to contradict it.

## THREE STRUCTURAL TRAPS IN ONE TABLE

Listed together because **the pattern is more useful than any one of them**: all
three produce clean-looking wrong answers rather than errors.

**1. `holds ⊆ exits` as market sets.** The exit row precedes every hold in all
398 shared markets. An earliest-row-per-market dedupe across hold+exit therefore
**silently erases 12,689 hold rows and reports exits under a "declined" label**.
The hold-only arm is the one that isolates a genuine non-action.

**2. `groupby(...).first()` is column-wise.** pandas returns the first *non-null
value of each column independently* and assembles a row **that never existed**:
on `[{t:1, x:nan}, {t:2, x:5}]` it returns `{t:1, x:5}`. `.head(1)` takes the
real row. This changed no visible output here, which is exactly why it is worth
naming.

**3. The unit of decision is `(market, side)`, not `market`.** **24 (market,
instant) pairs** in the entered branch carry more than one row at the *same
microsecond* — the same market with `side=yes` and `side=no`, sharing a `mid`
and differing in `fair_value`; one carries three. Deduping on `market_slug`
alone keeps an **arbitrary** side, and "arbitrary" here means *determined by
input row order*, which is why the two authors' entered figures differed. Fixed
by sorting on `["decided_at", "id"]`, which pins it.

And a fourth, spanning substrates: **`minutes_left_is_estimate` is a `'t'`/`'f'`
string.** That is `is_live` on the QUOTE tape and `is_actionable` on
`predictions` — three columns, three substrates, same silent-empty-filter
failure.

---

## METHOD, PINNED

* **Outcome** — `resolved_outcomes` joined on `market_slug`. **100.0% coverage
  on all three actions** (enter 2,974, exit 2,679, hold 13,680; all 480
  markets), and **1.0000 agreement with zero disagreements** against the 1,944
  rows carrying a native `settlement`. Validated independently by both authors
  before use.
* **Dedupe** — one row per market, earliest (`dedupe="earliest"`). A later mid
  has drifted toward the outcome and imports part of the answer.
  `dedupe="all"` is available and reproduces the undeduped figures.
* **Market probability** — `mid = (market_bid + market_ask)/2`; both legs are
  100% present.
* **Model probability** — `fair_value`, untransformed. **Verified to be the YES
  probability rather than side-relative**, because the side-relative reading
  would have made both authors wrong on every `no` row *and agreed with each
  other*: `corr(fv, settlement)` stays positive on `side=no` (+0.477 against the
  market's +0.506), and flipping the outcome there sends Brier from 0.195 to
  0.329.
* **Clustering** — `clustered_mean`: a cluster-robust sandwich on per-row
  differences, t at df = G−1, clusters are games. **Not** one mean per game
  followed by a t-interval; those differ under unequal game sizes, which this
  table has badly.

### Two figures that were superseded, recorded rather than removed

B's original entered-branch number (model 0.20173 / market 0.19692) used the
**1,944 rows carrying a native settlement — 65.4% of enters**, which is not a
neutral subset: spread markets are 40.7% of it against 31.4% of the rest, and
mean `minutes_left` differs by 1.9. The join covers all 2,974.

The two authors' figures then differed by 0.00041 on the model side with an
**identical market Brier** — 0.19448 both ways, so the market leg reconciles
exactly and the residual is entirely on the model side.

**The residual is an unresolved tie-break, and it is worth stating as a defect
rather than as a reconciliation.** The entered branch contains **24 (market,
instant) pairs** carrying more than one row — same market, same microsecond,
`side=yes` and `side=no`, sharing a mid and differing in `fair_value`; one
market carries three. Only **4 markets** actually resolve differently between
the two pipelines, but neither pipeline has a tie-break rule, so which row wins
is an artefact of input ordering.

Measured across orderings that are all equally "one row per market, earliest":

| tie-break | entered model Brier |
|---|---:|
| none, file order | 0.19928 |
| none, reversed input | 0.19916 |
| deterministic `(decided_at, id)` | 0.19959 |
| deterministic `(decided_at, id)` desc | 0.19916 |
| d5's original pipeline | 0.19969 |

**The span is 0.19916–0.19969 and no ordering is canonical.** An earlier draft
of this section described the span as 0.19928–0.19948 "containing d5's 0.19969";
it does not contain it, and the true range is wider. Corrected here.

**The pin is a total order, verified rather than assumed** — a tie-break only
breaks ties if its key is unique. `id` is unique across all 19,333 rows,
`(decided_at, id)` has zero duplicates, and five random input shuffles produce
**one distinct result**. So `head(1)` is deterministic regardless of input order
or pandas sort stability. *(Checked independently by Quant B.)*

**It changes nothing and must still be fixed.** ±0.0005 of instability sits an
order of magnitude below the effect being measured (~0.005) and nearly two below
the interval width (~0.037), so no verdict moves. But a number that shifts in
the fourth decimal depending on row order is not reproducible, and the fix is
one clause: sort by `["decided_at", "id"]` so the dedupe is deterministic. Until
that lands, **quote the entered model Brier as ≈0.199, not to five digits.**

---

## WHAT IS NOT REPORTED

Four calibration intervals were inspected (model/market × yes/no) and one
excluded zero — the market over-predicting YES by 11.06pp on rows where the
model bet against it. **One in four at the 5% level is what chance produces**,
and it is not a finding.

## WHAT THIS DOES NOT SETTLE

Whether the live model has an edge. It ties the market where it acts, at
G=34, on a sample constructed to be maximally unfavourable. **More games is the
only thing that moves this**, and the accrual arithmetic is the same as
everywhere else in the programme: intervals scale as 1/√G.
