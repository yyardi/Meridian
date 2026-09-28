# BTC15 — an LLM harness for the 15-minute (and hourly) Bitcoin Up-or-Down market

2026-09-28. The operator's design: every 15 minutes an OpenAI model reads the
market and takes a side; the system buys one contract of it ($1 to win),
learns from its own record, runs with no one watching, and stops at a $10
drawdown. This document says what was built and what the numbers mean.

## The market (verified against the venue, 2026-09-28)

**Traded on Polymarket US**, the operator's account: "BTC Up or Down: 15 min",
slug `cpc-btc-updown-15m-YYYY-MM-DD-HHMMz` (HHMM = window start, UTC), and an
hourly sibling `cpc-btc-updown-1h-…`. **Up pays $1 if the simple average of CF
Benchmarks' BRTI over the 60 seconds before the window ends is at least the same
average over the 60 seconds before it starts** — the market's `priceToBeat`,
known at the start; the closing average arrives as `settlementPrice` with
`outcomePrices` ["1","0"] (Up) or ["0","1"] (Down). Book 1c wide, tick 0.01;
fee `feeCoefficient × p × (1−p)`, 0.0695 today, read off each market.

*(Correction, 2026-09-28: the first build of this document said Polymarket US
lists no crypto and ran the harness on Kalshi. That came from the venue's
sports-only listing endpoint; its search and market endpoints list the BTC
markets, as the operator pointed out.)*

**Kalshi's `KXBTC15M` is the same contract on the same numbers** — Polymarket's
23:30Z window of 2026-09-27 resolved at 84,337.75, Kalshi's `expiration_value` for
that window. Kalshi is read as a reference: its same-window mid is a feature,
and `MERIDIAN_BTC15_VENUE=kalshi` would trade it instead.

## Data

CF Benchmarks has no free API. BRTI is built from constituent exchanges; four
publish free tickers reachable from the production host — **Coinbase, Kraken,
Bitstamp, Gemini** — and the composite is the median of their mids, polled once a
second. It is a proxy, and its error is measured: every window stores the
proxy's 60-second closing average beside Kalshi's official one
(`python -m core.btc15.report` prints the error). Coinbase candles (1m/5m/1h)
give history from the first second; OKX's public funding rate is the one
derivatives input.

About 60 features, each named with its unit (`features.py`): distance to strike
in dollars, basis points and **volatility units over the time left**; returns
from 10 s to 24 h; realized volatility at three horizons; RSI, MACD, EMAs,
Bollinger, stochastic, VWAP and volume on 1m, plus 5m and 1h trend; exchange
dispersion; the Kalshi book; funding; hour and weekday; the last eight window
results. Two baselines ride with every window: the market's own mid, and a
driftless random walk to the settlement average.

## The decision

At open + 30 s the harness records the features (from data at or before that
instant only — tested), then asks the model for **p_up** under a strict JSON
schema, with its own record attached: hit rate, Brier score against the market
and the random walk, P&L and drawdown, its last 20 calls with outcomes, and the
last 12 lessons it wrote. The harness turns the probability into a side
deterministically (YES at ≥ 0.5) and buys **one contract of that side at the
ask** — the model never sizes, times or cancels. After Kalshi settles, the model
writes a one-line lesson that the next window reads. A refusal, malformed
answer, timeout, stale price feed, or an answer that arrives inside the last
90 seconds is recorded and places nothing.

## The ledger and the $10

Its own SQLite file, not the shared Postgres. Money is in integer units of
$0.0001 from the venue's dollar strings — no floats. The database itself refuses
more than one contract, a price outside (0, $1), a second fill for a window and
a second settlement for a fill. Before every fill the guard recomputes equity
from the rows: an open position counts as lost until Kalshi settles it; a
trade happens only if, with every open position **and this one** losing in full,
equity stays within **$10 of its high-water mark** (which starts at zero, so the
loss from the start can never exceed $10 either). When the next trade alone
could breach it, trading latches off until an operator starts a new allocation
(`--new-epoch`). Predictions and data collection continue regardless. Paper
and live are separate allocations. A randomized test runs 3,000 trades and
checks the invariant from the rows after every one.

## What to expect, stated before the first number

A contract bought at the ask pays the spread and a fee: at 50c that is about
2.5c per window, so an uninformed model loses about $2.40 a day at 96 windows,
and one-contract results swing about ±$5 a day on noise alone. **A $10 drawdown
is therefore reached within days unless the model's hit rate is clearly above
break-even** (≈ 52% on 50c tickets; higher on favourites). The report compares
the model's Brier score with the market mid's; a model that does not beat the
mid is not reading anything the price does not already know.

## Running it

`docker-compose.btc15.yml`: `btc15` (15-minute) and `btc1h` (hourly, paper),
each one container with a 256 MB cap, log rotation and its own ledger and $10
allocation. Set
`OPENAI_API_KEY` and `MERIDIAN_BTC15_MODEL` in `/opt/meridian/.env` to let it
decide (`--check-openai` lists the models the key can use); until then it
records the feed, the features and every result. `MERIDIAN_BTC15_MODE=paper` is
the default. Live execution on Polymarket US reuses the order path the ARB desk
already sends through (immediate-or-cancel limit at the ask, one contract, the
ledger's guard before the order exists); until that adapter lands, `MODE=live`
predicts and places nothing.
