# COLLAPSED — a refinement of ABSENT that names the cause

**For c7's `alarm_v5.assess()`.** Not a second alarm. v5 already fires on the
09-05 incident, fast and correctly; it calls it ABSENT, which is right about
the symptom and wrong about the cause. The recorder had not stopped — a
low-frequency sweep kept writing while the high-frequency writer was gone.
The remediations differ (restart one container vs the whole path is down), so
the cause is worth a state.

## First: the question I was asked, and the answer is a negative

*"What does a degrading recorder look like an hour before it collapses, and is
there a gap value that separates busy from dying during live play?"*

**On this incident there is no degradation phase to calibrate against.**
5-minute buckets across the transition:

| bucket | markets | rows/s | median gap |
|---|---:|---:|---:|
| 09-05 22:05 | 2,425 | **248.5** | 3.4s |
| 22:10, 22:15 | — | *no rows at all* | — |
| 09-05 22:20 | 6,344 | **21.1** | 2,487.8s |

Healthy to dead in one step, with a hole in between. That is a container kill,
not a slowdown, and it is consistent with the documented name collision. **So
I cannot honestly fit a "dying" threshold to this data** — there is no dying,
and a threshold calibrated on an instantaneous death would be a guess dressed
as a measurement. What follows detects the *state*, fast, and does not claim
early warning it cannot deliver.

## Why it must be a longer window, and why v5 says "stopped"

During the collapse, the fraction of windows containing **no rows at all**:

| window | 5 min | 15 min | 30 min | 60 min |
|---|---:|---:|---:|---:|
| empty | **86.6%** | 60.7% | 21.4% | **0.0%** |

At v5's own cadence a collapsed recorder and a stopped one are **the same
observation**. The distinction only exists over a window long enough to
contain one sweep cycle. That is not a flaw in v5 — it is an identifiability
limit, and it is why the 600s stream guard reports ABSENT.

**So do not change when ABSENT fires.** When it does, look back 60 minutes and
ask whether anything is still writing at sweep cadence.

## ★ v2: the statistic is a COUNT, and needs no denominator at all

**Superseding the `poll_hz` design below.** c7 held the wiring because
`poll_rate(rows, markets, window)` needs a market count and every source is
poisoned — `is_live` is never cleared (C16), and a post-guard count collapses
alongside the numerator. They were right to hold. The fix is not a better
denominator; it is not needing one.

**Their proposed `RECENT_ACTIVITY_H` does not survive a slate boundary.**
Measured at the restore — a healthy recorder on a quiet Sunday:

| denominator | markets | poll_hz | vs threshold |
|---|---:|---:|---:|
| true live count | 166 | 0.19378 | 49.7× above |
| RECENT_ACTIVITY_H (6h) | 5,028 | 0.00640 | **1.6× above** |

A **30.3× inflation**, because a 6-hour lookback holds markets from games that
have finished. That exceeds the threshold's 14× margin, so it is not a near
miss: the *pre-incident healthy rate* of 0.0552 Hz divided by 30.3 is
0.0018 Hz — **COLLAPSED on a healthy recorder**. It passed here only because
the restore happened to run 3.5× faster than pre-incident.

**And the numerator was a mixture too.** Rows per market in the healthy hour
are **bimodal**, not skewed:

| p10 | p25 | p50 | p75 | p90–p100 | mean |
|---:|---:|---:|---:|---:|---:|
| 2 | 2 | **2** | 115 | **1,012** | 198.6 |

59% of markets get ≤2 rows an hour — the sweep touching them — while a second
mode sits at 1,012/hour, one poll per 3.56s. So total-rows/total-markets is an
average across two populations whose ratio moves with the slate. c7's
denominator disease was in the numerator as well.

**The statistic: count the markets polled above sweep cadence.**

```
COLLAPSED  ⇔  rows > 0  AND  n_live == 0
n_live = #{markets with more rows than sweep cadence would produce}
```

