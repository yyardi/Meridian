# STATUS — Meridian / Gridiron (updated 2026-09-14 10:40Z)

One file. What runs, what it has earned on paper, what is being read next, what
you need to run, and who is building what. Full numbers: `docs/RESEARCH_REPORT_2026-09-13.md`.

## 0. Your in-game idea, measured

You described buying the offence as it drove toward the end zone and taking 1–10% quickly.
Measured on 59 CFB games, 577 midfield triggers, game-clustered intervals, no fees involved.

| arm | horizon | mean move (¢) | 95% CI | touched +5¢ | touched −5¢ |
|---|---|---|---|---|---|
| crossed midfield | 30s | +0.092 | −0.024 to +0.209 | 1.0% | 0.5% |
| crossed midfield | 300s | +0.409 | −0.148 to +0.967 | 13.3% | 11.1% |
| had the ball, own half | 300s | −0.294 | −0.601 to +0.014 | 10.2% | 11.1% |
| scoring play (control) | 300s | +0.599 | +0.101 to +1.096 | 12.5% | 7.4% |

The control is the part that makes this worth reading. The same instrument detects a
touchdown and finds nothing when a drive crosses midfield, so the null is a measurement
and not a failure to look.

**What it means.** The move you remember is real and it happens 13.3% of the time within
five minutes. A move the same size against you happens 11.1% of the time. The median move
is 0.00¢ at every horizon in every arm. There is no supply of quick favourable moves to
fire at, and the ones that exist come almost one-for-one with adverse ones. That is the
answer, and it does not depend on fees.

Not yet replicated on NFL, which is the league you were actually watching. That run is in
progress on 15 settled games from yesterday. I am not sending you the conclusion as final
until it holds there.

## 0b. Where the money question stands, in one table

| question | measured | verdict |
|---|---|---|
| pregame taker edge, pooled | excess +0.357¢, CI −2.160 to +2.874, hurdle 4.101¢ | conclusively below cost, p=0.0018 |
| in-play taker edge, pooled | excess +2.055¢, CI upper +7.151, hurdle 6.905¢ | not conclusive, p=0.031, fails at m=2 |
| in-game drive scalp | see §0 | no move to trade |
| family-level dispersion, 286 cells | Var(t) 1.443 vs null 1.147; 36 cells \|t\|>1.96 vs band 4.1–24.5; 14 at p<0.01 vs 2.9 | more spread than the null, but max \|t\| 3.993 < Bonferroni 4.28 |
| only paper line excluding zero | wnba_spread_yes_80_100, +5.78¢ [+2.96, +8.60], 101 bets, 40 games | unverified: home/away twin not yet split, WNBA season over |

The fourth row is the only genuinely open thread. The collection of cells is more dispersed
than its own clustered null, which means something in the grid is not noise, and nothing in
the grid survives multiplicity on its own. Those two facts are both true and neither is a
strategy yet.

## 0c. Detection limit, so you know what we can and cannot see

Two independent routes agree: our sensitivity is 10–15¢ per bet, and we are blind below 5¢.
One route is pooled algebra, the other a planted-edge recovery curve, and they share no
implementation. An edge smaller than 5¢ exists or does not; we cannot tell from this tape.

## 0d. The board emptied at 09:35Z and came back at 11:40:59Z. Two of my three claims about it were wrong.

**Correction 1, and it invalidates my headline measurement.** I reported "venue events endpoint,
asked directly per league: 0 for cricket x5, table tennis, NFL, MLB" and called it a direct read
of venue content. `get_league_events` returns a **tuple**; my probe did
`getattr(r, "events", None) or []`, which on a tuple is always `[]`. **It printed zero no matter
what the venue said.** Its value under signal equalled its value under no signal, which is the
defect family I have a standing note about, and I used it as the load-bearing evidence. Unpacked
correctly at 11:44Z it reports NFL 29, MLB 43, table tennis 192, cricket 8.

**Correction 2.** I called this an incident. meridian-7f measured all 44.5 days: zero-hours peak
at exactly 10Z and 11Z, 8 and 9 of 44 days against 2 of 44 overnight. An empty 10-11Z is the most
common zero-hour we have.

**What actually survives, from the one instrument that was working.** The venue's own sports
listing reported **one** active event across the whole venue at 10:34Z and 11:17Z, and **1,150**
across 39 leagues at 11:44Z. That is a real change measured by a correct reading. Zero market rows
were written between 09:35:26Z and 11:40:59Z, a gap of 2h05m, and the first rows back were all
cricket.

| | value |
|---|---|
| last row before the gap | 2026-09-14 09:35:26Z |
| first row after | 2026-09-14 11:40:59.536Z |
| gap | 2h05m |
| venue listing during the gap / now | 1 event / 1,150 events |
| Kalshi | unaffected throughout |
| repopulation window, from `markets_seen` in the logs | 11:35:43Z saw 0, 11:40:59Z saw 11 -- 5m16s |

**It is a daily listing gap, not an incident.** The board came back well before tonight's MLB
first pitches, which was the criterion, and we now know the shape: **the venue's board is empty
for about two hours in the mid-morning UTC.** Only cricket is confirmed back; the other recorders
last swept at 11:30-11:35 and saw zero, so they have simply not looked since, which is the same
quiet-versus-empty trap running in the recovery direction.

**★ That gap lands on a registered measurement anchor.** For a 17:30Z kickoff, which is exactly
the England-Sri Lanka T20I the operator traded, `T-6h` is 11:30Z and sits inside the gap. The
cricket reversion anchor is being redefined as the last quote at or before `T-6h` with the
realised offset reported, so a match with a large offset is excluded and counted rather than
silently mis-anchored. Without it the measurement would have dropped or mis-anchored exactly the
afternoon-start matches, which are most of the ODI and T20I slate. Found by meridian-7f, and only
findable because the outage happened while someone was watching.

**And it is a live demonstration that the new column was the right fix.** Separating empty from
quiet during this gap took four `docker logs` calls grepping `markets_seen` out of container
output. As a column it is one query, and the alarm would have fired at 09:35 and cleared at 11:41
with nobody watching.

**So I had two routes agreeing and one of them could not disagree.** The listing and the events
probe told the same story, which is why I stopped checking. The events probe would have told that
story on any input.

**Neither of us has evidence about whether this is normal.** 7f used a row count to argue an empty
10-11Z is ordinary, immediately after establishing that a row count cannot tell empty from quiet,
so their eight days are equally consistent with a full and quiet board. My last Monday is one
draw. What the 44 days CAN say once the new column has data: 957 of 1,057 hours had at least one
row, so the board was provably non-empty and the alarm could not have fired, bounding its
false-positive rate at **9.5% or lower and no lower**. The unresolvable 100 hours are exactly the
ones the column exists to classify.

**Why no alarm fired, and why the obvious one cannot be it.** `board_coverage` takes its
`expected` from the sports listing, a different endpoint on the *same venue*. When the board
empties both sides go to zero together and `swept_nothing = (exp > 0 and obs == 0)` is false by
construction. It was built to catch a wrong slug, which is our error; it cannot catch the venue
going empty, which is theirs. An expected-versus-observed check only works when the expectation is
independent of what is observed.

**Shipped the missing quantity** (`dc2f676`): `service_heartbeats.markets_seen`, what the sweep
saw rather than what it wrote. The alarm is then "a completed sweep returned zero markets while
our own last 24 hours held markets whose start time is still in the future" -- expectation from
our past tape, observation from now. Forward-looking only: the observation side starts empty on
deploy. Staged on the box and not yet applied; it lands with the fleet rebuild.

**The weekday rule is right in principle and not buildable yet.** 6.4 weeks gives about 6
same-weekday-and-hour priors, so a rank rule false-alarms 14.3% per check, 3.4 times a day.
Two-hour persistence needs about 19 weeks, mid-January. Three-hour persistence works today at the
cost of three hours of latency.

## 0e. Table-tennis closes are stale, but I reported it against the wrong population

**Correction, before the table.** I reported "22.7% and 39.1% of table-tennis closes more than an
hour early" and gave those figures to the operator. They are measured on games that have merely
*started* (`ko < now()`). **The scan only scores games finished more than four hours ago**, and on
that population the same query reads 1.3% and 0.0%. My figures describe games the scan never
scores. Caught by meridian-7d, who reproduced my numbers exactly on my population before finding
the population was wrong -- which is the only way that error is findable.

Age of the scan's pregame close, on the population the scan actually scores, since 2026-09-01:

| league | games | median | p90 | over 60 min early |
|---|---:|---:|---:|---:|
| setkamecz | 12 | 19.2 min | 44.5 min | 0.0% |
| setkameua | 80 | 7.9 min | 39.2 min | 1.3% |
| cfb | 117 | 0.1 min | 0.2 min | 1.7% |
| nfl | 15 | 0.0 min | 0.1 min | 0.0% |

**The conclusion survives and the exposure is smaller than I said.** A 19-minute close on an
11-minute match is still the whole event. But the tail I led with was not the scan's tail.

**Minutes are the wrong unit; the ratio of close age to event duration is the right one.** 7d
measured it: cfb median 0.000, nfl 0.000, table tennis 0.405 with a p90 of 5.852. Their proposed
threshold is **0.10**, which passes 92.3% of cfb and 100% of nfl and 13.3% of table tennis, with
football clearing by three orders of magnitude rather than by tuning. Adopted.

**Football is clean in the median, not perfectly.** At market level, which is what the scan sums,
CFB is p90 56 minutes with 10% of closes more than an hour old.

**My cadence prediction: early evidence says yes, and the first read nearly said no.** Splitting
matches that started after the 11:10Z cadence change:

| post-fix matches | n | median | p90 |
|---|---:|---:|---:|
| close fell inside the 09:35-11:41 listing gap | 10 | 176.7 min | 186.7 min |
| close clear of the gap | 12 | 7.0 min | 12.0 min |

Unsplit, the post-fix sample reads median 12.0 and p90 181.7 -- a p90 twice as bad as before the
fix, which is what I saw first and what would have read as the fix failing. It is the outage, not
the cadence.

**My proposed fix for that -- exclude gap-affected closes -- is withdrawn. It is vacuous.** 7d
measured it: a 6-hour close window intersects a gap longer than 30 minutes for **91.6% of CFB
closes and 89.2% of table-tennis closes**. That is a deletion, not an exclusion. Worse, it does
not separate the two leagues, whose close ages differ by twenty minutes, so it cannot be the
mechanism. The structural reason is that **close age and gap-adjacency are the same quantity**: a
close is old exactly when a gap sits between the last observation and the start, so excluding
gap-affected closes from a close-age measurement removes the observations the measurement is
about.

**The test that needs no exclusion: do the median and the p90 move together?** A cadence fix
compresses the whole distribution. An outage leaves the median alone and explodes the tail. My own
early read is that signature exactly -- median 19.5 to 12.0 better, p90 91.7 to 181.7 worse -- and
it reproduces my split's conclusion without identifying a single gap or deleting any data.

**Table tennis was the loudest league, not the only one.** MLB's close is 28.1 minutes early on a
roughly three-hour game, a ratio of 0.156, which fails the 0.10 threshold and which nobody had
checked. **That is one game.** I verified it by a second route and the second route found n=1, so
it is an observation, not a measurement, and MLB is the operator's daily-volume league so it will
have a real sample within days. The single `t20icr` close is 123 minutes early.

## 0f. Scan cost has two regimes, and the cadence budget depends on which one you are in

| run | queries | cache | floor | wall | settlement calls |
|---|---:|---|---|---:|---:|
| 05:28Z | 13 | cold | none | 115.5 min | 22,503 |
| 10:07Z | 1 | warm | 2026-09-01 | 9.2 min | 20,954 |
| 12:34Z | 1 | warm | none | 14.0 min | 22,577 |

**Cold cache is settlement-bound**: 22,503 HTTP calls at 200-300 ms is 4,500-6,750s, which
accounts for essentially the whole 115 minutes. **Warm cache is query-bound**: the calls become
cache hits and the floor's measured saving is **34.1%**, against **33.5% predicted by EXPLAIN**
from planner cost alone. Two routes that share no implementation, agreeing to 0.6 percentage
points.

So the fifty-strategies-a-week cadence budgets against **query cost in steady state** and against
**venue calls and rate limits for the first run of any new league**. 7d withdrew an earlier
reading of this and so did I; the table above is the resolved version.

