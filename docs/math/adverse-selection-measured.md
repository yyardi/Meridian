# Adverse selection, isolated and measured — 2026-09-03

**The central empirical result of this program.** Every prior capture number was
a blend of two populations with **opposite signs**. Separating them is what this
document records, and the separated numbers say the strategy loses money.

Manager's analysis on prod; independently reproduced from D's separately-written
query (63.9% / −2.31¢ / −1.20¢ against 63.9% / −2.302¢ / −1.191¢). Mechanism is
the research agent's. Nothing here is a forward test — it is our own recorded
tape, scored correctly for the first time.

## The separation

A **phantom** is a simulated fill that could not have occurred: the model fills
on `mid ≤ B` while reality requires `ask ≤ B`. It exists because the shadow
quoter rests an order against a recorded book **that does not contain that
order** — so the recorded bid is free to fall below our own price, dragging the
mid onto it, while nobody ever offered anywhere near us. See WAVE_STANDARD
rule 24 (the counterfactual must contain itself).

Classification: book at the fill instant, ≤5s lookback, **17,339/17,339 matched
(100% coverage)**. Settlement present on **17,339/17,339**.

| population | n | settlement P&L / fill |
|---|---:|---:|
| **phantom** (never happened) | 11,084 | **+0.951¢** |
| **real** | 6,255 | **−3.376¢** |
| ledgered blend (what we believed) | 17,339 | −1.60¢ capture |

**Game-clustered CI on the real fills: [−5.06¢, −1.78¢]** (13 games, mean of
game means −3.419¢, t₁₂). Clustering is mandatory here — every fill inside a
game shares that game's outcome, so a per-fill CI is far too narrow. **12 of 13
games lose money**; the only positive game is +0.42¢.

## The mechanism — why the two populations have opposite signs

**A phantom books when the ask is still ABOVE our bid.** We "buy" at a price
nobody was offering, on a momentary dip that then reverts. **Free money that did
not exist.**

**A real fill happens when a seller crosses DOWN to us** — someone who wants out
at our price, now. **That flow does not revert.**

> **The simulator was earning mean-reversion; reality delivers informed flow.**

That is adverse selection, isolated on 17,339 fills with the two populations
carrying opposite signs. It is the textbook maker's problem, and our scoreboard
had been reporting the wrong half of it.

## What is dead, and how thoroughly

**Touch-joining is dead as a family on this tape.** On real fills, capture is
negative in **every** slice and the *upper* 95% bound is negative in every slice:

| by quoted spread | n | capture |
|---|---:|---:|
| ≤1.5¢ | 2,680 | −1.666¢ |
| 1.5–2.5¢ | 1,274 | −2.245¢ |
| 2.5–3.5¢ | 954 | −2.697¢ |
| 3.5–5.5¢ | 831 | −3.060¢ |
| >5.5¢ | 516 | −3.800¢ |

Best cell anywhere (tightest spread × ≥65¢): **−1.485¢, CI upper −1.365¢**,
against a required **+0.11¢**. By price band the range is only −2.19¢ to −2.59¢.

**The width gradient inverted when cleaned, and it has a mechanism.** The
contaminated view showed *wider is better* — an artifact, because the phantom
share **rises** with spread (43.6% at ≤1.5¢ → 78.9% at >5.5¢) and phantoms are
less bad. Clean, it is monotonic the other way. **A spread widens because
informed flow is expected; joining a wide spread means standing in front of
exactly that flow, and the extra half-spread does not compensate. The widening
is a warning, not an opportunity** — Glosten-Milgrom from the maker's side.

**Inventory does not degrade fill QUALITY.** Real fills by position before the
fill: 0 → −2.305¢, 1–2 → −2.334¢, 3–5 → −2.340¢, 6–10 → −2.530¢, >10 → −1.791¢.
Fills that ADD to a position (−2.310¢) are indistinguishable from those that
REDUCE it (−2.293¢). **This kills "inventory makes our fills worse" and leaves
"we accumulate and wear it" untouched** — that is inventory RISK, which a
per-fill mean structurally cannot see, and it is the version FLATTEN was
registered on.

