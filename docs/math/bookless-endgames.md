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
