# Ladder-sigma damping — registration (factor fixed by pre-existing constants)

**Status: REGISTERED, NOTHING BUILT, ACTIVATION CONDITIONAL.** Written
2026-08-24 ~23:15Z. This registration fixes the damping RULE before any
factor could be chosen in sight of the result that motivated it; it
activates only if Builder D's re-run (larger sample, declared sensitivity
arm on the reference price) confirms the original FAIL. If the re-run
overturns it, this registration parks unused. Append below the line after
first activation or parking.

## Why a registration is needed before a one-line change

The ladder-bucket test came back FAIL with the sign reversed: the model's
preferred tail rungs settle far below price. The ORIGINAL registration said
only "if it fails, the tail preference is an artifact and should be
damped" — an intent with no magnitude or mechanism. Builder D refused to
pick a damping factor after seeing −13.8pp, and was right: a factor chosen
in sight of the miss is a parameter fit to the result, with a registration
held up as cover. The manager's ruling: the damping needs its own
registration with the factor fixed by a rule stated INDEPENDENTLY of that
result — or an honest statement that no such rule exists.

## The independent rule — it exists, and it predates the test

Two constants published on 2026-08-07, months of games before the bucket
test ran (docs/math/live-totals-fv.md, docs/math/ladder-curve-fit.md):

* The v4 ladder's stored probabilities carry a **post-shrinkage effective
  sigma of ~20.75** (measured by fitting the model's own ladders).
* The **measured residual sd of final totals is 19.00** (fitted from the
  787-game history; the same table the live totals FV runs on).

Excess sigma mechanically inflates tail-rung probabilities: a distribution
wider than the outcomes it prices puts too much mass beyond every distant
line, in both directions. That is a complete, magnitude-specific mechanism
for a tail-preference artifact, and it was on the record before the bucket
test existed.

**The rule**: the sigma used to convert the model's projection into rung
probabilities becomes the PUBLISHED finals-residual sigma (19.00) instead
of the emergent post-shrinkage 20.75. Nothing else changes — not the
projection mean, not the shrinkage of the mean, not any per-bucket
adjustment. The "damping factor" is therefore 19.00/20.75, dictated
entirely by constants that predate the result; no number in this
registration was chosen after seeing −13.8pp.

**Stated limit**: this rule claims only to remove the KNOWN sigma excess.
Whether that suffices to fix the bucket miscalibration is exactly what the
gate below measures. If damped calibration still fails, the artifact has
another cause and this registration does NOT license further damping —
a second mechanism needs its own independent rule or the tail preference
stays.

## Gate

* Activation precondition: D's re-run confirms the FAIL (either reference
  price).
* On activation: the damped ladder runs beside the undamped in the
  prediction log's shadow (per-row version marking, the house pattern);
  the gate is paired bucket calibration — |settle − model_p| by bucket,
  clustered by game — damped vs undamped, on games priced AFTER
  activation. **Floors: ≥ 10 games with tail-bucket rungs.** PASS: the
  damped arm's tail-bucket miscalibration is measurably smaller. FAIL:
  not. Either way the answer is about the mechanism, not the wish.

---

*Registered 2026-08-24. Results (or parking) append below this line.*

## 2026-08-25 — D's re-run, the non-replication, and the activation ruling

**The re-run's numbers, recorded first** (69 games vs the original 56,
second reference price as a declared sensitivity arm): the calibration
FAIL is confirmed at the gate — but the tail-bucket sign reversal that
motivated this registration DOES NOT REPLICATE. The <0.30 bucket moved
from −13.8pp [−22.5, −5.2] to **−5.9pp [−13.3, +1.5] — spanning zero.**
D's original flag ("an opposite effect, not decay") described a
small-sample artifact that did not survive the larger sample. This ledger
exists to carry exactly that kind of reversal.

**Ruling (registration owner, from the text): ACTIVATE — on the
mechanism, with the evidentiary basis recorded as follows.**

* The literal activation condition ("D's re-run confirms the FAIL") is
  met. But the ruling does not rest on the letter: it rests on what the
  registration actually claims. The damping was never justified by the
  −13.8pp — deliberately: its factor (19.00/20.75) derives from two
  published constants measuring a MECHANICAL defect, a distribution wider
  than the outcomes it prices. That defect's evidence is the constants
  themselves, and it is exactly as real today as before the re-run. The
  bucket test was the alarm, never the evidence; a quieter alarm does not
  repair a known parameter error.
* The manager's stated risk — "damping against a marginal miss risks
  fixing noise" — applies to a factor FITTED to the miss. This factor
  ingests nothing from either bucket result, which is why the
  non-replication changes no number in the rule. The independent-constants
  design was chosen for precisely this contingency, before it happened.
* **The honest evidentiary label, on the record**: the damping activates
  on a mechanism argument (published sigma excess), NOT on strong
  empirical evidence of a tail artifact — the tail-specific evidence is
  now a CI spanning zero. A future reader should weigh the gate's outcome
  accordingly.
* Activation is low-stakes by construction: the damped ladder runs BESIDE
  the undamped in the prediction log's shadow, per-row marked; nothing is
  replaced. Parking (option 2) would leave a known parameter error
  unmeasured because its alarm got quieter — the gate exists to arbitrate
  exactly this, and it keeps its full authority: if damped calibration is
  not measurably better at floor, the damping dies per the stated limit,
  and no second mechanism inherits this registration.

Deployment of the shadow arm awaits the manager's word, as everything
does.
