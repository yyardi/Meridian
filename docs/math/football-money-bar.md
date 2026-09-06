# The football money bar — set before the model exists

**Purpose.** B and d5 are building a CFB live model with the market as a feature.
Every model this programme has scored on accuracy first and asked "does it pay?"
afterwards, and that order cost us today. This sets the money bar *before* the
model exists, so a fitted model can be judged the day it produces a number.

**The one-line answer.** A CFB model pays as a **taker** if its per-trade edge
beats **≈2.0–2.5pp** (at p=0.50); it pays as a **maker** at a lower nominal bar
(**~0–1.4pp**) but on adverse-selection terms the passive study could not fully
measure. Passive market-making *without a forecast* is closed (separate doc); a
**taker with genuine edge is a different strategy on a different bar and nothing
we established today closes it.**

---

## 1. The two bars

| strategy | pays | break-even edge (p=0.50) | selection |
|---|---|---|---|
| **Taker** (cross to the touch) | half-spread + taker fee | **2.0–2.5pp** | none — it initiates; owns the position at fair |
| **Maker** (rest at the touch) | nothing on costs (no fee, no rebate) | **0pp on costs; ~1.4pp once adverse selection is charged** | ~46% of intents never fill; fills are adversely selected |

The bars differ by the whole spread: a taker **pays** the half-spread, a maker
**earns** part of it (as price improvement) but is adversely selected into the
tail. That is why the maker's nominal bar is *lower* — it is not free, it is
paid in fill-selection instead of cents.

---

## 2. The CFB half-spread — measured, not assumed

The taker crosses the market book, so the input is the **market** best-bid/
best-ask half-spread `(ask − bid)/2` at in-game moments, on full-game markets.
Measured on the continuous CFB tape (`cfb_prices_20260906T194301Z.csv.gz`,
532,328 in-game full-game snapshots, stale books >10¢ half trimmed):

| population | median | trimmed mean | p5–p95 |
|---|---:|---:|---:|
| CFB, all mids | 0.50¢ | 1.23¢ | 0.50–5.50 |
| **CFB, 0.4<mid<0.6 (competitive)** | **0.50¢** | **1.04¢** | 0.50–3.50 |
| WNBA, all mids | 2.00¢ | 2.57¢ | 0.50–7.50 |
| WNBA, 0.4<mid<0.6 | 1.50¢ | 2.13¢ | 0.50–6.50 |

**CFB is *tighter* than WNBA, not wider.** CFB full-game markets sit at a 1-tick
spread (0.5¢ half) more than half the time; the distribution is bimodal — a tight
median with a heavy wide tail (16% of snapshots >5¢ half, 10.5% >10¢ and dropped
as stale). So the taker's spread cost is **0.5¢ if it has any spread discipline,
~1.0¢ if it crosses at a random in-game moment.**

> **⚠ RECONCILIATION FLAG (do not paper over).** d5's WNBA taker threshold and
> the passive-making close both use a WNBA half-spread of **1.193¢**. I cannot
> reproduce that from two independent WNBA market-book tapes — both give **~2.0¢
> median / ~2.1–2.6¢ mean**. So 1.193¢ is not the time-average market book; it is
> a *different population* — most likely **our own quoted half-spread** (we quote
> tighter than the market) or the spread at **touch-event moments** (tighter by
> selection). This matters two ways: (a) if 1.193¢ is our quote, the WNBA *taker*
> faces a wider real spread (~2.1¢ → τ≈3.6pp, not 2.69pp); (b) the making-close
> `H` may need the same audit. The CFB taker number below is measured directly
> from the CFB market book, so it does not inherit this gap — but the WNBA
> comparison is only valid once c7 pins what 1.193¢ measures.

---

## 3. Taker threshold τ(p) = half-spread + 0.06·p(1−p)

One taker fee (coefficient 0.06, venue-verified; **no maker rebate**), no exit
leg because binaries settle. The fee is largest at p=0.50 and shrinks toward the
extremes; the threshold tracks it.

| p | fee = 0.06·p(1−p) | τ at 0.5¢ spread (disciplined) | τ at 1.0¢ spread (random cross) |
|---:|---:|---:|---:|
| 0.50 | 1.50¢ | **2.00pp** | **2.50pp** |
| 0.40 | 1.44¢ | 1.94pp | 2.44pp |
| 0.30 | 1.26¢ | 1.76pp | 2.26pp |
| 0.20 | 0.96¢ | 1.46pp | 1.96pp |
| 0.10 | 0.54¢ | 1.04pp | 1.54pp |

So a CFB taker needs a per-trade edge of **~2.0–2.5pp near p=0.5**, less at the
extremes. Because CFB spreads are tighter than WNBA, this is **at or below** the
2.69pp WNBA figure d5 quoted — the tick-wide market is the reason.

