# Bookless endgames — the exit that isn't there

**Venue fact, measured three ways.** Polymarket US winner markets lose their
two-sided book late in decided games. Across the 22 signal-covered games through
2026-08-27: **13 endgames priceable, 9 bookless — a 59% yield.** "Priceable"
means: at least one two-sided winner quote inside the final 5:00 of regulation
(10s resample, venue box clock, clock staleness ≤ 60s). Unit note, stated
because two true numbers about one game will otherwise read as a contradiction:
**cohort ticks are 10-second resampled quotes inside the last 5:00; raw rows are
every 200ms snapshot.** wsh-phx 08-25 is "41 cohort ticks, zero in the window"
and "1,981 raw two-sided Q4 rows" simultaneously.

**The shape, not just the count.** The bookless nine are not marginal cases:
gsv-conn 08-26 and por-dal 08-25 carry 6,814 and 6,892 raw Q4 winner rows
respectively with NOT ONE two-sided — full tick streams, zero book, one-sided
from Q3 onward. atl-la 08-20 never quoted a two-sided Q4 winner row at all
(7,866 Q4 rows, zero two-sided). The book does not thin at the end of decided
games; it vanishes wholesale, well before the whistle.

**Verification provenance:** (1) original cohort funnel, 17 games;
(2) re-derived unchanged against the per-day parity-verified mirror after the
Aug-20 sync-hole repair — the 720k backfilled rows contained zero additional
two-sided Q4 winner ticks; (3) manager's independent raw-SQL count from
`market_snapshots`, a different-kind route from the funnel, matching exactly.

## Consequences

1. **The EV stop's structural limit** (belongs in that registration as a known
   limit): the exit book exists precisely while the game is in question and
   evaporates once it isn't. An exit rule works where you least need it and
   disappears where you would most want out. Position sizing in Q4 must price
   the possibility that there is no exit at any price.
2. **Cohort arithmetic is computable:** floor ETAs for endgame gates run at
   ~59% of signal games (measured 13/22), not at slate count.
3. **Selection cuts both ways:** books survive in competitive endgames — so any
   endgame study conditioned on a book existing is conditioned on the game being
   close. State it in the study, not after it.

## Methodological note from the measurement itself

**A filter applied before a join turns a property of the data into an apparent
property of the pipeline.** The two fully-bookless games first surfaced as "join
failed" because the two-sided filter ran before slug matching — absence of book
masqueraded as absence of slug, which reads as *our bug* and dispatches someone
to fix a join that was never broken. Order joins before filters, or label the
filtered universe explicitly.

**Reproduction:** survey funnel scripts against the mirror at per-day parity;
windows and as-of instants printed per findings #95a. First recorded
2026-08-25, re-derived 08-26, third confirmation 08-27.

---

*Referenced by #20's cohort rule, the EV-stop registration (limit clause), and
F10/F11 in the research artifact. Results append below this line, never above.*

## Within-game control (added 2026-08-28; GS-NY 08-27, 19-pt final)

The strongest instance in the set: **game, window, and instrument held fixed,
only the market varying.** In the twelve minutes 01:50→02:02Z the same recorder
captured near-identical row counts across that game's markets —

| market | Q4-window rows | two-sided | last two-sided |
|---|---|---|---|
| **winner** `aec-wnba-gsv-ny-2026-08-27` | 3,456 | **5** | 01:50:06Z |
| spread `asc-…-neg-10pt5` | 3,456 | 3,430 | 02:01:54Z |
| total `tsc-…-154pt5` | 3,178 | 3,178 | 02:01:32Z |
| total `tsc-…-157pt5` | 3,031 | 3,031 | 02:01:59Z |

Not an outage, not a coverage gap, not a board effect: **the venue stopped
quoting the winner of a decided game while that same game's spread and totals
books quoted continuously to the buzzer.** Every earlier instance compared
across games; this one holds everything fixed but the market.

### Is the hazard winner-specific? Partly — and the converse is FALSE

The obvious refinement — *winner books die, ladder books persist* — was tested
across all 70 games carrying Q4 winner coverage, measured as the share of Q4
winner rows that were two-sided. **It is half true, and the half that fails
matters more.**

**Where the winner book is fully dead (0.0% two-sided), the ladders always
survive — 7 of 7:**

| game | winner | spread | totals |
|---|---|---|---|
| atl-conn 08-13 | 0.0% | 33.9% | 96.2% |
| atl-la 08-20 | 0.0% | 5.9% | 35.5% |
| conn-dal 08-02 | 0.0% | 50.1% | 45.7% |
| gsv-conn 08-26 | 0.0% | 36.8% | 93.9% |
| lv-ny 08-09 | 0.0% | 28.1% | 95.6% |
| phx-wsh 08-09 | 0.0% | 30.3% | 86.7% |
| por-dal 08-25 | 0.0% | 68.5% | 90.8% |

**But ladders die independently, with the winner book healthy — at least 6
games:** phx-chi 08-03 (winner 86.8%, **totals 0.0%**), min-gsv 08-19 (71.9%,
**4.6%**), dal-wsh 08-05 (97.4%, **11.3%**), wsh-por 08-23 (86.7%, **18.5%**),
ind-ny 08-22 (77.9%, **22.5%**), la-min 08-06 (97.3%, **spread 28.5%**).

**So "ladder exits persist" is not a safe assumption, and an EV stop must not
be written as though it were.** The winner book dies more often and more
completely — consistent with P→1 leaving nothing to quote — but *every* market
type can go one-sided in an endgame, and a rule that trusts the ladder to be
there will find it missing in roughly one game in ten.

**Unit note, load-bearing:** the percentages above are the share of **whole-Q4**
winner rows that were two-sided. That is *not* the cohort's priceability test,
which asks for a two-sided quote **inside the final 5:00** on a 10s resample.
The two measure different things and will not agree; 7 fully-dead winners here
against 9 bookless in the cohort is the expected disagreement, not a
contradiction.

