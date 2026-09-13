# Research report, 2026-09-13: everything tested, every number, what is alive

Every number below is a backtest on recorded venue prices, game-clustered, with
its 95% interval. "Excludes 0" means the interval does not contain zero. G is
the number of games. Nothing has been traded. Two things are alive; everything
else is dead on evidence.

## 1. DEAD — market making on Polymarket US (six weeks, three strata, one retraction)

| stratum | what a maker did | markout at +2 min per fill | G | verdict |
|---|---|---|---|---|
| at plays | join the touch after every play, both sides | −0.82¢ [−1.26, −0.37] | 37 | loses, excludes 0 |
| dead windows | quote only when nothing is happening | −0.07¢ [−0.34, +0.20] | 33 | break-even |
| move side | quote only after a ≥1¢ move, on its side | −1.17¢ [−1.89, −0.46] | 43 | **loses, excludes 0** — the earlier +3.58¢ was a one-minute look-ahead, retracted |
| shield arms (model pulls the bad side) | same, with a WP model deciding | −0.50¢ [−1.11, +0.11] | 40 | spans 0 |

Pre-registered gate on the move side: FAIL, with power (14 of 43 games positive).
Adverse selection on this venue eats the spread every way it was tried. Closed.

## 2. DEAD — a model against the venue's price (taker)

| test | result | meaning |
|---|---|---|
| in-game WP model vs live venue mid, net of 6% fee | never positive after fee | the venue prices NFL/CFB off DraftKings within 0.3¢ |
| NFL WP head vs nflfastR | +0.0007 [−0.0044, +0.0059] Brier | our model equals the public one, no more |
| NFL cover model vs in-game normal | +4.9% Brier | better model, still not better than the price |
| totals | the normal IS the model | no model edge |
| pregame softness vs DraftKings (Polymarket, Kalshi, 3 samples) | +0.26¢, +0.20¢, −0.18¢, all span 0 | neither venue is soft at the close |
| overshoot after a ≥1¢ move | Polymarket CONTINUES (+0.53¢), Kalshi REVERTS (~6%) | chasing loses net of fee; fading works only on Kalshi and only under its fee |

## 3. ALIVE — the favourite–longshot bias on the venue's own ladders

Found by a broad, model-free scan (every pregame rung, settled from finals),
then checked out of sample and on a second sport with the venue's own settlements.

**CFB spreads, buy NO on rungs whose YES mid is 20–30¢ (net of fee):**

| population | net per $1 bet | interval | markets | G |
|---|---|---|---|---|
| games through 09-06 (found here) | +6.88¢ | [−1.27, +15.03] | 164 | 60 |
| held-out Saturday 09-12 | +4.56¢ | [−13.80, +22.92] | 47 | 16 |
| pooled | +6.36¢ | [−1.12, +13.85] | 211 | 76 |
| mirror (buy YES on 70–80¢ rungs) | −2.27¢ | [−15.61, +11.08] | 101 | 45 |

One-sided: cheap YES overpriced, expensive YES not underpriced — the classic
shape. Registered read: Saturday 09-19, held-out or pooled at G ≥ 25.

**WNBA, 88 games, 1,582 markets settled BY THE VENUE (not by us):**

| bet | net per $1 | interval | markets | G | games positive |
|---|---|---|---|---|---|
| **spreads: buy YES on favourite rungs, YES mid 80–100¢** | **+5.78¢** | **[+2.96, +8.60] excludes 0** | 101 | 40 | 38/40 |
| totals: buy UNDER on every rung | +5.40¢ | [−2.24, +13.04] | 792 | 88 | 52/88 |
| totals: buy OVER on every rung (mirror) | −10.63¢ | [−18.28, −2.97] excludes 0 | 792 | 88 | 33/88 |
| spreads: the CFB bet (buy NO on 20–30¢) | +2.77¢ | [−8.58, +14.13] | 61 | 52 | 43/52 |

Overs are overpriced in every one of eight buckets (6–11¢ each); favourites at
the top of the spread ladder are underpriced with an interval that excludes
zero. Same crowd behaviour, second sport, venue-authoritative settlement. The
WNBA numbers are the first "excludes zero on the right side" this project has
produced that survived its own checks. Caveat that stands: ~30 buckets were
looked at; the mechanism (cheap side overpriced, favourites underpriced) is
what makes it more than a lucky bucket, and it is why the next reads are
registered before they are run.

## 4. The plan (docs/math/longshot-no-candidate.md)

- 09-19: registered CFB read. Pass → bounded live week 09-26, $25/rung, weekly cap −$600, kill after two losing weeks.
- Shadow lister for the CFB bet being built now; tested on 09-12 tape.
- WNBA: playoffs are the next tape; the recorders record WNBA already. The favourite bet and the under bet get a registered read on the first 25 playoff games.
- NBA: the league is defined in the code; no tape yet (season starts in October). The recorders pick it up when the venue lists it. Kalshi NBA series need adding.
- Kalshi lag test (your friend's mechanism): the tape started 09-12; first read 09-19.

## 5. Infrastructure now on AWS, no laptop involved

ESPN recorders (CFB, NFL), venue recorder, Kalshi recorder with a 72-hour
pregame window (NFL games given kickoffs on 09-12; they were never polled
before), DraftKings line recorders for NFL and CFB a week ahead, the weekend
read as cron (Sun 15:50Z, Mon 10:20Z) writing to /opt/meridian/artifacts/reads.
