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