| window | n_live | state |
|---|---:|---|
| healthy hour | **2,586** | OK |
| collapse hour | **0** | COLLAPSED |
| collapse +5h, +11h | **0** | COLLAPSED |
| restore, quiet Sunday | **166** (all) | OK |

Categorical, not a cut on a continuous statistic. The one parameter,
`LIVE_ROWS_PER_HOUR`, only has to separate sweep (1–2/hour) from live
(1,012/hour): **collapsed reads 0 at every cut from 3 to 300/hour** while
healthy and restored stay non-zero throughout. A corridor, not a tuned
constant.

No denominator, no market count, no `is_live`, no mixture — and a slate
boundary cannot inflate a count. The counts come from the same query that
already produces `rows`.

A partial failure (a few markets live, thousands dropped) is deliberately
**not** COLLAPSED; that is coverage, and it belongs to the coverage check.
This state means the fast writer is gone entirely.

### ★ The empty-slate hole is real — and a schedule source does exist

c7 is right that `rows > 0 AND n_live == 0` fires on a night with no games:
the sweep still writes pregame boards, nothing is polled live, and a healthy
recorder reads COLLAPSED. **My own +11h case was an instance of it** — 12:00Z
on 09-06 is 08:00 ET Sunday with no live football, so that case fired on an
empty slate rather than demonstrating an ongoing incident. It did not test
what I claimed.

But the premise that *"both expectations are derived from our own write
stream"* does not hold here. **`espn_cfb_game_state` is a schedule source, it
is already in the database, and it is written by a different container** — the
ESPN CFB recorder, which stayed healthy throughout this incident (8,634 plays,
18,775 state rows) precisely because the failure was a name collision on the
*price* recorder.

```
COLLAPSED  ⇔  live_games > 0  AND  rows > 0  AND  n_live == 0
```

Every hour of the incident, with `live_games` from `state == 'in'`:

| hour | live games | rows | n_live | state |
|---|---:|---:|---:|---|
| 09-05 22:00Z | 18 | 188,394 | 2,332 | OK |
| **09-05 23:00Z → 09-06 06:00Z** | **2–32** | 5,810–12,690 | **0** | **COLLAPSED ×8** |
| 09-06 07:00Z–15:00Z | **0** | 157–9,349 | 0 | **OK** — empty slate |
| 09-06 16:00Z | 1 | 4,638 | 0 | **COLLAPSED** |

Eight consecutive hours of correct firing through the outage, silence across
the nine-hour empty stretch, and firing again the moment a game goes live with
the recorder still down.

**The limit, stated in the same terms as ABSENT's:** if the ESPN recorder is
*also* down, `live_games` reads 0 and COLLAPSED goes quiet — it **fails
quiet, not loud**. Visible in the table above: the 21:00Z hour reads 0 games
only because the ESPN export begins at 22:08Z. The two recorders are separate
containers, so one failure does not couple them, and an ESPN outage raises its
own ABSENT. But a simultaneous loss of both is silent here, and no source in
this system fixes that.

7-case adversary re-run on v2, all passing, including the slate-boundary case
that killed v1 and the disabled-control.

---

## v1, superseded: per-market poll rate

```
poll_hz = rows / (window_seconds × live_markets)
```

Rejected alternatives, both for measured reasons:

* **median per-market gap** — undefined exactly when things are worst. With
  one row per market per window there is no successor pair, which is the
  mechanism that drops the market and yields ABSENT.
* **rows/sec** — confounded by slate size. The collapsed buckets carried
  **more** markets (5,679–6,346) than some healthy ones (2,425), so an
  absolute cut would have to sit below the busiest healthy slate and would
  then miss a collapse on a small one.

`poll_hz` is defined whenever any row arrives and is normalised for slate size.

## Threshold — corrected, after my restore figure turned out wrong by 10.6×

