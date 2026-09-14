# The in-game scan — result, 2026-09-14

> **Companion to `docs/math/scan-result_2026-09-14.md` (pregame).** These are one finding:
> *the conclusion holds pregame and in-play.* Neither file should be read without the other.

`cfb/run_scan_live.py`, prod read-only, venue-settled. Registered in
`docs/math/scan-preregistration.md` (+ Amendment 1). A **screen**. Nothing was traded.

**296,964 sampled ticks** — cfb 212,643, nfl 65,308, wnba 17,739, mlb 228, tabletennis 44,
cricket 2 — drawn from ~18M live rows in 7 days, **790× the pregame population** and
structurally different: prices move continuously rather than one close per market.

## The answer: the tight-spread board produces what a pure null produces

| max half-spread | cells | p<.05 obs/null | p<.01 obs/null | min p | E[min p] | lose/win |
|---|---:|---:|---:|---:|---:|---:|
| ≤ 1¢ | 52 | **2 / 2.6** | **0 / 0.5** | 2.00e-02 | 1.89e-02 | 0/2 |
| ≤ 2¢ | 88 | 2 / 4.4 | 0 / 0.9 | 2.00e-02 | 1.12e-02 | 0/2 |
| ≤ 3¢ | 94 | 2 / 4.7 | 0 / 0.9 | 2.00e-02 | 1.05e-02 | 0/2 |
| ≤ 5¢ | 97 | 2 / 4.9 | 0 / 1.0 | 2.00e-02 | 1.02e-02 | 0/2 |
| all | 161 | 27 / 8.1 | 17 / 1.6 | 5.38e-06 | 6.17e-03 | 25/2 |

**At every tradeable cap the count is at or below the null**, zero cells reach p<0.01 against
0.5 expected, and the minimum p over the 52 tight cells is **2.00e-02 against an expected
minimum of 1.89e-02**. Nothing is nominated; no cell clears Bonferroni at any tradeable cap.

**Twenty-five of the twenty-seven significant cells are in the widest bucket.** All ten top
cells are `>3c` with half-spreads of **11 to 22 cents**, every one losing — rates of 3.8% to
74.2% against break-evens of 44.7% to 92.8%. Spread, not edge, exactly as pregame.

## Why this is a replication and not a confirmation

**The expectation was put on the record before the scan was read**: that it would reproduce the
pregame answer, and that if it did not, the first suspect would be end-of-life rows the clock
window was meant to exclude. It reproduced. A different mechanism — continuously moving prices
across a 790× larger population — reaching the same answer is a materially stronger statement
about the venue than either read alone.

## ★ The diagnostic that makes an in-game cell readable

| | pregame | in-game |
|---|---:|---:|
| observations per effective cluster | 1.66 rungs/game | **median 11.2×, max 91.4×** |

    cfb 1-3c   n=2,715  G=52  G_eff=29.7   ->  91.4x
    cfb <=1c   n=2,272  G=50  G_eff=25.6   ->  88.8x

**A cell reading n=2,715 carries about 30 independent observations.** `G_eff = n²/Σ(cluster²)`
prints on every cell for this reason: without it that cell looks like 2,715 and every interval
built from it is spectacular and meaningless — confidence manufactured from repetition rather
than evidence. Pre-conditioning, `Var(t) 13.026` against a G-implied baseline of 1.203 and
`max|t| 26.006` against 3.153 are that artifact; post-conditioning it vanishes.

## ★ Two cells that are noise, and are recorded rather than rounded off

The two significant tight-spread cells are **winning**, where pregame's tight cells ran 10/1
**losing**. Two of fifty-two against 2.6 expected is noise and is treated as noise. But it is
the one place the in-game and pregame directional signatures differ, so it is written down
rather than smoothed away. **If it recurs next week on independent tape it is worth a look; on
one week it is two cells out of fifty-two.**

## Pre-registered before any cell was seen

* **Sampling**: one tick per market per 10 minutes, first in bucket. Declared, not
  parameterised — a rate chosen after seeing the cells is the population error in its purest
  form.
* **Clustering unit**: the game, with `G_eff` on every row.
* **Spread as a grid axis** (≤1¢, 1–3¢, >3¢) from the start, not a conditioning discovered at
  the end.
* **Live from the clock, never `is_live`** — `core/board.py:market_state()` says the flag
  cannot be trusted in either direction, and 11,227 markets carry a stale `is_live=true`
  unwritten for 600s. Window = `[game_start_time, +LIVE_H by sport]`.

## The gate's blind spot, named an hour before it bit

`cfb/test_scan_live_endtoend.py` execs the whole program against a synthetic fixture with no
DB and no venue. Its limit was **stated in the commit before the first prod run**: the stub
returns rows regardless of query parameters, so it exercises every code path and **cannot
validate the SQL**.

The first prod run then failed on `make_interval(hours => 4.5)` — the function takes an
integer and the gate had passed it happily. **Diagnosis took one step instead of three,** which
is what naming a gate's blind spot buys. Fixed to `:liveh * interval '1 hour'`.

## What this does not rule out

Unchanged from the pregame file and restated because it must be: **edges above roughly 5–15¢
by family are ruled out; anything between the ~2.1¢ cost hurdle and that bound is not.**
"We found nothing" and "nothing is there" are different sentences and only the first is true.