## 0g. MLB is not missing 40% of its board. I was wrong, and the guard that told me so is broken twice.

**Retraction.** I reported that MLB was recording 49 of 81 listed events and that 40% of the
operator's daily-volume league was missing. I raised `MERIDIAN_EVENT_LIMIT` to 500 and wrote the
falsifiable test into the commit: if observed does not move off 49, the limit was not the cause.
**It swept at 12:31Z with `limit: 500` and observed 49.** The test failed, which is the only
reason I looked further.

Asked the venue directly, with an explicit limit of 500 so truncation cannot be the answer:

| league | sports listing `activeEventCount` | events the events endpoint returns | parsed |
|---|---:|---:|---:|
| mlb | 81 | 49 | 49 |
| nfl | 316 | 33 | 33 |
| cfb | 263 | 211 | 211 |

Parsing drops nothing: raw and parsed agree exactly in all three. **`activeEventCount` and "events
the board returns" are different quantities**, and NFL shows it starkly at 316 against 33. So
`board_coverage`'s `shortfall` is not a measure of missing data, and MLB's 32 was never data loss.

**That is the second structural defect in the same guard today.** meridian-7f found the first: its
`expected` comes from a different endpoint on the *same venue*, so when the board empties both
sides go to zero together and `swept_nothing` is false by construction. This is the second: the
two sides are not the same unit, so `shortfall` is a difference between incomparable numbers and
has presumably been non-zero on every league every cycle since it was written.

**Resolved, mostly.** 7d tested eleven candidate parameters on the events endpoint -- `closed`,
`active`, `archived`, `hidden`, `includeClosed`, `status`, `page`, `days`, `horizon`, `offset` --
and none changes the count. `offset=500` returns 0, so nothing sits beyond what the endpoint
gives. All 33 NFL events are active, not closed, not archived, not hidden, so it is not a flag
filter, and every league reports the same section, so it is not that either.

**Not a horizon**, which was the hypothesis worth testing because it would have been repairable.
Forward windows: nfl 14.5 days, cfb 12.6, mlb 3.5, wnba 3.5, setkameua 0.6, setkamecz 0.3. No
fixed window explains those.

**The two numbers do share a unit.** Verified independently of 7d's run: five leagues agree
exactly -- setkameua 168=168, setkamecz 32=32, setkamemd 34=34, setkawoua 6=6, t20icr 2=2 -- and
the three that disagree, MLB, NFL and CFB, are exactly the leagues that schedule furthest ahead.
Consistent with events being listed beyond what the board returns. **Not proven**: what the larger
population is remains open, and 7d is explicit that they could not establish it.

So `shortfall` is deleted and the two fields are renamed `venue_active_events` and
`board_events_returned` so nobody subtracts them again. Both stay, because the exact agreements
are the evidence they share a unit; it is only their difference that was meaningless. In its place
is the one like-for-like comparison available: the same call's raw payload against what parsing
kept.

**The `EVENT_LIMIT` change stays.** It was a fix for a problem I had not established, but the
default of 50 against a board that returns 49 is a margin of one, and it costs nothing.

## 0h. The migration defect is real. The prod anomaly I attached to it was not.

7d fixed five sites in `deploy/aws/merge_history.sh` where a failing database query was read as
"the table does not exist": an existing lookup rebuilt, a present parent skipped, a partial
migration reporting success. `set -e` protects none of them, verified directly here -- a failing
function inside an `if` takes the else branch and execution continues, while `V=$(f)` aborts.

**I then attached a prod anomaly to it that does not belong to it, on a premise that was wrong.**
I read `remap_pulse_decisions` at 0 rows against "a parent holding 19,333". The 19,333 is the
**live** table. The migration's **staged** parent holds 280. I compared the lookup against the
wrong side of the thing being merged.

**And it is not that defect's signature either.** The skip path returns before the CREATE, so it
leaves **no table at all**; an empty table means the CREATE ran and its inner join matched
nothing. 7d dated the run from relation filenodes inside the container, 16:14 to 16:20 on
2026-08-21, sequential and therefore one run, with `remap_pulse_decisions` written at 16:18:46 in
the middle of it. So my date caveat resolved in the direction that would have made it a finding,
and it still is not one.

Confirmed non-circularly: zero duplicate natural keys in the staged range, so nothing was
double-inserted. 7d's first test was the circular one -- re-running the join against live rows the
migration itself created -- and they caught it before sending. **Recorded as explained, not
observed:** nothing logged the join result at run time.

## 0i. The exit pairs are registered behaviour. The defect is one observation priced twice.

**Retracted, mine and 7d's.** They called the 60 exit pairs "one decision written twice". I went
further and said nothing records which price governs. **Both wrong, and mine was checkable in one
query.** Verified here independently:

| reason | rows | live | withdrawn | filled |
|---|---:|---:|---:|---:|
| `ev_stop` | 60 | 50 | 10 | **50** |
| `profit_target` | 60 | **0** | 60 | 0 |

Groups with two live orders: **0**. So `withdrawn_at IS NULL` names the governing price
unanimously, without any tie-break: the stop supersedes the target 60 times out of 60, because the
fill rests the target and `_manage_position` withdraws the incumbent before placing, in the same
cycle. That is registered behaviour with suite coverage, not a defect. A dedupe would have been
strictly worse than doing nothing: it would delete a limit that really rested and really stood
down, and could pick a price up to 9¢ wrong. PULSE is shadow-only, so nothing was ever placed at
either price.

**The real defect is the 7 pairs I noticed and mis-attributed.** Those differ in `created_at`,
13-28 seconds apart, in separate transactions **against one unchanged snapshot**. `_observations`
serves the newest row under a 60-second age window every cycle whether or not it is new, with no
watermark, and the fair value is not a function of the observation -- the ESPN venue clock and the
v4 availability flags are rebuilt from the database each cycle. So on a frozen book the clock
advanced 0.20-0.58 minutes and fair value moved a mean of 5.05¢, max 9.75¢. One stop rested at
0.7600 when the next snapshot's ask was 0.7400.

**Scope beyond those 7:** `decided_at` is the data's time, not the decision's. The gap between
them reaches 59.5 seconds, the configured window. **23.7% of 13,680 hold rows are priced off a
snapshot more than 10 seconds old.** Cadence is not uniform either -- in one hour of one game, one
market got 6,520 snapshots at a 0.2s median gap and another got 26 at 30.0s, so a sub-30-second
cycle re-prices the slow markets repeatedly.

Fix is a per-market floor on `captured_at`. Not made; `test_an_observation_is_evaluated_once` is
`xfail(strict=True)` and XPASSes when the watermark lands. Write-up in
`docs/math/one-observation-twice.md`.

## 0j. The suite was only fast enough, and my own verification command opted out of the fix

**The mechanism is time, not leftover state.** Eleven test modules pin `NOW` at import, which
happens once at collection, then insert snapshots at `NOW - 30s`. The engine's predicate is
`captured_at > now() - 60s`, evaluated at execution. So each module has a budget of elapsed time
before its own fixtures age out of the window it is testing, and whether it passes depends on its
position in the run. Measured budgets: daily_budget 2 tests at +30s, reprice 1 at +20s,
shadow_min_bankroll 1 at +30s, the other eight at 60s or more. Four tests in three files, which is
the "4 before the merge" I saw, reached from the other direction. Bisecting 113 predecessors found
nothing, and that negative is the tell: nothing is being left behind.

Verified independently: with the fix active and `MERIDIAN_TEST_NOW_SHIFT=32`, daily_budget fails
exactly 2 tests, matching its measured +30s budget.

**My "6 after" was a control failing in the flattering direction.** The strict xfail XPASSed in my
run because the market had aged out, so the third cycle wrote no row and the assertion passed.
A test reporting "fixed" when the data merely expired. It is gone, replaced by two real tests.

**And the standing verification command opts out of the fix.** It is `--noconftest`, and the fix
is a conftest fixture, so none of my runs get it. Same file, same machine:

| | result | wall |
|---|---|---:|
| with conftest | 7 passed | 0.84s |
| `--noconftest` | 3 failed, 4 errors | 48.06s |

Fifty-seven times slower, against the shared development database instead of a per-run one, which
maximises exactly the elapsed-time exposure the fix addresses. `--noconftest` is not simply wrong:
with local Docker down it is the only way to run the tests that need no database, and 209 of those
pass right now. But it is a different regime and nobody had written that down, so every "green"
I have reported today was from the regime without the fix.

**As of 14:40Z the operator closed local Docker, so there is no local test database at all.**
Database-backed tests cannot run on the laptop until it is back; `--noconftest` still runs the 209
tests that need no database and they pass. Verification of database-backed work is therefore on
the peer who wrote it plus the prod read, not on a second local run, and any claim resting on it
should say so rather than inherit the word "verified".



`tests/test_pulse_live.py` fails 4 tests before this merge and 6 after, and **every one of them
passes in isolation**. The two new tests pass and xfail exactly as designed when run alone. The
file shares a database across tests and earlier tests leave state behind.

This is not cosmetic. It means a green suite is evidence about an ordering, not about the code,
and it has been true all day: I saw the same shape in `test_recorder.py` this morning and
dismissed it as interference without recording it.

**And I pushed on it.** `pytest ... | tail -3 && git push` takes the pipeline's exit status from
`tail`, which always succeeds, so the push ran on a red suite. I have a standing note about this
exact line and this is the third time. The rule is `pytest ...; rc=$?` or `set -o pipefail`, never
a pipe into `tail` as the gate.

## 0k. The box was never down. I was blind to it for 70 minutes and reasoned my way to the wrong cause.

Unreachable 15:55Z to 17:05Z on both SSH and the dashboard port. It is back on **the same
address**, and nothing was wrong with it.

| check, after recovery | result |
|---|---|
| uptime | **3 weeks 3 days**, boot 2026-08-20 |
| containers running | 29 of 29 |
| newest market row | 17:04Z, and rows exist throughout the outage |
| cricket toss records | 459, latest 17:03Z |

**Nothing stopped. No reboot, so the migration trap never fired, and no data was lost.** The box
recorded normally for the whole seventy minutes; only my path to it was broken.

**My leading hypothesis was wrong and the reasoning behind it looked good.** An established ssh
session died with `Connection reset by peer` and every later connect timed out. I argued that a
host sending a reset was on the network at that instant and then stopped answering, that a pure
address rotation would leave an old session hanging rather than reset it, and that instance
stop-or-restart produces exactly reset-then-timeout. Each step is defensible and the conclusion
was false: uptime says three weeks. A reset can also come from a device in the path, and I had
assigned it to the only endpoint I was thinking about.

**Two things that worked, both by prior design rather than by luck.** The detached paper book
survived my connection dying and completed on the box -- the standing rule that killing a piped
ssh does not kill the container, for once paying off in the useful direction. And the monitor
armed on recovery reported the exact minute without anyone watching.

**And one probe that lied.** My first reachability test used `/dev/tcp` and said my own machine
could not reach a public DNS resolver or github, which would have made this a local network
fault. That syscall
is blocked by the sandbox, so the failure meant nothing; `curl` showed the network was fine. A
probe that cannot succeed says nothing when it fails.

## 0l. The six new MLB strategies select rows and their pairing is printed correctly

Verified end to end on the 15:52Z paper book, which ran on the box while I could not see it:

| strategy | bets | printed as |
|---|---:|---|
| `mlb_winner_away_all` | 1 | complement of `mlb_winner_home_all` |
| `mlb_winner_home_all` | 1 | complement of `mlb_winner_away_all` |
| `mlb_spread_yes_70_100` | 2 | no complement, correctly |

All on one settled game, so every line reads UNDERPOWERED, which is the honest state. What is
confirmed is the wiring: the rules match real market types, the declared pair is annotated, and
the away-favourite arm is **not** annotated as a complement, which is the distinction the test
asserts and the reason both arms can be reported together.

## 0m. Every prod ssh needs keepalives, or a stalled path hangs forever

The network path to the box is intermittently slow since this afternoon's outage. Twice now a
routine check has hung until its own timeout killed it, once at 600 seconds, while the box itself
was fine: uptime unchanged, all containers up, newest market row 17:28:27Z against a wall clock of
17:30:58Z.

Without `ServerAliveInterval`, ssh waits indefinitely on a stalled connection, so an unreachable
moment and a slow moment look identical and both consume the full timeout. Every prod command
should carry:

