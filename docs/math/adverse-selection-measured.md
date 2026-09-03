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
