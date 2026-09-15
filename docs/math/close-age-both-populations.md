# Close age, both populations, minutes and as a ratio

Measured 2026-09-15 on prod, September floor (a month boundary; a mid-month
one filters without pruning). The close is the last two-sided quote strictly
before kickoff, selected with the scan's own predicate so the population is
the one the scan reports on.

The reason for two populations and two units, stated when I committed to this:
**a cadence fix that moves the minutes without moving the ratio below 0.10 is
not a staleness fix.** So the minutes and the fraction are reported together,
on both `ko < now()` and `ko < now() - 4h`.

| league | population | closes | median | p90 | max | **fraction > 1h** |
|---|---|---|---|---|---|---|
| cfb | A: `ko < now()` | 15,818 | 0.1m | 56.3m | 359.8m | **0.095** |
| cfb | B: `ko < now()-4h` | 15,818 | 0.1m | 56.3m | 359.8m | **0.095** |
| nfl | A | 5,441 | 0.2m | 0.4m | 355.1m | 0.002 |
| nfl | B | 5,441 | 0.2m | 0.4m | 355.1m | 0.002 |
| mlb | A | 165 | 11.5m | 16.5m | 28.1m | 0.000 |
| mlb | B | 165 | 11.5m | 16.5m | 28.1m | 0.000 |
| **tabletennis** | **A** | **413** | 7.5m | **61.7m** | 191.7m | **0.107** |
| **tabletennis** | **B** | **372** | 7.5m | **66.6m** | 191.7m | **0.118** |
| cricket | A / B | 2 | 63.7m | 110.7m | 122.5m | 0.500 (n=2) |

## The two populations are identical everywhere except table tennis

cfb, nfl, mlb and cricket return **byte-identical** rows under both — same
closes, same quantiles, same fraction. Only table tennis moves: 413 closes
become 372, and the fraction over an hour rises **0.107 → 0.118**.

The reason is the schedule's density. A four-hour lag can only remove games
that started inside the last four hours, and football and baseball do not
start and finish inside that window — but Setka Cup runs matches continuously,
so 41 of 413 TT closes belong to matches that began in the last four hours.

**And the stricter population is WORSE, not better.** That is the part worth
having: if the looser population had been the pessimistic one, the TT
staleness could have been dismissed as a boundary artifact of including
just-started games. It is not. Restricting to long-finished matches raises the
fraction, so the looser population was *understating* it.

## The ratio, against a MEASURED duration rather than an assumed one

One hour is an arbitrary bar for a match that lasts a fraction of it, so the
scale-free version matters more here than anywhere else.

I have no end-of-match signal for table tennis, so the duration is bounded
from the data: over **534** consecutive-match gaps for the same player, the
**minimum is 30 minutes** — a player cannot start a second match before the
first ended, so 30m is the tightest upper bound the substrate supports. (The
median gap is 90m, which is scheduling, not duration.)

| population | median | p90 | max |
|---|---|---|---|
| A: `ko < now()` | **0.25 matches** | **2.06 matches** | 6.39 matches |
| B: `ko < now()-4h` | 0.25 | **2.22** | 6.39 |

So a median TT close is a quarter of a match stale and the p90 is **more than
two whole matches** before the one being priced. Using a 30-minute duration is
generous: if a match is really 15–20 minutes, every figure roughly doubles.

**The scan's own recorded ratio is not reproducible.** `cfb/run_scan.py`
carries, in a comment, "close age / event duration: cfb median 0.000 p90
0.001, nfl 0.000/0.000, tabletennis 0.405 / 5.852". No duration constant
exists anywhere in the code, so the number cannot be re-derived — and the two
TT figures are not consistent with any single duration (0.405 implies ~18.5m,
5.852 implies ~10.5m). A ratio in a comment with no constant behind it is a
claim with no test.

## What this says about the 0.10 threshold

* **cfb sits at 0.095**, just under it, on both populations. The scan's
  rounded "10%" is this number.
* **table tennis is above it on both**, 0.107 and 0.118.
* nfl (0.002) and mlb (0.000) are nowhere near it.

So the threshold currently separates exactly the league the TT cadence work
was about, and cfb is close enough that a small regression would cross it. The
ratio is the number to re-read after any cadence change: TT's minutes could be
halved by polling twice as often while the fraction over an hour stays where
it is, and that would be a cadence improvement rather than a staleness fix.