---

## 4. The maker bar, and its honest uncertainty

A maker rests and pays no fee (no rebate: `θ_maker = 0`), so on **transaction
costs** its break-even edge is exactly **0.00pp** — ce's number, and correct as
stated. But resting is **adversely selected**: fills arrive when the mid is about
to move against you. The passive-making study measured the adverse anchor
`A_CFB = −1.357¢` per fill (fills-weighted, rebate-free; CI [−2.75, +0.04] spans
zero). So a resting model's realized per-fill P&L ≈ `edge − |A| + benign-offset`:

- **Conservative maker bar ≈ 1.4pp** (edge must cover the full adverse anchor).
- **Lower with benign fills** (benign fills earn the spread and offset A), but the
  benign share is the one quantity the simulator structurally **cannot measure**
  — it is why the making close needs a probe. So the maker bar below ~1.4pp is
  **unverified**, not established.

Net: the maker bar is *nominally* below the taker bar, but it is soft — it rests
on the unmeasured benign side — whereas the taker bar is hard (measured spread +
known fee). **Prefer the taker bar as the design target unless a probe pins the
benign share.**

---

## 5. Money ↔ Brier — the mapping, so nobody re-derives it

The afternoon's confusion was mixing B's money scorer (`pulse_money_scorer.py`,
`pnl = s·(S − limit_price)`) with the Brier scorer (`pulse_branch_scoring.py`,
`Brier(mkt) − Brier(model)`). They are related but not the same, and the relation
is exact for a calibrated model.

Let `d = p_model − p_mkt` (signed edge), truth `y`, model calibrated (`E[y]=p`):

- **Money** (taker, bet the model's side, hold to settle) per market = **|d|**.
- **Brier improvement** per market = `(q−y)² − (p−y)²` = **d²** (in expectation over y).

So **per market, Brier improvement = money²**:

| per-trade edge |d| | Brier improvement (prob²) | ×10⁴ |
|---:|---:|---:|
| 1pp | 0.000100 | 1.0 |
| 2pp | 0.000400 | 4.0 |
| **2.5pp (taker bar)** | **0.000625** | **6.25** |
| 3pp | 0.000900 | 9.0 |
| 5pp | 0.002500 | 25.0 |
| 10pp | 0.010000 | 100.0 |

**The trap this closes.** Population Brier improvement (what the accuracy headline
reports) is `E[d²] = (mean money)² + Var(|d|)` — it is dominated by edge
*dispersion*, not by the money you make. Two consequences:

1. **A positive population Brier does not mean the model pays.** If the edge is
   spread thinly across all markets below τ, the model is more accurate and still
   loses to costs. Money needs the edge **concentrated above τ** on the markets it
   actually trades.
2. **The bar is on the per-*traded*-market edge, not the population Brier.** Judge
   a CFB model by: on the markets it chooses to trade, is mean `|d| > τ`
   (≈2.0–2.5pp taker)? Equivalently, is the per-traded-market Brier improvement
   `> τ² ≈ 6×10⁻⁴`? The population number (e.g. the live model's declined-branch
   `+0.002–0.003`, entered `≈0`) is not that bar — it mixes traded and untraded
   markets and hides whether the edge clears costs where it is spent.

Selection is the whole game: a model with a small average edge but the discipline
to trade only its `|d| > τ` markets pays; a more "accurate" model that trades
everything does not.

---

## 6. The route today's negatives do NOT close

Passive market-making is closed **for earning the spread without a forecast** —
the benign fill share (≤23.7–35.8%) cannot clear the passive break-even floor.
That result says nothing about a model with genuine directional edge:

- A **taker with edge > ~2.5pp** crosses, owns the position at fair, and eats no
  adverse selection. The making close does not apply to it — it is a different
  strategy on a different bar.
- The tight CFB market (0.5¢ half-spread median) makes that bar **lower on CFB
  than on WNBA**, which is the most encouraging thing measured today.

**Said plainly: nothing established today rules out a football taker with real
forecast edge. We only ruled out earning the spread without a forecast.** The
open question is entirely whether B and d5's model can produce ≥2.0–2.5pp of
per-trade edge, concentrated on the markets it trades — and that is now
judgeable on day one against the bars above.

---

*Measurements: CFB/WNBA half-spread from the continuous book tapes
(`cfb_prices_20260906T194301Z`, `delta_market_snapshots`), mine. Adverse anchor
`A_CFB` and the passive floor from `docs/math/market-making-close.md`. Taker fee
0.06 venue-verified; no maker rebate (`findings.md` C7/V24). The 1.193¢ WNBA
half-spread is c7's and is flagged unreconciled above.*