```
ssh -o ConnectTimeout=15 -o ServerAliveInterval=5 -o ServerAliveCountMax=4 ...
```

That turns an indefinite hang into a failure in about twenty seconds, which is the difference
between knowing the path is bad and waiting ten minutes to learn nothing.

**Current counts, 17:30Z:** MLB 8,781 rows over 62 games. Cricket toss records 474, of which 456
carry a toss time. Table tennis, cricket and MLB all recording, no container down.

## 0n. The PULSE fix is on the box and not running, and WNBA returns Thursday

`meridian-pulse-engine` runs an image built **2026-09-02** and mounts nothing, so it executes the
code it was built with. Checked directly:

| | |
|---|---|
| watermark in the running image | **absent** |
| watermark in the staged checkout | present, `core/pulse/live.py` |
| WNBA games listed | **5, Thursday 2026-09-17** |
| last WNBA tape before that | 2026-08-31 |

So the one-observation-priced-twice defect is fixed on disk and live in the process. On Thursday
PULSE gets its first games in seventeen days and will record decisions using the twelve-day-old
image, which re-prices a snapshot it has already acted on: 23.7% of hold rows were priced off data
more than ten seconds old, and fair value moved up to 9.75¢ on a book that had not changed.

Nothing is placed -- PULSE is shadow-only -- but the decisions it writes are the thing we measure,
so a rebuild after Thursday means the first live WNBA tape in three weeks was recorded by the
known-broken version.

**This is the abstract fleet-rebuild exposure with a date on it.** The rebuild command is in
section 1 and has not been run.

**I considered rebuilding just this one and decided not to, for a reason I had not seen until I
checked.** `meridian-pulse-engine` starts with `alembic upgrade head && python -m core.pulse.live`,
so rebuilding it applies migration `a1c7e35b9d20` and advances the database from
`c2d9a7e51f83`. Eight containers were rebuilt today and can currently restart -- api, kalshi,
mlb, cricket, tt, cricket-espn and both scalp engines -- and every one of them was built **before**
that migration was committed. Advancing the database to fix PULSE would take those eight from
restartable to stranded.

So a single-service fix here is not free, and doing the fleet one service at a time is the same
action the permission classifier declined in bulk. **The fleet rebuild is the right instrument and
it is the operator's to run.** If it has not run by Wednesday I will rebuild PULSE alone and accept
the eight, because a compromised Thursday tape costs more than a restart capability nothing has
needed in three weeks -- but that is a worse outcome than one paste tonight.

## 0o. "Staged on prod" is not "deployed". No container mounts the checkout.

Checked all 28 services: **not one of them mounts `/app/core`.** Every long-running container runs
the code baked into its image, so `git checkout origin/main -- <files>` on the box, which I have
done after every merge today and reported as "staged", changes nothing for any of them.

It is not useless. It is exactly how two other paths get current code, and both matter:

* **cron shell scripts run from the host filesystem**, so `scripts/nightly_scan.sh` and
  `prod_weekend_read.sh` do track git. Verified: the new paper-book block is on the box.
* **one-off `docker run` containers that pass `-v` explicitly** -- the nightly scan and the paper
  book mount `core/` and `strategies/` and pipe the script over stdin, which is why that path was
  built this way in the first place.

Verified by asking the running images, not by reading the checkout:

| today's fix | live now? | why |
|---|---|---|
| cricket ESPN upsert | **yes** | that container was rebuilt at 10:55Z |
| cricket and TT cadence | **yes** | rebuilt 11:10Z |
| MLB event limit | **yes** | rebuilt 10:28Z |
| nightly push, strategy line, paper book in the nightly | **yes** | host script, cron reads from disk |
| scan fixes: SQL bind, atomic JSON, partition floor | **yes** | mounted into the one-off container |
| six MLB strategy registrations | **yes** | same mount |
| `service_heartbeats.markets_seen` and its writer | **no** | `grep` in the running recorder returns 0 |
| `board_coverage` rename and limit logging | **no** | same, returns 0 |
| PULSE observation watermark | **no** | image built 2026-09-02 |

**So the rebuild is not housekeeping.** Three of today's fixes are inert until it runs, including
the PULSE watermark, which has a Thursday deadline, and `markets_seen`, which is the only
instrument that would distinguish an empty venue board from a quiet one the next time this
morning's two-hour gap happens.

**And I should stop saying "staged" as if it means deployed.** Every report I have written today
used that word after a merge. For the six rows above marked yes it happened to be true by another
route; for the three marked no it was not.

## 0p. Kalshi: I said CFB was testable today. It is not, and using it would have manufactured edge.

**Retracted.** I reported 525 settled college-football totals over 81 games as "a testable
population right now, no waiting". meridian-7d ran the coverage table I asked for before building
anything, and the population is selected in the direction of the answer.

**Only 6.1% of CFB markets ever settle in our tape, and the 6.1% is not random.** Verified here by
a second route, on the strike ladder within each game:

| outcome in our tape | markets | mean strike | mean rank within its game |
|---|---:|---:|---:|
| never settled | 3,742 | 55.8 | 0.536 |
| settled **yes** | 493 | 45.7 | **0.222** |
| settled **no** | 32 | 59.6 | 0.603 |

93.9% of settlements are YES, and they sit in the bottom quarter of each game's ladder.

**The mechanism is in the contract text.** `yes_sub_title` reads "Over 29.5 points scored", so an
Over market is **determined the moment the running total passes the strike, mid-game**, while a NO
cannot be determined before the final whistle. Our recorder stops before the whistle, so we capture
the first kind and miss the second: settlement seen a median 26.1 minutes before our last row for
that game, against 0.0 minutes for the 32 NO settlements, caught only on a final poll.

**So "settled in our tape" MEANS "the over hit early".** Price those at a pre-game close, settle
from `result`, and the number that comes out is not edge, it is the selection. Same shape as the
withdrawn-order arm that always flattered, which this project has already been caught by once.

**And the pre-game close is not definable for CFB regardless.** Of 492 CFB rows in `kalshi_games`,
zero carry a game start time, an ESPN id, or a Polymarket slug. `close_time` is not a boundary
either -- it is rewritten at settlement, so one ladder shows strikes 30/33/36 carrying their
settlement instant while strike 39 still holds the original placeholder.

**NFL is the clean population, and my guess about the sweep window was right in mechanism and
backwards in consequence.** The recorder stops **at kickoff** -- last row 16:59:28 for a 17:00
kickoff -- which is not a gap, it is exactly the boundary a pre-game book needs. 648 markets on 14
games, every one with a pre-game two-sided quote, 533 quotes each on a uniform poll, last quote a
median **32 seconds** before kickoff, and 547 inside the 0.10-0.90 band at spreads of 1.0-1.5¢.
30 of 32 NFL games carry both a start time and an ESPN id, which CFB has neither of.

What NFL lacks is Kalshi's `result` -- but for a total or a spread that is a function of the final
score, which the ESPN ids supply. **Deriving the outcome from the score removes the selection bias
and can be validated against the 610 CFB results**, which settling from `result` cannot.

**No verdict either way today, and the numbers moved twice.**

*My pessimism was wrong.* I said the effective sample was "at most 14 and realistically fewer".
7d measured it: a totals ladder is ~15 deterministic step functions of one scalar, a spread ladder
~22 of another, and on 114 CFB finals the two scalars correlate at 0.524, worth about 1.31
independent draws per game. So fourteen games behave like 14 clusters for totals alone and ~18
with spreads -- not 547, and **not fewer than 14**, because "fewer" would require the games to be
correlated with each other and they are not. (That rho is a CFB number on a blowout-heavy league;
NFL needs its own once there are finals.)

*The real population is smaller, for a reason on our side.* Only **9 of 15** NFL games reached
state `post` in our ESPN recorder, so only 9 have a final score to derive a settlement from.
Verified here independently: CFB 105 of 186, **56.5%**; NFL 9 of 15, **60.0%**. Deriving from a
game stuck at `in` would be a bias and not a gap -- a truncated game has a lower total, so Over
markets would settle NO when the real total cleared the strike, which is the CFB capture bias from
the opposite side and flattering in the same direction.

So **G = 9**, and what decides when we reach 25 is our own ESPN recorder, not Kalshi.

**The frame validated with no join at all.** Within a settled totals ladder every strike below the
final must be yes and every above must be no, checkable from Kalshi alone. Of 81 games with
settled totals, 2 carry both a yes and a no; both are monotone with **zero violations** and a mean
bracket of 3.00 points, exactly the strike spacing. Two games is not a small sample for a binary
structural fact -- an inverted frame violates on both.

**And a fourth fix is waiting on the rebuild.** `core/feeds/espn_cfb_recorder.py` in main already
keeps polling a departed game until `post` is observed, with a bounded three-hour give-up, written
against this exact measurement. The running image is from 2026-09-06 and does not contain it:
`grep` returns 0 inside the container and 4 in the checkout. **So the thing now gating the second
venue is fixed on disk and not running.**

**Two corrections to my brief.** The fee cannot be read from the tape: `kalshi_events` and
`kalshi_event_snapshots` are both empty, so the columns exist and carry nothing. The substitution
is to keep the quadratic shape, keep 0.07 marked unverified since it was never venue-declared in
anything we read, and make the multiplier a per-series input. And the frame question comes back
clean and better than the other venue's: `yes_sub_title` names the side on every contract with
`strike_type` agreeing, 4,792 of 4,792 on CFB totals and 266 of 266 on NFL, zero blanks anywhere.

**One thing worth keeping beyond Kalshi:** the local database mirror holds 98 settled rows against
production's 13,097, so this same analysis run locally concludes the population is empty.

## 1. What I need from you (everything else I now run myself)

**1. Rebuild the fleet. This is the only urgent item and it is not a strategy question.**

Twenty of the thirty containers run on images built before 2026-09-14 00:51, when the
Kalshi migration `c2d9a7e51f83` was added. The database is now stamped at that revision.
Those images do not contain it, so their start-up `alembic upgrade head` cannot resolve
where the database already is and the container dies. They are running only because they
started before the migration was applied and have not been restarted since.

Nothing is down right now. A reboot, an out-of-memory kill, or any single `docker restart`
takes that container down permanently until it is rebuilt, and a reboot takes all twenty at
once. Credit to meridian-7f for spotting that my two failing recorders were the symptom and
not the cause.

I rebuilt the four I touched today. A fleet-wide rebuild was refused by the permission
classifier, which I think is the right line for an action this size, so it is yours:

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$(cat ~/.meridian-server) 'cd /opt/meridian && sudo docker compose up -d --build && for f in nfl cfb-live espn-live quote pulse scalp mlb cricket cricket-espn; do sudo docker compose -f docker-compose.yml -f docker-compose.$f.yml up -d --build; done; sudo docker ps --format "{{.Names}} {{.Status}}" | wc -l'
```

Expect 30. Best run now or any time the venue board is empty.

**The rebuild is the fix, not the risk.** I wrote earlier that a partial rebuild is worse than
none; meridian-7f corrected the mechanism and they are right. The strand already exists. Every
container built before 2026-09-14 00:51 has been unable to restart since this morning, and a
partial rebuild does not newly strand anything. What it does is leave a subset on stale images
that report perfectly healthy until the next restart.

It also now carries a schema migration (`a1c7e35b9d20`, adding
`service_heartbeats.markets_seen`). The one genuinely new exposure is a container rebuilt from a
ref *between* the two migrations, which cannot arise if everything is rebuilt from one ref in
one pass. The command above does that.

**Verify afterwards, because the failure is silent.** Every container should be on the same
newly built image; any whose image ID differs is still stranded.

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$(cat ~/.meridian-server) 'for n in $(sudo docker ps --format "{{.Names}}" | grep "^meridian-" | grep -v postgres); do sudo docker image inspect $(sudo docker inspect $n --format "{{.Config.Image}}") --format "{{.Created}}" | cut -c1-10; done | sort | uniq -c | sort -rn'
```

A single line dated today is a complete rebuild. Today it prints nine dates, 8 on 2026-09-14 and
21 spread over 2026-08-21 to 2026-09-12.

I first wrote this check against image **IDs**, expecting one shared ID. Every service builds its
own tagged image, so the IDs always differ and the check could not have distinguished a finished
rebuild from an untouched fleet. Build **date** is the quantity that varies with the thing being
tested.

**2. Is the Kalshi account a direct member, or an FCM/broker customer?** This gates every
making strategy on Kalshi and I cannot find it out from the API. One sentence.

