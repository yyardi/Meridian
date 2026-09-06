# The two halves of `pulse_decisions`: entered and declined

**DESCRIPTIVE. NO GATE, NO VERDICT REGISTERED.** Joint work — Quant B scored the
entered branch, Builder D reconstructed and scored the declined one, both
through the same module (`analysis/pulse_branch_scoring.py`) rather than by
agreeing about method in prose.

**The headline is a negative and it comes before the numbers: at G=34 this
comparison cannot separate the two branches.** The entered/declined difference
is ~0.002–0.003 Brier against intervals ten times that width. Everything below
is reported so the attempt is on the record, not because it ranks the halves.

---

## The counterfactual is computable, and there is no selection effect

`settlement` is native on **enter rows only** — and only 65.4% of those (1,944
of 2,974). Holds and exits carry none, which is why the declined branch had
never been scored.

Joining `resolved_outcomes_20260901T195202Z.csv` on `market_slug` closes it
completely:

| action | rows | markets | joined |
|---|---:|---:|---:|
| enter | 2,974 | 480 | **100.0%** |
| exit | 2,679 | 398 | **100.0%** |
| hold | 13,680 | 376 | **100.0%** |

**The join is validated rather than assumed.** On the 1,944 rows that already
carry a native settlement the joined value agrees **1.0000, zero
disagreements** — if that had not been exact, nothing here would be usable.

**And the coverage is not selective**: 100% on every action and every market
type, so the counterfactual is not computed on "whatever happened to settle".
That hazard was checked before any score was run, because a counterfactual on a
settled subset would be an instance of the disease being diagnosed.

### It also superseded the entered-branch figure

The natively-settled 1,944 are **not a neutral subset** — spread markets are
40.7% of them against 31.4% of the rest, and mean `minutes_left` differs by 1.9.
The originally reported entered figure was computed on it; the numbers below use
the full join.

---

## Results — every branch ties, under both conventions

`Brier(market) − Brier(model)`; **positive = model wins**. Game-clustered.

**Row-weighted (cluster-robust sandwich, t at df = G−1):**

| branch | dedupe | n | G | diff | 95% CI |
|---|---|---:|---:|---:|---|
| entered | earliest | 480 | 34 | −0.00479 | [−0.02313, +0.01354] |
| hold | earliest | 373 | 33 | −0.00774 | [−0.03310, +0.01762] |
| exit | earliest | 398 | 34 | −0.00709 | [−0.02643, +0.01225] |
| declined | earliest | 398 | 34 | −0.00709 | [−0.02643, +0.01225] |
| entered | all | 2,974 | 34 | −0.00370 | [−0.01910, +0.01170] |
| hold | all | 12,689 | 33 | −0.00612 | [−0.02328, +0.01105] |
| exit | all | 2,678 | 34 | −0.00310 | [−0.02409, +0.01788] |
| declined | all | 15,367 | 34 | −0.00559 | [−0.02269, +0.01151] |

**Every interval contains zero.** The model ties the market on both halves, and
the halves tie each other.

### The estimand changes the point estimate by 2× and the verdict not at all

On identical rows (entered, earliest dedupe):

| estimand | diff |
|---|---:|
| row-weighted sandwich | −0.00479 |
| game-weighted mean-of-means | −0.00979 |

Game sizes run **1 to 18** after dedupe, so equal-weighting games and
equal-weighting rows are genuinely different questions and this table has the
imbalance to make it matter. **Both span zero**; the choice is worth stating and
does not change what may be concluded. Reported rather than resolved.

---

## Three structural facts about the declined branch

**1. "Declined" and "exit" are nearly the same set.** Deduping to the earliest
row per market, the earliest declined row is an `exit` in **all 398 markets** —
`holds ⊆ exits` as market sets. So a hold+exit arm under that convention
silently reports exits and contributes **none** of the 12,689 hold rows.
**The hold-only arm is the one that isolates a genuine non-action**, and it is
reported separately above for that reason.

**2. `edge_net` is populated on enters only** — 2,974 of 2,974, and **0 of
15,367** declined rows. The pregame model's finding (mean |edge| 0.0715 declined
against 0.0360 actionable, i.e. the gate declines the model's *largest*
disagreements) therefore **cannot be reproduced on this table as stated**. The
computable analogue is |`fair_value` − mid|:

| enter | hold | exit |
|---:|---:|---:|
| 0.0815 | 0.0879 | 0.1009 |

Same direction — declined disagreements are larger — but a gap of ~0.02 against
the pregame model's ~0.036, and with no interval attached it is a description,
not a finding.

**3. The halves are not selected alike, and it matters if they are ever
separable.** The entered branch is selected **twice** — the model chose to enter
*and* a fill process we have shown selects adversely filled it. The declined
branch is selected once. So any future difference between them confounds *what
the gate declined* with *what the book let us have*. **At present the intervals
are far too wide for the hazard to bite**, but it must be recorded before it
becomes load-bearing rather than after.

---

## Two defects found while doing this, both silent

**`pandas.GroupBy.first()` returns the first non-null value per COLUMN, not the
first row.** On `[{t:1, x:nan}, {t:2, x:5}]` it yields `{t:1, x:5}` — a record
that never existed — so "the earliest decision per market" silently mixes fields
across decisions wherever a column has nulls, and this table has several. Found
independently by both of us, from different symptoms: B while packaging the
module, D because two slices came out byte-identical when they should not have.
Fixed to `.head(1)`/`.tail(1)`.

It was checked against already-published work rather than assumed harmless: the
λ* result in [public-wp-models.md](public-wp-models.md) used the same call, but
its `dropna` ran *before* the groupby so no nulls existed to assemble across —
all columns identical in 100% of markets, **λ* unchanged at −0.0224**.

**A merge-suffix bug reported a complete join as 10.1% selective.** The joined
column landed in `settlement_r` while the original `settlement` was read. It
failed silently and in the direction that would have killed the work — a
complete join looking like a selective one.

---

## What would change the answer

**More games.** Not more rows: 15,367 declined rows are 34 games' worth of
opinion logged repeatedly. The pregame model's gate finding was borderline at
G=79 and this table has **34** — less than half. The binding quantity is games,
and no amount of within-game repetition substitutes.

---

*Computed 2026-09-06 against `pulse_decisions_full_20260901T195202Z.csv`
(19,333 rows, 34 games, 480 markets) joined to
`resolved_outcomes_20260901T195202Z.csv`. Descriptive only.*
