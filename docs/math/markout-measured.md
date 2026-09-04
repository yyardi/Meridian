# Markout at pre-named horizons — measured 2026-09-04

Horizons, definition and four predictions were fixed in
[`analysis/MARKOUT_PREDECLARATION.md`](../../analysis/MARKOUT_PREDECLARATION.md)
(commit bc85071) **before any number was computed**. Two predictions were
confirmed and **two were refuted**, and the refutations are the useful part.

Substrate: `market_snapshots` price loop (never `book_levels`). 38,465 settled
fills, 24 games. Estimator: `clustered_mean` — pooled mean, game-cluster-robust
SE. Population: real / phantom as classified by `core.quote.report.classify_fill`.

## Coverage — rule 22, counted not dropped

| horizon | matched | unmatched |
|---|---:|---:|
| 10s | 29,189 / 38,465 (75.9%) | 9,276 |
| 30s | 31,574 / 38,465 (82.1%) | 6,891 |
| 60s | 37,262 / 38,465 (96.9%) | 1,203 |
| 300s | 38,049 / 38,465 (98.9%) | 416 |

Short horizons lose a quarter of the sample to the staleness cap. **The results
below are consistent across horizons whose coverage differs by 23 points**,
which is the only reassurance available that the missing rows are not driving
them — it is not proof.

## The raw numbers

| h | phantom | real | gap |
|---:|---|---|---:|
| 10s | −0.595 [−0.838, −0.352] | −2.876 [−3.390, −2.363] | +2.282 |
| 30s | −0.265 [−0.465, −0.065] | −2.596 [−2.890, −2.302] | +2.332 |
| 60s | −0.209 [−0.402, −0.015] | −2.572 [−2.873, −2.272] | +2.364 |
| 300s | +0.076 [−0.153, +0.306] | −2.308 [−2.579, −2.037] | +2.384 |

## ★ The check that had to be run first, and nearly killed it ★

The metric ruling calls markout "the metric that **exhibits the mechanism**", and
a ~2.3¢ gap that barely moves across 10s–300s looks exactly like the shape
`capture` had: **an identity wearing a measurement's clothes.** The gap is
computed from `mid_at_fill`, and `mid_at_fill` is built from the same `bb`/`ba`
that **define** the real/phantom split — so some of that gap is the criterion
restating itself.

Decomposed against **h = 0** (markout evaluated at the fill instant — pure
definition, zero dynamics):

| horizon | phantom | real | gap | of which NEW since h=0 |
|---:|---:|---:|---:|---:|
| **0s** | −1.872 | −3.154 | **+1.282** | — *(definitional)* |
| 10s | −0.595 | −2.876 | +2.282 | +0.999 |
| 30s | −0.265 | −2.596 | +2.332 | +1.049 |
| 60s | −0.209 | −2.572 | +2.364 | +1.081 |
| 300s | +0.076 | −2.308 | +2.384 | +1.102 |

**+1.282¢ of the 2.38¢ gap — 54% of it — is the classification criterion's own
algebra and carries no information.** Any future statement about "the markout
gap" that does not subtract h=0 is quoting a number that is more than half
definitional.

**But markout is NOT an identity**, and that is what capture failed:
`corr(markout, mid_at_fill level)` = **+0.394 at 30s, +0.155 at 300s** — against
capture's +1.0000. At 300s, 97.6% of markout's variance is independent of the
definitional level. It has real degrees of freedom.

### The drift — the part that is a measurement

Markout minus its own h=0 level: what actually moved *after* the fill.

| h | phantom drift | real drift | difference |
|---:|---|---|---:|
| 10s | **+1.209** [+1.05, +1.36] | +0.224 [+0.05, +0.40] | +0.985 |
| 30s | **+1.579** [+1.35, +1.81] | +0.501 [+0.09, +0.92] | +1.077 |
| 60s | **+1.641** [+1.43, +1.85] | +0.559 [+0.20, +0.92] | +1.081 |
| 300s | **+1.912** [+1.59, +2.23] | +0.760 [+0.23, +1.29] | +1.152 |

