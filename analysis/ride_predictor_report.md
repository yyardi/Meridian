# Ride predictor — Quant B, 2026-09-02

**Question assigned:** can "this entry never gets an exit fill" be predicted
at entry time, and is a calibrated ride probability a usable sizing input?

**Artifact:** `analysis/ride_predictor.py` (`--selftest`: shuffled labels →
LOGO AUC 0.474; injected clock effect → 0.821 recovered). **Pins:**
`20260901T195202Z`; substrate A's ledger; 1,944 scored fills, 137 rides
(7.0%), 34 games. **Validation:** leave-one-game-out — no prediction scored
by a model that saw its own game. **Label caveat:** "ride" is defined under
the optimistic shadow fill rule, so predicted probabilities are LOWER bounds
on real no-exit risk. **Multiplicity:** 11 clustered intervals here, on data
already mined by the loss map's 197+; the model was specified once in code
(9 features, one interaction) before fitting; operating thresholds are two
pre-named rules plus the registered mask baseline. Book depth is not a
feature — the tick pin carries no depth columns.

**No in-sample result justifies capital. The forward test is the evidence.**

---

## The answer, in three sentences

**Yes, rides are predictable at entry** — LOGO AUC 0.700 vs 0.587 for the
registered hand mask, calibrated where it matters (top quintile: predicted
18.0%, observed 17.0%). **The predictor is substantially a book-death-state
predictor wearing a strategy's clothes** — the discrimination comes from
elapsed-time × margin (+0.91, z=+3.9; the decided-late state where
`bookless-endgames.md` says books die) and low contract price (−0.72,
z=−5.2). **And it does not yield an EV filter, because the market has
already priced the risk it detects:** realized per-$ is FLAT across
predicted-risk quintiles (+2.3, +1.0, +2.6, +1.4, +0.8¢/$ — every CI
straddling zero), so cutting high-risk entries buys no mean return.

## Why the gradient is flat — risk and reward coupled through price

| OOF p̂ quintile | trip per-$ (mean) | mean cost | ride per-$ (mean) |
|---|---|---|---|
| q1 (p̂≈1.8%) | +3.7¢ | 0.68 | −32¢ |
| q3 (p̂≈5.2%) | +6.1¢ | 0.44 | −100¢ |
| q5 (p̂≈18.0%) | +17.8¢ | 0.26 | −83¢ |

High-ride-risk states are cheap-contract states: a successful roll pays the
5¢ target on a small cost (+17.8¢/$ in q5) exactly where a ride loses
nearly everything. The two gradients cancel almost exactly. **P(ride)
predicts the SHAPE of the outcome distribution — variance and left tail —
not its mean.** That is why every filter built from it fails to improve the
mean book while genuinely removing rides.

## Operating points (confusion in trades and dollars, both arms)

At equal kill count (709 entries, 36%), the fitted model vs the registered
hand mask (Q4 ∪ |margin| ≥ 10):

| | recall (rides killed) | precision | ride $ avoided (opt) | trip $ forgone (opt) | net (opt) | kept book (opt) | kept book (pess) |
|---|---|---|---|---|---|---|---|
| fitted model | **68%** (93/137) | 13% | $21.21 | $23.05 | **−$1.84** | +2.1¢/$ [−0.2, +4.4] | −16.7¢/$ ◄ |
| hand mask | 53% (72/137) | 10% | $20.05 | $25.80 | −$5.75 | +2.4¢/$ [+0.5, +4.3] | −26.6¢/$ ◄ |
| EV-neutral p*=8.8% (kills 24%) | 55% (75/137) | 16% | $18.37 | $17.63 | +$0.74 | +1.9¢/$ [−0.4, +4.1] | −18.9¢/$ ◄ |

Read the net column: **at every operating point the filter's optimistic
dollar effect is ≈ zero** (−$5.75 to +$0.74 on a book whose trips earned
+$55.86), and the kept book's CI overlaps the unfiltered book (+1.6¢/$
[−1.4, +4.7]) everywhere. The pessimistic kept book stays decisively
negative at every point — per the standard, an optimistic-only improvement
would be a finding, not an edge; here there is not even that. Games losing
(shadow $): 12/34 unfiltered → 7–8 of 31–32 at these points (hindsight
perfect ride removal: 3, the manager's per-game cut — no realizable filter
approaches it). The model's better pessimistic kept book (−16.7 vs −26.6)
is mechanical: it preferentially kills cheap entries, where the per-$
concession bites hardest.

## What survives (candidates for c7), and what died

