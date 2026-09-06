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
| enter | 480 | 34 | −0.00479 [−0.0231, +0.0135] | tie |
| hold | 373 | 33 | −0.00774 [−0.0331, +0.0176] | tie |
| exit | 398 | 34 | −0.00709 [−0.0264, +0.0123] | tie |
| declined | 398 | 34 | −0.00709 [−0.0264, +0.0123] | tie |
| all | 480 | 34 | −0.00468 [−0.0231, +0.0137] | tie |

Positive would mean the model beats the market. **Nothing here is
distinguishable from zero or from anything else here.** The pregame model's
gate finding was already borderline at G=79; this table has less than half that.

**If the ordering leads, the ordering gets read.** The ordering is not evidence.

Levels, for reconciliation: model 0.19928 / market 0.19448 on entered,
earliest-row-per-market.

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

**3. The unit of decision is `(market, side)`, not `market`.** Seven markets
carry two rows at the *same microsecond* — the same market with `side=yes` and
`side=no`, sharing a `mid` and differing in `fair_value`. Deduping on
`market_slug` alone keeps an arbitrary side.

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
**identical market Brier**. That residual is **tie-breaking on the seven
microsecond-tied markets** of trap 3; first-vs-last tie-break spans
0.19928–0.19948, containing d5's 0.19969.

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
