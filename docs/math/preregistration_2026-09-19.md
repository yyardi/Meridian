# Pre-registration — the 2026-09-19 read

Written 2026-09-13, **before** the 09-19 tape exists. Registers the football
ladder lines in `strategies/ladder.py`, their estimator, their decision rule,
and — the part that governs everything else — the **multiplicity correction**
owed by lines that were found in the same data they will be read on.

Everything numeric below was recomputed for this document from
`market_snapshots` on prod with SQL written independently of
`cfb/run_longshot_decomp.py`. Where my route reproduces that script the
agreement is stated; where it cannot, that is stated too.

---

## 1. The estimator

**Per-contract net P&L in cents on a $1 ticket, averaged equally over bets,
with a 95% interval from the game-clustered sandwich** (`clustered()` in
`cfb/run_paper_book.py`; G games, `G_eff = n²/Σ cluster²`).

Two things this fixes by naming them:

- **Equal-weight-per-bet, not per-game.** A game contributing 6 rungs counts
  6×. The per-game equal-weight estimator is a *different number* and has been
  as far as 1.7¢ from this one on CFB. Whichever is quoted, the label must say
  which — "game-clustered" names the *interval*, not the *estimate*.
- **Pricing.** YES pays the ask, NO pays `1 − bid` (`strategies/base.py:price_of`).
  Fee `0.06·p·(1−p)` on the YES price either way.

## 2. The decision rule, and what it can actually produce

Registered rule: **G ≥ 25 AND the 95% interval excludes 0 AND the home/away
twin does not contradict.**

Projected onto the outcomes this design can produce, **the third clause is
much weaker than it looks and the second is not a 5% test.** Both are
addressed in §3 and §4.

## 3. Multiplicity — the binding constraint

### 3.1 The family is not what the line count suggests

Two separate over-counts, each verified by re-running the code rather than
reading it:

**(a) `run_longshot_decomp.py` Q5 prints 20 cells but computes 10 distinct
statistics.** Every cell appears twice — once as a bucket's "main" and once as
its mirror's "twin". `NO on YES-mid [0.4,0.5)` *is* the twin printed beside
`YES on [0.5,0.6)`, and is also the main of its own row. So the table's
home-beats-away symmetry across "five twin pairs" is **five comparisons
displayed ten times**, not ten findings.

**(b) `strategies/ladder.py` registers 29 names but 24 distinct statistics.**
Five pairs select an *identical row set* with *opposite sides*:

| pair | league / type |
|---|---|
| `cricket_home_yes_all` ↔ `cricket_away_no_all` | cricket / match_winner |
| `cfb_total_under_all` ↔ `cfb_total_over_all` | cfb / full_game_total |
| `nfl_total_under_all` ↔ `nfl_total_over_all` | nfl / full_game_total |
| `mlb_total_under_all` ↔ `mlb_total_over_all` | mlb / full_game_total |
| `mlb_f5_total_under_all` ↔ `mlb_f5_total_over_all` | mlb / first_five_total |

For any such pair, on every row and **whatever settles**:

> **pnl_YES + pnl_NO = −(ask − bid) − fee(ask) − fee(bid)**

an exact, outcome-independent constant. The two lines are one number and its
negation minus the round-trip. **"Under beat over" is arithmetically
guaranteed** whenever under exceeds −½·round-trip; it carries no information
about totals. Read one of each pair; the other is bookkeeping.

### 3.2 The correction

The flagship cell — buy the AWAY side at YES-mid 50–60¢ — is
**−11.62¢ [−21.74, −1.50], n 227, G 104**. That implies **SE 5.163¢, |t| 2.251,
p = 0.0244**.

| family m | α\* | required \|z\| | Bonferroni CI | verdict |
|---:|---:|---:|---|---|
| 2 | 0.0250 | 2.241 | [−23.19, −0.05] | clears |
| **10** (Q5 alone) | 0.0050 | 2.807 | [−26.11, **+2.87**] | **fails** |
| **16** (Q5+Q1+Q2, one script) | 0.0031 | 2.955 | [−26.88, **+3.64**] | **fails** |
| **24** (the registry) | 0.0021 | 3.078 | [−27.51, **+4.27**] | **fails** |

> **The cell clears Bonferroni only if the family is 2 cells or fewer. It was
> found among at least 10, in a script that examined at least 16.**

**Expected false "excludes zero" results at 20 looks under a global null:
1.00 — exactly one.** P(at least one) = 64.2%. At 10 looks, 0.50 and 40.1%.
A single "excludes zero" from a 10–20 cell sweep is the *modal* outcome of
pure noise, not evidence against it.

**Threshold a found-in-sample line must clear to be believed:** the
Bonferroni-corrected interval for its family must exclude zero — |z| ≥ 2.81 at
m = 10, ≥ 3.08 at m = 24 — **on tape that did not generate it.**

## 4. The defect in tonight's two CFB spread registrations

`cfb_spread_no_50_60` buys **NO** on rungs with YES-mid ∈ [0.50, 0.60). Those
are the **same 227 rows** the −11.62¢ cell was measured on, taken on the
**opposite side**. By the identity in §3.1 it is not an independent
hypothesis; it is the fade, and it inherits the source's standard error while
paying the round-trip.

Measured on those rungs: mean spread **1.21¢**, **round-trip 4.17¢**.

> **E[`cfb_spread_no_50_60`] = +11.62 − 4.17 = +7.45¢, SE ≈ 5.16,
> 95% CI [−2.67, +17.57] — SPANS ZERO, uncorrected, in-sample.**

