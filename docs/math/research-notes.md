# Research notes — what the literature says, and what we do about it

Reviewed 2026-08-01. Each finding is tied to a concrete action in this repo.

## 1. Odds beat models — so anchor on the market

[Štrumbelj (2014)](https://www.sciencedirect.com/science/article/abs/pii/S0169207014000533) and the surrounding literature find that **probability forecasts derived from bookmaker odds are better than, or at least as good as, statistical models** built from sports data — across five team sports and 37 competitions.

**Implication for us:** a PPG model beating the sportsbook line was always the hard game. The measured result matches the literature exactly: our fixed model's error (13.99) is statistically *tied* with the line's (13.93), not below it. The model's proper role is a **small correction to the market anchor**, not an independent oracle — and our incremental-information slope (0.42, p≈0.055) says the correction is borderline-real but must be shrunk, never taken at face value.

Also from this paper: use **Shin probabilities** rather than basic normalisation when de-vigging odds — basic normalisation is biased. Our `remove_vig()` uses proportional normalisation; upgrading to Shin is a cheap TODO.

## 2. The WNBA specifically is thin, and its home advantage is overstated

[Paul & Weinbach (2014)](https://www.mdpi.com/2227-7072/2/2/193), using 2007–2012 WNBA data: the market is thin, simple strategies don't profit, **but road favourites won more often than home underdogs** — evidence that books overstate WNBA home advantage (small crowds, less home edge).

**Implication:** our measured home advantage is **+2.2 points** (2024–2026, 775 games). The projection currently has *no explicit HCA term* — a gap in the margin model — but per this research it should be added at the measured WNBA value, not basketball folklore's 3–4.

## 3. Totals lines are biased early in the season

[Learning and price formation research on the NBA](https://www.sciencedirect.com/science/article/abs/pii/S1544612307000177) finds totals lines significantly biased early each season while the market is still learning the new scoring environment; a simple strategy against early-season closing totals hit 56.7%.

**Implication:** this is exactly our 2026 regime shift (league mean jumped from ~163 to ~174; our model's residual bias was −2.7 in 2026 vs −0.3 in prior years). Early-season, when books anchor on last year, is the one window where a current-season-weighted model has a structural advantage. Our `estimate_totals_distribution` already weights the current season; the backtest should report early-season performance as its own cohort.

## 4. Thin prediction markets misprice; that is the actual strategy

Industry coverage ([DeucesCracked 2026](https://www.deucescracked.com/blog/prediction-markets-vs-sportsbooks-2026-kalshi-polymarket-guide), [Covers](https://www.covers.com/betting/prediction-sites/polymarket-vs-kalshi)) is consistent: prediction markets produce **tighter pricing on liquid contracts and worse pricing on thin ones** — and WNBA on Polymarket US is thin.

**Implication:** the original project hypothesis — fade Polymarket toward sportsbook consensus when they diverge — is the strategy the literature supports. It needs no model that beats the sportsbook, only the paired prices the recorder now captures every 15 minutes.

## 5. General efficiency literature: expect small edges or none

Surveys ([The Sport Journal](https://thesportjournal.org/article/nba-gambling-inefficiencies-a-second-look/), [weak-form efficiency reviews](https://myweb.ecu.edu/robbinst/PDFs/Weak%20Form%20Efficiency%20in%20Sports%20Betting%20Markets.pdf)) find major-sport lines broadly efficient; documented profitable pockets are small, niche, and decay. A [2019 multi-book study](https://arxiv.org/abs/1910.08858) finds the durable inefficiency is **price dispersion across books**, not mispriced consensus.

**Implication:** line-shopping across venues (which the cross-market strategy is a form of) is better-supported than out-modelling any single book.

## The winner's curse, which our own data now demonstrates twice

Selecting bets where our model disagrees most with the market means selecting where our *error* is largest. Both measured cases:

- Totals: largest-edge quintile is the worst performer
- Moneyline: chosen-side realised probability sits ~10 points below predicted in every calibration bucket

The fix is structural: edge estimates must be **shrunk toward the market** by the measured incremental slope (~0.4 today), and any bet triggered by raw model-minus-market disagreement is mostly buying our own noise.
