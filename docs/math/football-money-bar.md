# The football money bar — set before the model exists

**Purpose.** B and d5 are building a CFB live model with the market as a feature.
Every model this programme has scored on accuracy first and asked "does it pay?"
afterwards, and that order cost us today. This sets the money bar *before* the
model exists, so a fitted model can be judged the day it produces a number.

**The one-line answer.** A CFB model pays as a **taker** if its per-trade edge
beats **≈2.5–3.5pp** (at p=0.50) — measured on tonight's clean CFB tape, **one
game** (G=1); it pays as a **maker** at a lower nominal bar (**~0–1.4pp**) but on
adverse-selection terms the passive study could not fully measure. Passive
market-making *without a forecast* is closed (separate doc); a **taker with genuine
edge is a different strategy on a different bar and nothing we established today
closes it.** Every spread below is labelled **full** or **half** — an unlabelled
spread is two different numbers.

---

## 1. The two bars

| strategy | pays | break-even edge (p=0.50) | selection |
|---|---|---|---|
| **Taker** (cross to the touch) | market **half**-spread + taker fee | **~2.5–3.5pp** (CFB, one game, clean tape) | none — it initiates; owns the position at fair |
| **Maker** (rest to settlement) | our quoted **half**-spread, no fee/rebate | **0pp on costs; ~1.4pp once adverse selection is charged** | ~46% of intents never fill; fills are adversely selected |

The bars differ by the whole spread: a taker **pays** the half-spread, a maker
**earns** part of it (as price improvement) but is adversely selected into the
tail. That is why the maker's nominal bar is *lower* — it is not free, it is
paid in fill-selection instead of cents.

---

## 2. The CFB half-spread — measured on tonight's clean tape (one game)

The taker crosses the market book, so the input is the **market full-spread
`(ask − bid)`**, halved for the crossing cost — the **half-spread** `(ask−bid)/2`
— at in-game moments on full-game markets.

**Measured on tonight's restored tape** (`cfb_prices_tonight_20260906T221035Z`,
2026-09-06 20:33–21:43Z), one genuinely-live game (venue 16486; 51 full-game
markets; **0% frozen** — every market with ≥20 snapshots moved), quotable band
(mid ∈ [0.20, 0.80], full spread ∈ [1¢, 15¢]):

| CFB in-game full-game (game 16486) | **full** spread | **half** spread |
|---|---:|---:|
| median | 2.00¢ | **1.00¢** |
| mean | 3.91¢ | **1.96¢** |

The CFB taker crossing cost is a **half-spread of ~1.0–2.0¢** (median–mean).
**G = 1** — one game, enough for a spread distribution, not for any interval;
Saturday's slate is the volume. It brackets the WNBA market-book half-spread (1.50¢
median / 2.25¢ mean, `delta_market_snapshots`, same band), so CFB is **not**
dramatically different from WNBA — the earlier "CFB is much tighter" claim is gone.

> **⚠ The earlier 0.5¢ CFB half-spread median was frozen-contaminated, withdrawn.**
> The only CFB tape before tonight (`cfb_prices_20260906T194301Z`) was 99.5% inside
> the 2026-09-05 17–22Z venue freeze (99% of markets with ≥20 snapshots had ≤2
> distinct book states; one had 1,178 snapshots and 6 distinct books). Tonight's
> tape moves (95.3% of markets), so it is a real spread. Note H in the making-close
> is a *different* quantity — our *quoted* half-spread `s_q/2 = 1.569¢`, resolved
> there (making-close §1) — not this market-book spread.

---

## 3. Taker threshold τ(p) = half-spread + 0.06·p(1−p)

One taker fee (coefficient 0.06, venue-verified; **no maker rebate**), no exit
leg because binaries settle. `half-spread` here is the **CFB market half-spread**
measured tonight (1.0¢ median / 1.96¢ mean, one game; §2). The fee is largest at
p=0.50 and shrinks toward the extremes; the threshold tracks it.

| p | fee = 0.06·p(1−p) | τ at 1.0¢ **half**-spread (CFB median) | τ at 1.96¢ **half**-spread (CFB mean) |
|---:|---:|---:|---:|
| 0.50 | 1.50¢ | **2.50pp** | **3.46pp** |
| 0.40 | 1.44¢ | 2.44pp | 3.40pp |
| 0.30 | 1.26¢ | 2.26pp | 3.22pp |
| 0.20 | 0.96¢ | 1.96pp | 2.92pp |
| 0.10 | 0.54¢ | 1.54pp | 2.50pp |

So a CFB taker needs a per-trade edge of **~2.5–3.5pp near p=0.5** (median–mean,
one game), less at the extremes. This is close to WNBA (§2), **not** dramatically
tighter — the earlier "CFB is much tighter" claim was frozen-tape contamination
and is withdrawn. G=1; Saturday's slate firms the number.

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
   (≈2.5–3.5pp taker, CFB one game)? Equivalently, is the per-traded-market Brier
   improvement `> τ²` (≈6×10⁻⁴–1.2×10⁻³)? The population number (e.g. the live model's declined-branch
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

- A **taker with edge > ~2.5–3.5pp** (CFB, one game) crosses, owns the position at
  fair, and eats no adverse selection. The making close does not apply to it — it
  is a different strategy on a different bar.
- CFB's measured spread is close to WNBA's (§2), so the bar is ~2.5–3.5pp on both;
  the frozen-tape "CFB is much tighter" claim is withdrawn.
- **Where the edge must come from (ce).** ESPN's CFB win probability carries almost
  no *pregame* information — over 33 kickoffs its first-tick WP has sd 0.0222
  (range 0.52–0.66), against the venue's pregame boards at sd 0.2663, a ~12× gap.
  So a taker edge cannot come from ESPN's public model; it must come from a
  **pregame prior the venue does not already have** — and the venue has a strong
  one. The bar to beat is the **venue**, not ESPN, and τ (above) decides whether
  any residual edge survives costs.

**Said plainly: nothing established today rules out a football taker with real
forecast edge. We only ruled out earning the spread without a forecast.** The
open question is entirely whether B and d5's model can produce ≥~2.5–3.5pp of
per-trade edge **against the venue's own pregame prior**, concentrated on the
markets it trades — and that is now judgeable on day one against the bars above.

---

*Measurements: CFB market-book half-spread from tonight's clean tape
(`cfb_prices_tonight_20260906T221035Z`, game 16486, one game, 0% frozen), mine, on
the engine's quotable band; WNBA comparison from `delta_market_snapshots`
(2026-07-31…08-20). The earlier CFB tape (`cfb_prices_20260906T194301Z`) was inside
the 2026-09-05 venue freeze and is withdrawn (§2). Adverse anchor `A_CFB` and the
passive floor from `docs/math/market-making-close.md`. Taker fee 0.06
venue-verified; no maker rebate (`findings.md` C7/V24). All spreads labelled
full/half. The making-close H is our quoted half-spread s_q/2 = 1.569¢
(making-close §1), a different quantity from this market-book spread; the withdrawn
1.193¢ is superseded. ESPN pregame-WP dispersion from ce.*
