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