## ★ CAPTURE IS AN IDENTITY, NOT A MEASUREMENT — 2026-09-03, later ★

**Retiring capture was right for a weaker reason than the real one.** We retired
it as "wrong for a maker in both directions". It is worse than wrong:

`capture = mid_at_fill − quote_price`, and the fill rule only fires once the mid
reaches the quote, so the s/2 terms cancel and

> **capture ≡ −(overshoot of the mid past our price)**

Measured on 6,146 real WNBA fills: **corr(capture, −overshoot) = +1.0000, mean
absolute residual 0.0000¢. Zero degrees of freedom.** It is not a measurement of
anything; it is a restatement of the crossing geometry. Its ceiling of −0.50¢ is
**half the venue's price increment**, not a fee.

**CONSEQUENCE 1 — cross-board capture comparisons carry NO economic content.** A
capture gap between two boards says only that their mids jump different discrete
distances when they cross. **Football mids plausibly step larger than basketball
mids. That is microstructure, not economics.** The claim "CFB is 1.5¢ worse than
WNBA", made from capture, is **withdrawn — not downgraded to directional.**

**CONSEQUENCE 2 — the width gradient's "replication" is the instrument
reproducing its own algebra.** Spread appears on both sides of the identity, so
the gradient is **forced**. Same fills, both metrics:

| band | n | CAPTURE | SETTLEMENT |
|---|---:|---|---|
| ≤1.5¢ | 2,610 | −1.67 [−1.80, −1.55] | −4.10 [−6.80, −1.40] |
| 1.5–2.5¢ | 1,248 | −2.23 [−2.44, −2.01] | −2.29 [−6.24, +1.66] |
| 2.5–3.5¢ | 943 | −2.68 [−2.94, −2.42] | −4.61 [−7.46, −1.76] |
| 3.5–5.5¢ | 829 | −3.06 [−3.44, −2.68] | −1.85 [−5.80, +2.11] |
| >5.5¢ | 516 | −3.80 [−4.25, −3.35] | −5.96 [−10.09, −1.82] |

**Capture perfectly monotonic with ~0.3¢ CIs; settlement not monotonic with ~8¢
CIs. Identical fills.** *The tell, reusable:* **CIs an order of magnitude too
tight for a noisy economic quantity.** A result that replicates because it
**cannot fail** is not a replication.

**★ THE ASYMMETRY, which is the transferable lesson ★** The phantom-rate
replication (CFB 64.4% vs WNBA 63.9%) and the width-gradient "replication" look
like the same kind of evidence and are **opposites**. The phantom rate IS the
claim — it is a property of the SIMULATOR, and finding it stable across two
sports confirms exactly what the mechanism predicts. The width gradient is the
instrument reproducing its own algebra. **Same word, opposite epistemic status.**

*Does overshoot at least predict settlement?* Per game on WNBA where both exist:
Pearson **−0.096** (p=0.755), Spearman −0.066 (p=0.831), n=13 games. In terciles
it runs backwards. **Stated precisely: the IDENTITY is deterministic and
decisive and needs no sample; the correlation test is WEAK — 13 games cannot
exclude a moderate relationship — so it shows NO EVIDENCE that overshoot
predicts settlement, not proof that it cannot.** The case rests on the identity.

**UNTOUCHED: the pre-registered surprise is UNTESTED, not refuted.** *"BASE near
zero on football"* is a claim about SETTLEMENT, and settlement is unreadable at
6/11 games settled (clustered CI **[−41.9, +16.8]**). **Football may still be
better, worse, or the same. Capture cannot tell us.** (D's identity and tests,
`analysis/capture_is_not_a_proxy.py`.)

## Metric ruling

**Capture-vs-mid-at-fill is RETIRED.** For a maker it is wrong in both
directions. The manager's decomposition claiming ~61% of the loss was
"mechanical half-spread" and the true loss ~−0.90¢ is **withdrawn** — a
flattering heuristic superseded by settlement, which needs no decomposition.

