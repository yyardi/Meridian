# Injury features — wired, point-in-time correct, and not yet measurable

**The delta is not zero. It is unmeasured, and those are different findings.**

```bash
python -m core.backtest --availability-mode off      # control
python -m core.backtest --availability-mode report   # injury-aware
```

## The measurement

Walk-forward, 2024–2026, totals, identical seeds:

| | `off` | `report` | delta |
|---|---|---|---|
| bets | 308 | 308 | 0 |
| filled | 218 | 218 | 0 |
| wins | 116 | 116 | 0 |
| ROI | −2.33% | −2.33% | **+0.000000** |
| mean CLV | 1.751 | 1.751 | **+0.000000** |
| hit rate | 53.21% | 53.21% | **+0.000000** |

Bit-for-bit identical, including the bet sequence.

## Why bit-identical is the useful part

A real-but-small injury effect would perturb *something* — one bet's size, one
selection, one price. Perfect identity across every metric is not a small
effect; it is the arm **never engaging**. So the honest reading is "unmeasured",
and it is worth separating the two cases because they license opposite actions:

* *delta ≈ 0 with differing bets* → injuries carry no signal here. Stop.
* *delta identically 0* → the code never ran. Fix the data, then measure.

Measured cause:

| | window | n |
|---|---|---|
| injury reports (`Out`/`Injured Reserve`/`Suspension`) | 2026-08-01 → 2026-08-18 | 252 |
| games with a settled outcome | 2020-07-25 → **2026-07-31** | 1,645 |
| **games where the arm could ever fire** | — | **0** |

The two datasets are adjacent and disjoint. Injury collection began the day
after the last game the backtest can score.

## Why the game logs stop on 2026-07-31

Not a retention policy — a silent parser outage, diagnosed and fixed in this
same branch. ESPN moved the season type from `event.seasonType` to
`event.season.type`; `_rows_for_event` refuses an event whose season type is
unknown (correctly — a preseason game in the regular-season record corrupts
every feature built from it), so every completed game was dropped. See
`docs/findings.md` **V23**.

That fix is the unblock. Backfilling 2026-08-01 → 2026-08-18 creates ~51 games
of overlap, at which point this table can be filled in for real.

## What is already correct, and needs no work

The wiring the measurement is waiting on already exists and is point-in-time by
construction — this was verified, not assumed:

* `PlayerAvailabilityIndex.absent_from_reports(team_id, as_of)` walks an
  oldest-first log and `break`s at the first row past `as_of`. The ordering that
  makes the `break` sound comes from `load_injury_log` sorting globally by
  `captured_at`, which preserves per-team order.
* `absent_from_injury_reports` (the SQL path) filters `captured_at <= as_of`.
* A later `Cleared` correctly supersedes an earlier `Out`, because the walk
  keeps the last status at or before `as_of` rather than any status.
* `core/backtest/engine.py` engages it only under `availability_mode="report"`;
  `"oracle"` remains the hindsight upper bound and is not tradable.

## The oracle arm: run, and it does NOT clear zero

The `oracle` arm takes absence from the box score — with hindsight, explicitly
not tradable. It exists to bound the question without waiting for forward data:
if perfect information moves nothing, no real injury feed can help either.

It moved something. Raw, 2024–2026:

| | `off` | `oracle` | delta |
|---|---|---|---|
| bets | 308 | 363 | **+55** |
| filled | 218 | 246 | +28 |
| ROI | −2.33% | **+3.16%** | **+5.48 pts** |
| mean CLV | 1.751 | 1.830 | +0.079 |
| hit rate | 53.21% | 56.10% | +2.89 pts |

A model that loses becoming a model that wins. **Do not act on that table.**

Two things are wrong with reading it as a result. First, **the denominator
changed**: the oracle did not re-price 308 bets, it selected 363. Those are two
different portfolios, so the ROI comparison is not like-for-like — part of the
gain is exposure, not skill.

Second, and decisive, the sample does not support it. Game-clustered bootstrap
(C4 — resample **games**, not bets; 4,000 resamples over 344 clusters):

| | |
|---|---|
| point estimate | **+5.27 pts** |
| 95% CI | **[−6.63, +16.85] pts** |
| crosses zero | **yes** |
| P(delta > 0) | 0.805 |

**The loosest possible upper bound on roster awareness cannot be distinguished
from zero.** A real point-in-time injury feed is strictly weaker than hindsight
— later, noisier, and blind to in-game rest decisions — so it is bounded above
by an interval that already contains zero.

### What follows

* **Do not build a feature on this.** Anything consuming an injury signal today
  would be consuming noise with a 20% chance of being the wrong sign.
* **Do not conclude injuries are worthless either.** P(delta > 0) = 0.805 is
  suggestive, and the honest state is "accruing".
* The cheap settlement the oracle was run to provide did not arrive. It
  narrowed the question rather than closing it: the ceiling is real but
  unresolved, so this stays registered and accruing rather than becoming a
  build item.

## What this cannot answer yet

Whether injury awareness is worth anything. The `oracle` arm — absence taken
from the box score, with hindsight, explicitly not tradable — exists to bound
that question without waiting, and running it is the next step regardless of
the backfill. An oracle delta near zero would mean roster awareness cannot help
this model even with perfect information, which would settle the question more
cheaply than a season of forward data.
