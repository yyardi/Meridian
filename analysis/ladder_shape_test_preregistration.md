# Ladder shape test — pre-registration

**Written 2026-09-06, before d5's sigma surface exists and before any ladder has
been scored.** ce's ask: re-siting the identity from the winner market to the
spread/total ladder makes it falsifiable for the first time, because a winner
market prices ONE line — any monotone update yields a valid probability, so the
distributional assumption is unobservable — while a ladder prices ~40 lines that
must move consistently.

That is the whole point, so the test must be specified before the data, and it
must be able to fail. Six of tonight's instruments reported success without
testing anything.

---

## 1. THE MODEL, AND WHY THE FAILURE MODES SEPARATE THEMSELVES

A spread ladder at line `L` prices `P(margin > L)`. Given an anchor `mu`
(expected margin) and a scale `sigma`:

    P(margin > L) = Phi((mu - L) / sigma)

Apply the probit link and the ladder is **linear in L**:

    probit(p(L)) = mu/sigma - L/sigma

    slope     = -1/sigma      <- a WRONG SIGMA is a SLOPE error
    intercept = mu/sigma      <- a WRONG ANCHOR is a SHIFT
    curvature = 0             <- any CURVATURE is a distributional failure

**This is the thing a single line cannot show.** On one rung there is one number
and any (mu, sigma) pair reproducing it is admissible. Across rungs the model has
40 constraints and 2 parameters.

The three failure modes are **orthogonal by construction, not by assumption**:

| rung | sensitivity to `sigma` | sensitivity to `mu` |
|---|---|---|
| at the money (`L = mu`) | **exactly zero** — `p = 0.5` for every sigma | **maximum**, 2.55pp per point |
| ~1 sigma out (`L-mu ~ 15.7`) | **maximum**, 5.35pp at -20% sigma | reduced |

So the anchor is read at the money and the scale is read from the wings, and
neither contaminates the other. Computed at d5's pregame median `sigma = 15.65`:

    L-mu   k     p_true   sigma-20%  sigma-10%  sigma+10%  sigma+20%
       0  0.00   0.5000    +0.00pp    +0.00pp    +0.00pp    +0.00pp
       5  0.32   0.3747    -2.99pp    -1.34pp    +1.11pp    +2.03pp
      10  0.64   0.2614    -4.92pp    -2.26pp    +1.92pp    +3.58pp
      15  0.96   0.1689    -5.35pp    -2.55pp    +2.29pp    +4.33pp
      20  1.28   0.1006    -4.55pp    -2.28pp    +2.20pp    +4.28pp
      25  1.60   0.0551    -3.22pp    -1.71pp    +1.81pp    +3.65pp
      30  1.92   0.0276    -1.93pp    -1.10pp    +1.31pp    +2.75pp

### ★ CONSEQUENCE THAT CONSTRAINS THE DATA, NOT THE STATISTIC

**A shape test restricted to rungs near the line has NO POWER on sigma, however
many rows it holds.** Sensitivity peaks about one sigma out, ~15.7 points from
the spread. If the traded ladder is dense near the money and thin in the wings —
which is what liquidity usually looks like — then the rungs that carry the
information are the illiquid ones.

**Pre-registered requirement: a game is admissible only if it has at least 3
rungs with `|L - mu| >= 10` points (`k >= 0.64`) on both sides.** Report the
count of games failing this rather than dropping them silently. This is a
requirement on d5's surface as much as on mine.

---

## 2. THE LINK IS FIXED TO PROBIT, DECLARED IN ADVANCE

d5 measured probit and logit as indistinguishable on 14 pregame ladders, median
R^2 0.992 both. **Because fit cannot choose between them, the choice must be made
a priori and on interpretability, or this becomes a link-selection test** — which
is ce's warning and is exactly the forced-gradient shape.

**Probit, for one reason: `sigma` is then in POINTS**, directly comparable to
d5's surface (median 15.65, cross-game fit `sigma ~ 13.69 + 0.0915*|line|`).

The logistic scale matching `sigma = 15.65` is **8.63** — a ratio of 0.5513. So
an unfixed link mis-states sigma by **45%** while fitting equally well. Two
sessions could each report "sigma" and differ by half with neither wrong.

**The link may not be re-selected after seeing residuals.** If probit shows
systematic curvature that logit removes, that is a REPORTABLE FINDING about the
margin distribution, not a licence to switch and re-run.

---

## 3. THE RESIDUAL: DIAGNOSE IN LINK SCALE, REPORT IN PROBABILITY POINTS

Both, for different jobs, and neither alone:

- **Diagnosis in probit units.** Only there is the ladder linear, so slope and
  shift decompose orthogonally and curvature is visible as curvature. In
  probability points the same error is heteroscedastic — compressed at the tails —
  and a wing miss looks small when it is not.
- **Reporting in probability points, at the traded rungs.** Money is linear in
  probability; a probit-unit residual has no economic meaning. This is the same
  distinction that made "the relative gain is U-shaped while the tradeable
  disagreement decays" the correct reading of the winner-market result.

Quoting only the link-scale number would repeat tonight's error of scoring in the
unit that is convenient rather than the one that pays.

---

## 4. PASS CRITERIA, DECLARED BEFORE ANY LADDER IS SCORED