- **PRIMARY: settlement P&L.** It is the money. Its limit, stated: on a binary
  held to expiry it is dominated by directional variance, so **the effective
  sample is games, not fills.**
- **SECONDARY: markout at pre-named horizons.** Lower variance, real power at
  this n, and it is the metric that **exhibits the mechanism** — phantoms
  profit because price reverts, real fills lose because it continues.
- **Phantom flag on every arm and every cut**, always reported.

## Consequence for the Saturday design

**Engines are for counterfactual PRICES; cuts are for counterfactual
SELECTIONS.** Per-fill capture is a market fact at the fill instant and does not
depend on the engine's inventory or history — so WIDTH, LATE-SUPPRESS and
PATIENCE are **stratifications of BASE's own fills**, readable on all of BASE's
fills rather than a fifth of the slate. They need no arm slot, which dissolves
the power constraint that made WIDTH-FLOOR the binding arm.

**FLATTEN is the only registered arm that is genuinely a price counterfactual** —
you cannot recover "what if we had offered a cent tighter" from a tape where we
never did. **It is also the only arm that leaves the losing family rather than
partitioning it.** Saturday: BASE + FLATTEN as engines, everything else as
pre-declared cuts, FLATTEN additionally scored on dispersion and tail rather
than mean.

## FLATTEN's k, re-run on real fills — RESOLVED

