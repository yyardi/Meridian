# Does the winner-market identity transfer to spreads and totals?

> ⚠️ **PROVENANCE, 2026-09-06.** Every σ figure below was fitted on ladders
> selected by a "kickoff" that was **the ESPN recorder starting at 22:08Z, not a
> kickoff**. All 14 games were already in progress — period 2 at 14-0, period 4
> at 49-3. **Zero of 14 was observed at 0-0.**
>
> The numbers survive, and the reason is uncomfortable: those ladders were
> **frozen — 0.0% of 575 full-game spread markets showed more than one distinct
> mid** over a median of 27 snapshots. A frozen board still carries its last
> pregame quotes, so a pregame σ was recovered from a selector that asked for
> the wrong rows. ESPN's `live_spread` agreeing at 0.41 points is consistent:
> it moves in only 4 of 50 games, so it is a static pregame line too.
>
> **On a board that is actually quoting, the same selector returns in-game
> ladders under a pregame label, with no error and no null.** Fixed by
> `fit.true_kickoff` (period 1 AND 0-0). Found by Quant B warning that
> `is_live == 'f'` is not pregame — a different mechanism that would have
> produced the same class of artifact.

**Short answer: yes, with one assumption, and the assumption is a measurable
surface rather than a fitted constant — but it is a surface, not a number, and
nobody has built it.** Separately, the cheap option (test the anchor alone
against spread prices) is already answered by data in hand, and the answer is
no.

The identity is c7's:

    logit(p̂) = logit(anchor) + [ logit(ESPN_live) − logit(ESPN_at_kickoff) ]

A winner market prices **P(home wins)**. A spread market prices
**P(margin > −L)** and a total prices **P(points > L)**. Those are different
questions about a *distribution*, not relabellings of the same probability.

## The two halves transfer differently

**The anchor transfers for free.** `live_spread` already *is* a margin
quantity — it is the negated expected margin — and `espn_spread_anchor` covers
50 of 50 games. Nothing needs to change.

**The update term does not.** ESPN's WP delta is a probability update about
*who wins*. To move a spread ladder it must become a shift in a margin
distribution, and that needs the distribution's **scale**:

    P(margin > −L) = Φ( (μ + L) / σ )

with μ from the anchor and σ from somewhere. **σ is where a zero-parameter
identity quietly becomes a fitted model** — unless σ is read off the market
rather than fitted to outcomes, which is what the rest of this page does.

## The ladder measures σ, and it is not a constant

A game's spread ladder is an empirical margin CDF: ~40 rungs, each a
`(line, P(cover))` pair. Under any location-scale family,
`link(mid) = (μ + L)/σ` is **linear in L with slope 1/σ**. So the ladder both
names the distribution and measures its scale.

Measured on the 09-05 pregame ladders, 14 games, interior rungs only
(`0.05 < mid < 0.95`, because the venue clips at 0.015/0.985):

| | median R² |
|---|---:|
| probit link (normal margin) | **0.99210** |
| logit link (logistic margin) | 0.99162 |

Probit wins on 8 of 14 games. **The two are not distinguishable**, and that is
good news for the transfer: the identity updates additively in *logit* space,
which is itself a distributional assumption, and over the tradeable range the
ladder says it costs nothing to make.

Implied margin sd: **median 15.65 points**, range 14.03–19.61. The logistic fit
gives scale 9.15 → sd 16.59, agreeing.

### ⛔ THE LINE DEPENDENCE IS REFUTED — 2026-09-07, gated, and with power

Three games gated on `true_kickoff` (period 1, 0-0), closing ladders inside the
≤900 s window, on a board that was quoting:

| game | rungs | σ | R² | \|line\| | slope 0.1182 predicts |
|---|---:|---:|---:|---:|---:|
| 16453 | 34 | 15.98 | 0.9778 | 8.1 | 14.15 |
| 16488 | 23 | 15.61 | 0.9871 | 22.5 | 15.85 |
| 16486 | 25 | 15.98 | 0.9959 | 23.9 | 16.01 |

```
fitted slope on these three   -0.0105     (shipped: +0.1182)
predicted rise 8.1 -> 23.9     1.87 pts   observed  0.00 pts
TOTAL spread of all 3 sigma    0.37 pts
predicted effect               5.0x the ENTIRE observed range

(An earlier version of this block quoted "signal-to-scatter 9.7x, the test
HAD power". **That overstated it and B caught it**: n = 3 with two fitted
parameters leaves ONE degree of freedom, so a residual sd is barely a
quantity and a ratio built on it is not a power statement. The lines above
use no fitted dispersion -- the predicted effect is five times the entire
observed spread, which needs no distributional assumption to read.)
mean |error|:  flat 15.86  0.16 pts   |   shipped relation  0.70 pts
```

**The level reproduces on a fresh cohort. The slope does not, and this cohort
predicts an effect five times larger than the entire observed spread.** Use `MarginScale.flat()`.

**How it survived:** it was fitted on frozen mid-game ladders where lopsided
games carried more one-sided rungs, and a tail-only probit fit inflates σ. The
symmetric-window control below argued against exactly that mechanism — **and ran
on the same 14 contaminated ladders, so it never had the power to clear
itself.** Everything after this heading is the superseded fit, kept so the trail
is legible.