**The first version of this spec said the restored recorder ran at 0.0182 Hz,
a third of its former rate, and called that the risk to the design. That was a
denominator error.** The `cfb_restored` export spans **339 seconds, not an
hour**, and I divided by 3600. Corrected:

| state | rate | median gap | vs threshold |
|---|---:|---:|---:|
| collapsed | 0.00028 Hz | *no cadence — one burst/hour* | **14× below** |
| healthy (slate) | 0.0552 Hz | 3.4s | **14× above** |
| **restored** | **0.1938 Hz** | **1.7s** | **49× above** |

**The restored recorder is not degraded. It is running 3.5× faster than
pre-incident**, with a median gap of 1.7s against 3.4s.

`COLLAPSED_HZ = 0.0039` — one poll per 254s per market, log-symmetric between
the two regimes that actually bind, healthy and collapsed. **14× margin each
way**, and the restore is no longer anywhere near the cut.

**This dissolves the blocking question, and the question was sound.** c7 was
right that if 0.0182 were the healthy operating point, the same number would
be either normal or an active incident and no threshold could be set from one
observation. But 0.0182 was never an operating point — it was my arithmetic.
The healthy regime is 0.055–0.194 Hz across two independent observations, two
orders above the collapsed state.

The general form is worth more than the number: **a rate computed over an
assumed window is a claim about the window.** I checked the numerator against
the data and took the denominator from the file's name.

## The adversary — 9 cases, observed both firing and silent

A monitor never seen firing has no evidence behind it. Run against the real
exports, all passing:

| case | → |
|---|---|
| real healthy hour | OK |
| **real collapse hour** | **COLLAPSED** |
| real collapse, 5h later | COLLAPSED |
| after the restore | OK |
| true stop, nothing writing | STOPPED |
| **busy: slate doubles, rate holds** | **OK** |
| small slate at healthy cadence | OK |
| tiny slate below MIN_MARKETS | OK |
| **disabled-control: collapsed hour, rate forced healthy** | **OK** |

The last one is the check for the failure found in three of five of
Debugger's own guards: if forcing the statistic healthy on collapsed inputs
left the state COLLAPSED, the classifier would not be reading its input.

The busy case is the one a gap-based or rows/s-based alarm fails: double the
slate and double the throughput, per-market gap rises, and nothing is wrong.

## Integration contract (from c7)

`assess(rows, activity) -> list[tuple[league, state, reason]]`, enumerating
every league in `EXPECTED_LEAGUES ∪ observed`. States today are
`OK / INSUFFICIENT / ABSENT / ALARM`. The pure function drops in unchanged and
is called per league **before** the movement branch — a collapsed recorder
makes the movement statistic meaningless rather than zero, which is c7's point
and a better placement than mine.

Two of their corrections adopted:

* `MIN_MARKETS_RATE = 20` renamed apart from their `MIN_MARKETS = 12`. Theirs
  is a false-positive budget on a **share**; mine is a denominator floor for a
  **rate**. Different quantities, named so nobody unifies them later.
* The 60-minute window must be **derived from `RUN_EVERY_MIN`**, not
  hardcoded. It is a property of the sweep's cadence, and if that changes the
  window must change with it or COLLAPSED silently degrades back to STOPPED.

## What I could not do

`scripts/alarm_v5.py` is **not in any commit or worktree I can reach** — it
appears to be uncommitted in c7's session — so I have not seen `assess()`'s
signature, its return type, or how states are ordered. The reference
implementation is a pure function (`rows_60m, markets_60m → str`) with no
dependencies, so it should drop in, but **the integration contract is c7's to
confirm and I have not verified it against their code.** Reference
implementation and the 9-case control are in the session scratchpad; c7 should
own the file.

Two numbers here are also worth their sanity-check: `MIN_MARKETS = 20` is a
judgement, not a measurement, and the 60-minute window is derived from *this*
sweep's cadence. If the sweep interval changes, the window must change with it
or COLLAPSED silently degrades back into STOPPED.
