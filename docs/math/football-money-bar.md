# The football money bar — set before the model exists

**Purpose.** B and d5 are building a CFB live model with the market as a feature.
Every model this programme has scored on accuracy first and asked "does it pay?"
afterwards, and that order cost us today. This sets the money bar *before* the
model exists, so a fitted model can be judged the day it produces a number.

**The one-line answer.** A CFB model pays as a **taker** if its per-trade edge
beats τ **for the market type and price it trades** — measured on tonight's clean
tape (one game, G=1): **~2.0pp on spreads, ~3.5pp on totals near p=0.5**, and
**~0.5pp on the winner market at the blowout prices it occupied** (its p=0.5 spread
is unmeasured). It pays as a **maker** at a lower nominal bar (**~0–1.4pp**) on
adverse-selection terms the passive study could not fully measure. Passive
market-making *without a forecast* is closed (separate doc); a **taker with genuine
edge is a different strategy on a different bar and nothing we established today
closes it.** Every spread below is labelled **full** or **half**, and every τ its
market type and price — an unlabelled number is several.

---

## 1. The two bars

| strategy | pays | break-even edge (p=0.50) | selection |
|---|---|---|---|
| **Taker** (cross to the touch) | market **half**-spread + taker fee | **per type**: ~2.0pp spread, ~3.5pp total @ p=0.5; ~0.5pp winner @ blowout (p=0.5 unmeasured) | none — it initiates; owns the position at fair |
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

The spread depends on **market type**, with a 16× range across types (c7), so
pooling hides which bar a strategy faces:

| CFB market type (game 16486) | median mid | **half**-spread median | **half**-spread mean |
|---|---:|---:|---:|
| winner (aec) | 0.04 | **0.25¢** | 0.29¢ |
| spread (asc) | 0.47 | **0.50¢** | 1.40¢ |
| total (tsc) | 0.46 | **2.00¢** | 2.96¢ |
| — pooled | — | 1.00¢ | 1.99¢ |

The pooled median (1.00¢) is dominated by the wide totals markets. **τ must be
quoted per type AND per price.** The winner market sat **entirely at extreme
prices** tonight (mid p5–p95 = 0.022–0.077 — a blowout, 0% in [0.35, 0.65]), so
its 0.25¢ is a near-zero-price spread and its half-spread **at p=0.5 is
unmeasured**; pairing 0.25¢ with the p=0.5 fee (as "0.25+1.5=1.75pp") mixes two
price regimes. Spreads and totals sat near p=0.5 (mid 0.46–0.47), so those pair
with the p=0.5 fee cleanly. **G = 1**, one blowout game — a spread distribution,
not a CFB fact; Saturday (with close games) measures the winner market at p=0.5.
The spread/total numbers bracket WNBA (half 1.50¢/2.25¢), so CFB is **not**
dramatically tighter — the earlier "CFB is much tighter" claim is gone.

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
leg because binaries settle. τ is **per market type, at the price that type
trades** — not pooled:

| market type | **half**-spread (median) | median mid | fee at that mid | **τ (median)** |
|---|---:|---:|---:|---:|
| winner (aec) | 0.25¢ | 0.04 | 0.22¢ | **~0.5pp** (near-certain; p=0.5 unmeasured) |
| spread (asc) | 0.50¢ | 0.47 | 1.49¢ | **~2.0pp** |
| total (tsc) | 2.00¢ | 0.46 | 1.49¢ | **~3.5pp** |

A model faces the bar of **the type it trades**: a win-probability model (e.g.
ESPN-vs-venue) trades the winner market — τ ~0.5pp at the blowout prices seen
tonight, **unmeasured at p=0.5**; a spread model faces ~2.0pp; a totals model
~3.5pp. The old pooled "2.5–3.5pp" mis-charges the winner-market strategy by ~1.5pp
— use the per-type row.

> **τ is a FUNCTION of price, so the decision rule cannot use a scalar (c7).** The
> fee alone ranges ~7× across the price axis (0.22¢ at p=0.04 → 1.50¢ at p=0.5),
> and the half-spread varies too. **Each trade's edge must be compared against τ at
> that trade's own price** — a scalar τ would be a *fourth* population mixture,
> this one on the price axis, after market type, column, and weighting. And when
> quoting a τ, state the observation count in the price band: the winner market's
> 0.25¢ is 2,425 observations all inside a 5-point window (mid 0.02–0.08) — one
> price, not a distribution.

> **Estimator, pre-registered before Saturday's slate (per ce).** The bar is the
> **per-snapshot median half-spread, per market type, at the price that type
> trades** (time-weighted; median for robustness to the stale/wide tail); the
> per-snapshot **mean** is reported alongside as the no-discipline upper bar. NOT
> per-fill (fill-selected spreads bias wide) and NOT pooled across types. Fixed now
> so it is not a free parameter after the slate — the mean–median gap is a full
> point, and the estimator-choice lesson has flipped a programme sign before.

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
   (τ at the type and price it trades — §3, per-type)? Equivalently, is the
   per-traded-market Brier improvement `> τ²` (τ² scales with the bar: ~4×10⁻⁴ at
   τ=2.0pp, ~1.2×10⁻³ at τ=3.5pp)? The population number (e.g. the live model's declined-branch
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

- A **taker whose edge exceeds τ at the type and price it trades** (~2.0pp spreads,
  ~3.5pp totals near p=0.5; ~0.5pp on the winner market at blowout prices) crosses,
  owns the position at fair, and eats no adverse selection. The making close does
  not apply to it — a different strategy on a different bar.
- CFB's measured spread/total half-spreads are close to WNBA's (§2); the winner
  market at p=0.5 is unmeasured. The frozen-tape "CFB is much tighter" is withdrawn.
- **Where the edge must come from (ce).** ESPN's CFB win probability carries almost
  no *pregame* information — over 33 kickoffs its first-tick WP has sd 0.0222
  (range 0.52–0.66), against the venue's pregame boards at sd 0.2663, a ~12× gap.
  So a taker edge cannot come from ESPN's public model; it must come from a
  **pregame prior the venue does not already have** — and the venue has a strong
  one. The bar to beat is the **venue**, not ESPN, and τ (above) decides whether
  any residual edge survives costs.
- **The winner-market tension (c7) — a strategy feature, not a measurement gap.**
  In blowouts τ is tiny but the outcome is near-certain, so there is little to bet;
  in close games there is something to bet and the spread is **unmeasured and
  likely wider**. Close games may simply carry the cost that blowouts do not —
  Saturday supplies close-game data, but the tension survives it.

**Said plainly: nothing established today rules out a football taker with real
forecast edge. We only ruled out earning the spread without a forecast.** The
open question is entirely whether B and d5's model can produce per-trade edge
**exceeding τ for the type and price it trades** (~2.0pp spreads, ~3.5pp totals;
winner-market p=0.5 unmeasured) **against the venue's own pregame prior**,
concentrated on the markets it trades — and that is now judgeable on day one
against the bars above.

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
