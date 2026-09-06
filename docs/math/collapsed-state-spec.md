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

## Threshold, with both margins stated

`COLLAPSED_HZ = 0.0138` — one poll per 73s per market. Geometric midpoint of
measured healthy (0.057–0.154 Hz) and collapsed (≤0.0033 Hz).

| state | measured | vs threshold |
|---|---:|---:|
| healthy hour | 0.0552 Hz | **4× above** |
| collapse hour | 0.00028 Hz | **50× below** |
| **after the restore** | **0.0182 Hz** | **1.3× above** |

**★ The restore margin is thin and that is the risk to this design.** The cut
was calibrated against the pre-incident rate, but the *restored* recorder runs
at a third of it. A restore slightly slower than 09-06's would false-fire, and
a false fire on day one is how a monitor gets disabled. Either widen the
threshold to ~0.005 Hz (still 56× above the collapsed state, but only 3.6×
below the restored one) or — better — have the operator confirm which cadence
is intended, because a restored recorder at a third of its former rate may
itself be the finding.

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