### σ grows with the line — measured, n = 14, and shipped

Fitted by `core.gridiron.scale.MarginScale`:

    σ = 13.19 + 0.1182·|line|        n = 14 games, corr = +0.948

A single σ = 15.65 misprices a 40-point game by ~2.3 points of scale. Bigger
favourites carry more margin variance, so **a constant σ is a mixture**, biased
hardest where the anchor is most informative.

**The relation survives every filter choice**, which is the sensitivity check
that matters on a 14-game cohort:

| R² floor | games | σ(line) | corr |
|---|---:|---|---:|
| none | 14 | 13.19 + 0.1182·\|line\| | +0.948 |
| 0.95 | 13 | 13.30 + 0.1116·\|line\| | +0.942 |
| 0.97 | 12 | 13.62 + 0.0939·\|line\| | +0.915 |
| 0.99 | 8 | 13.06 + 0.1232·\|line\| | +0.974 |

Intercept 13.1–13.6, slope 0.094–0.123 throughout.

### Fitting the ladder retires the bracket filter

A side effect worth having. `spread_anchor` interpolates to the P(YES) = 0.5
crossing, so it needs the ladder to *bracket* it — which dropped 2 games in 14,
both extreme. A probit fit recovers the crossing analytically from all rungs and
needs no bracketing:

| | games | mean \|diff\| vs DraftKings | worst |
|---|---:|---:|---:|
| interpolated, bracket filter | 12 | **0.41** | 1.67 |
| probit fit, no filter | 14 | 0.68 | 2.59 |
| probit fit, R² ≥ 0.95 | **13** | 0.53 | 1.88 |

Almost all the degradation is one game whose ladder fits worst (R² 0.9362, off
by 2.6 points). So the fit buys a game of coverage for ~0.1 points of accuracy,
and `r2` is returned per game so the caller can make that trade explicitly
rather than inherit it.

### σ also falls within a game — OBSERVED ONCE, NOT MEASURED

**This is n = 1 and it is deliberately not in the shipped surface.** A
two-argument surface with 14 games on one axis and one game on the other would
read as equally supported in both directions, and a later reader could not tell
which half was a single game.

Live ladder, 2026-09-06 game 16486, 5-minute buckets:

| regulation left | σ | R² |
|---:|---:|---:|
| 2933 s | 15.23 | 0.971 |
| 2556 s | 14.41 | 0.968 |
| 2268 s | 11.61 | 0.998 |
| 1987 s | 11.66 | 0.994 |
| 1884 s | 11.52 | 0.981 |

`corr(reg_left, σ) = +0.568` over 13 buckets, one game, and two buckets fit
badly (R² 0.89 and 0.93). The direction is plausible and the magnitude is not
established. **Saturday's slate supplies this axis.**

**An earlier version of this table ran to σ = 10.64 and was wrong.** The
buckets past 21:37Z reused the last game-state row after the ESPN recorder
stopped, so the decay was being read against a clock that had stopped
advancing — the axis manufactured the tail of its own trend. Those buckets are
now excluded rather than annotated.

**And the clock is not monotone even before that.** `reg_left` jumps
**backwards four times**, once by a full 900 s at a period boundary (ESPN
reporting `period 1, 15:00` mid-game at 3-0). Any use of game clock as an axis
has to enforce monotonicity first; this one does, with a `cummin`.

## Why spreads are a better instrument, not just a bigger one

**A winner market cannot falsify the identity's distributional assumption.** It
prices one line, so *any* monotone update from "ESPN moved" to "our p moved"
produces a valid probability. The assumption is unobservable there.

**A ladder prices ~40 lines that must move consistently.** A wrong distribution
shows up immediately as a shape error — a departure from linearity in the right
link. So re-siting to spreads makes the identity **falsifiable for the first
time**, which is a reason to prefer it beyond coverage and beyond the
degenerate-baseline problem.

## The cheap option is already answered, and it is no

"Test the anchor alone against spread prices, even if the identity does not
transfer" is cheap — but the data is in hand and it does not clear.

`live_spread` **is** a DraftKings spread and the venue ladder **is** our spread.
They were measured agreeing at **corr +0.9992, mean |diff| 0.41 points**. That
is a venue-gap test, not a forecast-skill test, and the gap converts to:

| disagreement | at σ = 15.65 | vs CFB spread τ ≈ 2.0 pp |
|---|---:|---|
| mean, 0.41 pts | **1.05 pp** | does not clear |
| worst game, 1.67 pts | 4.26 pp | clears, n = 1 |

**At the mean the anchor-versus-venue gap is about half the bar.** Worth knowing
before anyone builds it: the two spreads are the same number, and being the same
number is exactly what makes the anchor a good validator and a bad signal.

---

*Measured 2026-09-06. Pregame ladders from `cfb_prices_20260906T194301Z`;
live ladder from `cfb_prices_tonight_20260906T221035Z`. σ read from prices only,
never fitted to an outcome. No skill claim on this page.*
