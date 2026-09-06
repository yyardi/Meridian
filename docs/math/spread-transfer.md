# Does the winner-market identity transfer to spreads and totals?

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

### σ grows with the line

| | |
|---|---|
| `corr(\|home_spread\|, σ)` | **+0.911** (n = 12) |
| fitted | σ ≈ **13.69 + 0.0915·\|line\|** |
| at a 7-point line | σ ≈ 14.3 |
| at a 40-point line | σ ≈ 17.4 |

A single σ = 15.65 misprices the extremes by ~1.7 points of scale. Bigger
favourites carry more margin variance — unsurprising, and it means **a constant
σ is a mixture**, biased exactly where the anchor is most informative.

### σ collapses within a game, by a third before halftime

Fitted every 5 minutes off the live ladder, 2026-09-06 game 16486 (29 rungs,
13,439 live full-game spread rows):

| regulation left | σ | R² |
|---:|---:|---:|
| 2933 s | 15.23 | 0.971 |
| 2556 s | 14.41 | 0.968 |
| 2278 s | 11.61 | 0.998 |
| 1987 s | 11.66 | 0.994 |
| 1884 s | 10.64 | 0.997 |

**15.23 → 10.64 over half a game**, and the early value reconnects with the
15.65 pregame median. A constant-σ transfer would misprice the second half by
30–50% of scale.

**Caveat, and it is a real one: n = 1 game.** Also, `reg_left` freezes at 1884 s
because the ESPN recorder stopped at 21:37Z while prices kept moving — the last
rows are real time passing against a stale clock. σ keeps falling through them,
which is consistent, but the x-axis is not trustworthy there. Freshness is not
liveness.

**So the transfer needs σ(line, time_remaining) — a two-argument surface.** It
is not a free parameter: every value above was read off the same ladder that is
being traded, never fitted to an outcome. But it is new work, and it does not
exist.

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