Phantoms recover ~1.9¢ over five minutes; real fills recover ~0.76¢. Both
intervals exclude zero. **That is the reversion asymmetry, measured on the
non-definitional part.**

## The predictions, scored

**P1 — "phantoms POSITIVE, real NEGATIVE at every horizon." REFUTED.**
Phantom markout is **negative** at 10s, 30s and 60s, and only +0.076 at 300s
with an interval spanning zero. The doc's phrase *"phantoms profit because price
reverts"* is **half right and half wrong**: phantoms do revert, strongly and
measurably (+1.9¢ of drift), but they revert *from a level so far below our
price that they do not reach profit inside five minutes.* On settlement phantoms
are +0.951¢ (WNBA); on markout at these horizons they are not. **Markout does
not exhibit "phantoms profit" — it exhibits "phantoms revert."** Those are
different claims and the record conflated them.

**P2 — "the gap is LARGEST at the shortest horizon and decays." REFUTED.**
It grows monotonically, 2.282 → 2.384, and the *drift* difference also grows,
0.985 → 1.152, **still rising at 300s.** The pre-declaration said: *"If the gap
grows with horizon, something other than reversion is producing it."* Holding to
that: the honest reading is that **my predicted timescale was wrong** — the
divergence has not completed within five minutes, so 300s does not bound it. A
longer horizon is needed to find where it settles, and that is a new question,
not a rescued prediction.

**P3 — "markout's per-game sd is materially below settlement's." CONFIRMED, and
it is the reason to have built this.** CFB real fills, per-game sd:

| metric | per-game sd | ratio to settlement |
|---|---:|---:|
| settlement | 4.102¢ | 1.000 |
| markout 10s | 1.034¢ | 0.252 |
| **markout 30s** | **0.652¢** | **0.159** |
| markout 60s | 0.617¢ | 0.150 |
| markout 300s | 0.846¢ | 0.206 |

**6.3× lower at 30s.** And because the identity check above came back at +0.394
rather than +1.0, this is a genuine variance advantage rather than the
degenerate tightness that made capture look precise.

**P4 — "real markout at 30s is negative but smaller in magnitude than the −3.4¢
settlement loss." CONFIRMED.** WNBA real fills: markout 30s **−2.272¢**
[−2.527, −2.018] against settlement −3.376¢. Thirty seconds carries the
immediate information in the flow; settlement carries the full directional
outcome.

## What this does NOT license

**Markout is not promoted.** Settlement remains PRIMARY, and the
pre-declaration fixed this before the variance advantage was known precisely
because it is the temptation: *choosing a metric by its variance is how capture
survived as long as it did.* A maker marked out favourably who settles badly has
lost money, and settlement is what the account sees.

Its legitimate uses are two: a **diagnostic** of the mechanism (the drift table
above), and a **power lever** — any question genuinely about short-horizon price
response can be asked at ~1/6 the dispersion. Neither is licence to restate a
settlement question in markout terms because the interval is prettier.

**No in-sample result justifies capital. The forward test is the evidence.**

## ★ THE INFORMED-FLOW MECHANISM IS NOT VISIBLE IN THE ONE STATISTIC THAT IS CLEAN ★

B established (`analysis/composition_gradient_is_forced.py`) that the
classification rule is exactly **real ⟺ excess ≥ s/2**, at 100.0% agreement on
38,465 fills — so **the spread sits on both sides of any composition statistic**,
and a geometry-only null with no flow story reproduces the monotone
"real share falls with width" decline on both boards. That retires the
composition gradient the same way capture was retired, and B retracted their own
supporting sentence rather than let it stand.

B's proposed replacement is the right one, and it is what this study already
had: **DRIFT = markout(h) − markout(0) = mid(t+h) − mid(t).** The quote price
cancels algebraically. There is no `s`, no `qp` and no threshold anywhere in it
— it is the mid's own subsequent motion, signed to our side.

**Declared before looking:** horizons pre-named at bc85071; the registered width
bands; real fills only; and the prediction that **if flow reaching us in wide
markets is more informed, wide-band drift should DECREASE** (continue against
us). Residual confound stated in advance: the statistic contains no `s`, but the
population is selected by a rule that does.

