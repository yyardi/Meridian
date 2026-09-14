# The scalp engine's freshness gate, measured before its first live tape

`MAX_AGE_S = 30`, checked against **both** the play's `wall_clock` and the
venue tick's `captured_at`, with `now = datetime.now(UTC)` in the live loop.
Measured 2026-09-14, before tonight's 00:15Z kickoff.

## The venue half never fires. The play half fires on almost everything

**How old is a play when we FIRST see it?**

| league | plays | p50 | p75 | p90 | already >30s on arrival |
|---|---|---|---|---|---|
| nfl | 2,727 | **52.8s** | 62.7s | 73.0s | **93.7%** |
| cfb | 23,094 | 57.8s | 70.9s | 93.0s | 97.3% |

The engine evaluates at `now ≥ first_seen_at`, so **93.7% is a lower bound**
on the refusal rate, not an estimate.

**And a fresh play is usually not available anyway.** Gap between consecutive
plays: median **43s** (NFL), p90 143s, **87.9% of gaps exceed 30 seconds**.
Football is played in bursts separated by huddles, TV breaks and reviews, so
even with zero pipeline lag the newest play is usually older than the gate.

**The venue tick is fine.** Live NFL winner markets on 09-13, 17:00–20:00Z:
median gap 6.5s, p90 9.5s, **0 of 11,665 gaps over 30 seconds.** The tick half
of the gate never refuses anything. The whole effect is the play half.

The 20-second `SUMMARY_INTERVAL` is not the cause either: a 52.8s median with
a 20s poll puts ESPN's own publishing lag at roughly 30–45 seconds. Polling
continuously would not get under 30.

**Prediction for tonight: near-zero triggers, and it will look like "the
strategy found no opportunities" rather than "the gate refused everything".**
That distinction is the whole value of counting triggers-skipped-for-stale
alongside triggers-fired.

## And the gate was admitting exactly the corrupt rows

`(now - t).total_seconds() > max_age_s` treats a **negative** age as perfectly
fresh. A timestamp in the future is not fresh; it is wrong.

**85 of 2,727 NFL plays (3.1%) recorded 09-10..14 carry a `wall_clock` 24
hours ahead** — minimum lag **−86,378s**, which is −86,400 plus the usual
lag, and p01 −86,350.9s. CFB has zero negatives and a clean minimum of
+12.4s, so the clock alignment is fine in general and this is an NFL-specific
date defect.

So under the old test those 85 rows were among the few that passed, while
93.7% of good plays were refused. **The one gate meant to stop bad data was
selecting for it.**

Fixed: `age > max_age_s or age < -1.0`. One second of tolerance for ordinary
clock skew between the feed's clock and ours; a day is not skew. Mutation-
tested — removing the future check fails the test.

## What is NOT changed here

`MAX_AGE_S` itself. Whether a 30-second gate is right for a feed whose median
play is 52.8 seconds old on arrival is a strategy decision: raising it admits
older information, and the right number depends on how fast the edge decays,
which nothing here measures. The measurement says what the current value
does; the value is the operator's.

The underlying NFL 24-hour date defect is also unfixed — the gate now refuses
those rows rather than trading on them, but the parser still writes them.


---

# Replayed exactly over the prior slate: the gate passes 0.23% of live time

Tonight's run does not have to be predicted. The 2026-09-13 NFL slate is
recorded, and the engine's own selection rule can be replayed over it with no
sampling and no simulation.

The engine takes `DISTINCT ON (game_id) ... ORDER BY wall_clock DESC`, so at
any instant it holds the greatest `wall_clock` among rows **already
recorded**. That makes the visible maximum a step function of the recording
times, so the passing intervals are exact arithmetic rather than a sampled
estimate: within each segment `[t_i, t_{i+1})` holding visible maximum `w`,
the gate passes over `[w, w+30) ∩ [t_i, t_{i+1})`.

| games | live hours | **time the gate passes** |
|---|---|---|
| 13 | 40.62 | **0.23%** |

Per game, 0.09% to 0.40% — **thirteen games inside a four-fold band**, so the
0.23% is not an average over a bimodal mixture. It is structural, not an
incident.

At the engine's 2-second cycle that is roughly 73,000 evaluations across the
slate and about 170 that clear the gate, ~13 per game, in games lasting three
hours. And clearing the gate is necessary but not sufficient — a trigger
condition still has to fire inside that window.

## Correcting the shared expectation about the 85

Both of us said tonight's fired trades would be disproportionately the
future-stamped rows. **They will not be, and neither of us checked.**

All 85 future-stamped NFL plays belong to **one game** — 401872657, recorded
2026-09-11 00:41–01:54Z with `wall_clock` stamped 2026-09-12 00:37, exactly
24 hours ahead. A single game, three days ago, long outside the engine's
six-hour window. Nothing tonight will be pinned to them.

Which changes what the fix is for. `age < -1.0` closes a real hole and the
defect will recur — one game in four days is a rate, not a one-off — but it
is **not** a protection for tonight, and saying so is the difference between
a fix and a story about a fix. Tonight's near-zero fired count will be
entirely ESPN's publishing lag exceeding a 30-second gate, with no corrupt
row involved.

The replay figure is also what makes `stale_skips` worth logging rather than
merely present: 0.23% predicts skipped in the tens of thousands against fired
in single digits, and those two numbers are the whole content of the run.
