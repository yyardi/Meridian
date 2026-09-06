# The football money bar — set before the model exists

**Purpose.** B and d5 are building a CFB live model with the market as a feature.
Every model this programme has scored on accuracy first and asked "does it pay?"
afterwards, and that order cost us today. This sets the money bar *before* the
model exists, so a fitted model can be judged the day it produces a number.

**The one-line answer.** A CFB model pays as a **taker** if its per-trade edge
beats **≈3.0–3.75pp** (at p=0.50) — a WNBA-derived **proxy**, because the only CFB
book tape available today was frozen (§2); it pays as a **maker** at a lower
nominal bar (**~0–1.4pp**) but on adverse-selection terms the passive study could
not fully measure. Passive market-making *without a forecast* is closed (separate
doc); a **taker with genuine edge is a different strategy on a different bar and
nothing we established today closes it.** Every spread below is labelled **full**
or **half** — an unlabelled spread is two different numbers.

---

## 1. The two bars

| strategy | pays | break-even edge (p=0.50) | selection |
|---|---|---|---|
| **Taker** (cross to the touch) | market **half**-spread + taker fee | **~3.0–3.75pp** (WNBA proxy; CFB unmeasured) | none — it initiates; owns the position at fair |
| **Maker** (rest to settlement) | our quoted **half**-spread, no fee/rebate | **0pp on costs; ~1.4pp once adverse selection is charged** | ~46% of intents never fill; fills are adversely selected |

The bars differ by the whole spread: a taker **pays** the half-spread, a maker
**earns** part of it (as price improvement) but is adversely selected into the
tail. That is why the maker's nominal bar is *lower* — it is not free, it is
paid in fill-selection instead of cents.

---

## 2. The CFB half-spread — UNMEASURED (the only CFB tape today was frozen)

The taker crosses the market book, so the input is the **market full-spread
`(ask − bid)`**, halved for the crossing cost — the **half-spread** `(ask−bid)/2`
— at in-game moments on full-game markets.

> **⚠ RETRACTED — the CFB number was frozen-contaminated.** The only CFB book tape
> available today (`cfb_prices_20260906T194301Z.csv.gz`) is 99.5% inside the
> 2026-09-05 17–22Z venue freeze: 99% of markets with ≥20 snapshots show ≤2
> distinct book states (one had 1,178 snapshots and 6 distinct books). A frozen
> book is whatever the venue stopped updating at, not a traded spread. An earlier
> version of this doc read a **0.5¢ half-spread median** off it and concluded "CFB
> is tighter than WNBA"; **both are withdrawn.**

**A clean CFB tape exists but is not reachable to me.** The restored live tape
(post-2026-09-06 20:00Z, ~82% pct_moved, ~700 rows/market) is clean, but it is in
prod: SSH is classifier-blocked for me, and the local restored export carries no
`best_bid`/`best_ask`. Measuring it needs a **post-20:00Z CFB
`best_bid`/`best_ask` export pulled to `backups/exports/`** (same shape as
`cfb_prices`); then it is a one-command measurement. Until then the CFB
half-spread is **UNMEASURED**.

**Proxy until a clean CFB tape lands: the WNBA market-book half-spread**, on the
engine's quotable band (mid ∈ [0.20, 0.80], full spread ∈ [1¢, 15¢]), from
`delta_market_snapshots` (2026-07-31…08-20, not frozen; 1.81M snapshots):

| WNBA market-book, quotable band | **full** spread | **half** spread |
|---|---:|---:|
| median | 3.00¢ | **1.50¢** |
| mean | 4.50¢ | **2.25¢** |

The proxy taker crossing cost is a **half-spread of 1.5–2.25¢**. This is the
*market-book* spread the taker crosses; it is distinct from H in the making-close,
which is *our quoted* half-spread `s_q/2 = 1.569¢` — that reconciliation is now
resolved (making-close §1). CFB may differ once measured; Saturday's slate is the
volume, tonight is whether the pipeline yields a number at all.

---

## 3. Taker threshold τ(p) = half-spread + 0.06·p(1−p)

One taker fee (coefficient 0.06, venue-verified; **no maker rebate**), no exit
leg because binaries settle. `half-spread` here is the **WNBA-proxy market
half-spread** (1.5¢ median / 2.25¢ mean; CFB unmeasured, §2). The fee is largest
at p=0.50 and shrinks toward the extremes; the threshold tracks it.

| p | fee = 0.06·p(1−p) | τ at 1.5¢ **half**-spread (median) | τ at 2.25¢ **half**-spread (mean) |
|---:|---:|---:|---:|
| 0.50 | 1.50¢ | **3.00pp** | **3.75pp** |
| 0.40 | 1.44¢ | 2.94pp | 3.69pp |
| 0.30 | 1.26¢ | 2.76pp | 3.51pp |
| 0.20 | 0.96¢ | 2.46pp | 3.21pp |
| 0.10 | 0.54¢ | 2.04pp | 2.79pp |

So on the WNBA proxy a CFB taker needs a per-trade edge of **~3.0–3.75pp near
p=0.5**, less at the extremes. Whether CFB is tighter or wider than WNBA is
**unknown** until a clean CFB tape is measured (§2) — the earlier "CFB is tighter"
claim was frozen-tape contamination and is withdrawn.

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
   (≈3.0–3.75pp taker, WNBA proxy)? Equivalently, is the per-traded-market Brier
   improvement `> τ²` (≈9×10⁻⁴–1.4×10⁻³)? The population number (e.g. the live model's declined-branch
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

- A **taker with edge > ~3.0–3.75pp** (WNBA proxy) crosses, owns the position at
  fair, and eats no adverse selection. The making close does not apply to it — it
  is a different strategy on a different bar.
- Whether CFB's spread makes that bar lower or higher than WNBA is **unknown**
  until a clean CFB tape is measured (§2); the frozen-tape "CFB is tighter" claim
  is withdrawn.

**Said plainly: nothing established today rules out a football taker with real
forecast edge. We only ruled out earning the spread without a forecast.** The
open question is entirely whether B and d5's model can produce ≥~3.0–3.75pp of
per-trade edge (on the WNBA-proxy bar), concentrated on the markets it trades —
and that is now judgeable on day one against the bars above.

---

*Measurements: WNBA market-book half-spread (proxy) from `delta_market_snapshots`
(2026-07-31…08-20), mine, on the engine's quotable band. CFB half-spread
UNMEASURED — the only CFB tape (`cfb_prices_20260906T194301Z`) was inside the
2026-09-05 venue freeze (§2); a clean post-20:00Z export is needed. Adverse anchor
`A_CFB` and the passive floor from `docs/math/market-making-close.md`. Taker fee
0.06 venue-verified; no maker rebate (`findings.md` C7/V24). All spreads labelled
full/half. The making-close H is now resolved as our quoted half-spread s_q/2 =
1.569¢ (making-close §1), superseding the withdrawn 1.193¢.*
