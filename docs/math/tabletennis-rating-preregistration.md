# Table tennis player ratings — pre-registration, written before any rating is fitted

2026-09-15, 01:55Z. Registered **before** a single rating is computed and before any
price is compared to one. Written because tonight's results close off every other
source of edge.

## Why this and not something else

Measured tonight, on this venue:

* **Taking loses** because the half-spread is 2.5–7.5¢ and no directional signal
  we have measured exceeds it. Pregame CFB is calibrated to within 0.6pp on 117
  games.
* **Making loses** because the spread is exactly the adverse-selection premium:
  across 223,303 fills the edge earned rises from 0.50¢ to 5.29¢ with the spread
  while the adverse move rises from 3.65¢ to 9.97¢, leaving a flat −1¢ in every
  bucket.

Both sides of the book are internally priced. **So edge has to come from
information the venue does not have.** Faster data is out: plays reach us a median
53 seconds late. That leaves a better model of the sport.

## Why table tennis is the only place to test one

| | games/day | players | appearances per player, 2 days |
|---|---:|---:|---:|
| setkameua | ~250 | 171 | 6.2 |
| setkamecz | ~50 | 50 | 4.1 |
| setkamemd | ~40 | 48 | 3.4 |
| setkawoua | ~5 | 6 | 5.0 |

**345 matches a day against a closed pool of ~275 players.** MLB gives 10–15 a
night, CFB ~117 but only Saturdays, NFL 15 a week. Nowhere else can a player-level
model reach useful sample inside a month.

## The hypothesis, stated so it can fail

**H:** a rating fitted only to settled match outcomes carries information the
venue's price does not, in a market this small and this fast.

**Null:** the venue's price already contains everything the rating knows, so
regressing outcome on (price, rating) leaves the rating's coefficient at zero.

## The test, fixed now

1. **Rating:** Elo, K=24, start 1500, fitted **only** on settled matches strictly
   before the match being predicted. No future information, no price input.
2. **Minimum history:** both players must have **≥10 prior settled matches in the
   same competition**. Below that the rating is noise and the match is excluded
   and counted.
3. **Primary test:** logistic regression of the outcome on the venue's implied
   probability and the Elo-implied probability. **The registered quantity is the
   Elo coefficient and its game-clustered interval.** Zero means the price
   already knows.
4. **Secondary, and only if the primary excludes zero:** net P&L of taking the
   side the rating prefers when the two disagree by more than the half-spread plus
   fee, reported per competition and never pooled across them.
5. **Power floor:** ≥200 predicted matches and ≥25 distinct players per
   competition. Below that, report the count and stop.

## What would make this wrong, written before it can be excused

* **The four competitions are different leagues.** Pooling them is the error that
  produced three false descriptions in one day here. Every figure is reported per
  competition.
* **Players are named by slug fragment.** `doblad` is not verified to be one
  person; a collision merges two players into one rating. Before any result is
  believed, the appearance counts must be checked against ESPN or the venue's own
  event payload, and a name that appears in two competitions treated as two
  entities until proven otherwise.
* **Settlement is currently thin.** 138 table-tennis entries in the cache against
  342 games with a close on 09-14 alone. The primary test does not run until
  settlement coverage is measured, not assumed.
* **The rating is fitted on the same venue's matches it then predicts.** That is
  fine for information but not for a claim about skill; the claim is only ever
  "the price misses something", never "we know who is better".