The registered line is *weaker than the observation that motivated it*, and
was already insignificant on the tape it came from before any correction. The
same holds for `cfb_spread_yes_40_50`, the complement of the twin cell.

This is not an argument against registering them. It is the reason their
decision rule cannot be "excludes 0 on 09-19".

## 5. What one Saturday can read

Measured slate size in this cell: **35 games (09-05), 45 (09-12) — call it 40.**
At G = 40 the sandwich SE is **8.33¢**, so:

> **A cell must show 16.3¢ to exclude zero on one Saturday, uncorrected.**

| target | effect | G needed | Saturdays |
|---|---:|---:|---:|
| headline cell, uncorrected 95% | 11.62¢ | 79 | **2.0** |
| headline cell, Bonferroni m=10 | 11.62¢ | 162 | **4.0** |
| headline cell, Bonferroni m=24 | 11.62¢ | 195 | **4.9** |
| registered fade, uncorrected | 7.45¢ | 192 | **4.8** |
| registered fade, Bonferroni m=24 | 7.45¢ | 473 | **11.8** |

> **Answering the question as asked: none of tonight's spread registrations is
> readable on one Saturday.** The headline cell needs ~5 clean Saturdays to be
> believed at its own family size; the line actually registered needs ~12,
> which is the rest of the regular season. These assume the effect is real at
> its observed size — if it regresses, as an in-sample maximum usually does,
> every figure rises.

**Therefore the 09-19 read on these four lines is registered as an INTERIM
OBSERVATION, not a decision.** Print the cell, print G, print the interval;
take no verdict. The first decision point is the accumulated read at G ≥ 195.

## 6. Per-line register

Held-out status is relative to the tape that generated the hypothesis.

| line | population | 09-19 status | family | rule for 09-19 |
|---|---|---|---|---|
| `cfb_spread_no_20_30` | cfb full_game_spread, YES-mid ∈ [.20,.30), NO | held-out | 10 (decomp grid) | G≥25 ∧ Bonferroni-10 excludes 0 |
| `cfb_spread_home_all` | cfb spread, YES-mid ∈ [.05,.95], NO | held-out | 10 | as above |
| `cfb_spread_no_50_60` | **same 227 rows as the −11.62¢ cell, opposite side** | **in-sample-derived** | 10 | **interim only — see §5** |
| `cfb_spread_yes_40_50` | complement of the twin cell | **in-sample-derived** | 10 | **interim only** |
| `cfb_total_under_all` | cfb full_game_total, all, NO | back-read 09-05/09-12, then held-out | 2 (pair) | read ONE of the pair |
| `cfb_total_over_all` | exact complement of the above | — | — | **do not read separately** |
| `nfl_spread_no_20_30` | nfl spread [.20,.30), NO | held-out, no prior | 1 | G≥25 ∧ excludes 0 |
| `nfl_spread_home_all` | nfl spread [.05,.95], NO | held-out, no prior | 1 | as above |
| `nfl_spread_no_50_60` | nfl spread [.50,.60), NO | held-out, no prior | 2 | as above |
| `nfl_spread_yes_40_50` | nfl spread [.40,.50), YES | held-out, no prior | 2 | as above |
| `nfl_total_under_all` | nfl full_game_total, all, NO | back-read then held-out | 2 (pair) | read ONE of the pair |
| `nfl_total_over_all` | exact complement | — | — | **do not read separately** |

**The NFL lines have no Saturday read.** Week 2 is Sunday 09-20. Registering
them under a "Saturday 09-19" heading would read a slate that has not played.
Their read date is **09-21**, after Sunday settles.

The NFL spread lines carry **no prior** — they were not found in NFL tape — so
they are a genuine out-of-sample test of the CFB hypothesis and their family is
the 2 (or 4) NFL cells, not 24. **This is the strongest test on the board**
and it is the one nobody has to correct heavily.

## 7. Settlement — checked, and it holds

The one input my SQL route could not reproduce was settlement. It has now been
checked against the venue directly, on the flagship bucket:

- **Population: reproduced exactly.** Independent SQL returns **227 rungs,
  104 games** for YES-mid ∈ [0.50,0.60) — the script's n and G to the unit.
  The selector is verified.
- **Venue settlement coverage: 227/227. Zero unsettled.**
- **Frame check: 65 rungs where both the venue's label and an ESPN final
  exist — 65 agree, 0 disagree.** ESPN scored under the venue's stated frame
  (YES = away margin + line > 0). By the rule of three, 0 disagreements in 65
  bounds the frame-error rate at **≤ 4.6% (95%)** — small, not zero.

**A criticism of mine that the data retires:** Q5 discards the unsettled count
(`b, _ = bets_for(...)`), so a reader cannot see how much of a cell was
dropped. On this cell the answer is **nothing — 0 of 227**, so the omission
changes no number here. It stays worth fixing, because the next cell that
drops rows will drop them silently, but it is a hygiene point and **not** a
defect in the −11.62¢ figure.

**What this means for the headline.** The number is not wrong. Its selector,
its population and its settlement all reproduce. **The case against acting on
it is entirely power and multiplicity** — §3 and §5 — plus the structural
point in §4 that the line actually registered is the fade, not the finding.
Those are the grounds to hold it as an interim observation, and the ESPN
subsample (−9.03¢ on 29% of the rungs, §5) is consistent with the effect being
real and simply too small to read on one slate.
