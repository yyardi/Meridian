"""BTC15 — an LLM decision harness for Kalshi's 15-minute Bitcoin market (KXBTC15M).

Every 15 minutes Kalshi lists a market that pays $1 if the 60-second average of
CF Benchmarks' BRTI just before the close is at least the same average just
before the open (the market's ``floor_strike``). The harness builds a feature
set from free exchange data, asks an OpenAI model for P(up), buys exactly one
contract of the side it favours at the ask, and settles off Kalshi's own
result. Every buy and settlement is written to an integer-unit ledger that
enforces a $10 maximum drawdown before any order exists.

    prices.py    free BRTI constituents (Coinbase, Kraken, Bitstamp, Gemini) -> 1 Hz composite
    features.py  pure functions: returns, volatility, TA, distance to strike, baselines
    kalshi.py    read-only KXBTC15M client: current window, market by ticker, results
    ledger.py    SQLite ledger in 1/10,000-dollar units; fee; drawdown guard; experience
    model.py     OpenAI structured-output decision and post-settlement lesson
    harness.py   the loop: poll, decide once per window, fill, settle, reflect
    report.py    the scorecard

docs/math/btc15-harness.md explains the design; docker-compose.btc15.yml runs it.
"""