Per game, fit `probit(p_obs) = a + b*L` by OLS across admissible rungs, then:

    sigma_implied = -1/b        mu_implied = -a/b

**PASS requires all three:**

| # | criterion | threshold | what it catches |
|---|---|---|---|
| 1 | max abs residual across rungs, in pp | **<= 2.0pp** | local mispricing |
| 2 | quadratic term in `probit(p) ~ L + L^2` | **not significant at 5%** | distributional/shape failure |
| 3 | `sigma_implied` vs d5's surface | within **+/-10%** | wrong scale |

The 2.0pp in criterion 1 is ce's stated venue-gap bar and is deliberately NOT
tuned to the data. The +/-10% in criterion 3 is chosen because it is the point at
which the wing rungs move ~2.3pp, i.e. it is the same bar as criterion 1
expressed in the other parameter — not an independent guess.

**A game failing 1 but passing 2 and 3 is a local mispricing. Failing 2 is a
distributional failure and is the finding this whole re-siting exists to look
for. Failing 3 alone is a scale error with the shape intact.** These have
different remedies and the spec keeps them separate.

---

## 5. ★ THE NULLS. BOTH MUST BE RUN AND BOTH MUST BE ABLE TO FAIL

A shape test that cannot fail is what this programme has spent the day finding.

**5a. Self-consistency (must PASS).** Score a ladder against `sigma` fitted from
that same ladder. Passes by construction — so this is a **weak** control and is
recorded as such: it detects a broken implementation, nothing more. It is not
evidence the test discriminates.

**5b. Cross-game transfer (must MOSTLY PASS).** Score each ladder against
`sigma` fitted on the OTHER games, leave-one-game-out. This is the real
positive control and it can genuinely fail.

**5c. Deliberately wrong sigma (must FAIL).** Perturb `sigma` by -20%, -10%,
+10%, +20% and confirm rejection. **Pre-registered expectation: +/-20% must be
rejected on a clear majority of games; +/-10% is the boundary and is the honest
power question.** If +/-20% is NOT rejected, the test has no power and no result
from it may be reported — that outcome is itself the finding, reported as
"the shape test could not discriminate", never as a pass.

**5d. Projection check, before any of the above touches data.** Enumerate the
achievable outcome range and project it onto the branches, per
`analysis/probe_design_projection.py`. Any branch that is unreachable, or that is
taken on every possible outcome, is a design defect and must be fixed before the
run. My probe returned REFUTED on all 41 possible outcomes once already.

---

## 6. ★ SKILL vs VENUE GAP — THE TEST MUST TELL THEM APART

ce's constraint, and it is the sharpest one. `live_spread` is **DraftKings'**
spread; the ladder is **ours**. They agree at 0.41 points, which the model above
converts to exactly **1.05pp** at the money — reproducing d5's figure from an
independent direction, against a ~2.0pp bar.

**So a shape test that imports the DK anchor and then passes has measured
DK-versus-us agreement, not skill.** It would pass trivially and look like a
result.

**The fix is structural, not a caveat.** Estimate the anchor FROM the ladder
(the intercept) rather than importing it, and read the two comparisons apart:

- **slope / `sigma_implied`** — a statement about the distribution. This is the
  skill claim and criterion 3 is its test.
- **intercept / `mu_implied` vs DK `live_spread`** — a VENUE-GAP measurement. It
  is worth having and must never be labelled skill. At 0.41 pts it is currently
  half the bar, meaning there is almost nothing there to trade.

**Any headline combining the two is inadmissible.** Report them on separate rows
with separate names, per `estimator-not-named-in-the-label`.

---

## 7. THE SEAM WITH d5 — WHAT `sigma` MUST RETURN

Written now so the surface is built to be consumed rather than adapted:

    sigma(line, ...) -> float, POINTS of game margin, NOT a logistic scale,
                        NOT a probability, NOT a variance

* **Units: points.** The 0.5513 probit/logit ratio means a mislabelled scale is a
  45% error that fits equally well.
* **Points vs variance** must be unambiguous in the name. `sigma` not `s2`.
* **One value per (game, line)**, or a callable. The cross-game fit
  `sigma ~ 13.69 + 0.0915*|line|` is already line-dependent, so a scalar per game
  will not do.
* **`sigma(t)` is held at n=1** per ce and is NOT part of this test. If a time
  argument appears in the interface it must be optional and default to pregame,
  so that adding it later does not silently change what has been scored.
* **State the fit's n on every call or in the surface's metadata.** n=12 for the
  cross-game fit; a consumer cannot quote an interval without it.

---

## 8. WHAT THIS TEST CANNOT DO

* It scores the ladder's SHAPE, not money. A ladder can be shaped correctly and
  untradeable, and passing says nothing about edge.
* n is 12-14 pregame ladders. Every result carries G and no headline travels
  further than G allows.
* It is pregame. The identity's live update term is not exercised here at all,
  so a pass does not transfer to the live case — which is where the winner-market
  work said the tradeable disagreement had already decayed to 3.50pp.
* Rungs within one game are NOT independent observations; they are 40 views of
  two parameters. **Clusters are games. Never rungs.** A rung-level interval would
  be roughly `sqrt(40)` too narrow and would look like a decisive result.
