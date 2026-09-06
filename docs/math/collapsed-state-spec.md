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

## The statistic: per-market poll rate

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
