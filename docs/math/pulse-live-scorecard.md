# The PULSE live scorecard — the in-game model scored against settlement

**Question:** does the live WNBA model (`core/pulse/live.py`, the anchored win
curve `Phi((margin + E·t/40) / (sigma·sqrt t))` of `core/pulse/win_curve.py`
plus the totals and spread heads) forecast better than the venue price it saw
at the same instants, and what were its decisions worth held to settlement?

**Status: written before the first run. Results append below the line.**

The pregame sibling (`predictions`, scored by `core/scorecard.py`) was
measured for weeks and reported as PULSE. The live model's rows in
`pulse_decisions` — 2,422 on 2026-09-22 alone, ~4,000 a day since 09-18 —
had never been scored against settlement. `cfb/run_pulse_live_scorecard.py`
does it; this note says what it counts.

## What a decision is

One row per decision of the loop at one observation of one market
(`core/pulse/storage.py`): `action` ∈ {enter, exit, hold} — an entry rested
at the touch on the side `fair_value` favours, an exit rested against an
open position (profit target, or a stop at the touch), or a throttled hold
mark. There is no `none` row; a state the guards refuse goes to
`pulse_abstentions`. Every row carries `fair_value` (P(YES)), the touch
(`market_bid`, `market_ask`), `limit_price`, the desired and live-faithful
sizes, and the lifecycle stamps `filled_at` / `withdrawn_at` / `settlement`
(the last only on filled enters). `decided_at` is the observation's
`captured_at`. No order exists behind any row.

## Dedupe

`(market_slug, decided_at, action)` is not a key: 84 collisions in 19,333
rows on 2026-09-14 — 24 enter groups (a YES and a NO on one tick, different
prices: two decisions) and 60 exit groups (profit target and stop on one
observation: two decisions, correctly sequenced; 7 on a snapshot priced
twice, [one-observation-twice.md](one-observation-twice.md)). Calibration
keeps the first-written row per (market, instant, action): one (probability,
outcome) pair per instant. P&L keeps one per (market, instant, action, side,
limit_price): one line per bet. Both removed counts print beside their
tables.

## Settlement and fee

Settlement is the venue's own label through `core/settlements.py` (the paper
book's route; 0.5 excluded and counted), falling back to the label the engine
stamped on the market's filled enters (the same endpoint, asked earlier) and
counting the source. The fee is `core.fees.recorded_fee(price, coefficient)`
with `market_snapshots.fee_coefficient` joined on the snapshot's unique key
`(market_slug, captured_at = decided_at)`, because `pulse_decisions` does not
store it; the venue raised the coefficient at 2026-09-17 04:07Z and the read
spans that instant. A row whose snapshot is gone is excluded from P&L and
counted, never charged at today's.

## The numbers

* **Calibration**, per scoreable row (in play, settled 0/1, a fair value and a
  two-sided touch): Brier and log loss of `fair_value` and of the venue mid
  `(bid+ask)/2` at the same instants, side by side, by action × regime, by
  `estimates_version`, and by `|fair_value − mid|` bucket with the win rate of
  the side the model leans to. The headline is the per-row gap
  `Brier(mid) − Brier(fair_value)`, positive when the model forecast better;
  a model that does not beat the venue has no signal. Log loss clips p to
  [0.001, 0.999] (`fair_value` is exactly 0 or 1 at the buzzer) and prints
  how many rows hit the clip.
* **Paper P&L** of enter decisions: one contract crossing the recorded touch
  (YES at the ask, NO at 1 − bid), held to settlement, fee at the row's
  coefficient — the paper book's arithmetic, pinned equal in the tests.
  Beside it the **limit arm** (at the rested limit, no maker fee, assumes the
  fill): it exceeds the taker arm by spread + fee on every row before any
  fill selection, and is printed only so that flattery has a size.
* **Estimator**: a game is one outcome. Intervals are the cluster-robust
  sandwich over `event_slug` with the G/(G−1) correction and t at df = G−1
  (`clustered_mean`) on the row-weighted mean; the equal-weight mean of game
  means with its own t(G−1) interval is printed beside it, and Kish
  G_eff = (Σn_g)²/Σn_g² beside both. n rows, n markets, n games on every line.
  Playoffs (decided_at ≥ 2026-09-14 UTC) are their own row beside the
  regular season.

## What it cannot show

Decisions are not fills. A resting order fills when the market comes to it
and is withdrawn when the price leaves, so the withdrawn arm always beats the
filled one (+3.71¢ favourable vs −4.55¢ adverse mid move, measured 2026-09-06)
before any skill enters; the scorecard prints the arms and the signed mid
move to fill, and reads nothing into the gap. The taker P&L has no depth
check and no latency: it is what the opinion was worth to a taker at that
instant, not what a limit captured. Nothing here is sized, gated or armed.

## Run

    docker run --rm --network meridian_default --env-file /opt/meridian/.env \
      -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
      -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb \
      -v /opt/meridian/artifacts/reads:/opt/meridian/artifacts/reads \
      -w /app meridian-api python cfb/run_pulse_live_scorecard.py

`DAYS` (default 45) bounds `decided_at`; the snapshot join is floored at the
month of `now − DAYS` so the partitions prune. The reads mount is the
settlement cache; without it every market is asked again and nothing is kept.

---

*Results append below this line, dated, with the command's output.*