The parameter was re-derived with the phantom filter, scored on settlement
(D's whole-book replay):

| k | all-fills ΔP&L | real fills | real ΔP&L | per-game, clustered |
|---:|---:|---:|---:|---|
| **1¢** | +$76 | 5,295 | **+$17.55** | **+1.95¢ [−2.80, +6.70]** |
| 2¢ | +$57 | 5,713 | −$38.98 | −4.33¢ [−11.12, +2.46] |
| 3¢ | +$28 | 6,094 | −$37.83 | −4.20¢ [−11.61, +3.20] |
| 5¢ | −$14 | 6,657 | −$50.85 | −5.65¢ [−12.81, +1.51] |

**RETRACTED 2026-09-03, same day: the "positive region collapses to {1¢}
alone" claim was an artifact of EXCLUSION.** Filtering phantoms from the score
does not remove them from the POLICY — the simulator's inventory counted them,
and inventory steers the lean, so phantom fills chose quote paths that exclusion
cannot undo. **Re-run with the order inserted into the book, all of 1/2/3¢ beat
k=0 and the curve is a clean monotone decay from a peak at 1¢.** k=1¢ is still
best, but **the improvement figure moved twice more: +$30.43 was itself measured
on a substrate missing 25% of the board; at full coverage it is +$10.10 and the
positive region is {1¢} alone.** See the registration's FINAL k-curve. **The dramatic finding was the artifact;
the undramatic one was closer to right.** Known-answer check: at k=0 the two
methods must and do agree to the penny (4,321 fills, −$156.35). **k=1¢ stands as registered — hardened
in the sense of surviving the artifact test, NOT in the sense of being proven
positive: its per-game CI spans zero.**

**The boundary was predicted correctly from a mechanism that turned out to be
wrong, and the record should say so.** The manager predicted the flip at
s/2 = 2¢ via *"a lean past half the spread manufactures an instant phantom."*
The phantom share barely moves with k (61.9 / 65.0 / 66.5 / 65.8 / 63.8%) — **no
jump at 2¢, so that mechanism is not operating**; the post-only clamp (lean
capped at bid + one tick) removes the instant-fill regime before it can bite.
**A correct boundary from a wrong mechanism is a coincidence until something
else explains it.**

The manager's second explanation — *s/2 is the touch-to-mid distance, so
leaning past it means quoting THROUGH fair value* — **is also REFUTED, by its
own prediction.** If the boundary were spread capture reaching zero it would
have to SCALE with each market's spread. Split by each market's own median
quoted spread, real fills, per-fill settlement:

| band | median s | s/2 predicts | measured best k |
|---|---:|---:|---:|
| tight <2.5¢ | 2.0¢ | ≤1.0¢ | 3¢ |
| mid 2.5–4.5¢ | 3.5¢ | ≤1.7¢ | 1¢ |
| wide >4.5¢ | 7.0¢ | ≤3.5¢ | 1¢ |

**No scaling; if anything it runs inverse.** Two mechanisms proposed, two
refuted by the data each predicted.

**THE CLAMP RESOLVES THE ODD CELL AND UNIFIES THE PICTURE.** In a 2¢ market with
a 1¢ tick, `max(A₀−k, bid+tick)` clamps every k ≥ 1¢ to the SAME quote. The
tight band reads −3.03 / −3.21 / −2.89 / −3.02 across k = 1/2/3/5¢ — **four
indistinguishable numbers because they are the same policy four times**, and its
"best k = 3¢" is noise between identical quotes. The honest statement is about
**EFFECTIVE lean = min(k, s − tick)**: once the clamp is accounted for, **~1¢ is
best in every band; larger k only differs where the spread is wide enough to
permit it, and that is exactly where it hurts.**

**k=1¢ THEREFORE STANDS ON AN EMPIRICAL REGULARITY, NOT A MECHANISM** — it
improves per-fill P&L in **all three** spread bands (tight −4.17→−3.03, mid
−3.04→−2.82, wide −2.81→−1.13). Consistency across heterogeneous markets is a
stronger basis than the aggregate that motivated it. **Registered as a
regularity with two dead explanations behind it, rather than attaching a third
story that might also fail** (D's call, and the right one).

**★ THE CAVEAT THAT OUTRANKS THE PARAMETER: EVERY CELL IS NEGATIVE AT EVERY k.**
The best cell on the board is wide-band k=1¢ at **−1.13¢/fill**. **Flattening
improves a losing book; nothing here makes it a winning one.** The aggregate
+$17.55 at k=1¢ is a fill-count and mix effect, **not a per-fill positive** —
which must be said plainly before *"FLATTEN is the only arm that leaves the
losing family"* hardens into *"FLATTEN wins."* **It leaves the family by being
less negative.**

**PORTING TO GRIDIRON:** because the boundary does NOT scale with spread,
expressing k as a fraction of spread would be wrong — **a fixed 1¢ is the
correct default for NFL**, noting the clamp interaction: NFL's traded cells at
5–6¢ leave room for a 1¢ lean to be a genuine 1¢, unlike WNBA's tight band where
it was forced.

## Two independent measurements agree

| instrument | population | settlement P&L / fill |
|---|---:|---:|
| fills table + book join (manager) | 6,255 real fills | **−3.38¢** |
| whole-book replay (D) | 4,321 real fills | **−3.62¢** |

Different code, different populations, neither author having seen the other's
query — **a quarter of a cent apart.**

**CHARACTERISED CAREFULLY, because "convergence" was the wrong word and it was
used three times before being audited.** These two numbers do **not** estimate
the same quantity. The manager's count reads the engine's OWN RECORDED FILLS
from `shadow_quote_fills` and classifies them against the book. D's count comes
from a REPLAYED k=0 POLICY that re-derives quote placement from the tape — D
said so explicitly ("a third object again, not a subset count of your tape").
**Two constructions that select different fill sets by construction cannot
validate each other by matching; if they truly measured one deterministic
quantity on a fixed tape they would agree EXACTLY, and 2% would be a
discrepancy rather than agreement.**

**CHECKED AT THE ROW LEVEL rather than argued, and it is worse than "different
constructions": the two sets overlap on only 2,462 fills — about 41% on
(market, 5s bucket, side, price), and still only ~49% ignoring price entirely.
They share fewer than half their members.** The replay re-derives quote
placement from policy on a 5s grid; v1 ran on the raw tick stream with
move-triggered requoting. **The totals landing 2.4% apart is an aggregate
coincidence, and comparing per-fill means across populations sharing under half
their members is not a replication.**

**This also retracts an older milestone claim** — that the whole-book replay
baseline and the fills-table read were "the first time the settlement economics
were measured twice". They were **one quantity measured once, and a different
quantity measured once, sitting next to each other.**

**NOT retracted, so this does not over-correct in the other direction: the
k-curve's internal comparisons stand.** Every k uses the same procedure on the
same grid, so differences BETWEEN k values are real and k=0 is a valid
within-procedure baseline arm — it is a control, not a replication of v1.

What the closeness DOES support, and it is not nothing: **the economics do not
depend sensitively on which quote path is used** — an engine's actual historical
quotes and a policy replay of the same rule land within 2% on population and
half a cent per fill. That is robustness to quote path, **not** two instruments
agreeing on one measurement. The stronger claim was asserted and is withdrawn.
 After a night in which the headline moved
because the measurement was wrong, two instruments agreeing is worth more than
either alone. The contamination gap reproduces through both bases (D's −3.62¢
real vs −1.87¢ all-fills; the manager's −3.38¢ real vs the ledgered blend).

## Superseded note on FLATTEN's parameter

**Open and blocking on FLATTEN's parameter:** leaning an ask from A₀ to A₀ − k
satisfies the model's condition at quote time whenever **k ≥ s/2**, while
reality needs **k ≥ s** — so any lean past half the spread manufactures an
instant phantom. At ~4¢ spreads that threshold is 2¢, and the registered k-curve
turned positive→negative between 2¢ and 3¢. **k=1¢ may have been selected by the
artifact.** The curve must be re-run on real fills only before the slate.

## What this does and does not say

It does **not** say market making cannot work here. It says **joining the touch
and waiting loses 3.4¢ a fill on this tape**, that no selection within that
family rescues it, and that the mechanism is adverse selection rather than
mis-tuning. **No in-sample result justifies capital. The forward test is the
evidence.**

## ★ THE SEPARATION IS NOW CODE, AND IT READS 24 GAMES — 2026-09-04 ★

Everything above was ad-hoc queries against prod. `core/quote/report.py` — the
scoring path the QUOTE dashboard and `python -m core.quote.report` both read —
**had no phantom classifier at all**, was already past its floors on the blend
(38,465 settled fills / 24 games against floors of 500 / 10), and still printed
capture. It would have scored tomorrow's slate on the blend. It no longer can:
the floors and the verdict bind on `population='real'`, and the blend is never
scored.

### The substrate trap, which cost the first run and is reusable

The obvious table for "the book at the fill instant" is `book_levels`. **It is
the wrong one, and it fails quietly in the flattering direction.** `book_levels`
is a **slow depth loop** sampled independently of the price loop. Measured
against these fills it sits a **median 6.8 s and mean 13.3 s behind** the fill
instant (max 128.6 s). Against the registered ≤5 s lookback that drops **73.6%
of all fills and 93.6% of the September ones**, and the survivors are biased:

| substrate | matched | phantom share | WNBA real fills |
|---|---:|---:|---:|
| `book_levels` (depth loop) | 26.4% | **84.9%** | 1,531 → wrong |
| `market_snapshots.best_bid/ask` (price loop) | **100.0%** | **63.9%** | **6,255 → exact** |

`market_snapshots` is the loop the fill was generated from, so the touch is at
**age 0.0 s on 38,465/38,465 fills, in both eras**. The report now prints that
max age beside the counts, so a future run on the wrong table says so out loud
instead of returning a clean, wrong number.

**The tell, reusable:** a coverage-dependent instrument that returns a *plausible*
number. 84.9% is not absurd on its face; nothing in the output complained. It
was caught only by refusing to compare it to anything until coverage was
measured. Counts and composition before ratios — the third time on this feed.

### Validation before any new claim

The classifier is written independently of the manager's original query and
reproduces it **to the digit** on WNBA: 17,339 fills, **6,255 real**, phantom
share **63.9%**, real settlement **−3.376¢/fill**, clustered **−3.419¢
[−5.062, −1.777]** on 13 games, phantom **+0.951¢**, **12 of 13 games lose**.
Every one of those matches the recorded values above.

### The 24-game read — the effect replicates and tightens

Settlement P&L per fill, real population, mean of game means, game-clustered:

| cohort | fills | G | mean | 95% CI |
|---|---:|---:|---:|---|
| WNBA (the recorded 13) | 6,255 | 13 | −3.419¢ | [−5.062, −1.777] |
| **CFB (11 NEW games)** | **7,396** | **11** | **−2.683¢** | **[−5.439, +0.073]** |
| **pooled** | **13,651** | **24** | **−3.082¢** | **[−4.502, −1.661]** |

**20 of 24 games lose money on real fills.** The interval narrowed from 3.29¢
wide to 2.84¢ wide and stayed entirely negative.

### ★ THE PRE-REGISTERED SURPRISE IS TESTED, AND IT DOES NOT APPEAR ★

*"BASE near zero on football"* was recorded above as **UNTESTED, not refuted** —
settlement was unreadable at 6/11 games with a clustered CI of **[−41.9, +16.8]**.
All 11 CFB games now carry settled real fills. The CI is **[−5.44, +0.07]**, a
band **80× narrower**, and it sits on the losing side.

**CFB − WNBA = +0.736¢, se 1.448, Welch t = +0.51, band [−2.29, +3.76].** There
is **no evidence football is different**, and the surprise's own direction —
football better — is not supported. Stated precisely: this does not prove the
two leagues are identical; the band still admits a ±3¢ difference. It says the
football escape hatch the registration hoped for **is not visible at 11 games**,
and touch-joining loses on football at the same order as on basketball.

The phantom share replicates across sports as the mechanism predicts, because it
is a property of the SIMULATOR: **WNBA 63.9%, CFB 65.0%.**

### The width gradient, checked from the other side

The ruling above says capture's monotone width gradient was the instrument
reproducing its own algebra, and predicts settlement will not be monotonic.
Independently recomputed on 24 games of real fills:

| quoted spread | n | settlement, clustered |
|---|---:|---|
| ≤1.5¢ | 6,660 | −1.974¢ [−4.089, +0.142] |
| 1.5–2.5¢ | 2,741 | −1.609¢ [−4.106, +0.888] |
| 2.5–3.5¢ | 1,486 | −6.716¢ [−9.424, −4.008] |
| 3.5–5.5¢ | 1,445 | −3.411¢ [−6.975, +0.153] |
| >5.5¢ | 1,319 | −5.609¢ [−9.106, −2.112] |

**Not monotonic, CIs ~3¢ wide.** The prediction holds. *Note this cuts against
the earlier reading that "a spread widens because informed flow is expected" —
on settlement, the widest band is not the worst and the ordering is noise. That
mechanism was argued from capture and does not survive the metric it was
retired for.*

### A unit trap in the record above

The table at the top gives the ledgered blend as **−1.60¢**, and that is a
**capture** number. On **settlement** — the primary metric — the WNBA blend is
**−0.610¢** against −3.376¢ real: the blend understates the real loss by
**5.5×**, not the ~2.1× the capture figures imply. Pinned as a test
(`tests/test_quote_report.py`), because the two numbers look comparable and are
not.

### What is now enforced rather than written

`scripts/guard_coverage.py`: rules **22, 23 and 25 are WIRED** (they were all
UNWIRED at 22:46 yesterday), all three from `core/quote/report.py`.

* **22** — no count in the report can print bare. A population that returns zero
  prints `UNPROVEN INSTRUMENT`, because this run has no evidence that branch can
  fire. Provenance is attached only to the quantity it belongs to: the first
  wiring printed the regime's fill history beside a *population's* zero, which
  makes the zero mis-readable and is worse than a bare zero.
* **23** — the touch join is BACKWARD and its age is **asserted non-negative**,
  not merely capped. D shipped a forward join today whose `age <= 5` admitted a
  book from 25 hours *after* the fill; a one-sided cap on an age whose join
  points the other way is vacuous and reads exactly like a freshness gate.
* **25** — the staked-ROI prints its numerator, denominator and per-event mean,
  and warns that its argmax ranks inactivity. It fires on the live prod read.

**No in-sample result justifies capital. The forward test is the evidence.**
