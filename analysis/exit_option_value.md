# What is an exit worth? — pricing the ride tail at entry (Track D follow-on)

**2026-09-02. In-sample, descriptive, hypothesis-generating. No PASS/FAIL.**
Artifact: `analysis/exit_option_value.py` (mutation-tested: breakeven algebra,
excursion scan, and mark-at-horizon each recover injected known answers before
real data). Reproduce:

    .venv/bin/python analysis/exit_option_value.py

Pins: `20260901T195202Z` (decisions, ticks, resolved). Ledger built by the
decomposition's own `build_legs` (one source of truth); policy: money at
price, **drop-linking** (A's re-linked policy quoted beside every number it
moves). All fills are modelled — premiums and profits are upper bounds,
losses are trustworthy (fill rule stated in
`pulse_execution_decomposition.py`).

## 1. The arithmetic

Trips +5.83¢/$ money-weighted (1,790 rows / 28 games; clustered +8.03
[+6.14, +9.92]); rides **−45.26¢/$** (154 rows / 30 games; clustered −77.18
[−91.26, −63.10]). A's re-linked policy: 1,807 / +5.83 and 137 / −50.62 on
the same tape.

- Observed ride share **p = 7.9%** (154/1,944).
- Breakeven ride share **p\* = r_trip/(r_trip − r_ride) = 11.4%** — the ride
  probability above which the book loses even under the optimistic fill rule.
  Headroom: **+3.5pp**.
- Pessimistic arm (strip engine-booked concessions, charge the measured
  4.70¢/leg): trips **−8.03¢/$**, rides **−51.74¢/$**. Convention note: the
  per-game cut's −16.46/−65.45 charges 4.70¢/leg **on top of** the engine's
  booked concessions; this script credits the booked 1.5¢/leg back first
  (no double-count). Same sign everywhere; the convention is now pinned in
  both places.

## 2. The breakeven exit premium δ*(p) — the sizing input the engine lacks

δ*(p) = p·(r_trip − r_ride)·cost/ct: the entry concession whose certain cost
equals the expected ride loss avoided **if a guaranteed exit converted each
ride into an average trip** — generous twice over (a ride's counterfactual
trip is below-average; trip P&L is doubly optimistic), so an **upper bound**
on what exit certainty could ever be worth at entry. Mean cost 41.4¢/ct.

| state cell | p | δ* (¢/ct) |
|---|---|---|
| overall (this tape) | 7.9% | **1.68** |
| \|margin\| ≥ 10 (B, A-ledger) | 10.8% | 2.28 |
| Q4 (B) | 16.6% | **3.51 — exceeds the measured alpha (3.47)** |
| minutes_left 5–10 (B) | 18.1% | **3.83 — exceeds it** |

Reading: at late-state ride shares, fairly pricing the exit option costs more
than the model's entire measured alpha — **late entries are uneconomic once
exit risk is priced, even optimistically scored**. Overall, the fair premium
is about the size of one more concession leg. The engine currently prices a
2% and a 30% ride-risk entry identically; this table is the correction curve,
and B's fitted P(ride | entry state) (LOGO AUC 0.700) is the p̂ that would
drive it.

## 3. The term structure — when the exit option decays to zero

Value of exiting each ride at the first two-sided live mid at/after horizon h
versus what the ride returned (per $ staked; equal-weighted clustered, then
money-weighted):

| h | clustered ¢/$ | money-weighted | n rides |
|---|---|---|---|
| fill+1m | +67.07 [+52.71, +81.42] | +39.3 | 144/154 |
| fill+5m | +61.61 [+48.82, +74.40] | +38.3 | 135 |
| fill+10m | +50.04 [+36.31, +63.77] | +32.7 | 124 |
| fill+20m | +38.75 [+24.43, +53.06] | +23.0 | 111 |
| end−10m | +25.05 [+8.92, +41.18] | +9.4 | 61 |
| end−5m | +9.33 [−16.91, +35.58] | **+0.4** | 50 |

The option decays throughout the hold and is worthless in the final minutes —
reconciling exactly with B's "rides are worth 0.000 at book close." And the
book was **alive** for most of that decay: median exit-book runway 36.9 min
(p25 16.9), median book death only 8.8 min before the event's last live tick.
**The ride loss is not unavailability; it is adverse selection against the
static exit while a market existed** (B's addendum, confirmed from the time
axis). A guarantee that kicks in late buys nothing; exit value is
front-loaded.