1. **P(ride) as a variance input, not a mean input.** *Falsifiable:* on a
   forward cohort scored with FROZEN coefficients (fit on these 34 games,
   frozen at registration), top-quintile predicted entries show (a) ride
   share ≥ 2× the cohort base rate and (b) per-$ variance materially above
   bottom-quintile, while (c) the q5−q1 MEAN per-$ difference is ~0 as
   predicted here. If (a)+(b) hold, fractional-Kelly sizing has a real
   input — tail-aware sizing, not entry filtering. *Confound:* the label is
   fill-model-dependent (lower bound); forward calibration slope must be
   reported per estimates_version.
2. **The fitted instrument dominates the hand mask** at equal kill (recall
   68% vs 53%) — if c7 ever upgrades the registered companion mask, this is
   the better instrument, but swapping instruments mid-registration is
   c7's call and requires a fresh registration; the companion's forward
   accrual is untouched by this report.
3. **Died: the EV filter.** Cutting predicted-high-ride entries does not
   improve the mean book at any operating point, optimistic or pessimistic.
   This kills the naive reading of the per-game table ("remove the rides,
   keep the wins") for any realizable entry-time rule — the wins and the
   rides live in the same states, and the market prices the exchange.

No anchoring check owed (rule 3): every number is realized P&L or a fitted
probability against the venue's own prices; no historical base-rate
comparison appears.

**No in-sample result justifies capital. The forward test is the evidence.**

---

## Addendum 2026-09-02 — reconciliation with D's exit-option premium, label bound quantified, book-state check closed

Written with D (`analysis/exit_option_value.md`), before c7 registers
anything on either doc. Adds 5 clustered intervals (the per-contract
quintile column) to this report's count.

**1. The label's lower bound is now a number (D's excursion scan):** under
a k-concession fill rule the optimistic ride share (7.9%, drop policy —
the same lineage policy as the k-curve and the 11.4% breakeven; this
report's re-linked base is 7.0%) rises to 9.5%
(k=1¢), 11.1% (k=2¢), 14.6% (k=3.15¢) and **17.7% at the full measured
4.70¢ — above the optimistic-rule breakeven ride share of 11.4%**. The
optimistic label undercounts no-exit risk by 2–10pp depending on the
concession assumed; the flipped trips hide −$66.37 of settle P&L.

**2. Units reconciliation — per-dollar flat, per-contract mildly negative:**

| p̂ quintile | E[pnl/ct] clustered | trip ¢/ct | ride drag p̂·E[loss] ¢/ct |
|---|---|---|---|
| q1 (1.8%) | +1.59 [−0.66, +3.83] | +2.51 | 0.84 |
| q3 (5.2%) | +1.15 [+0.14, +2.15] | +2.57 | 1.36 |
| q5 (18.0%) | **−0.72 [−2.32, +0.87]** | +2.53 | **2.84** |

Per contract, trip capture is ~flat (+2.2–2.6¢/ct) while the ride drag
rises with p̂ — so the per-contract gradient drifts mildly negative, though
q5's CI still spans zero. The per-dollar flatness of the main report is
the same data divided by cost (0.68 → 0.26 across quintiles).

**3. Consequence for D's δ*(p):** D's late-cell δ* of 3.5–3.8¢/ct is
approximately the **gross** ride drag (my q5 measures 2.84¢/ct on the
pooled tape; D's late cells run higher). But realized trip capture in the
same states already compensates ~75% of it per contract (~100% per dollar,
equal-weighted). **Charging gross δ* as an entry threshold on top of
edge_net double-charges**; the net uncollected premium is ~0.7–1¢/ct at
q5 with a CI spanning zero — in-sample, indistinguishable from already
fair. One refinement of this report's own language: the compensation
channel is the ENGINE's fixed 5¢ profit target divided by a falling cost —
engine-mediated, not a market law — so "the market has priced it" is
better said as "this exit policy's payoff structure collects it." Under
any changed exit policy (the taker arm included) the netting must be
recomputed, which is precisely where D's δ* table becomes the right
instrument. δ* as a variance/sizing input is untouched by this.

**4. Book-state check (joint note's open item) — CLOSED:** D's per-intent
flags (±60s window, from the pins) joined to all 1,944 scored fills.
Adding `share_two_sided` + one-sidedness to the model changes LOGO AUC by
**+0.000** (0.700 → 0.700); book state ALONE scores 0.323 — individually
anti-predictive. Verdict: **state proxies subsume book state at intent.**
Late books are an order of magnitude sicker (D: ~12% one-sided within 60s
vs ~1% early — the joint note's falsification does not fire), but book
sickness does not mark which individual entry rides. Caveat: the ±60s
window extends past intent, so this is mechanism attribution, not a
deployable feature.

**No in-sample result justifies capital. The forward test is the evidence.**
