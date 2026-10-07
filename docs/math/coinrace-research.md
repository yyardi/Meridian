# Coin Race (KXCRYPTOLEAD15M): the market, and the research program registered before any of it runs

2026-10-07. The operator's ask: find what can be done algorithmically on this market, with real
data, before any money or the incentive program.

## The contract

Every 15 minutes Kalshi lists five markets, one per coin — BTC, ETH, SOL, XRP, HYPE — asking
which has the highest return over the window. Return = (end − start) / start, where start and end
are each the time-weighted average of CF Benchmarks' spot rate over the 60 seconds before the
window's start and end (the market's own rule text). Exactly one market resolves YES. Fee type
`quadratic`: takers pay 0.07·p(1−p) per contract rounded up to the cent; resting orders pay
nothing. The liquidity program also pays $20 a market a window to resting size near the touch
(docs/math/kalshi-incentive-farming.md).

History on the public API at registration: **4,000 settled windows (20,000 markets) from
2026-08-25 to 2026-10-07, 13.0M contracts traded.** Winner frequency: HYPE 32.1%, XRP 21.7%,
BTC 16.9%, SOL 15.8%, ETH 13.1% — the most volatile coin wins most often, as a race of
correlated random walks predicts; whether the market prices that correctly is question 1.

## Questions (screens on recorded data; none of them is a result)

A screen chooses what runs live; only a live paper arm at live prices is a result
(operator rule, 2026-09-30). Each bar is fixed here, before the data.

1. **Pricing.** A model of P(coin i wins | the five coins' spot path so far, their vols and
   correlations, time left, the 60-s averaging at both ends), Monte Carlo of correlated paths
   with parameters estimated only from data before the day being scored. Scored walk-forward
   by day against the market's own last trade price at minutes 1, 5, 10 and 13 of each
   window. **Passes** if its log-loss beats the market's at some minute with a day-clustered
   95% CI excluding zero, AND a taker rule at the model's edge net of fees is positive with a
   window-clustered CI excluding zero. Otherwise directional trading on this market closes.
2. **Basket.** Exactly one of five pays $1, so the five YES prices sum to 1 in a frictionless
   book. Buying all five YES at the asks costs Σask + five taker fees; selling all five (buying
   all five NO) pays the mirror. On the per-minute book samples since 2026-10-03
   (`farm_scorer.sqlite`, `lip_sample`) and the live tape once it exists: how often either
   basket clears $0 after fees, by how much, at what displayed size, for how long. **Passes**
   at ≥ $50 a day at displayed size, not 80% in five windows.
3. **Farming fill cost.** The program pays resting size near the touch; the cost is being hit by
   someone who knows more. From the public prints: for a resting bid at 1–3¢ and one tick in
   front of the best bid, the fills per window and the settlement P&L per fill, by minute of
   the window. **Passes** if the expected fill cost at 1,000 a side is under 30% of the paper
   reward at the same size (docs/math/kalshi-incentive-farming.md).
4. **Late-window lag** (needs a live book tape and second-level spot; recorded after the prod
   disk is freed). Does the book trail the spot-implied probability in the last three minutes by
   more than the round-trip fee? Registered when the tape exists.

## What follows a pass

A paper arm on the live tape at zero cost, with its read registered before its first fill.
Live money (a Kalshi trading key and collateral) is the operator's switch.