**3.** One SQL backfill the permission classifier blocks (163 cricket/TT rows with a NULL game
   id, pregame closes a re-sweep cannot recreate). Optional; it recovers one sweep.

```bash
ssh -i ~/.ssh/meridian-aws.pem ubuntu@$(cat ~/.meridian-server) 'sudo docker exec -i meridian-postgres psql -U meridian -d meridian' <<'SQL'
UPDATE market_snapshots SET game_id = coalesce(event_id, event_slug)
 WHERE game_id IS NULL AND (event_id IS NOT NULL OR event_slug IS NOT NULL)
   AND market_slug LIKE ANY (ARRAY['aec-cplcr-%','aec-t20icr-%','aec-t20iwcr-%','aec-odicr-%','aec-county-%','aec-setkameua-%','aec-setkamemd-%','aec-setkamecz-%','aec-setkawoua-%']);
SQL
```

## 1b. Fixed today without asking you

| defect | effect | state |
|---|---|---|
| scan crashed writing JSON (numpy int64) | no cell table, truncated artifact with a fresh mtime | fixed, atomic write |
| nightly push read the same on a crash as on a quiet night | you were told "0 cells cleared the bar" by a run that scored no cells | fixed, 6 tests |
| `:t::regclass` never bound a parameter, 4 sites | the partition floor had never once executed | fixed, suite-wide sweep added |
| settle cache read a truncated file as empty, then overwrote it | would have destroyed ~20,000 cached settlements | fixed, quarantines instead |
| MLB recorded 49 of 81 listed events | 40% of your daily-volume league missing | limit raised, awaiting tonight's slate |
| board coverage `truncated` flag silent at 49 vs 50 | the guard for this exact default read false | limit now logged beside observed |
| cricket cadence env never reached the containers | I recorded a 5-min cadence in this file that the containers did not have; they were sleeping the 3600s code default | containers recreated; cadence now 60s near start |
| cricket ESPN recorder was not running at all | no toss time exists for any match, and toss times cannot be backfilled | started 10:48Z, 24 matches and 16 toss times in the first minutes |
| that recorder failed a whole cycle on a duplicate write | one match seen twice in one instant discarded every match in that cycle | upsert, real-database test |
| paper book died writing its JSON on a datetime | no paper book for the day, two hours after the scan was fixed for the same thing | one shared writer in core/jsonio.py |

Scan runtime went from 1h56m to **9 minutes** once the floor actually bound and the
settlement cache was warm.

## 2. What is running (AWS, no laptop)

| container | records | league |
|---|---|---|
| cfb-espn-recorder / nfl-espn-recorder | plays, win prob, game state, live DK line | CFB, NFL |
| recorder / cfb-recorder / nfl-recorder | venue boards (every rung, every market) | WNBA, CFB, NFL |
| live-recorder / cfb-live-recorder / nfl-live-recorder | in-game book at 0.2–1s | WNBA, CFB, NFL |
| nfl-odds-recorder / cfb-odds-recorder | DraftKings pregame line path, 7 days ahead | NFL, CFB |
| kalshi-recorder | Kalshi boards, 72h pregame window | CFB, NFL (WNBA when listed) |
| mlb-recorder | venue boards, event limit 500 since 10:28Z | **MLB — 8,781 rows over 62 games at 17:30Z** |
| cron Sun 15:50Z / Mon 10:20Z | the pre-registered read, to /opt/meridian/artifacts/reads | — |
| cron daily 04:40Z | nightly strategy scan, full table to artifacts/reads, terse push to ntfy | all |
| scalp-nfl / scalp-cfb | paper taker loop, ytg40 trigger, tp 5% stop 10% | NFL, CFB |
| cricket-recorder / tt-recorder | venue boards, event limit 500; cricket 60s within 8h of start, TT 300s | cricket, table tennis |
| cricket-espn-recorder | ESPN toss time, innings state, result | cricket |

## 2b. The paper book's only positive line is the away-team confound again

Read of 2026-09-14T1107Z, 24 strategies, up from 7. **One line excludes zero. Its
home-referenced twin does not carry the sign.**

| arm | what it buys | mean bet | 95% CI | n | G |
|---|---|---:|---|---:|---:|
| `wnba_spread_yes_80_100` | away team, spread mid ≥ 0.80 | **+5.78¢** | [+2.96, +8.60] | 101 | 40 |
| `wnba_spread_no_00_20` | home team, same price band | −2.05¢ | [−8.27, +4.16] | 150 | 53 |

The registry names the pairing itself -- `wnba_spread_no_00_20` is commented "the home-favourite
twin of yes_80_100" -- so this is not my inference about which two lines mirror each other.

Backing a heavy favourite makes 5.78¢ when it is the away team and loses 2.05¢ when it is the
home team. **That is side-dependence, not a favourite effect**, and it is the third time this
confound has produced an "excludes 0" headline.

**What I have NOT established.** A difference of +7.83¢ with an independence-assumed SE of 3.48
gives z = 2.25, but independence is the wrong assumption: both arms are drawn from the same WNBA
games on opposite sides, so they are negatively correlated and the true SE is larger. **That z is
an upper bound, not an estimate.** The honest test is the difference computed on the per-bet rows
with game clustering, which the summary table cannot give me and which I will not fake from CI
half-widths.

**And the gate that should have caught this cannot fire.** The paper book's own footer records
that the twin-contradiction clause requires the twin to be significantly negative, which on this
tape is an 11.6¢ swing from where it sits -- it passed on every achievable outcome and tested
nothing. So "POSITIVE, excludes 0" on the away arm is printed without the twin ever having been
able to object. WNBA's season also ended 08-31, so nothing here is actionable either way.

## 3. Strategies and paper P&L (nothing has ever been placed)