## 4. Pessimistic ride relabeling p(k) — B's "lower bound," quantified

A modelled trip whose exit-side mid never traded ≥ k through the exit limit
(over the exit's whole possible life, rest → last live tick) would not have
exited under a k-concession fill rule:

| k (¢ through limit) | flipped trips | p(k) | flipped settle P&L |
|---|---|---|---|
| 1 | 30 | 9.5% | −$11.11 |
| 2 | 61 | 11.1% | −$21.08 |
| 3.15 (= 4.70 − engine's 1.55) | 129 | 14.6% | −$45.78 |
| 4.70 (full measured) | 191 | **17.7%** | −$66.37 |

**At the full measured concession the ride share alone (17.7%) exceeds the
optimistic-rule breakeven (11.4%).** For B's predictor: the tape's ride label
undercounts real no-exit risk by 2–10pp depending on k — "predicted ride risk
is a lower bound" now has a number.

## 5. Does crossing at intent buy exit availability? No — measured

Crossing moves entry from `filled_at` back to `decided_at`. For rides that is
median **79s** of extra runway (p75 359s), against a median **36.9 min** of
exit-book runway the position already had and did not use — an added-runway
ratio of **4.8%** — and the term structure shows the value was mostly gone
before the book was. Book death is late-game-anchored (median 8.8 min before
the live end, spread p25 2.3 / p75 25.5), not entry-anchored. **Crossing buys
certainty of entry (the never-reachable third); it buys ~nothing on exit.**
The ride tail is state-owned: B's mask (the crossing-arms companion
registration) is the lever pointed at it, and §2's premium is what exit risk
costs where the mask does not apply. D and B have now bounded the problem
from both ends.

## 6. Book state around intents — the joint note's open check, answered

Share of intents with any one-sided/empty tick within 60s after intent:
early filled 1.0% (17/1,653), early unfilled 1.5% (12/823), **late filled
12.0% (35/291), late unfilled 11.1% (23/207)**.

Split verdict for `late_game_liquidity.md`: late books ARE one-sided an order
of magnitude more often than early — the check's stated falsification
("two-sided and deep") does not fire — but within late states the rate is
**flat between filled and unfilled intents**, so one-sidedness at intent does
not discriminate individual non-fills. Lateness drives book sickness AND
non-fills without the first proximately causing the second at this
measurement; consistent with the withdrawal autopsy (late unfilled are
predominantly never-reachable — price motion). Per-intent flags
(`--emit-book-state`: id, late, unfilled, n_ticks, share_two_sided,
one_sided_after) regenerate from the pins for B's feature test, which is the
sharper version of this check.

## Candidates / negatives / boring

**Candidates** (each with its forward test): (1) *ride-risk-priced entries* —
require edge ≥ concessions + δ*(p̂) with B's fitted p̂; forward test: paper arm
beside the engine, game-clustered paired per-$. **Open reconciliation before
any registration**: B's predictor work finds per-$ outcomes flat across ride-
risk quintiles — the market may already charge for ride risk through the
contract price, in which case δ*(p̂) on top double-counts; one reconciling
paragraph between the two docs is owed first (agreed with B). (2) *front-loaded exit
management* — the term structure says exit value dies with the hold, not the
book; a forward arm that reprices or abandons exits early (vs the static
entry+5¢ target) is testable on the same tape forward; c7's call whether it
rides a vehicle or stands alone (landed gates do not grow arms).

**Negatives**: a guaranteed exit at book death is worth +0.4¢/$ — insurance
against the *bookless* endgame per se has ~no value; crossing at intent does
not touch the ride tail; and the pessimistic arm is negative everywhere
including trips (−8.03¢/$ this convention, −16.46 the other), so **fixing the
ride tail does not by itself rescue the book** — stated before anyone funds
the fix.

**Boring**: excursion scan found tape coverage for all 1,790 trips; ledger
anomalies unchanged (17 orphans, 0 multi-exit); money-weighted vs
equal-weighted term structures agree in shape (cheap-cost denominators
inflate the equal-weighted level, both printed).

Multiple comparisons: many intervals and medians across horizons, k-grids and
cells; several nominally significant cells are expected by chance; ranking is
mechanism + effect size + robustness. Every number inherits the modelled-fill
assumption.

**No in-sample result justifies capital. The forward test is the evidence.**