**REAL fills, drift by width (¢, positive = the mid moved our way):**

| band | n | h=30s | h=300s |
|---|---:|---|---|
| ≤1.5¢ | 5,456 / 6,612 | +0.294 [−0.087, +0.675] | +0.534 [−0.062, +1.130] |
| 1.5–2.5¢ | 2,199 / 2,727 | +0.747 [−0.003, +1.496] | +1.098 [+0.374, +1.822] |
| 2.5–3.5¢ | 1,177 / 1,475 | +0.836 [+0.442, +1.230] | +0.492 [−0.297, +1.281] |
| 3.5–5.5¢ | 1,155 / 1,422 | +0.219 [−0.160, +0.597] | +1.019 [+0.524, +1.514] |
| >5.5¢ | 1,011 / 1,282 | +1.022 [+0.383, +1.660] | +1.225 [+0.371, +2.079] |

**MY PREDICTION IS REFUTED.** Drift does not decrease with width. It is
non-monotonic and flat-to-slightly-rising, with heavily overlapping intervals at
G=24. **There is no evidence that the flow reaching us in wide markets is more
informed.**

That matters because the mechanism has now failed in every instrument that could
carry it. *"A spread widens because informed flow is expected; joining a wide
spread means standing in front of exactly that flow"* was argued from **capture**
(an identity — retired), then replicated by the **width settlement gradient**
(non-monotonic, ~3¢ CIs), then by **composition** (forced by `s/2` — retired by
B), and now tested on **drift**, which is algebraically clean: **no support.**
Four instruments, one surviving as a genuine test, and it does not find the
effect. **Stated at its correct strength: this is absence of evidence at G=24
with intervals ~1¢ wide, not evidence of absence — a real 0.5¢ gradient would
not be visible here. But the mechanism should stop being asserted.**

**PHANTOM fills, drift at h=300s, as the contrast:**

| band | n | drift |
|---|---:|---|
| ≤1.5¢ | 6,294 | +0.969 [+0.554, +1.383] |
| 1.5–2.5¢ | 4,636 | +1.006 [+0.519, +1.494] |
| 2.5–3.5¢ | 3,607 | +1.701 [+1.289, +2.114] |
| 3.5–5.5¢ | 4,967 | +2.613 [+2.095, +3.131] |
| >5.5¢ | 5,027 | +3.385 [+2.918, +3.853] |

Strongly monotone, intervals separating cleanly. **And it is very likely the
residual confound rather than a finding**: for the mid to reach our price
*without the ask following*, it must travel further in a wider market, and a
larger excursion mechanically reverts further. The selection is `s`-dependent
even though the statistic is not — exactly the caveat declared before the run.
**Recorded as a candidate for the same forced-gradient treatment B applied to
composition, not as a result.** The geometry-only null that would settle it has
not been built.

## ★ THE LARGER PROBLEM THIS EXPOSES ★

**Real-fill drift is POSITIVE in every band, at every horizon** — the mid moves
*our way* by +0.2 to +1.2¢ in the five minutes after a real fill. And the same
fills settle at **−3.4¢**.

So the loss is **not** in the immediate flow. Whatever takes 3.4¢ off a real
fill happens *after* the horizon at which "adverse selection" is normally
measured. This is consistent with the refutation of P2 above — the phantom/real
divergence was still growing at 300s and had not settled.

**This does not overturn the central result.** The settlement number is the
money, it is measured, and it is negative on 21 of 24 games. What it overturns is
the *narrative attached to it*: we have been calling this "adverse selection" and
describing informed sellers crossing down and the price continuing. **The price
does not continue at 10s, 30s, 60s or 300s — it comes back, slightly.** The
mechanism is either much slower than any horizon measured here, or it is
something other than short-horizon information.

**Named as the next question rather than answered:** extend the horizon ladder
past 300s — 15m, 1h, end-of-period — and find where a real fill's drift turns
over, if it does. That is a pre-registration to write, not a run to do now, and
the horizons must be named before anyone looks.

**No in-sample result justifies capital. The forward test is the evidence.**