| strategy | status | paper result |
|---|---|---|
| QUOTE shadow maker (3 leagues) | measured negative with power | −2.2% ROI in-game [−3.8, −0.6], −4.1% pregame; 169k fills, 149 games |
| PULSE (WNBA in-game model loop) | paused for lack of games since 08-31; resumes on playoffs | 57 fills, below its 100-fill floor; round trips +8.5% in the unregistered view |
| CFB spread: buy NO on 20–30¢ rungs | paper line, read 09-19 | **+$15.73 on $220 staked**, 289 bets, 107 games: +5.44¢ per $1 [−1.46, +12.35], spans 0 |
| WNBA spread: buy favourites 80–100¢ | paper line, read on playoffs | +$5.84 on $93, 101 bets, 40 games: +5.78¢ [+2.96, +8.60] excludes 0 — BUT its home-side twin is −2.05¢ [−8.27, +4.16]: an away-listing artifact until the playoffs say otherwise |
| WNBA totals: buy UNDER every rung | paper line, read on playoffs | +$43.75 on $414, 792 bets, 88 games: +5.52¢ [−2.10, +13.15], spans 0; two of six weeks carried it |
| CFB: home side every rung ("home shift") | paper line, read 09-19 | +$47.44 on $1,571, 2,503 bets, 117 games: +1.90¢ [−3.83, +7.62], spans 0 |
| NFL: same two rules | paper line, 2 games | −$17.91, UNDERPOWERED |
| MLB: under/over, favourite/dog, 20–30¢ NO | **recorder live**: 5,181 rows across 62 games as of 2026-09-14 08:00Z, accruing on its own rather than by hand | first calibration at 100 settled games |
| **In-game: buy the near-certain side at 90–99¢ and hold to settlement** (the fee collapses to 0.3% round trip there, and holding pays entry only) | **measured, and the idea fails for a reason opposite to the scalp's.** CFB, 59 games. Crossing + fee total only **0.45–2.26¢** across all eight cells against the scalp's 8–11¢, so the fee thesis is confirmed on the cost side — but calibration is then the whole term and runs **−18.19 to +2.21¢**. Not dead from cost; unmeasurable from outcome variance. Mid entry moves cells by 0.4–1.8¢, so a resting maker entry cannot rescue any of them. No cell's win rate beats its break-even by more than 1.7pp | the one cell excluding zero, +1.68¢ [+1.41, +1.96], is **degenerate — 7 of 7 games won, so the interval measures the band's price width, not outcome risk. On the binomial it is 7/7 with a 95% lower bound of 65.2% against a 98.3% break-even.** Do not quote it |
| **CFB / NFL spreads: buy NO (home) on rungs whose YES mid is 50–60¢**, twin = buy YES (away) at 40–50¢ | registered 09-13 20:05Z, **CORRECTED 22:30Z by the audit** (`docs/math/preregistration_2026-09-19.md`). The −11.62¢ measurement itself REPRODUCES: independent SQL returns the same 227 rungs and 104 games, the venue settled 227 of 227, and on the 65 rungs where an ESPN final also exists the two agree 65/65 under the stated frame (frame-error rate ≤4.6%). The objection is power and multiplicity, not correctness. This line is the exact complement of the −11.62¢ away cell that motivated it — same 227 rows, opposite side — so its in-sample expectation is +11.62 − 4.17 (round-trip cost) = **+7.45¢, 95% CI [−2.67, +17.57], SPANS ZERO**, and it inherits the source's standard error. It cannot be stronger than the cell that generated it. The source cell was one of ≥10 statistics; at 20 looks the expected number of false "excludes zero" is exactly 1.00. **Interim observation on 09-19, no verdict**; first decision at G ≥ 195, which is 5 Saturdays uncorrected and 12 corrected | +7.45¢ [−2.67, +17.57] in-sample |
| **NFL spreads: the same pair, read Sunday 09-21** | the strongest test on the board and the one I mis-dated: NFL week 3 is a SUNDAY, and these lines carry **no prior** (the cell was never found in NFL tape), so their family is 2–4 names, not 24, and they need almost no correction | no in-sample number by construction |
| CFB / NFL totals: buy UNDER every rung; buy OVER every rung (mirror) | registered 09-13 18:30Z; the two-Saturday back-read is running, labelled a back-read | — |
| **Cricket and table tennis: tape started 2026-09-13 22:23Z** | by hand, ~5 sweeps each as of 23:45Z: table tennis **1,125 rows across 351 matches**, cricket 61 rows across 16. The table-tennis match count more than doubled once the event limit was fixed, which is the truncation showing up in the tape rather than only in a config file. Expected-vs-observed matched per competition on every one, which is the check that makes an empty board distinguishable from a wrong slug | no strategy read yet; six lines registered awaiting tape |
| MLB first-five totals under/over; first-five spread NO 20–30¢ | registered 09-13 18:30Z, no tape | — |
| **NFL/CFB in-game momentum scalp** (buy the offence at the opponent's 40 / red zone / after a 2¢ move; take profit 2–10%, stop 5–20%; taker and maker exits) | **measured negative with power on CFB** (60 games, 27 cells, G 37–42): every cell −7.2 to −11.0¢ per $1 ticket, every interval below zero, home and away both negative. Mid drift after the trigger ≈ 0 (−0.6 to +0.7¢): the loss is half-spreads (3.8–5.7¢) plus two fees (4.1–5.4¢). Maker exit within 0.3¢ of taker. NFL: no finals yet, rerun tonight. Script `cfb/run_momentum_scalp.py`; the live paper loop still deploys so the same number accrues on the dashboard | best cell T2 red zone, TP 10 / stop 5: −7.22¢ [−9.52, −4.93] |
| DraftKings line move → Polymarket lag, take the DK-implied rung at the ask | measured on CFB 09-12 (23 games, 25 bets): venue lags DK by a median 30 min (n 19), but taking the rung is −9.2¢/$1 [−30.7, +12.3] at the first sweep, −13.0 at +1h, −24.5 [−46.7, −2.4] at +3h, all UNDERPOWERED (G 14–15); 5 of 24 moves already at price. Frame audit requested; NFL settles tonight; read 09-19 | — |
| Kalshi vs Polymarket same instant (CFB 09-12, 45 matched games, 66k pairs) | measured: median gap 0.25–0.5¢, <1% of instants beyond 3¢, 49 after-fee dutch instants in 66k (0.07%); who-is-stale underpowered (G 6–7). No pregame cross-venue trade. The 20–30¢ NO rung on Kalshi: −2.33¢/$1 [−13.31, +8.66], 36 games, loses about its fee | — |

**Five of the 29 registered names are arithmetic complements of another five**
(`cfb_total_under_all`/`over_all` and the nfl, mlb, mlb_f5 and cricket pairs):
they select identical rows with opposite sides, so their P&Ls sum to minus the
round-trip cost, a constant. "Under beat over" on such a pair is **guaranteed**
whenever under clears −½ round-trip, and is not evidence of anything. Read one
of each pair. There are 24 distinct statistics on the table, not 29.

"Measured negative with power" means: bet it and you lose, on the evidence. The
code stays; the bet does not get money. All lines above are scored every Monday
by `cfb/run_paper_book.py` (venue-settled, taker fee charged) and shown on the
dashboard's SCOREBOARD page once that page lands (being built). First run 2026-09-13 17:45Z: `docs/paper_book_2026-09-13.txt`, also on the box in artifacts/reads.

**The decision rule lost a clause tonight, and only a projection catches that
kind.** The registered rule was "G ≥ 25 AND excludes 0 AND the home/away twin
does not contradict". Projected onto the outcomes this design can produce, the
third clause passes on essentially all of them: for the twin to contradict the
away cell it would have to sit below −9.62¢, an 11.59¢ swing from where it
measures. A clause that cannot fire reads as corroboration while testing
nothing, and makes the rule look like three hurdles when it has two. **The twin
is now reported beside the cell and never gated on** — in the rule, in the paper
book's own footer, and in the pre-registration.

**A hand-run sweep must mount the checkout, or it silently records nothing.**
My first cricket sweep reported `markets_seen: 0, errors: 0` and exited 0 — a
clean success. The container runs the api IMAGE, built 09-05, which has no
`venue_leagues`, so it asked the venue for a league called "cricket"; that is
our internal name, not a venue slug, and **an unknown league returns 200 with an
empty list rather than a 404**. The tell was the duration: 0.03s against the
real sweep's 5.5s. Mounting `/opt/meridian/core` and `/opt/meridian/strategies`
fixes it, and the expected-vs-observed coverage line then proves the board was
actually read. MLB is unaffected — "mlb" happens to be the venue's own slug too.

**Cricket and table-tennis rows had NO game id, which is the column the paper
book joins on.** Found by counting distinct join keys per league: MLB 53 across
1,551 rows, cricket and TT **0** across 163. Cause (`core/polymarket/schemas.py`):
the venue sends `gameId` on US team sports and not on these, so it defaulted to
None and was written through. FIXED and merged: the key now falls back
`gameId → event.id → event.slug`, both branches counted on the cycle line so a
fallback becoming the normal path is visible, and an event with no identifier at
all writes NULL loudly rather than getting a manufactured id. Without this, all
six cricket/TT lines would have printed "no markets on tape" forever — the
Kalshi-NFL shape, a third time.

**Verified on real rows after the fix, not only in tests:** cricket 30 rows /
15 distinct ids / 15 still NULL, table tennis 299 / 151 / 148 — the NULLs are
exactly the 163 pre-fix rows and every row written since carries an id. That is
the fix proven at the level it acts on rather than at the level it was written.

**Standing check this earned:** for any column two tables join on, count its
distinct non-NULL values per league before trusting a report that reads off the
join. Three leagues have now been caught this way and none by being told.

**★ Table tennis is the only market on this venue where a strategy can be
READ quickly, and that is a bigger lever than any edge found so far.** Measured
against the venue at 22:40Z: the four Setka Cup competitions list **301 events
inside the next ~18 hours** (setkameua 200, setkamecz 48, setkamemd 38,
setkawoua 15). Every other family is volume-starved by comparison:

| league | games available | G = 100 reached in |
|---|---|---|
| table tennis | ~300 / day | ~8 hours |
| MLB | ~15 / day | ~1 week |
| CFB | ~45 / Saturday | ~3 weeks |
| WNBA (in season) | ~6 / day | ~2 weeks |
| NFL | ~16 / week | ~1.5 months |

**CORRECTED 23:10Z, before it travelled far** (`docs/math/tabletennis-preregistration.md`).
My "powered by Tuesday" was wrong: the per-bet standard deviation is the OUTCOME's,
√(p(1−p)) ≈ 50¢, not the spread's, and that governs. So ~300 matches detects an effect of
**6.47¢**, while the hurdle for a position held to settlement is **2.00–2.50¢**. Detecting an
edge that merely clears the hurdle needs n ≈ 2,000–2,600, i.e. **13–17 days**, and is
UNREACHABLE if the same player pool recurs across days at ρ ≥ 0.15.

| honest claim | |
|---|---|
| rules out LARGE edges in days | yes, and nothing else on the board does |
| establishes a hurdle-sized edge quickly | no |

One correction in the other direction: the fee is charged **once** on a position held to
settlement, not on entry and exit, so that hurdle is half what I had been assuming. Two fees
apply only to a round trip (the scalp and the momentum studies were charged correctly).

★ **The deepest point, and it constrains every result this family can produce:** a
favourite-longshot edge exists only if the market misprices particular PLAYERS. If it does,
the player correlation ρ is large and the effective sample saturates at P/(2ρ) — a constant,
so more matches buy nothing. If ρ ≈ 0 there is no player-linked edge to find. **You cannot
have a large player-linked edge and a small design effect; a result showing both is a defect,
not alpha.** Hypotheses clustered on TIME rather than player (the staleness cut) escape this
and are therefore ranked above the favourite cut.

★ **The trap that outranks the clustering: there is no independent settlement source.** The
CFB decomposition survived because ESPN agreed with the venue 65/65 on the frame. Here there
is no second source, so a frame error is unfalsifiable from inside and **would present as a
large, stable, beautiful edge** — exactly how a 20¢ phantom was manufactured on Kalshi once.
Registered gate: realized YES rate ≈ mean YES price, and favourites must win MORE than half;
a flipped frame shows them winning less. Fails → halt and re-derive, never report.

Measured from the venue's own slugs: 115 players, 156 matches, mean 2.7 appearances per
player per day, max 5, and **zero players cross competitions** — so within a day the design
effect is only ~1.3. Whether the pool recurs ACROSS days is the one measurement that decides
whether this family can ever answer anything, and it cannot be made from one day of tape.

**RESOLVED, and it was a defect in the thing about to be deployed.** `MERIDIAN_EVENT_LIMIT`
defaults to 50 PER COMPETITION, and setkameua alone lists 237 — so the recorder was taking 50
of them. Measured on the box: limit 50 → 151 markets, limit 500 → **336 with expected ==
observed on all four competitions**. The overlays now set it explicitly. Without this the
table-tennis container would have deployed recording a fifth of the league it exists for, and
the only symptom would have been a league that looked small. The coverage line is what makes
it visible; the limit is what makes it right.

**The coverage check itself was then corrected, and my hypothesis about it was wrong.**
I guessed its MLB warning (43 observed against 75 expected) was a false alarm caused by
live games being counted on one side only, and proposed subtracting them. Refuted by one
case: setkawoua listed 1 event, returned 1, and that event was LIVE — liveness appears on
both sides and cancels. My fix would have removed from one side a quantity present in both,
left MLB red at 43-vs-64, and made the next reader conclude the gap was real. The true cause
is that the two endpoints count different populations by a different amount per league, and
`missing` was therefore true on every long-game league most of the day. It is now reported
as three numbers with no verdict, keeping three booleans that can only ever mean a defect:
`not_swept`, `swept_nothing` (the wrong-slug case — an unknown competition returns 200 with
an empty list, never a 404) and `truncated` (observed equals the limit exactly, which is what
caught the 50). **Why the venue counts 32 more than it returns is still open and named
rather than guessed.** One thing now excluded: I probed the events endpoint with a horizon
out to 09-30 and it returns the same 42 events spanning five days, so it is not a date window.

This does NOT say there is an edge there — the discovery found 1–2¢ spreads and
a median 27k shares resting, i.e. a tight, liquid, well-attended book, and the
0.06·p(1−p) fee is 6% of a 50¢ ticket against a 1–2¢ spread, so taking is
expensive. What it says is that **a table-tennis question gets ANSWERED in two
days where a football question takes the rest of the season**, and every read
this project is waiting on is waiting on games. The registered CFB lines need
5–12 Saturdays; the same statistical power exists in TT by Tuesday. It is the
first structural route to the operator's number that is not "wait for more
football". Requires the recorder to actually run.

★ **FRAME VERIFIED END TO END — BUT MY FIRST CLAIM OF IT WAS ONE LINK SHORT,
AND THE AUDIT CAUGHT THAT.** The chain that has to hold is:

    bestBidQuote  --[A]-->  marketSides[0] (YES)  --[B]-->  /settlement

I verified B and announced the frame was correct. **Every price we record comes
from `bestBidQuote`, and A was assumed.** It mattered: if `bestBidQuote` were the
NO book, `p_fav = max(m, 1−m)` is unchanged in VALUE (it is symmetric, so nothing
would look wrong) but WHICH player we call the favourite flips, and the measured
favourite win rate becomes 1 − 0.615 = 0.385. **Observed was 0.476, sitting
between the two** — the exact signature, invisible to the check I had run.

Both links are now measured:

| link | check | result |
|---|---|---|
| A | `bestBidQuote.value` vs `marketSides[0].price` on live markets | **identical to the cent, 10 of 10** (and `bestAskQuote` == `marketSides[1].price`) |
| B | resolved `marketSides[0].price` vs `/settlement` | **30 of 30 agree, 0 disagree** |
| A+B together | calibration slope of settled outcome on recorded price | **+0.899**, positive as a point estimate |

**So the frame is sound and inversion is ruled out by direct field identity, not
by inference.** It also dissolves an apparent contradiction in our own notes:
`marketSides[]` is not two books, it is the two sides of ONE (YES) book — side0's
price is the YES BID and side1's is the YES ASK, which is why side1 carries the
NO team's name while holding a YES price. Both prior notes were right about
different things.

**`cfb/run_tt_frame_lookup.py`.** Secondary: `outcomes[]` order disagreed with
`marketSides[]` on 3 of 30, so anything reading outcomes would be wrong ~10% of
the time. We read sides.

### What is left is a mispricing question, and it is not yet readable

Calibration slope, n=35: **+0.8990 (se 0.5813), 95% [−0.2404, +2.0384]**, price
sd 0.1431 over a 0.195–0.795 range, intercept +0.0866, realized rate 0.5714
against a mean price of 0.5393. Positive and near +1 as a point estimate, and it
**spans zero** — prices are not yet shown to carry information at this n, so
nothing here is readable as an edge in either direction. The slope reaches a 1.5%
wrong-call rate at n=61; we have 35. **No table-tennis edge number until then.**

### RETIRED, not superseded: "favourites underperform" was never a trend

The YES-frame gap was **−2.9¢ at n=21 and +3.2¢ at n=35**. The 21 are inside the
35, so **the 14 new matches averaged +12.35¢** — two adjacent subsamples of one
process differing by 15.3¢. The standard error of that mean is 10.9¢ at n=21 and
8.5¢ at n=35, **both larger than either observed gap**, so neither reading was
ever readable. A real −13.8¢ effect does not flip sign on the next fourteen
draws. The story is retired rather than carried forward as a trend; it was the
first draw from a wide distribution.

**The slope also rejects inversion on its own, independently of the field check:**

| hypothesis | z | p | |
|---|---:|---:|---|
| inverted (slope = −1) | +3.267 | 0.0011 | **REJECTED** |
| prices uninformative (slope = 0) | +1.547 | 0.122 | not rejected |
| perfect calibration (slope = +1) | −0.174 | 0.862 | not rejected |

Two routes sharing no code, same answer. That is corroboration rather than
repetition, which most of tonight's agreements were not. Also confirmed across
the whole sample rather than the 30: `side0.long == true` on all 6,560 rows.

**So the reason no table-tennis number is readable has CHANGED**: not "the frame
is under suspicion", which is settled, but "the prices have not yet been shown to
carry information at all". Next milestone **n = 56** gets the slope interval off
zero, about 8.6 hours of recording.

### The original shortfall, for the record

**Table-tennis favourites underperformed their price early on.**
`cfb/run_tt_frame_lookup.py`. A RESOLVED market states its own outcome — its
`marketSides[]` prices become 1 and 0 — so the settlement label can be checked
against a DIFFERENT field written by a different part of the venue. On every
settled table-tennis match: **30 compared, 30 agree, 0 disagree.** Settlement
follows `marketSides[0]`, which is what we record as the YES price. **The frame
is not inverted**, so the shortfall below is either noise at n=21 or genuine
overpricing of favourites — the calibration slope separates those, and no halt
is required. (Secondary: `outcomes[]` order disagreed with `marketSides[]` on
3 of 30, confirming the known trap; we read sides, never outcomes.)

**This replaced a 61-match statistical gate with a lookup, and that was the
researcher's correction to their own design:** a frame error is a global,
code-level mismatch between the price field and the settlement field, so one
piece of ground truth settles what 61 matches settle only probabilistically. The
registered gate could not have separated inversion from mispricing at any n,
because both predict the same thing.

### The shortfall that prompted it, now a mispricing question rather than a frame one

**Table-tennis favourites are underperforming their price.** Measured 00:45Z on the 21 settled matches with a
pregame close (`cfb/run_tt_frame_gate.py`):

| arm | value | direction |
|---|---|---|
| mean FAVOURITE price | 0.6145 | — |
| **arm B, mean(y_f − p_f)** — the one to watch | **−0.1383** | **wrong side of zero** |
| arm A, favourite win rate | 0.4762 | below 0.5, the flipped-frame signature |
| YES is favourite | 7 of 14 won, mean p_f 0.621 | 50.0% |
| NO is favourite | 3 of 7 won, mean p_f 0.602 | 42.9% |

**n needed 61 for a 5% wrong-call rate, 122 for 1%. We have 21**, so this is NOT
a verdict — the 17-match version carried a 19.3% wrong-call probability. But the
sign is the one the pre-registration says to halt on, and the registered response
to a failing gate is **halt and re-derive the frame, never report an edge**. No
table-tennis edge number may be computed until this resolves, which is ~9 hours of
recording at the listed rate. Watch arm B, not arm A: subtracting p_f removes
Var(p_f) so it dominates for free, and the unoriented YES-frame version has zero
power by construction when the venue assigns YES without regard to strength.

**Corrections to my own table-tennis numbers, measured:** the spread is **2.59¢
mean / 3.00¢ median**, not the 1–2¢ the discovery reported, so the hurdle is
**2.72–2.80¢** rather than 2.00–2.50 and every "days to detect" figure was ~12%
optimistic. And a trap that nearly produced a fabricated headline in the other
direction: **~92% of listed Setka markets have not started**, so an unfiltered
"last quote before kickoff" is just the newest sweep hours ahead of a kickoff that
has not happened — that gives median staleness 11 hours and a 50¢ median spread,
both artifacts. Filtered to started matches the same data gives 8.2 minutes and
3.0¢. Every pregame-close query on this family needs `ko < now()`.

**The sweep gap costs nothing measurable**, now from data: median close 8.2 min
before start, no mass beyond 120 min so capture ≈ 1, and regressing |p−0.5| on
minutes-before gives slope +0.00007/min (r = +0.006). Honest limit: n=27 bounds
|r| only below ~0.39, so that is "no detectable attenuation", not "none" — re-run
at n≈200. It still does NOT license price-bucket hypotheses on hand-swept tape,
and hypothesis #5 (within-day sequence effects) shares a cause with the sampling
and cannot be read on it at all.

**Earlier, superseded reading —**  Ran the pre-registration's frame gate (`cfb/run_tt_frame_gate.py`)
at 00:20Z on the 17 matches with a pregame close that started more than 45 minutes ago:

| | |
|---|---|
| settled by the venue | **17 of 17, zero failures** |
| mean YES price | 0.5588 |
| realized YES rate | 0.5294 (gap −0.029) |
| favourites won | 6 of 11 = 54.5% |

Gate 2 does not fail. **It also could not have.** P(≥6 wins of 11 | a true rate of 0.50)
is 0.500 — exactly a coin — and the 95% lower bound on the true rate is 27%. A flipped
frame would show ~45%, and separating 55% from 45% needs a few hundred matches. So this is
**not** "the frame is verified"; it is a check that has run and has no power yet, which is
the same shape as the decision-rule clause retired earlier tonight and must not be quoted
as corroboration.

What IS established, and it is worth having: the venue settles Setka Cup markets and our
settlement path reads them — 17 for 17 through `core/settlements.py`. The end-to-end route
from board sweep to settled outcome works on this family.

★★ **KALSHI IS 1,000× BIGGER THAN WHAT WE RECORD, AND THE SAMPLE-SIZE PROBLEM
IS SOLVED THERE.** Survey 2026-09-14 (raw under scratchpad/kalshi/). The public
API exposes **14,018 series across 20 categories, 11,697 open events, 107,599
open markets**. We record football winner markets on a 72h window — about 0.1%
of it, and the 0.1% that is worst for us.

| lead | settled events/week | spread | maker fee | why |
|---|---:|---:|---|---|
| **ITF Women's + ATP Challenger tennis** | **833** | 1.0¢ | **none** | 7× the outcomes of our entire CFB tape, two-sided on 23 of 25 books |
| Crypto 15-min + hourly ladders | 664 + 164 | 1.0–2.0¢ | none | continuous settled outcomes, 96/day, forever |
| Weather (rain, city highs) | 7 per series | 1–2¢ | none | no Polymarket equivalent; settles on a public forecast release |
| Mentions / Entertainment | 2–27 | 1–4¢ | none | $99k of live maker incentives; plausibly the least sophisticated crowd on the venue |

**Three facts that change what is possible:**

1. **Maker fees apply to only 160 of 14,018 series — and every series we currently
   record is in that 160.** The high-volume tennis, weather, crypto and mentions
   series carry **no maker fee at all**. The making case was killed on the one
   corner of this venue where making is most expensive.
2. **2,469 markets run live Liquidity Incentive Programs with $373,187 in pools**,
   paying makers to rest two-sided quotes whether or not they fill. There is no
   Polymarket analogue. `GET /incentive_programs` is public and we did not know
   it existed.
3. **Fee rounding is better than recorded**: not "round up to the cent" but
   `ceil_6dp` plus a per-order accumulator that rebates the overpayment, with a
   $0.0001 grid for direct members. Materially cheaper at small edges.

**Do NOT move football to Kalshi.** Measured same-instant: Kalshi is never
tighter at the touch, Polymarket quotes a half-cent tick on NFL where Kalshi is
on whole cents, Polymarket is far better on far-dated CFB (3¢ vs 25¢), and those
are exactly the series that carry maker fees. Keep the 72h pregame Kalshi
recording as the cross-venue reference it already is.

**★ The "4× fee dispute" is probably OUR OWN transcription error, and the real
defect is a scope error.** 0.07 / 0.0175 = 4.0, and 1/p(1−p) at p=0.5 = 4.0 to
machine precision: **0.0175 IS the coefficient's value at mid-book**, so reading
it as a coefficient applies p(1−p) twice. Treat 1.75¢ as standing for the
maker-fee series. The discriminator needs no PDF — whether the third-party text
attaches `·p(1−p)` or states a flat per-contract figure.

**What does not dissolve is the scope.** `docs/math/the-rebate.md` derives
"structurally impossible" from fee arithmetic alone and says so —
*"half-spread 0.5¢ against a 1.75¢ maker fee means −1.25¢ **before** adverse
selection"* — so adverse selection was never load-bearing in that conclusion.
Its evidence sentence is correctly scoped to NCAAF; its three conclusion
sentences say "Kalshi", "there" and "venues". Against 160 maker-fee series of
14,018, that does not follow. **And on the series we actually want — tennis,
crypto, weather — the maker fee is zero, so the half-spread is not eaten before
adverse selection even begins and the question becomes empirical.** Making was
closed on an arithmetic that does not apply to the markets we now care about.

What survives regardless, being Polymarket-side: the maker rebate, the guarded
true-P&L column (+0.023¢ WNBA, −0.062¢ CFB), the +0.061¢ [−0.762, +0.883] over
24 games, and the circuit-breaker effect. **None of the positive Polymarket
result is at risk.**

**FIRST FULL SCAN COMPLETED 07:24Z — and its headline is the artifact, for the
third independent time.** `scan_2026-09-14T0528Z.txt`, 22,503 settlement calls
over 13 patterns. It launched at 05:28, before the degeneracy guard landed, so it
carries the full inflation: **Var(t) 18.527 against a 1.153 baseline, max|t|
31.543 against an expected 3.402, 62 cells over |t|>1.96 against 16.3 expected.**
Two agents and I each measured this independently on our own passes; this is the
same thing a third time on the canonical code. Its Higher Criticism printed
**169,089.25**, the known ceiling failure appearing in production rather than in
a synthetic — flagged `[CONTESTED]` in the output with the registered fallback
`count(p<0.01)=34` printed beside it, which is why all three statistics are
reported every run and none is chosen after its value is seen.

**Per-pattern closes, valid (the guard does not affect row counts):**

| pattern | closes | | pattern | closes |
|---|---:|---|---|---:|
| cfb | 15,818 | | cplcr | 1 |
| nfl | 5,051 | | t20icr | 1 |
| wnba | 1,582 | | setkameua | 29 |
| mlb | 15 | | setkamemd | 6 |
| | | | t20iwcr / odicr / county / setkamecz / setkawoua | 0 |

**Tomorrow 04:40Z is the first trustworthy run**, carrying the degeneracy guard,
the `2026-09-01` partition floor and the single-pass `LIKE ANY`. Three changes in
one unattended run is more than ideal, but they are independent and each kills
the run rather than warning: a cell with no outcome variation is excluded with
its reason printed, a non-boundary floor is refused, and a row matching two
patterns aborts.

★★ **THE FIRST REAL ANSWER TO "DOES TAKING WORK": THE VENUE IS WELL CALIBRATED
AND BUYING AT THE ASK IS NEGATIVE-EV AT EVERY PRICE.** Measured across 20,019
settled bets, 258 games, by decile of the YES price:

| decile | bets | mean ask | observed win rate | break-even |
|---|---:|---:|---:|---:|
| 0.0 | 2,900 | 0.056 | **0.039** | 0.059 |
| 0.1 | 1,860 | 0.172 | **0.158** | 0.181 |
| 0.5 | 2,450 | 0.580 | **0.541** | 0.595 |
| 0.9 | 941 | 0.958 | **0.935** | 0.961 |

Observed tracks price almost exactly — the venue prices these markets well — and
sits just BELOW break-even in every band once the fee is in. **That is the same
conclusion the momentum scalp, the extreme-price hold and the paper book each
reached separately, now visible directly in the calibration rather than inferred
from a P&L.** It is the strongest negative result this project has produced and
it is about the venue, not about one strategy: **there is no price region where
crossing the spread pays.**

★ **AND THE INSTRUMENT BUILT TO JUDGE THE SCAN WAS RETRACTED BY ITS OWN AUTHOR,
BECAUSE THE SPECIFICATION WAS MINE AND IT WAS WRONG.** I briefed "permute
settlements within games". The strata span every price decile, so a shuffle
hands a 5¢ longshot the outcome of a favourite: decile 0 goes 0.039 → 0.140,
decile 9 goes 0.935 → 0.766, everything flattened toward the pooled 0.439. That
manufactures about +8¢ per contract at the cheap end and −19¢ at the expensive
end. **The null was not "the scan with the edge removed", it was "the scan with
CALIBRATION removed"** — an artifact larger than any edge we could be hunting,
against which nothing can clear. Six statistics all landing BELOW the null median
was the tell, and `cells excluding zero` at 95 where a correct null gives ~16 is
unmissable. It also explains the planted-edge control never recovering: the
reference was saturated, not the tape underpowered.

**There is no repair by re-stratifying.** Permuting across deciles destroys
calibration; permuting within a decile holds the win count fixed and gives zero
variance; the scan's cells ARE the price strata. Wrong instrument, not a
mis-tuned one. Replacement is parametric: draw `y ~ Bernoulli(break_even(ask))`
within game clusters, so calibration is preserved by construction. It does not
enter the pre-registration until its control recovers a planted edge — the bar
the permutation version never cleared.

★★★ **THE SCAN IS ANSWERED, ON A REFERENCE THAT CAN BE DEFENDED — AND THE
CAPABILITY STATEMENT MATTERS MORE THAN THE RESULT.**

**The result.** 362 cells, 36 significant at p<0.05 — but split by direction,
**6 above break-even and 30 below.** Six is BELOW the ~12 that chance alone
gives, so there is no evidence of an edge anywhere; the excess is losses. Mean
win rate minus break-even across all cells is **−0.0157**. Best cell above
break-even is p = 1.70e-02 against a Bonferroni threshold of 1.4e-04 — **short by
a factor of 120**; two of those six are 32/32 and 35/35 on high-priced favourites
where a single loss erases them. Consistent from three directions: the decile
calibration table, the directional split, and the aggregate.

**The capability statement, which is the part that changes what we do next.**
Power measured by planting known edges into H0 data, 120 trials per point:

| planted edge | 0¢ | 2¢ | 5¢ | 10¢ | 15¢ | 20¢ |
|---|---:|---:|---:|---:|---:|---:|
| min-p detects | 0.07 | 0.06 | 0.11 | 0.42 | 0.93 | 1.00 |

**Minimum detectable edge is ~10–15¢ per contract. Below 5¢ the scan is blind** —
power is indistinguishable from the false-positive rate. **A 1–3¢ edge, the size
actually worth trading, is NOT answerable with this tape.** So "no edge found" and
"no edge exists" are different statements and only the first is supported.

**The new null is calibrated where the old one was not:** Var(t) p50 **1.096**
against a theoretical G-implied 1.15, cells-excluding-zero **21 of 310 (6.8%)**
against a nominal 5% — where the permutation gave **95**. It reproduces
break-even at every decile because the null win rate IS the price.

★ **And the control was broken twice, both found by one question: what does it
do at ZERO effect?** Version one redrew each bet independently while the null
draws one uniform per game, so it "recovered" a **zero**-cent plant 70% of the
time — firing on the redraw. Version two kept real settlements outside the
planted bucket, so min-p picked up the tape's own most extreme cell and scored
**0.97 recovery at zero cents** against a nominal 0.05. The sandwich statistics
escaped that one only by magnitude, which is being right for the wrong reason,
and the next statistic added would have inherited it. Version three draws every
row under H0; all four statistics now sit at 0.04–0.07 at zero plant.

The permutation stays in the file marked NOT-the-null, with the decile table in
its docstring, because its failure is the most instructive artifact in the
programme — and a test asserts the code cannot silently go back to it.

**TUESDAY LIST — three changes that need the operator and must not go mid-slate:**

1. **ESPN recorder final-state fix** (merged, not deployed): a game leaves the
   live board before it is final, so only ~41% ever reached `post`.
2. **NFL ties cannot be recorded by the quote engine.** `core/quote/engine.py`
   and `storage.py` run for NFL, where a tie settles at 0.5, but the storage
   `CheckConstraint` is `settlement in (0,1)`. Changing the Python alone turns a
   silent discard into a **write failure on the first tied game** in a live
   engine — so the migration widens the constraint first, then the Python routes
   through `settlements.label`. Rare, but both football engines are running now.
3. **`shared_buffers` is 128 MB** against a 57 GB table on a 7 GB box — measure
   before changing, and it needs a postgres restart that drops every recorder.

**Suite: 1,791 → 1,958 passing, 0 failing, verified on the MERGED main rather
than on any branch** — a green branch and a green merge are different claims, and
every branch tonight was merged into a main that had moved underneath it.

**Three things to check on the 04:40Z nightly, because each is currently believed
on an EXPLAIN or a unit test rather than on a real unattended run:** does
`since=2026-09-01` print on the coverage line (the floor), does the run come in
materially under tonight's two hours (the single-pass query), and does CELLS_JSON
parse (the int64 fix).

★★★★★ **THE CAPABILITY STATEMENT, CORRECTED TWICE AND NOW MEASURED — THE
PROGRAMME CANNOT RULE OUT THE EDGE SIZES WORTH TRADING.**

**MEASURED, not modelled** — `clustered()` on the bets with game as the key, so
the within-cluster covariance is estimated rather than assumed:

| population | n | G | G_eff | pooled mean | 95% CI | bound | hurdle |
|---|---:|---:|---:|---:|---|---:|---:|
| pregame | 20,024 | 263 | 116.9 | **−3.743¢** | **[−6.299, −1.188]** | **2.56¢** | 2.1¢ |
| in-play | 33,815 | 140 | 44.2 | −4.851¢ | [−9.971, +0.270] | 5.12¢ | 3.0¢ |

★★ **RETRACTED AND REPLACED: ZERO WAS THE WRONG NULL, AND AGAINST THE RIGHT ONE
BOTH POPULATIONS ARE CONCLUSIVE.** Buying at the ask and holding to settlement on
a fairly priced market has E[pnl] = −(half-spread + fee). **So the null is −cost,
not zero**, and "the mean excludes zero" says only that the cost is real.

| population | own mean cost | pooled pnl | **excess over −cost** | 95% CI | bound vs hurdle |
|---|---:|---:|---:|---|---|
| pregame | **4.101¢** | −3.743¢ | **+0.357¢** | [−2.160, **+2.874**] | CI EXCLUDES 4.101 → **CONCLUSIVE**, z 2.92, p 0.0018 |
| in-play | **6.905¢** | −4.851¢ | **+2.055¢** | [−3.041, **+7.151**] | CI INCLUDES 6.905 → **NOT conclusive**, z 1.87, p 0.031 |

**Corrected again: `bound ≤ hurdle` compares a HALF-WIDTH to a threshold and
silently assumes the point estimate sits at zero.** The correct test is whether
the interval excludes the hurdle. In-play's estimate sits +2.055, a shift of 79%
of its own SE, pushing the upper end to 7.151 — past the 6.905 hurdle. The
shortcut cannot see that because it never looks at where the estimate is.

**And the programme's own multiplicity applies: two populations, so m=2.** At
z ≥ 1.960 pregame clears comfortably (it clears even m=10) and **in-play fails**.
Reporting both as conclusive would have been the first claim tonight surviving
only by not being corrected for multiplicity — in a programme whose entire
subject is multiplicity.

**PREGAME is the result and it is strong:** across 20,024 bets on 263 games the
gross edge is +0.357¢ [−2.160, +2.874] against a population cost of 4.101¢, so a
tradeable edge is **excluded at p = 0.0018**. The pregame board is priced at cost
within measurement error and the design could have seen an edge the size of the
cost itself. **IN-PLAY is directionally the same and not yet decisive** (p = 0.031
one-sided, fails at m=2). That is 140 game-clusters, not a flaw in the method —
**the fix is Saturday, not a rewrite.**

**And the 2.1¢ hurdle I had been carrying was a CFB-spread figure applied to a
population spanning table tennis, MLB, quarter markets and cricket.** The
population's own cost is 4.10¢ and 6.91¢. Since conclusiveness is bound ≤ the
population's OWN hurdle, both clear it. Fourth instance tonight of a single-league
constant applied to a multi-league population.

**And the pregame bound is 2.56¢ against a 2.1¢ hurdle — 1.2× short, not 2.9×.**
The first modelled figure (6.04¢) assumed ρ=1 within each game cluster, which is
nearly true for spread rungs settling off one margin and false across market
types; it bracketed the truth from the pessimistic side by 2.4×. **One more
Saturday plausibly closes the pregame gap**, which makes 09-19 worth more than it
looked an hour ago.

> **Superseded by the row above: against each population's OWN cost hurdle,
> both are conclusive. The earlier gap was an artifact of a hurdle imported from
> one league and a null of zero the design could never produce.**

**Two corrections that produced this, both from the author of the original
figure.** The registered 5–15¢ detection bound was **projected, not measured** —
per-cell G was assumed rather than counted, and the real grid slices far finer.
Measured per-cell it is **27–40¢**. A projected G is exactly the population error
this programme exists to catch, committed inside the document that defines the
catching. And my "790× larger population" for the in-play scan was true of rows
and false of information: **32,402 ticks carry 1,738 effective clusters against
pregame's 19,316 rows carrying 8,371** — 1.7× the rows, one fifth the information.

★ **THE PER-CELL ARM IS DEAD, NOT WEAK.** At G_eff 27.1 pregame and 12.1 in-play,
no cell in either population could clear a nomination at ANY achievable effect
size (they would need 27¢ and 40¢), and in-play fails the registered G≥25 floor
outright. **So the screen/confirm design has no stage-1 output at these cell
sizes, and computing per-cell p-values was measuring a branch that cannot fire** —
the same defect as the retired decision-rule clause, one level up.

> **The entire pregame tape supports 1.87 decision-grade cells. It was cut into
> 309. In-play supports 0.79. It was cut into 144.**

**What survives, and why:** the headline negative was always a POOLED statistic
across all cells, never a claim about any one of them, and pooling is precisely
why it has force. Zero cells at p<0.01 against 2.2 expected stands. The honest
headline is **"no edge above ~6¢"**, not "the venue is efficient". To become
conclusive needs **8.3× more distinct games pregame and 7.6× in-play** — 2,178
and 1,067 against 263 and 140.

★★★★★ **REPLICATED IN-PLAY (on rows, not on information). The pregame conclusion
holds on continuously moving prices, and the expectation was on the record before
the data was seen.** 296,964 sampled in-game ticks (cfb 212,643, nfl 65,308,
wnba 17,739, mlb 228):

| max half-spread | cells | p<0.05 / null | p<0.01 / null | best p | null E[min p] | lose/win |
|---|---:|---|---|---|---|---|
| ≤1¢ | 52 | 2 / 2.6 | **0 / 0.5** | 2.00e-02 | 1.9e-02 | 0/2 |
| ≤2¢ | 88 | 2 / 4.4 | **0 / 0.9** | 2.00e-02 | — | 0/2 |
| ≤5¢ | 97 | 2 / 4.9 | **0 / 1.0** | 2.00e-02 | — | 0/2 |
| all | 161 | 27 / 8.1 | 17 / 1.6 | 5.38e-06 | — | 25/2 |

**At every tradeable cap the count is at or below the null, zero clears p<0.01,
and the best cell is essentially exactly what chance produces** (2.00e-02 against
an expected minimum of 1.9e-02). All ten top cells are wide-spread — 11 to 22¢ —
and every one loses. Nothing nominated at any tradeable cap.

**Recorded and not smoothed:** the two surviving tight cells are WINNING, where
pregame tight cells ran 10/1 losing. Two of 52 against 2.6 expected is noise, and
it is the one place the two populations' directional signatures differ. Worth a
look only if it recurs on independent tape.

★ **THE LIMIT ON THIS RESULT, WHICH MATTERS MORE THAN THE RESULT: the two scans
agree, and they share a codebase, an author and a settlement source.**
`run_scan_live.py` was derived from `run_scan.py` — same `clustered`, same
`poisson_binomial_p`, same fee constant, same venue endpoint. **So the
replication is strong on POPULATION and weak on IMPLEMENTATION: a defect in the
shared statistic would reproduce identically in both and read as confirmation.**
The pregame degeneracy was caught only because a second, independently written
implementation existed to disagree. **If the in-play result ever has to carry
weight on its own, it needs the same treatment — a second implementation by
someone who did not write the first.** Recorded now rather than discovered when
the number matters.

★ **The diagnostic that made this readable:** in-play a cell carries a **median
11× and up to 91× ticks per effective cluster** (pregame: 1.66 rungs per game).
A cell reading n=2,715 holds about 30 independent observations. Printing
`G_eff` on every row rather than in the summary is now a requirement for any
scan this project runs — without it that cell looks like 2,715 observations and
every interval built from it is spectacular and meaningless.

★★★★ **SCREEN CLOSED: NO EDGE ON ANY TRADEABLE SPREAD, AND THE BOARD IS
QUIETER THAN NOISE THERE.** Conditioning on cost, which needed no new tape:

| max half-spread | cells | p<0.05 obs/null | p<0.01 obs/null | best p | null E[min p] | lose/win |
|---|---:|---|---|---|---|---|
| ≤1¢ | 131 | 11 / 6.6 | **0 / 1.3** | 1.18e-02 | 7.58e-03 | 10/1 |
| ≤2¢ | 221 | 16 / 11.1 | **0 / 2.2** | 1.18e-02 | 4.50e-03 | 15/1 |
| ≤3¢ | 244 | 20 / 12.2 | 2 / 2.4 | 7.30e-04 | 4.08e-03 | 19/1 |
| ≤5¢ | 270 | 26 / 13.5 | 5 / 2.7 | 1.64e-04 | 3.69e-03 | 24/2 |
| all | 327 | 43 / 16.4 | 16 / 3.3 | 1.21e-04 | 3.05e-03 | 40/3 |

**The p<0.01 count is 0, 0, 2, 5, 16 — strictly increasing with the spread cap.
A cost effect shrinks toward the null as the cap tightens; an edge does not.**
And the direction never moves: if an edge were hiding under the cost, winners
would appear as the cost is removed, and the opposite happens at every cap.

**On the tradeable subset (221 cells, half-spread ≤2¢): zero at p<0.01 against
2.2 expected, and the best cell is 2.6× LESS extreme than a pure null produces**,
52× from the Bonferroni bar. Not "nothing found" — the tight-spread board is
measurably flatter than chance. **Zero cells nominated at any tradeable cap.**
The three that clear unconditionally have half-spreads of 4.5–19.5¢.

Not leaned on: the ≤1¢ row's 1.67× excess at p<0.05 with **zero** at p<0.01 and a
minimum p above the null expectation is the signature of many marginal cells, not
one real one — recorded as unexplained, likely residual clustering, rather than
claimed clean.

Also fixed: the G floor gated only the sandwich path, so **57 primary cells were
ranking without it**, including a G=2 cell at p=8.9e-04. All 57 now print with
their reason; m 383 → 327.

★★★ **Why the excess existed at all: it is the spread, not an edge.**
Post-exclusion the distribution IS wider than the null (Var(t) 1.503 against a
1.148 baseline, 44 cells over |t|>1.96 against 15.5, 16 at p<0.01 against 3.1).
The width has a cause and it is not opportunity:

| cell | G | win rate | break-even | mid | ask − mid |
|---|---:|---:|---:|---:|---:|
| cfb 4th-quarter total, dec 0.7 | 36 | 63.9% | 87.9% | 75.0 | **+12.9** |
| cfb 3rd-quarter total, dec 0.7 | 20 | 50.0% | 84.7% | 75.0 | **+9.7** |
| cfb 1st-quarter total, dec 0.7 | 27 | 63.0% | 89.0% | 75.0 | **+14.0** |
| cfb 1st-quarter spread, dec 0.5 | 61 | 37.7% | 61.7% | 55.0 | **+6.7** |

**Break-even sits a median +9.7pp above the decile centre**, because the ask is
7–14¢ above the mid in these thin quarter markets. **Ten of ten top cells lose;
none wins.** The scan is correctly detecting the venue's spread on illiquid market
types. It is untradeable in the direction it points — nobody crosses a 14¢ spread
— and the mirror, selling into those spreads, is the making study already measured
negative with power.

**So the screen is answered: no edge, and the apparent global effect is cost.**
Consistent from four directions now — the decile calibration table, the
directional split (6 above break-even against ~12 by chance), the aggregate
(−0.0157 mean win rate minus break-even), and this.

**Next scan, and it needs no new tape: condition on the spread.** Bucket on
ask-minus-mid rather than on the mid alone and ask whether anything survives with
cost held constant.

**Not yet comparable:** two implementations give post-exclusion Var(t) 1.308 and
1.503, but on 308 versus 309 cells and with different within-game rung selection.
Non-convergence is only a finding once the inputs are shown identical.

## 3b. Open defects found tonight (none is a strategy question)

| defect | measurement | state |
|---|---|---|
| ~~`/api/games` has no limit bound~~ | `limit=-1` → 500 immediately; `limit=100000` → 200 in **29.1s**; a twelve-digit limit → 200 in 24.2s; `limit=abc` → 422 in 0.25s. An unauthenticated GET holds a worker for half a minute on a service bound to all interfaces | **FIXED, merged** (432cbe9): all five limits declared `Query(ge, le)`, caps sourced from the callers that actually pass one, the silent clamp deleted. Live on the box only after the api rebuild |
| ESPN recorder never observes the final | only ~41% of games reach `state='post'`; 14-day census 105 `post` vs 81 `in`. Cause: `refresh_live` collects only `state=='in'`, so a game leaving the live board is never polled again — it departs BEFORE it is final | **FIXED, merged** (878c0ee), **NOT DEPLOYED**: a departed game is polled at 60s until `post` is observed, exit on the state field never the clock, loud abandon 3h after departure, and an abandoned game is never marked final. Deploys **Tuesday, between slates**, with the plays-regression fix |
| `is_live` is never cleared | over the whole tape: 31,156 markets were ever live, **12,290 still say so on their last row, and 11,227 of those (91.4%) have not been written in 600s** — the same threshold the alarm uses; oldest such row 43 days. (My 30-day cut gave 5,364 of 12,160 over a day: the same fact at a looser threshold.) | **audited**: the scalp engine and the paper book never read it, and `core/board.py:market_state()` already guards it with the same 600s the alarm uses. **FIXED for the fair-value path** (5c8b328): `live_fv` and `live_totals_fv` now decide through `market_state()`, so there is one definition of live in the codebase; the flag stays only as a cheap prefilter. Its filter had been untested — all 58 existing tests passed with it neutralised, because every one was a pure-function test. The six analysis selectors are annotated and deliberately UNCHANGED: their populations are already published, and silently re-cutting them would make earlier findings irreproducible. **How the drag gets measured when someone wants it:** not as a standalone full-tape pass, but as a second column on a study already scanning those rows — the same statistic computed twice, once as published and once with a `captured_at` freshness guard, reported as a pair. One scan, both numbers, and the original stays reproducible beside it |
| `core/retention.py` dropped two indexes | hand-kept index lists missed the tipoff partials that took `/api/picks` from 4.75s to 0.42s | FIXED, merged |

## 4. Registered reads (dates fixed, criteria written before the tape)

- **Sat 09-19 (CFB):** interim observation only — print cell, G and interval, take no verdict. At ~40 games a Saturday a CFB cell must show **16.3¢** to exclude zero on one week, and nothing registered clears that. Full rule and corrections: `docs/math/preregistration_2026-09-19.md`.
- **Sun 09-21 (NFL):** the real test. Same two spread rules, no prior, family of 2–4, so the interval means what it says.
- Kalshi-vs-DraftKings lag on the first full week of tape.
- **ESPN cannot settle a football read; the venue endpoint is the only complete route.** The ESPN recorder stops polling a game before it observes the final transition, so a game has live state but never a result: on the best slate only 18 of 44 mapped games reach `state='post'` (~41%), and a 14-day census over all CFB games is 105 `post` against 81 stuck at `in` (three independent routes agree; there are exactly two terminal values and zero partially-settled games, which is what a per-GAME stage failure looks like). The venue endpoint returned 227 of 227 on the flagship bucket. ESPN keeps the independent frame check (65/65 agreement where it does finalise) and loses the settlement job. **Fix is in the recorder, not the map: keep polling until `post` is observed rather than until the clock runs out.**
- **The gate on every ESPN-settled read is recorder uptime across the slate, not the game map.** The earliest ESPN CFB state row in existence is 2026-09-05 22:08Z: the map wrote 13 of 13 rows for 09-03/09-04 and there was nothing to join to, and 09-05 lost its early games the same way. With the recorder up all day, 09-12 is 44 of 44. If a recorder dies mid-slate the games before it returns are lost silently — which is what `scripts/alarm_v5.py` (merged tonight) exists to catch.
- **WNBA playoffs:** favourite and under lines on the first 25 games; PULSE resumes.
- **MLB:** ladder calibration at 100 settled games (≈ one week after the recorder starts).
- **Mon 09-14 10:20Z:** the automatic NFL/CFB read (maker gate already FAIL at G=43).

## 5. Being built right now (agents, in their own worktrees, reviewed before merge)

Operator priorities set 09-13 evening: NFL in-game first (recorded at 0.5 s), simple take-profit/stop rules scored as paper lines, MLB recording daily. Aim $7k/week; $1k/week matters. Three peer sessions were alive at hand-over (Debugger, Builder D, Quant A); three researcher agents were spawned by the manager; a manager check-in runs every 30 min.

| agent | deliverable |
|---|---|
| Debugger (done) | MERGED 09-13 20:30Z: recorder plays regression + leak guard, idempotent index migration, health.py sees all 24 containers (test fails both ways), Kalshi recorder gives NFL a clock from the venue (kickoff+3h occurrence, applied in the open; the team map is WNBA-only so ESPN linking would mis-pair). Suite 1437→1451 passed, 25→21 failed (residual predates) |
| Builder D (done) | MLB: settlement cache, MLB ladder calibration, daily 10:40Z `mlb` cron mode — MERGED, crontab line installed |
| Quant A | DK line move → venue lag: first pass found the lag (CFB median 30 min, n=19, G=15; NFL median 61 min, n=7) but settled from the idle WNBA resolver table, so P&L had G=0; rerunning on the venue's settlement endpoint |
| researcher 1 | CFB 20–30¢ NO decomposed: favourite-fails vs dog-covers, monotone buckets with home-referenced twins, NO-mid definition |
| researcher 2 | Kalshi vs Polymarket cross-venue: gap, dutch count, who is stale, the longshot rung on Kalshi |
| researcher 3 (done) | momentum scalp grid: measured negative with power, see §3 |
| honest dashboard + JSON scoreboard | MERGED 09-13 (080aa97, 5891b4b, −255 lines); live after command 2 above |
| Builder D (done) | football in-game PAPER taker loop `core/gridiron/scalp.py` — MERGED 09-13 19:40Z, 47 rule tests, read-only by construction; live after command 3 above; parameters get refitted from tonight's backtest |
| Quant B (done) | in-game extreme-price hold to settlement: the fee is 0.06·p(1−p), so a 95¢ ticket pays 0.3% round trip against 6.0% at 50¢, and holding to settlement pays entry only — the one price region every measured strategy never reached. Bands 0.90–0.99 both sides, by period, one entry per game per band |
| research/audit | pre-registration for 09-19 with the multiplicity correction (~20 registered lines, several found in the data they will be read on), and a second-route audit of tonight's decomposition headline |
| researcher 4 (done) | cricket / TT discovery: 15 cricket events (CPL liquid), 4 Setka Cup TT leagues (69 events/day, 1–2¢), YES = home there; ENG v SL was England Lions; ESPN header/summary endpoints give toss, innings, result; Cricinfo 403 |
| Builder D (done) | league sweep: cricket/TT slugs resolved to NO league (fixed, 8 consumers route through one function); strategies/ interface (base.py, ladder.py) with a 198-row oracle proving identical selection; sandbox guard against a ladder name running the quote query — all MERGED |
| Builder D (done) | cricket + table-tennis recorder overlay (docker-compose.cricket.yml, venue_leagues sweep, expected-vs-observed per competition, settlements accept 0.5, six paper lines registered) — MERGED, in the paste above |
| builder (ESPN cricket feed, done) | core/feeds/espn_cricket_recorder.py (197 lines): toss timestamp, innings, result per match, change-detected — MERGED, in the paste |
| Debugger (done) | **production defect**: `core/retention.py` kept its index lists by hand and `migrate()` dropped the two tipoff partial indexes (the ones that took /api/picks from 4.75s to 0.42s); now read from the catalog. Also: the suite's order-dependence was `test_retention`'s destructive fixture on the shared DB, not a flaky test, and the "wallet NULL state cannot exist" claim was RETRACTED by its author — the column is still nullable and the historical tape needs that branch. Full suite 21 failed/1631 passed → 19 failed/1641 passed/0 errors — MERGED |
| Debugger (done) | suite triage: 23 → 3 failures, 0 dead tests, fixtures and guards fixed, stale infra docs reduced to pointers — MERGED |
| Builder D (done) | human_market moved out of core/api.py: the engines no longer load FastAPI on first label call (34 → 10 modules) — MERGED |
| codebase map / Kalshi–DK lag / shadow lister | merged earlier 09-13 |

## 6. Open questions for the researcher (docs/math/longshot-no-candidate.md §7)

1. ANSWERED 09-13 (`cfb/run_longshot_decomp.py`), then narrowed by audit: not a longshot effect. The one cell excluding zero is away at 50–60¢, −11.62 [−21.74, −1.50], G 104, verified end to end by an independent route. Its home twin is +1.97 [−7.65, +11.59], a null — what is established is that the AWAY side is expensive at coin-flip rungs, not that the home side is cheap everywhere.
2. Home shift in CFB weeks 1–2: real early-season mispricing or a 1.9σ draw? ~200 games decide.
3. Does the WNBA under-bias exist outside late August? Playoffs answer.
4. Kalshi vs DraftKings during the week: which moves first? Tape now exists.
5. ANSWERED 09-13: not monotone (−0.05, +2.48, +5.44, −2.64, +1.97 across 0→50¢), so the bucket boundary did the work.
