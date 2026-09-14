# Truncation has two signs, and they are not the same direction

A note prompted by the observation that several defects found on 2026-09-14
"point the same direction". They do not. They share a **cause** and split on
**sign**, and the thing that decides the sign is worth naming because it
predicts which way the next one will go.

## The cause: a premature read of a process that only accumulates

A football score is monotone non-decreasing in time. Every defect below is a
measurement taken before the process finished. That single fact produces two
opposite biases depending on what the truncation touched.

## Sign one: truncation corrupts the VALUE, and the value comes out LOW

| defect | mechanism | direction | realised effect |
|---|---|---|---|
| `period >= 4` excluded the `post` row | read the last in-game row | total too LOW → settles **UNDER** | **0 of 36** totals moved |
| backfill 401856660 | 31-3 (34) against a post row of 51-10 (61) | total too LOW → **UNDER** | 1 game, now corrected |
| ESPN recorder stopped at the whistle | 81 of 186 games have no confirmed final | not a direction — a HOLE | 42 games excluded |

A total read early is low because points only get added. So a totals market
settles UNDER more often than the truth, and `cfb_total_under_all` is a
registered strategy that flatters.

## Sign two: truncation selects the SAMPLE, and the sample comes out HIGH

| defect | mechanism | direction |
|---|---|---|
| Kalshi settled-set capture | an "Over X" market resolves the instant the running total passes X, so a recorder that stops early captures the ones that went over EARLY | selects HIGH totals → flatters **OVER/YES** |

Same stopping condition, opposite sign. 93.9% of the captured totals
settlements are YES, and the settled-yes markets sit at a mean strike of 45.7
against 55.8 for the never-settled.

**This is the part that matters.** Truncation on the *value* of a monotone
quantity biases it down. Truncation on *which observations exist* biases
toward whatever resolved first — and for an over/under ladder, what resolves
first is the high outcome. One cause, two signs, and reading them as one
direction would have had us correcting in the wrong direction on one of them.

## And the repair does not inherit the defect's sign

The `max(home_score), max(away_score)` repair I nearly recommended for sign
one would have overstated twelve totals by 2–7 points — **flattering OVER**,
the opposite of the defect it was repairing. In nine of the twelve the
maximum home score and maximum away score never co-existed in any single row,
so the "in-game maximum" was not a scoreline that ever happened.

So "the repair errs the same way as the defect" is not a safe default either.
Both signs have to be checked against the mechanism, not inferred from the
direction of the thing being fixed.

## What to do with this

Before believing any settlement-derived result, ask two questions rather than
one:

1. **Was the value read after the process finished?** If not, a monotone
   quantity is understated.
2. **Was the observation's existence conditional on the process finishing?**
   If not — if it exists *because* the outcome resolved early — the sample is
   selected toward whatever resolves early, which is usually the extreme.

The second question is the one nobody asks, and it is the one that made a
610-market Kalshi population unusable.
