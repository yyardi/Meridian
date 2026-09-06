# The 09-05 slate cannot train a market-as-a-feature model — the market half is 41 minutes stale

The game half of the join is in excellent shape: **8,634 play rows, 100%
non-null** on down, distance, yards_to_goal and pos_team. The market half, on
the same slate, is unusable.

## The collapse, quantified

Per-market inter-observation gap in the venue price tape:

| window | markets | median gap | p90 | p99 | gaps < 60s |
|---|---:|---:|---:|---:|---:|
| **before**, 09-05 21:00–22:00Z | 6,344 | **3s** | 30s | — | **99.7%** |
| **the live slate**, 09-05 23:00Z → 09-06 06:00Z | 9,882 | **2,487s** | 2,489s | 4,707s | **0.0%** |

**Not one gap under five minutes across the entire slate.** Hourly density
fell 198.6 → 29.7 → 1.9 observations per market per hour and then sat at
exactly 1.0–2.0 for seventeen hours.

## It is the documented name collision, and the numbers match exactly

`docker-compose.cfb-live.yml`'s own header records it: bringing up
`cfb-live-recorder` destroyed the identically-named CFB **venue price**
recorder from `docker-compose.nfl.yml:108`, and price recording stopped for 22
hours — *"188,394 rows in the 22:00Z hour before, 4,638-9,371/hour after
(sweep only)."*

Measured here independently: **188,394** rows in the 22:00Z hour, and
**4,638** in the 16:00Z hour on 09-06. Both figures reproduce to the row. What
remained running was the sweep, which is what a 41-minute median gap is.

**It has since recovered** — 10,891 rows across 166 markets in the 20:00Z hour
on 09-06, **65.6 per market per hour**. The recorder is back up. This is a
closed incident, not a live outage.

## What it means for the model, which is the part that matters

A market-as-a-feature model needs the price *at the play*. On this slate the
nearest price observation is **~20 minutes old on average** (half a 41-minute
median gap) and can never be fresher than five minutes.

A feature that stale does not move within a possession, a drive, or often a
quarter. It would enter training as **approximately constant within each
game** — carrying team and total priors, and none of the in-game information
that is the entire point of joining it to down and distance.

So:

- **B can build on the real feature set today.** The game-state half is
  complete and correct.
- **B cannot validate in-game market response on the 09-05 slate.** Not
  "degraded" — the in-game price signal is absent by construction.
- **Saturday 09-12 is the first slate that can produce a usable join**, and
  only if the price recorder stays up through it.

## Which recorder to harden

The ESPN CFB recorder produced 8,634 rows at 100% non-null. The venue price
recorder produced a 41-minute median gap on the same slate, from a **container
name collision** — a failure mode with nothing to do with parsing, ESPN, or
football.

The cheap guard is not another parser test. It is a **freshness alarm on the
price tape**: median per-market gap over the last N minutes, alarming when it
exceeds a live-game threshold. The collapse ran seventeen hours before this
measurement and was found by reading an export, not by a monitor. Every
data-*arrival* check stayed green, because rows kept arriving — one per market
per hour.

That is the [freshness-is-not-liveness](../../MEMORY.md) shape again, one turn
worse: there the values froze while timestamps advanced; here the arrival rate
fell 99.5% and nothing noticed either.
