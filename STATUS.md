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

**REPLICATED ON NFL, 2026-09-15**, on 15 games by a different implementation after meridian-06
stopped responding. Same structure: the control fires, the trigger does not.

| arm | horizon | n | G | mean | 95% CI |
|---|---|---:|---:|---:|---|
| inside the opponent's 40 | 30s | 187 | 15 | +0.332¢ | [−0.091, +0.755] spans zero |
| inside the opponent's 40 | 300s | 181 | 15 | +0.927¢ | [−0.217, +2.070] spans zero |
| scoring play (control) | 30s | 127 | 15 | +1.467¢ | [+0.327, **+2.606**] excludes zero |
| scoring play (control) | 300s | 126 | 15 | +1.973¢ | [+0.733, **+3.212**] excludes zero |

**Split by side, which my own standing rule requires and I had not done:**

| arm | side | horizon | n | G | mean | 95% CI |
|---|---|---|---:|---:|---:|---|
| midfield | away offense | 300s | 78 | 15 | +0.765¢ | [−1.091, +2.620] |
| midfield | home offense | 300s | 103 | 15 | +0.819¢ | [−0.626, +2.265] |
| scoring | away offense | 300s | 66 | 15 | +1.404¢ | [−0.152, +2.961] **spans zero** |
| scoring | home offense | 300s | 60 | 14 | +1.990¢ | [+0.471, +3.509] excludes zero |

**The trigger is clean: both sides span zero and agree with each other** (+0.765 against +0.819),
so the null is not the away-team confound in disguise. **The control is weaker than the pooled
number suggested:** pooled it excludes zero at both horizons, but split it does so only on the
home-offense side. Each side carries roughly half the sample, so this is underpowered rather than
contradictory -- but "the control fires" is a pooled claim and I reported it without checking
whether it survived the split.

Median move 0.00¢ in every arm at every horizon, as on CFB. **Two leagues, two implementations,
same answer.** The honest limit: at 300s the trigger's interval reaches +2.07¢ and a round trip
costs about 3¢, so this does not clear costs -- but with 15 clusters it cannot exclude a 2¢ effect
either, and should not be read as if it could. Write-up: `docs/math/nfl-drive-drift.md`.

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

## 0q. "Reached post" is not "has a final score", and the obvious repair is worse than the defect

The ESPN fix waiting on the rebuild polls a departed game until `post` is observed. Two questions
about it, both answered before the rebuild rather than after, and the second one found a defect in
the repair rather than in the recorder.

**Is the three-hour give-up long enough? Yes, by orders of magnitude, and the obvious measurement
would have been censored.** Among games that reached post the delay from the last `in` row is a
median 0.5 minutes -- but that population is selected on having posted *while polling continued*,
which is the Kalshi capture bias in miniature and cannot bound the 81 stuck games. The answer
comes from the other side: the stuck games are abandoned **at the whistle**, not mid-game. CFB
period 4, 69 games, median observed span 3.28 hours, clock 0:00. A 3.28-hour span is a full
college football game. The gap to bridge is minutes.

A separate worry of mine was real and is not the bound: one game went post, back to `in` 9.75
hours later, then post again. A three-hour bound would not cover that, but post had already been
observed, so the exit condition rather than the bound was always the binding constraint.

**Is `post` sufficient for a final score? Complete yes, stable no.** Verified here independently:
105 CFB post games, **zero** null scores, and **12** whose post score is *below* a score seen
earlier in the same game, understating by up to 7 points. NFL: 9 post games, zero of either.

**And the obvious repair is the wrong one.** Taking `max(home_score)` and `max(away_score)` across
the game looks right and is not: in **9 of those 12** the maximum home score and the maximum away
score **never co-existed in any single row**, so the per-column max names a scoreline that never
happened. (7d measured 7 of 12 by a slightly different row restriction; the direction and the
conclusion are the same and my count is the larger.) These are ESPN publishing a score and
correcting it *downward*, with the post row carrying the correction. `max()` would overstate up to
seven totals points and push Over markets toward YES -- the same flattering direction as every
other defect today, introduced while fixing one.

**The rule is the LAST post row.** A non-monotone score history is a flag to inspect, not a reason
to reach for `max()`.

**One change to the fix before it ships.** Exit on `post` observed **twice, a few minutes apart,
with the same score**, rather than on the first post. Of 114 post games the median has exactly one
post row, so the naive "112 of 114 unchanged" is vacuous for 77 of them -- the comparison is a row
against itself. Among the 37 where it *can* fail, **2 changed score after first post**, 5.4%, by up
to 9 total points. One confirming poll, one extra request per game, against a measured 5% rather
than an imagined tail.

## 0r. The operator's strategy cannot be executed on this feed at 30 seconds

Denver at Kansas City, kickoff **2026-09-15 00:15Z**. `meridian-scalp-nfl` has been up since
05:20Z with zero rows in `paper_scalps`. It beats every 2 seconds, so its silence is liveness and
not death -- the heartbeat table answers what the log cannot.

**The freshness gate cannot be met by the data.** Verified independently, six days of tape:

| league | plays | age when FIRST seen, median | p90 | already past a 30s gate on arrival |
|---|---:|---:|---:|---:|
| nfl | 2,727 | **53s** | 73s | **93.7%** |
| cfb | 23,094 | 58s | 93s | 97.3% |

The engine evaluates at or after first sight, so 93.7% is a **lower bound** on refusals, not an
estimate. Consecutive plays are a median 43 seconds apart, so even with zero pipeline lag the
newest play is usually older than the gate. **The poll interval is not the cause**: a 53-second
median against a 20-second poll puts ESPN's own publishing lag at 30-45 seconds. The venue tick
half never refuses anything -- zero of 11,665 gaps over 30 seconds.

**So the expected result tonight is near-zero triggers, and it will read as "the strategy found no
opportunities" rather than "the gate refused everything".** Recorded as a prediction before the
game rather than an explanation after it.

**The gate was also selecting for corrupt rows.** `(now - t) > max_age` treats a *negative* age as
perfectly fresh, and **85 of 2,727 NFL plays (3.1%) carry a wall clock 24 hours in the future** --
min lag −86,378s, which is −86,400 plus the usual lag. CFB has zero negatives, so this is an
NFL-specific date defect in the parser, not a clock misalignment. Those 85 were among the few rows
that **passed** while 93.7% of good ones were refused: the one gate meant to stop bad data was
selecting for it. Fixed on main (`age > max_age_s or age < -1.0`, a day is not skew).

**CORRECTION, to 7d and to me, said twice by both of us without checking.** We each wrote that
tonight's few trades would be disproportionately those corrupt rows. **They will not be.** All 85
belong to **one game**, 401872657, seen 2026-09-11 00:41 to 01:55Z and stamped 2026-09-12 00:37 --
verified here, a single row in the group-by. That is three days ago and far outside the engine's
six-hour window. **Tonight's near-zero count will be entirely ESPN's publishing lag against a
30-second gate, with no corrupt row involved.** The fix closes a real hole and one game in four
days is a rate rather than a one-off, so it will recur -- but it is not a protection for tonight,
and saying so is the difference between a fix and a story about a fix.

**What the corrupt row does when it lands is worse than "it passes", which is why the hole
matters.** The engine takes `DISTINCT ON (game_id) ORDER BY wall_clock DESC`, so one
future-stamped play **wins that selection for as long as it sits in the window** -- pinning the
engine's whole view of that game to itself, on every 2-second cycle, with a negative age the old
test read as perfectly fresh. On the 09-11 game that is 85 rows over 73 minutes.

**And tonight did not need predicting: the gate replays exactly over the recorded 09-13 slate.**
13 games, 40.62 live hours, no sampling. **The gate passes 0.23% of live time**, per game 0.09% to
0.40% -- thirteen games inside a four-fold band, so it is structural rather than an incident. At
the 2-second cycle that is roughly 73,000 evaluations across the slate and about **170** that clear
it, ~13 per game. Clearing the gate is necessary and not sufficient; a trigger still has to fire
inside that window.

**The replay is now an instrument, not a query.** `cfb/run_gate_replay.py --league --since --until`
reports **per game**, the only grouping the engine ever sees, and reads `MAX_AGE_S` from the
engine's own `params_from_env` so it cannot drift from the thing it measures. Run against the
baseline on prod at 21:20Z it reproduces exactly: 13 games, 40.62 live hours, **0.23%**, per game
0.09% to 0.40%. It exists because comparing a fresh slate to a baseline only means anything if the
population is built identically, and three false descriptions today came from re-deriving a query
and quietly changing its grouping.

7d verified it by a **second implementation** rather than by derivation: python interval arithmetic
in age space against the SQL in timestamp space, identical to the decimal, and capable of
disagreeing. And a mutation run caught a clamp they had written minutes earlier that **could not
bind** -- the proof is now a comment where the clamp was, and the aggregate is unchanged at 0.23%
after removing it, which is what establishes it was never doing anything.

**0.23% is a CEILING, not an estimate.** I asked whether a replay reproduces on a live slate,
since a replay knows what arrived and a live run does not. 7d found five ways the two differ and
**all five make the replay optimistic**: a row is visible at COMMIT rather than at its stamp, the
engine calls `now()` after its fetch rather than at the instant, a 2-second cycle can miss a
sub-2-second window entirely, the replay contains only rows that were recorded so recorder
downtime is invisible to it, and the dead time after a game's last play leaves the denominator and
inflates the percentage. So the live rate can only come in **under** 0.23%.

**The mechanism is the arrival process, not the polling.** A play's 30-second freshness window
opens at its own wall clock, and it arrives a median 53 seconds later, so `[w, w+30)` is **already
entirely in the past** when we first see it. A window only opens at all for the **6.3%** of NFL
plays that arrive with a lag under 30 seconds, and is then 30-minus-lag seconds wide. The gate is
not sampling a fresh stream too slowly; it is asking for a freshness this feed almost never
produces.

**RETRACTED: "ESPN publishes several plays at once and then nothing."** Nothing is bursty. Both of
us pooled a per-game quantity and neither noticed:

| what was measured | median gap |
|---|---:|
| arrival stamps, NFL, 13 games **interleaved** (7d) | 1.6s |
| arrival stamps, **every league** interleaved (me) | 0.7s |
| **arrival gaps WITHIN one game -- what the engine sees** | **44.1s** |

Verified here: 2,226 within-game gaps, p50 44.1s, p90 154.6s. `LIVE_SQL` filters by league and
takes `DISTINCT ON (game_id)`, so the engine never sees a pooled stream, and 44.1s is essentially
identical to the plays' own 43.0s spacing. My 0.7s was the same artifact as 7d's 1.6s, one level
further out.

**The conclusion never moved, which is exactly why the wrong description survived.** The tell was
sitting there: a per-game quantity (43s play spacing) next to a pooled one (1.6s arrival spacing),
and the difference read as a finding about ESPN instead of as a difference in what had been grouped
by. Third time today a pooled statistic produced a false description while the headline number
stayed right.

**The mechanism is unaffected because it rests on the LAG, not the spacing.** A play's window opens
at its own wall clock, it arrives a median 53 seconds later, so the window is already entirely past
on arrival for 93.7% of plays. Per-game spacing only adds that nothing rescues the gap: the next
row for that game is another 44 seconds away.

**Two things that fix does not reach tonight.** It needs a rebuild, and rebuilding this container
runs `alembic upgrade head`, which advances the database and strands the containers built earlier
today. **I am not rebuilding for tonight, because nothing is lost by waiting:** the plays and the
venue ticks are both recorded, so the engine can be re-run against tonight's tape once the fix
ships. The live-path check is worth less than the restart capability.

**And the engine counted its refusals and threw the number away.** `stale_skips` was incremented
and never logged, so zero trades and total refusal produce identical output. Now reported while a
game is live.

**A DECISION FOR THE OPERATOR, not one I should take.** `MAX_AGE_S` is 30 and the feed's median
play is 53 seconds old on arrival. The floor is ESPN's publishing lag, so **the real choice is
roughly 60-75 seconds or not trading on plays at all.** Raising it admits older information, and
whether that is acceptable depends on how fast the edge decays -- which nothing measured here
touches, and which the drive-scalp study says is moot anyway, since the conditional move at the
trigger is 0.00¢ at the median.

## 0w. Tonight's order of events, checked against the crontab rather than repeated

I told the operator twice that the nightly scan was "about ninety minutes" and then "inside the
hour" away. **Both were wrong.** I inherited the figure from a peer's messages and repeated it
across several reports without ever reading the crontab. Checked at 21:21:48Z:

| event | time | from 21:21Z |
|---|---|---|
| NFL kickoff, Denver at Kansas City | **2026-09-15 00:15Z** | 2h54m |
| nightly scan + paper book | **2026-09-15 04:40Z** | **7h18m** |
| daily MLB read | 2026-09-15 10:40Z | 13h18m |

**The game comes first, not the nightly**, and by four and a half hours. I had the order backwards
as well as the interval, and said so to the operator.

This is the day's own lesson landing on the smallest possible claim. A peer said "nightly in about
two hours" in several messages, it was consistent with nothing I had checked and contradicted by a
crontab line I had read hours earlier for a different reason, and I repeated it because it was
adjacent to work I trusted. The standing note about verifying the clock exists because of exactly
this, twice before.

## 0x. DECISION: the hand-trade audit must raise, not return a partial list

7d swept for instruments carrying their own copy of a production threshold. Keyed on **value** the
sweep was useless -- 383 pairs, almost all unrelated constants that happen to both be 30 or 120,
which is a coincidence detector and the same error as pooling. Keyed on **name** it is 4, and one
has already drifted.

| | `core/audit/hand_trades.py` | `scripts/export_wnba_trades.py` |
|---|---|---|
| `MAX_PAGES` | **50** | **200** |
| `PAGE_LIMIT` | 100 | 100 |
| at the cap | logs a warning, **returns a partial list** | **raises** |

Same endpoint, same loop, same pause. They disagree about both *where* the cap is and *what
hitting it means*, and production is the permissive one. Neither binds today at 681 events and
seven pages, which is exactly why both look right.

**Decision: `hand_trades` raises, and both caps go to 200.** Four reasons, in order.

Its own docstring says "Walk the whole feed to eof". Returning a partial list breaks the contract
the function states about itself, and a docstring nobody can rely on is worse than none.

A partial reconciliation **looks complete**. The warning goes to a log; the caller receives a list
indistinguishable from a whole one. That is the defining failure of this entire day, and it has
appeared in a nightly push, a coverage guard, a refusal counter and a settlement filter.

The stricter sibling already exists, which is the argument that decided the MLB exclusion too:
consistency with a policy already in the tree beats a principle argued from scratch, because it
means the audit is the inconsistent one rather than the case needing a new rule.

And it costs nothing today. Seven pages of fifty. The stricter choice is free now and its benefit
arrives precisely when the failure would otherwise be invisible.

**The guard cannot see the case that motivated it, and that is stated rather than papered over.**
`core/gridiron/scalp.py` has no module-level `MAX_AGE_S` -- the threshold is a string default
inside `params_from_env` -- so there was never a named constant for the replay's copy to collide
with. 7d widened the matcher to walk locals, re-ran the mutation, found it still passed, and
reverted the widening as dead complexity. Second guard they wrote today that could not fire, and
both times the mutation noticed and reading did not.

## 0y. MLB reaches the power floor this week, and it is the only league that will

First pitch tonight **22:40Z**. Measured at 21:52Z:

| | |
|---|---|
| MLB games starting in the next 12h | **10**, all 10 with a pre-game close already recorded |
| MLB games on the board with live quotes | 49, spanning several days |
| MLB rows on tape | 16,377, from 6,081 this morning |
| settled MLB games to date | **1** |

**Tonight's ten, and what the 04:40Z nightly will actually see.**

| first pitch | games | typical end |
|---|---:|---|
| 22:40Z | 2 | 01:40Z |
| 23:07Z | 5 | 02:07Z |
| 00:40Z | 1 | 03:40Z |
| 01:38Z | **2** | **04:38Z** |

The nightly runs at **04:40Z**, so eight of the ten finish comfortably before it and **two end two
minutes prior** -- those will almost certainly not be settled in time, and three hours is a median
that extra innings push later. **Expect the morning push to report roughly 8 of 10**, with the rest
counted-not-scored, which is the correct behaviour rather than a shortfall. The daily MLB read at
10:40Z catches all ten.

**All ten games carry all five market types with live quotes**, checked at 23:22Z: full-game
winner, full-game spread, full-game total, first-five spread and first-five total, 10 games each.
So every one of the fourteen registered MLB strategies gets tape tonight, including the six
registered at 15:00Z while a single game had settled.

**So tonight takes MLB from 1 settled game to about 11.** At roughly 10-15 a night it clears the
paper book's G ≥ 25 floor around **Wednesday** and reaches 100 games inside a week. Nothing else
in the programme accrues at that rate: CFB gives ~117 games a week but only on Saturdays, NFL gives
15, WNBA is 5 games on Thursday and cricket is two settled matches in total.

**That is the whole reason the operator asked for MLB**, and it is the first forward-looking number
today that is not a defect. The six MLB strategies registered at 15:00Z -- registered while exactly
one game had settled, so no outcome could have chosen them -- get their first real tape tonight and
a properly powered read within the week.

**Caution, stated now rather than when the number arrives.** Ten games is ten clusters, not ten
independent observations per market type: a full-game winner, a full-game spread and a first-five
spread on the same game all move with the same result. The G that matters is the game count, which
is the mistake that made 525 Kalshi markets look like a sample and 547 band markets look like a
population.

## 0z. The researcher's session ended with four files uncommitted. Rescued.

meridian-7f is gone from the peer list. Four files of their work existed **only** as uncommitted
changes in the shared checkout at a detached HEAD, where the next `git checkout` anyone ran would
have destroyed them:

| file | state |
|---|---|
| `docs/math/cricket-preregistration.md` | **221 lines, untracked, never committed** |
| `docs/math/scan-preregistration.md` | +230, the conclusiveness correction |
| `docs/math/tabletennis-preregistration.md` | +30, the listing-gap amendment |
| `docs/math/kalshi-tennis-preregistration.md` | +13, recorded as checked |

**This is not recoverable work in the ordinary sense.** A pre-registration's entire value is that
it was written before anyone looked at the prices, and nobody can recreate that property
afterwards, including its author.

**Not copied wholesale, because that would have been a delete.** `origin/main` carried 100 lines on
`scan-preregistration.md` that the researcher's base did not have, so a straight copy would have
silently reverted them -- the same shape as closing a duplicate PR that turns out to carry
something. Extracted as patches against their own base and applied with `--3way`; all three applied
cleanly and the merged file is 602 lines.

**Verified in both directions rather than trusting the clean apply.** The only lines removed
relative to main are the three carrying the old definition of "conclusive" that the correction
replaces. My first check for the table-tennis amendment returned zero because I searched for my own
summary of it instead of its wording -- the same proxy-matching error the threshold sweep found
this afternoon, committed twice in one day.

**Standing consequence:** an agent's work is not safe until it is pushed, and the shared checkout at
a detached HEAD is where it goes to die. Worth asking every peer to push before they stop, and
worth me checking `git status` there whenever a session disappears.

## 0aa. Three times today a proxy stood in for the thing, and all three answered CLEAN

| who | the check | the proxy | the thing | what the proxy said |
|---|---|---|---|---|
| me | is the table-tennis amendment in the rescued file? | my own summary of it | its actual wording | **0 hits** -- nearly reported it lost |
| 7d | which thresholds are duplicated? | the numeric **value** | the constant's **name** | **383 pairs**, almost all coincidences |
| 7d | is any debugger branch unmerged? | commit **reachability** | whether the content is on main | **1 unmerged commit** -- nothing was lost |

**Every one gave a clean-looking answer**, which is why none of them announced itself. A proxy does
not fail loudly; it answers a question next to the one you asked, and the answer is well-formed.

Verified the third myself by content rather than by graph: the five `Query(..., ge=1, le=...)`
bounds from `debugger/bounds` are present on main, five for five, and the branch's apparent
divergence is main having moved 212 commits since. All eleven debugger branches check out.

**The rule, in the form that says when it binds:** when a check is cheap, ask what it is actually
matching. The cheap handle for a thing -- its value, its name in your head, its position in a
graph -- is not the thing, and the moment the two can differ is exactly the moment nobody looks.

**And on work safety:** 7d has no push rights, so what protects their output is that refs live in
the shared `.git` rather than in their `/private/tmp` worktree. Committed work survives the session;
uncommitted work would not. They hold none. The exposure was 7f's alone and it is closed.

## 0ab. The rebuild ran. 28 of 28 on today's images, and three engines refuse to start — my omission.

Operator ran it at about 00:50Z. **All 28 containers are on 2026-09-15 images**, so the six inert
fixes are live. Three containers are in a restart loop:

```
meridian-quote-engine        Restarting (1)
meridian-gridiron-engine     Restarting (1)
meridian-gridiron-cfb-engine Restarting (1)
```

**The cause is in the command I gave, not in the rebuild.** All three fail closed on purpose:

```
RuntimeError: MERIDIAN_ENGINE_COMMIT is absent — the quote engine refuses to start
(amendment 12: every fill/observation row stamps its binary; build the image with
--build-arg GIT_COMMIT=$(git rev-parse HEAD))
```

They stamp every row they write with the binary that wrote it, and they will not run unstamped.
My command omitted the build argument. **This is a guard working exactly as designed** -- it would
rather not run than write rows whose provenance is unknown, which is the opposite of every defect
found today.

**Cost of being down is paper tape, not money.** All three are shadow systems; nothing places an
order. What is lost is quote-engine fills and gridiron observations for as long as they are stopped.

**Why the first fix did not take.** The image was never rebuilt -- same build time, and
`MERIDIAN_ENGINE_COMMIT=` present but **empty**. The compose file declares the argument as
`GIT_COMMIT: ${GIT_COMMIT:-}`, which resolves from the **environment**, and `sudo` strips the
environment. `scripts/deploy_engine.sh` does `export GIT_COMMIT` *and* `--build-arg`; I passed only
the second. The working command sets it for the sudo'd process:
`sudo GIT_COMMIT=$C docker compose ... build ...`.

**Why not the project's own script.** It refuses when tracked files are modified, on the correct
reasoning that the stamp would then name a commit that does not describe the built image. On prod
65 tracked files are modified relative to `HEAD` (a5fa9cf) purely because I have staged files from
`origin/main` all day without moving `HEAD` -- **my staging method defeats this guard by
construction.** After a move to origin/main, two would remain.

**And a hard reset is out, measured before recommending it.** The two remaining files are the
softness snapshot CSVs, which the daily read appends to and which the image does COPY:

| file | on disk | in origin/main |
|---|---:|---:|
| kalshi softness snapshots | 215 lines | 97 |
| polymarket softness snapshots | 175 lines | 93 |

`git reset --hard` would destroy **200 rows of collected measurements** that exist nowhere else.
So the stamp names the code, two data files in the image are ahead of it, and that deviation is
recorded here rather than hidden -- no engine reads those CSVs.

**And there is a provenance trap in the obvious fix.** `scripts/deploy_engine.sh` exists for this
and takes the stamp from `git rev-parse HEAD`, but prod's HEAD is `a5fa9cf` while the code on disk
is `origin/main` at `46573e7`, because files are staged by checkout without moving HEAD. Using the
script would stamp every row with a commit that is not the code. Checked before recommending: the
tree differs from `origin/main` in **two files**, both prod-generated softness CSVs, so `46573e7`
is a truthful stamp and `a5fa9cf` is not.

## 0ac. MEASURED LIVE: the gate refused 1,608 plays and opened nothing

The rebuild landed, the three engines are up with the correct stamp, and the counter that shipped
with it answered the question the same night.

| | |
|---|---|
| live football window | 00:28:05Z to 01:22:03Z, **54 minutes** |
| plays refused for staleness | **1,608** |
| positions opened | **0** |
| rows written | **0** |
| gate limit in force | 30.0s |
| live pass rate | **0 of 1,608** |

**This is the whole point of the counter.** Without it tonight reads "the strategy found no
opportunities". With it, tonight reads "the gate refused every play and never opened one". Those
are opposite conclusions from an identical empty table, and the number separating them was being
computed and thrown away until this afternoon.

**It confirms the replay and the ceiling.** The replay put the pass rate at 0.23% of live time and
7d showed five reasons that figure is a **ceiling** rather than an estimate. Live it came in at
**zero**, which is under the ceiling, in the direction all five gaps predicted.

**And it settles the operator's strategy as an executable rule, separately from whether it has
edge.** The drift study says the price does not move at the trigger. This says that even if it did,
the engine cannot act on it at 30 seconds, because ESPN publishes a play a median 53 seconds after
it happens. Two independent reasons, one about the market and one about the plumbing.

## 0ad. Being 53 seconds late does NOT cost us the move — so raise the limit

The operator asked why I was lukewarm about raising the freshness limit, and the honest answer is
that I had not measured the thing that decides it. Now I have. NFL midfield triggers, 185 of them
across 16 games, splitting the price move around the moment the play reaches us:

| | ¢ |
|---|---:|
| move **before** we see the play (play happens → we receive it) | +0.291 |
| move **after** we see it (we receive it → +5 min) | **+0.776** |
| total | +1.066 |

**73% of the move is still ahead of us when the play arrives.** We are late, but we are not
structurally too late -- the market has not already absorbed it. That refutes the reason I had for
hesitating, and the operator's instinct was the right one.

**So raise it.** A 30-second limit the feed can never satisfy means the engine never trades at all,
which is not caution, it is a permanent refusal dressed as one. 60-75 seconds matches what ESPN
actually delivers.

**And the real blocker is elsewhere, which is why raising it will not make money.** The whole move
is about **1¢** and a taker round trip costs roughly **3¢**. Capturing 73% of 1.066¢ is 0.78¢
against a 3¢ cost. The drift study said the same thing from the other direction: the trigger's
interval spans zero on both leagues.

**Two different claims, and I had been running them together.** "We are too late" is false. "The
move is too small to pay for the trade" is true. Only the second one is a reason not to trade, and
it has nothing to do with speed.

## 0ae. Table tennis is now running 345 games a day. The scan has seen 68 of them.

The operator asked for edge in table tennis. The blocker was never the market -- it was that we
could barely measure it. That changed today.

| date | TT games on tape | with a pre-game close |
|---|---:|---:|
| 2026-09-13 | 14 | 8 |
| **2026-09-14** | **349** | **342** |
| 2026-09-15 (partial) | 345 | 85 so far |

**345 games a day, 98% of them with a two-sided pre-game close.** That is the event-limit fix at
10:28Z and the cadence fix at 11:10Z landing. Before today the recorder was capped at 50 events per
competition and sweeping hourly.

**The scan's 68 settled table-tennis bets are not a defect.** It ran at 10:07Z, before most of
09-14's matches had finished, and its own filter only scores games finished four hours earlier.
**Tonight's 04:40Z run sees the whole of 09-14: roughly 342 games instead of 68, a five-fold jump,
growing by ~345 a day.**

**For scale against everything else we have:** MLB gives 10-15 settled games a night and clears the
power floor on Wednesday. CFB gives ~117 but only on Saturdays. NFL gives 15 a week. **Table tennis
gives 345 a day.** It is, by a wide margin, the fastest-accruing market in the programme, and it is
the one the operator picked out.

**What the first 68 bets hint at, stated as a hint and not a finding.** Buying YES in the 0.50-0.60
band lost 22.9¢ per contract, interval [−42.3, −3.5], on 22 games. Max |t| across the 12
non-degenerate tests is 2.32 against a Bonferroni threshold of 2.87, so **it does not clear
multiplicity on 68 bets.** With 342 it is testable properly, and with a week of tape it is
testable per competition, which matters because the four Setka competitions are different leagues
in different countries.

**The open question is settlement, not tape.** 342 games have a close; the settlement cache holds
138 table-tennis entries. Whether the venue settles all 342 is unknown and tonight's run answers it.

## 0af. The LIVE market is not priced right — and it is not measurable either. One lead, killed.

The operator's objection was correct and my pregame answer did not address it. Everything I had
reported was **pre-game**. In-play is a different market and it is the one place efficiency has
never been established.

**In-play CFB, 33,815 settled bets across 140 games. The shape is not flat:**

| price band | implied | realised | lift |
|---|---:|---:|---:|
| 0.0-0.3 | — | — | −1.1 to −1.4 pp |
| **0.3-0.7** | — | — | **+6.5 to +7.4 pp** |
| 0.7-1.0 | — | — | +3.1 to +3.9 pp |

Four consecutive mid bands underpriced by about 7 points. Pregame CFB, by contrast, is calibrated
to within 0.6pp on 117 games. **So the live book is measurably worse-behaved than the pregame
book** -- which is what the operator said and what I had not checked.

**The lead: 0.30-0.70 with a spread of 1¢ or less.** Gross **+10.87¢ [+0.16, +21.58]**, n=3,400,
G=84. Net of the taker fee, **+8.94¢**. That excludes zero on the gross and would be the largest
edge this programme has ever measured.

**Three checks, and it does not survive.**

1. **Per game: 41 of 84 games have a positive mean.** A coin flip. A real 10¢ edge shows up in most
   games; this shows up in half. The top three games carry 24% of the absolute total, with
   per-game extremes of ±60¢ on one to seven observations.
2. **Spread buckets are not monotone.** Tight +10.87, medium +3.57, wide +5.47. If tightness were
   the mechanism there would be a gradient.
3. **Tight spread does not help elsewhere.** Outside the band it gives +2.87 and −0.20, while the
   *widest* bucket at 0.70-0.95 gives +5.88. The story does not generalise.

**So: a post-hoc region, driven by half the games, with no coherent mechanism. Dead.**

**What survives is more important than the lead.** Pooled in-play is **+2.56¢ [−3.57, +8.69]** on
114 games. That interval is ±6¢ wide. **We cannot detect anything smaller than roughly 10¢
in-play, so "the live market is efficient" is not established — we are blind to it.** 140 games is
the entire in-play CFB sample and it arrives once a week.

**The only market that reaches in-play power quickly is table tennis at 345 games a day.** In-play
table tennis is currently 320 rows across 194 games, because the live recorder does not cover it.
That is the single highest-value thing left to build.

## 0ag. The spread IS the adverse-selection premium. Measured on 223,303 maker fills.

Every analysis tonight was about **taking**. This is the other side, and it is the most structural
result of the session. 223,303 settled shadow maker fills, ~160 games per bucket:

| quoted spread | fills | G | edge earned | adverse move | **net P&L** |
|---|---:|---:|---:|---:|---:|
| under 2¢ | 99,879 | 163 | +0.50¢ | −3.65¢ | **−1.56¢** |
| 2-4¢ | 57,290 | 158 | +1.18¢ | −4.42¢ | **−1.07¢** |
| 4-8¢ | 42,895 | 157 | +2.56¢ | −6.26¢ | **−0.73¢** |
| 8¢ and wider | 23,239 | 155 | **+5.29¢** | **−9.97¢** | **−1.02¢** |

> **QUALIFIED by §0aw, same night.** Two things below are weaker than they read. (1) `edge earned`
> is the band's own half-spread and `adverse move` is the mark-to-mid move; a resting quote fills iff
> the move exceeds the half-spread, so that *decomposition* is largely an identity. Only the **net**
> column is a measurement (it marks to settlement, which I verified). Any argument from the
> earned-to-adverse *ratio* — including my own "1.88× implies a 23.5¢ loss at 12.5¢ earned" — is
> built on algebra and is withdrawn. (2) **The flatness is estimator-dependent.** This table is
> fills-weighted. Equal-weight game means give −2.65, −1.53, −1.11, −0.78 — not flat, monotonically
> improving, and the widest band no longer excludes zero. Making still loses on both. "The spread is
> *exactly* the adverse-selection premium" does not survive the change of estimator.

**The edge you earn rises ten-fold with the spread. The adverse move rises faster. The net is flat
at about −1¢ in every bucket.** That flatness is the finding: the spread is not a gift, it is
priced compensation for trading with someone who knows something. Quote into an 8¢ spread and you
collect 5.29¢ and lose 9.97¢ to the market moving against you before settlement.

**This closes the loop on why nothing works.** Taking loses because the half-spread is 2.5-7.5¢
and no directional signal we have measured exceeds it. Making loses because the spread is exactly
the adverse-selection premium. **Both sides of the book are priced**, and that is a real answer
rather than an absence of one.

**What it implies about where edge could exist.** Not in the prices -- they are internally
consistent. It would have to come from information the venue does not have: a better model of the
sport, or genuinely faster data. We are **53 seconds slow** on plays, so not faster. That leaves
the model, which is where the operator's cricket thesis lives and where a table-tennis model at 345
games a day would be testable.

*Caveat named: these are gross figures, before any maker fee. If makers pay the taker schedule the
numbers are worse; there has never been an observed maker rebate on this venue.*

## 0ah. Kalshi vs Polymarket arbitrage: the venues agree to half a cent, and 492 CFB games cannot be compared at all

The operator asked to look deeply at cross-venue arbitrage. Two findings, one negative and one
actionable.

**The join exists and is mostly unpopulated.** `kalshi_games` carries `polymarket_event_slug`,
`espn_game_id` and team codes:

| league | Kalshi games | with a PM slug | with an ESPN id | **joinable to Polymarket** |
|---|---:|---:|---:|---:|
| cfb | 492 | 0 | 0 | **0** |
| wnba | 78 | 78 | 0 | 0 |
| nfl | 32 | 0 | 30 | **14** |

**CFB is where Kalshi has the most tape -- 500,483 `KXNCAAFSPREAD` rows and 394,793
`KXNCAAFTOTAL` -- and not one of its 492 games can be matched to a Polymarket game.** No ESPN id,
no slug. That is the single blocker on cross-venue work and it is ours, not the venue's.

**On the 14 that do join, the venues are the same price.** Tonight's Denver at Kansas City, every
Kalshi quote for the hour before kickoff against the Polymarket quote at that instant:

```
Kalshi  DEN  bid 0.4500  ask 0.4600
Polymkt DEN  bid 0.4550  ask 0.4600
```

**Identical asks, and Polymarket's book is the tighter of the two** at 0.5¢ against Kalshi's 1¢,
held for an hour without moving. Buying either side and selling the other loses 0.5-1¢ before a
combined taker cost of about 3.25¢ (Kalshi 0.07·p(1−p) plus Polymarket 0.06·p(1−p)).

**And that corrects something I said earlier tonight.** I reported median spreads of 5¢ on NFL and
15¢ on CFB. Those are dominated by illiquid market types -- quarter spreads, team totals. The
liquid winner market on the game everybody is watching is **half a cent wide**. The spread is not
uniformly enormous; it is enormous where nobody trades.

**Full scan, all 14 joinable games, 165 aligned samples:**

| | |
|---|---:|
| mean absolute gap between the two mids | **0.40¢** |
| p90 gap | 0.75¢ |
| samples where one venue's bid exceeded the other's ask | **5 of 165** |
| largest crossing ever observed | **1.50¢** |
| combined taker cost at mid prices | **~3.25¢** |

**No arbitrage exists.** The venues track each other to under half a cent on average, the book
crossed at all in 5 samples of 165, and the best crossing in the entire sample is less than half
the cost of executing it. All five crossings ran the same way, buy Kalshi and sell Polymarket, so
there is not even a two-sided pattern to exploit.

**What this does not cover, stated so nobody reads it as broader than it is.** The winner market
only, NFL only, 14 games, sampled every ten minutes. A transient dislocation inside a ten-minute
window would not appear. And the illiquid market types -- spreads, totals, quarters -- are
untested, which matters because that is precisely where a gap is most likely and where Kalshi
holds 900,000 CFB rows we cannot join.

## 0ai. The Kalshi CFB join is buildable: 93 games, zero ambiguous

Followed the blocker to the end. The names differ by mascot -- Kalshi says **"Arizona vs BYU"**,
the map says **"Arizona Wildcats @ BYU Cougars"** -- so a Kalshi name is a *prefix* of an ESPN
name. **That is precisely the containment trap that once produced a fake 20¢ Kalshi edge here,
where "Washington" is a prefix of "Washington State".**

**The safe rule is to require BOTH teams on the same date and demand a unique hit.** Measured:

| | |
|---|---:|
| Kalshi CFB games | 492 |
| join uniquely, away-home | **93** |
| join in the reversed orientation | **0** |
| **ambiguous, rejected** | **0** |
| no match | 399 |

**Zero ambiguous is the safety result.** One team is ambiguous; two teams on one date is not. The
prefix trap cannot fire under this rule, and that should be an assertion in the implementation
rather than a happy observation -- if an ambiguous pair ever appears, reject it and count it.

**Zero reversed confirms the frame**: Kalshi's first-named team is the away team, consistently,
which is the same convention the NFL side showed.

**Why 399 miss.** Only 253 of the 492 fall on dates the map covers at all, so 93 of 253 is the real
rate, 37%. The rest are name variants -- "Miami" against "Miami (OH)", "UL Monroe" against
"Louisiana-Monroe" -- and each one fixed is another comparable game.

**What it unlocks.** 93 college-football games against 14 NFL, in the league where Kalshi holds
**900,000 rows** of spread and total quotes. The NFL arbitrage test found the venues 0.40¢ apart on
the liquid winner market; the untested case is the illiquid spread and total ladders, and this is
the population that makes testing them possible.

## 0aj. Cross-venue CFB: no arbitrage, 72 of 76 games agree to 1.8¢, and 4 need a human look

Built the join and ran it. **93 Kalshi CFB games join uniquely with zero ambiguity**, 76 carry
aligned price samples, and the answer is the same as NFL.

| | |
|---|---:|
| games agreeing within 10¢ | **72**, mean gap **1.80¢** |
| games disagreeing by more | **4**, mean gap **13.50¢** |
| overall mean absolute gap | 2.57¢ |
| combined taker cost | ~3.25¢ |

**No arbitrage.** Even including the four outliers the average gap is below the cost of executing
both sides, and excluding them it is 1.80¢ against 3.25¢. CFB disagrees about five times more than
NFL's 0.40¢, which is what a less-watched market should look like, and still not enough.

**Two false alarms on the way, both caught before they travelled.**

*A 54¢ "arbitrage"* on Oklahoma State at Tulsa: Kalshi 0.245, Polymarket 0.8225. Tulsa won 24-10
and Kalshi had them at 75%, so Kalshi was right and the pair cannot both be the same game priced
honestly. **Not reported as edge.**

*A suspected frame inversion.* That single case looked like Polymarket's YES being the home team
for CFB, which would have inverted every college-football number produced tonight. Tested both
orientations across all 977 samples: as-is gives a mean absolute gap of **2.57¢**, flipped gives
**73.36¢**. **The frame is correct** and the flipped version's tidy-looking sum of 0.991 is
arithmetic, not evidence -- two prices averaging 0.217 will always sum to ~1 when you subtract one
from one.

**The open item is the 4 games, and the obvious explanation fails.** They are not low-confidence
map rows: their mean match confidence is **0.898** against **0.884** for the 72 good ones, so the
map's own score is slightly *higher* on the bad ones. Something else is wrong with those four and
it needs a per-game look rather than a threshold.

## 0ak. The first paper scalp ever placed: opened, forced out 2 seconds later, lost the fee

`paper_scalps` row 1, the operator's own strategy, live, on Denver at Kansas City:

| | |
|---|---|
| entered | 01:33:19.712, NO side (home), at **0.6650** |
| exited | 01:33:21.712, at **0.6600** |
| **holding time** | **2.0 seconds** |
| exit reason | **stale** |
| P&L on $25 | **−$1.20**, of which **$1.01 is fee** |
| refusals that night | **5,600**, for this one fill |

**The gate does not only block entry. When it permits one, it forces an immediate exit.** A play
reaches us a median 53 seconds old; this one arrived just inside the 30-second limit, the engine
entered, and two seconds later the same play was 32 seconds old and the position was closed for
staleness. **The holding time is bounded by 30 seconds minus the play's age at entry**, which is a
second or two, and a round trip costs about 4.8% of the stake at these prices.

**So the strategy as configured cannot hold a position at all.** That is a mechanical fact about
the pipeline, independent of whether the price moves. Combined with the drift result -- no
detectable move at the trigger on either league -- the live path and the market both say the same
thing by different routes.

**This is exactly what the refusal counter was built for.** Without it, `paper_scalps` holding one
losing row would read as "the strategy traded once and lost". With it: 5,600 refusals, one fill,
forced out in two seconds by the same rule that let it in.

## 0al. Table tennis at 5× the sample: the lead is dead, and it died the way flukes die

I did not wait for the nightly. I settled the whole table-tennis backlog by hand out of the
api container (`core.settlements.settler` + `PolymarketGatewayClient`): **350 markets found,
342 settled**, settlement cache 21,542 → 21,752. Tonight's 04:40Z run gets all 342 for free.

The lead under test was §0ag's: buy YES in the 0.50–0.60 band, measured at −22.93¢ per
contract on 68 bets (t = −2.32), i.e. fade it. Here it is on 342.

| band | n | G | implied | realised | gross ¢ | t |
|---|---:|---:|---:|---:|---:|---:|
| 0.3–0.4 | 43 | 43 | 0.351 | 0.326 | −2.53 | −0.35 |
| 0.4–0.5 | 91 | 91 | 0.443 | 0.385 | −5.86 | −1.14 |
| **0.5–0.6** | **97** | **97** | **0.545** | **0.469** | **−7.60** | **−1.53** |
| 0.6–0.7 | 66 | 66 | 0.643 | 0.652 | +0.83 | +0.14 |
| 0.7–0.8 | 26 | 26 | 0.739 | 0.692 | −4.67 | −0.52 |

POOLED n=342 G=342 gross **−3.60¢ [−8.67, +1.47]**. Seven band tests, Bonferroni |t| = 2.69,
max observed 1.53. Nothing clears. G = n on every row: one bet per game, so there is no
clustering to deflate this — the sample is as effective as it looks.

**The manner of death is the finding.** The effect went −22.93¢ → −7.60¢ while the sample
went 68 → 342. It shrank by two thirds as the data grew five-fold, and |t| *fell* (2.32 →
1.53) even though n rose 5×. A real effect holds its magnitude and gains significance as
n grows; a fluke shrinks toward zero at rate 1/√n, which is what this did. This is the
cleanest example the programme has produced of why the pre-registered bar exists, and it
cost nothing because nothing was ever placed on it.

> **CORRECTED by §0bc: the cost figure below is wrong.** Table tennis does not quote ~8¢ wide at the
> point you would trade it. At the LAST pregame quote in the tradeable range (724 markets, median 8.3
> minutes before start) the median spread is **2¢**, giving a total cost of **2.26¢ (median) to 3.73¢
> (mean)** — §0bd, after two wrong single-point bars. So −3.60¢ was *larger* than the median cost, and the sentence below
> argues against the conclusion it supports. **The result is unchanged and dead on its interval alone**
> ([−8.67, +1.47] spans zero); only my reason for it was wrong.

**Even the residue is untradeable.** −3.60¢ is the whole pooled tilt, and it does not exclude
zero. Table tennis quotes ~8¢ wide, so the half-spread alone is ~4¢ before the 0.06·p·(1−p)
taker fee. The mispricing is smaller than the cost of acting on it — the same wall as every
other market in §0: *both sides of the book are priced.*

**What this does not close.** §0ag's capacity finding stands: the venue runs ~345 TT games a
day against a closed pool of ~275 players who each play several times a week. That is the
one substrate here with enough independent clusters per week to test a model that knows
something about the sport, and the Elo pre-registration (`docs/math/tabletennis-rating-preregistration.md`,
K=24, ≥10 prior matches, primary quantity = the Elo coefficient against venue implied
probability) is registered and waiting on sample. A dead price-bucket lead says nothing
about a rating model; they are different hypotheses on the same tape.

## 0am. The nightly scan found four significant cells, and all four are the spread

The 04:40Z scan tested 315 cells (league × market type × price decile) and 4 cleared
Bonferroni at p < 1.59e-04. That is 4 more than chance expects. Before nominating anything
I recomputed them by a second route — per-fill from `scan_rows.json` (19,866 rows) with the
0.06·p·(1−p) taker fee applied at the traded price, against the scan's own per-game
Poisson-binomial — and priced the home-referenced twin beside each one.

| cell (CFB, decile) | n | mean ask | mean bid | YES wins | YES net | NO-twin net |
|---|---:|---:|---:|---:|---:|---:|
| team_first_quarter_spread 0.5 | 114 | 0.602 | 0.486 | 36.8% | **−24.76¢** | +10.28¢ |
| game_third_quarter_total 0.7 | 23 | 0.843 | 0.617 | 47.8% | **−37.25¢** | +12.54¢ |
| game_fourth_quarter_total 0.7 | 40 | 0.873 | 0.622 | 65.0% | **−22.93¢** | −4.20¢ |
| game_first_quarter_total 0.7 | 37 | 0.899 | 0.591 | 62.2% | **−28.28¢** | −4.46¢ |

Every significant cell is a large YES-side **loss**, in a market quoted 11.6¢ to 30.8¢ wide.
And the fade does not rescue them: two of the four twins lose money too. If the YES loss were
a mispricing, the other side would collect it in all four. It collects in two. What both sides
are paying is the width.

**The population says the same thing, monotonically.** Sign of every cell with |t| > 1.96,
cut by median half-spread:

| half-spread | cells | \|t\|>1.96 | YES wins | YES loses | NO-twin wins |
|---|---:|---:|---:|---:|---:|
| ≤ 1¢ | 139 | 28 | 10 | 18 | 17 |
| 1–2¢ | 60 | 11 | 1 | 10 | 8 |
| 2–3¢ | 17 | 5 | 0 | 5 | 3 |
| 3–5¢ | 18 | 6 | 1 | 5 | 3 |
| **> 5¢** | 66 | **35** | **1** | **34** | 11 |
| ALL | 300 | 85 | 13 | 72 | 42 |

In the cheap markets, significant cells split 10 winning / 18 losing — near enough even, which
is what noise looks like. In the wide markets they split **1 winning / 34 losing**. The
one-sidedness is not a property of the sport or the market type; it is a monotone function of
how wide the quote is. A cost effect does exactly this. An edge could not: an edge has no
reason to be found only where trading is most expensive, and no reason to point the same way
every time. The scan's own cost-conditioned table reaches the identical conclusion from the
per-game side — 8 significant cells at ≤1¢ against a null of 6.8, i.e. **zero excess** once
the expensive markets are excluded.

**AMENDMENT, same night, game-clustered.** The table above is per-fill, which I labelled as an
upper bound. Here it is again with one observation per game inside each cell, which is the estimator
that should have been quoted first. Cells carry 2.52 fills per game in the cheap band, so roughly a
√2.5 deflation is expected and is what happens:

| half-spread | cells | \|t\|>1.96 per-fill | **per-game** | null expected | excess, in sd |
|---|---:|---:|---:|---:|---:|
| ≤ 1¢ | 139 | 28 | **14** | 7.0 | **+1.9σ** |
| 1–2¢ | 60 | 11 | 6 | 3.0 | +1.2σ |
| 2–5¢ | 35 | 11 | 9 | 1.8 | +4.1σ |
| **> 5¢** | 66 | 35 | **27** | 3.3 | **+9.5σ** |
| ALL | 300 | 85 | 56 | 15.0 | — |

The σ column widens the binomial sd by √2 for the YES/NO pairing, as the scan's own module does, and
is still an **upper bound on significance** because cells share games and are therefore positively
correlated — a permutation null is the only honest one, and it would widen these further.

**This closes the loose end and does not change the conclusion.** The cheap band's apparent excess —
14 against 7 — is **1.9σ before any correlation correction**, which is noise. The wide band's is
9.5σ. So the clustered estimator says the same thing as the per-fill one, more honestly: **there is
no detectable excess of significant cells where trading is cheap, and all of the excess lives where
it is expensive and points one way.** That is the cost, and it is not hiding an edge underneath.

**Estimator label.** My table is per-fill and unclustered, so these |t| are upper bounds —
cell 1 is 114 fills over 63 games, so its true t is roughly t/√1.8. The scan's clustered
per-game version is the one to quote for any nomination. The agreement between the two is on
the *pattern*, which is what is being claimed; I am not claiming the magnitudes to a cent.

**Nothing nominates.** The best fade in the table, +10.28¢, carries an unclustered t of 2.31
that falls to ≈1.7 once clustered, against a Bonferroni bar of 4.30 at m_eff = 299. It goes on
the held-out list, not into a strategy.

## 0an. The 30-second gate is not a threshold, it is a wall: measured on 200 games

The engine's only trade lasted one cycle. 7d read it as structural rather than unlucky and
argued the mechanism: a pass window is `MAX_AGE_S` minus lag seconds wide, so entries admitted
near the boundary are stale on the next cycle by construction. That is a claim about the shape
of the lag density below 30s, and it was made from one trade in one game. I measured the
density directly.

Play arrival lag = `first_seen_at − wall_clock` on `espn_cfb_live_plays`, **35,521 plays across
200 games since 2026-09-01** (month-boundary floor so the partition prunes):

| MAX_AGE_S | plays that clear the gate | window left to hold them |
|---:|---:|---:|
| 20 | 0.5% (and ~half of that is clock junk) | ≤ 0s |
| **30 (live today)** | **3.0%** | **≤ 6s = 3 cycles** |
| 45 | 21.7% | ≤ 21s |
| 60 | 54.8% | ≤ 36s |
| 75 | 77.6% | ≤ 51s |
| 90 | 84.8% | ≤ 66s |

Median lag **57.7s**. First percentile **24.0s**. Minimum honest lag ~20s; the 85 rows with
negative lag (0.24%) are clock artifacts, and they are most of what sits under 20s.

**7d's mechanism is confirmed, and it is worse than argued.** It is not that admitted plays
*tend* to sit near the boundary. At 30s the entire admissible set lives between 24s and 30s,
because p01 is 24.0s — **no play in 200 games arrived with more than six seconds of gate life
remaining.** Last night's single game showed it exactly: of 171 plays, 0 arrived under 20s,
0 under 20–30 except 5, and the one trade the engine opened was evicted by the same gate that
admitted it, two seconds later, for a $1.20 loss of which $1.01 was the fee. The engine is not
refusing trades it narrowly dislikes. It is admitting only from a sliver where an immediate
stop-out is arithmetically forced.

**The floor is the feed, not our configuration.** p01 = 24.0s across 200 games means no setting
of `MAX_AGE_S`, no faster poll, and no code change on our side buys sub-20s information. That
is ESPN's publish delay. Any plan premised on beating the market to a play is dead on this
substrate, and it is dead for a reason we cannot engineer around.

**What raising the gate buys, stated honestly: sample, not profit.** §0 already establishes
that taking loses because the half-spread exceeds every signal we have measured, and nothing
here contradicts that. What 30s does is prevent the question from being *asked* — 1,608 plays
refused and zero opened over 54 minutes of football, then one admission that could not survive
a cycle. At 60s the same engine sees 54.8% of plays with 36 seconds to hold them, which is the
first configuration under which the in-game scalp produces a measurable number instead of a
count of refusals. Nothing is ever placed with real money, so the cost of finding out is zero.

**My recommendation, reversed from earlier in the programme.** I argued for caution on raising
this. The caution was not supported: I had not measured the density, and the density says 30s
is not a conservative setting of a dial, it is an off switch dressed as a dial. Raise
`MAX_AGE_S` to 60. The decision is still the operator's; what has changed is that it is now a
decision with numbers under it.

## 0ao. A hardcoded 15¢ cap decided what "the spread IS the adverse-selection premium" could see

§0ag is the most structural result the programme has, and tonight I found the boundary it was
measured inside. `core/quote/adverse_selection.py` carries `MAX_SPREAD = 0.15` with this comment:

> *A spread wider than this is not a market-making opportunity, it is an empty book with two stale
> orders in it.* … *Deep rungs carry measured 22-26¢ spreads and do not trade.*

That is not a preference, it is an empirical claim, and nobody had checked it. `shadow_quote_fills`
confirms the reach: 227,275 fills, **maximum `spread_at_quote` = 0.1500**, p99 = 0.14. Every maker
number we have ever published is conditioned on spread ≤ 15¢.

**The premise is false in its strong form.** CFB snapshots joined to `market_trade_stats`,
month-boundary floor, since 09-01:

| quoted spread | observations | median shares traded | % with zero volume | mean open interest |
|---|---:|---:|---:|---:|
| < 2¢ | 96,402 | 2,682 | 17.1% | 78,599 |
| 2–4¢ | 40,297 | 2,923 | 12.7% | 17,481 |
| 4–8¢ | 43,744 | 2,444 | 10.8% | 13,102 |
| 8–15¢ *(cap)* | 40,425 | 1,546 | 15.7% | 8,618 |
| 15–25¢ | 36,511 | 391 | 21.6% | 3,536 |
| **25¢+** | **65,751** | **131** | **30.5%** | **1,430** |

The comment is right that these books are thin — 55× less open interest than the sub-2¢ book. It is
wrong that they do not trade: median 131 shares at 25¢+, and **69.5% of those observations have
non-zero volume**. And this is not a fringe: **32% of CFB quoted observations sit above the cap.**

**What I tried first, and why I threw it away.** I computed a "maker upper bound" per spread band
from the scan's settled rows — rest on both sides, average the two outcomes. It printed +16.73¢ at
25¢+ with a per-game t of 88. It is worthless: `((ask − y) + (y − bid))/2` cancels `y` exactly, so
the column is half the spread minus fees and contains no settlement information whatsoever. The
t-statistics measure how precisely we know the spread. This is the sixth instrument in this
programme to cut by spread and then recover its own algebra (`forced-gradients`), and the tell was
the same as always: a t in the dozens where the substrate cannot support one.

**So the question stays open, and it is open in the honest direction.** A maker's P&L is the spread
minus adverse selection, and adverse selection is *which* side gets hit, which no identity gives
you — it has to be observed. The observed trend argues against the wide book: earned rose
0.50→5.29¢ across the four measured buckets while adverse rose 3.65→9.97¢, a ratio of about 1.88,
and at 12.5¢ earned that ratio predicts a 23.5¢ loss. But that is extrapolation past the last data
point, and the mechanism need not be constant — adverse selection scales with how *informed* the
flow is, and whoever crosses 25¢ in a dead quarter-total market is not obviously informed. The scan
says takers on **both** sides of those books lose (−17.65¢ and −20.08¢ at 25¢+, summing to the
width), so the width is genuinely being paid to someone.

**What I changed, and what I deliberately did not.** `MAX_SPREAD` now reads
`MERIDIAN_QUOTE_MAX_SPREAD` with the default **unchanged at 0.15**, so no live behaviour moves until
someone decides it should, and three tests pin it — including one asserting the *gate* admits a 30¢
quote once raised, not merely that the constant changed. All three were mutation-checked against a
re-hardcoded constant; two fail, as they must. I did not raise the default: that is a live-behaviour
change to four modules that share this constant, and it belongs to the operator, not to a caveat.

> **ANSWERED by §0ax, same night: NO, and not for the reason expected.** The fill rate in the widest
> band is **0.44%** against 10.0% in the tightest — 145 fills in a whole Saturday — while 0.25–0.50 is
> the *second most quoted* band in the sample. The wide book is heavily quoted and almost never trades
> with you. Observed net also tracks a geometry-only null within about a cent in nearly every band, so
> the mark-to-mid instrument adds little beyond its own algebra. The hypothesis is closed on
> tradability rather than on the sign of a P&L.

**The registered hypothesis, before any data.** Quoting at the touch in books wider than 15¢ earns
more than the adverse selection it attracts. Falsifier: net P&L per contract ≤ 0 on ≥100 game
clusters. It cannot be tested on anything we currently hold, because the cap prevented the fills
from ever being recorded.

## 0ap. The paper book's first run with table tennis in it agrees with §0al, from a route I did not choose

The 04:40Z book scored **35 registered strategies** (up from 24) against the venue's own
settlements, 22,270 of them served from the cache I warmed by hand last night — 1 live fetch for
the whole run.

**Table tennis, now scored by strategies registered before I looked at any of this:**

| arm | bets | G | mean bet | 95% CI | verdict |
|---|---:|---:|---:|---|---|
| `tt_home_fav_yes_60` | 101 | 101 | −2.92¢ | [−11.96, +6.12] | spans 0 |
| `tt_home_dog_yes_40` | 63 | 63 | −3.15¢ | [−14.80, +8.50] | spans 0 |

That matters more than another band table of mine would. §0al killed the 0.50–0.60 lead using bands
I chose after seeing the tape; these two arms were registered in the ladder beforehand, are scored
by a different code path, and land in the same place — slightly negative, interval spanning zero.
G = n on both, so no clustering is hiding in them. Two independent routes, one of which could not
have been tuned by me, now say table tennis prices are not exploitable by price-bucket rules.

**The one line that excludes zero is the same one as §2b, unchanged.** `wnba_spread_yes_80_100`
still reads +5.78¢ [+2.96, +8.60] on n=101 G=40, with its home-referenced twin
`wnba_spread_no_00_20` at −2.05¢ [−8.27, +4.16]. Identical to the 09-14 read because the WNBA
season is over — tonight's coverage line says *0 closes, 1,582 excluded by since* — so no new games
entered it. It is the away-team confound for the third time, it is not new evidence, and it is not
tradeable this season regardless. Nothing about tonight's run updates it in either direction.

**MLB: six arms registered on one settled game are now scored on nine, and all six are still
`UNDERPOWERED (G<25)`.** `mlb_winner_away_all` +25.51¢ [−1.47, +52.49] against `mlb_winner_home_all`
−28.88¢ [−55.85, −1.92] is the declared-complement pair behaving exactly as a complement pair must;
neither is evidence. MLB clears the power floor later this week, not tonight.

## 0aq. The Elo harness runs today and correctly returns nothing; eligibility is closer than the settled set shows

7d built the fit harness (`core/tt/{elo,fit,rule}.py`, `cfb/run_tt_elo.py`, 18 tests, suite 2249)
against the registered spec, and the deliverable is that **it runs on today's real data and produces
zero eligible matches without crashing** — `NOT YET` distinguished from `FAIL` inside the rule rather
than in prose. A harness you first execute on the day the data arrives is a harness you debug then.

**I verified it by parsing the slugs myself**, independent of their code, over all 750 TT board slugs
(not just the 356 settled), zero unparsed:

| competition | players | max matches, any player | settled (7d) |
|---|---:|---:|---:|
| setkameua | 171 | 14 | 256 |
| setkamecz | 50 | 7 | 48 |
| setkamemd | 48 | 7 | 39 |
| setkawoua | **6** | 5 | 14 |
| **total** | **275** | — | 357 |

Three things this settles. The pool is **exactly 275** — the capacity figure in §0ae was a board
count and it is confirmed to the unit. **Zero tokens appear in more than one competition**, which 7d
measured as 0-of-180 on the settled set and I now confirm as 0-of-275 on the full board, so the
closed-pool-per-competition assumption the whole capacity argument rests on holds on the larger
population too. And **`setkawoua` has a six-player pool**, so it can never meet the ≥25-cluster
floor — permanently `NOT YET`, which the runner prints rather than leaving it looking pending.

**One thing my route sees that the settled view cannot: 34 tokens already carry ≥10 matches on the
board.** Eligibility is bounded by settlement, not by play. The settled max is 9 (hence zero
eligible today), but the matches that make 34 players eligible have already been *scheduled or
played* — they simply have not settled yet. That is consistent with 7d's +1/+2/+3-day curve and
tightens the expectation rather than loosening it.

**A correction to me, which I accept.** I told 7d that "a large Elo coefficient with a small design
effect is a defect signature." Their positive control has β = +1.09 with deff 1.17, where the effect
is real by construction — so my rule would have flagged a true result. `deff` tracks the *imbalance*
of appearances, not the presence of an effect: with balanced pairing the player clusters do not
concentrate residuals and deff sits near 1 either way. The settled set is balanced (180 tokens, 712
appearances, max 9), so the heuristic as I stated it would probably have fired on a genuine finding
and cost us an argument about a number that was never evidence. Narrowed: the signature is a large
coefficient with deff ≈ 1 on an **unbalanced** panel. `deff` is reported next to the appearance
distribution and is **not** a verdict input.

**And a fourth proxy error today, theirs, caught by them.** Their batched mutation runner reported
"18 passed" for an Elo sign flip — a false negative from the runner, not a gap in the tests; grepping
to confirm the mutation had landed turned it into 5 failures. A mutation runner that reports "not
caught" without evidence the mutation applied is measuring its own plumbing. Same family as my
`grep -v " Up "` that matched nothing because the separator was a tab, and my `pgrep -f nightly_scan`
that matched my own command line and reported the job still running after it had finished.

## 0ar. Close age against both populations, and a ratio in our own comment that cannot be re-derived

7d ran the close-age table on both populations — every close with `ko < now()`, and the stricter
`ko < now() − 4h` that the scan actually scores.

| league | population | closes | median | p90 | frac > 1h |
|---|---|---:|---:|---:|---:|
| cfb | both identical | 15,818 | 0.1m | 56.3m | 0.095 |
| nfl | both identical | 5,441 | 0.2m | 0.4m | 0.002 |
| mlb | both identical | 165 | 11.5m | 16.5m | 0.000 |
| tabletennis | `ko < now()` | 413 | 7.5m | 61.7m | 0.107 |
| **tabletennis** | **`ko < now() − 4h`** | **372** | **7.5m** | **66.6m** | **0.118** |
| cricket | both (n=2) | 2 | 63.7m | 110.7m | 0.500 |

**The two populations are identical everywhere except table tennis**, because a four-hour lag can
only drop games that started inside the last four hours and only Setka Cup runs densely enough for
that to bite. **And the stricter population is the worse one, 0.107 → 0.118.** That is the result
rather than the table: had the looser population been the pessimistic one, TT staleness could have
been dismissed as a boundary artifact of counting just-started matches. It is not an artifact — the
looser population was *understating* it.

**A close is stale in units of the thing being priced.** There is no end-of-match signal for TT, so
7d bounded match duration from the data: across same-player consecutive matches the minimum gap is
30 minutes, since a player cannot start a second match before the first ends. **I re-derived this
independently over the full 750-match board (1,225 gaps, against their 534): minimum exactly 30.0m,
zero gaps below it.** On that bound a median TT close is 0.25 matches stale and the p90 is over two
whole matches before the one being priced — and 30m is the generous end, so at a true 15–20m every
figure roughly doubles.

*I nearly filed a correction here and it would have been wrong.* Minimum 30.0, p01 30.0, p05 30.0,
median 90.0 are suspiciously round, and my first reading was that TT is scheduled on a 30-minute
grid, which would make the minimum a scheduling artifact carrying no information about duration.
The check refutes that: all 750 start times sit on a **5-minute** grid (every start is a
5-minute boundary, all 750 with zero seconds), so gaps of 10, 15, 20 and 25 minutes are perfectly
schedulable and **not one occurs**. The 30-minute floor is empirical, not structural. Their number
survives a test I expected it to fail.

**And the scan's own ratio is not reproducible — it is my comment and it is wrong.** `cfb/run_scan.py`
carries `tabletennis 0.405 / 5.852` in a comment with **no duration constant anywhere in the file**,
and the two figures are not consistent with any single duration: 0.405 against a 7.5m median implies
~18.5m, 5.852 against a 61.7m p90 implies ~10.5m. One of them is wrong and neither can be
re-derived. A ratio living in a comment, with no constant and no test behind it, is a claim nothing
can falsify — the `a-description-has-no-test` failure in its purest form, written by me.

**Against the 0.10 bar:** cfb sits at 0.095 on both populations — the scan's rounded "10%" is this
number — TT is above on both, nfl and mlb are nowhere near. The threshold currently separates
exactly the league the cadence work was about, and cfb is close enough that a small regression
crosses it.

## 0as. The Elo fit is now deployed and fires itself — after dying on its first real run

Installed at **09:00Z daily**, not the 05:20Z the script's header first carried. The scan is the job
this must not disturb and it does not finish at a fixed time: measured finishes on the last four runs
are 05:26, 06:10, 07:24 and 10:16, so 05:20 would have landed inside its window most nights and added
DB contention to a job that seq-scans 62M rows — the exact thing choosing a separate script was meant
to avoid. 09:00Z clears the worst observed finish and precedes the 10:40Z MLB read. The header now
states the deployed time and the reason, so the comment and the crontab cannot drift apart.

**Then I ran it once by hand instead of trusting the install, and it failed.**
`FileNotFoundError: /opt/meridian/artifacts/reads/settlements.json` — with the file sitting on the
box. The container mounts `-v /opt/meridian:/app`, so a host path handed to it resolves to nothing
inside. A cron line that has never executed is a hypothesis, and this one was false.

**The failure path is what made it cheap**, and it matters more here than anywhere else in the fleet:
this job pushes *only on a verdict transition*, so a permanently broken run is otherwise
indistinguishable from "nothing changed" — forever, silently, on the one channel meant to carry the
result we have been waiting three days for. It pushed `TT ELO FAILED exit 1` instead. That design was
7d's and it earned its keep on day one.

**Fixed, and the guard needed two corrections of its own.** The in-container spelling is now separate
and named (`COUT`/`CSTATE`) rather than the host variables reused. The test I wrote to catch "the
exact defect" grepped for a literal `/opt/meridian` and **passed on the real bug**, because the defect
was the *variable* `$OUT`. The second version then flagged the legitimate shell redirect `> "$F"` —
evaluated by the shell on the host — and so failed on the fix rather than the bug. Both directions are
now mutation-verified: 6 pass on the fix, 2 fail on the bug. Suite 2260.

**Running clean on prod:**

| competition | settled | players | eligible | verdict |
|---|---:|---:|---:|---|
| setkameua | 256 | 113 | 0 | NOT YET — 0 predicted < 200 |
| setkamecz | 48 | 32 | 0 | NOT YET |
| setkamemd | 39 | 29 | 0 | NOT YET |
| setkawoua | 14 | **6** | 0 | NOT YET — pool of 6 can never meet the ≥25 floor |

State recorded, nothing pushed, which is correct: a first run has no transition by definition. Nobody
has to watch this now. It will say `PASS` or `FAIL` on setkameua the night the floors are met.

## 0at. Two tables live code depends on exist only because a script was once run by hand

`espn_cfb_backfill_games` (55 rows) and `espn_cfb_backfill_plays` (9,537 rows) have **no Alembic
migration and no model**. They exist solely because `archive/cfb/backfill_cfb.py` was executed on that
box once. A database rebuilt from migrations would not have them.

> **CORRECTED, same night, by 7d.** I first wrote here that `core/feeds/espn_cfb_recorder.py` — live
> code — reads these tables, and told the operator a clean rebuild would break a running recorder on
> startup. **That is wrong.** The single hit under `core/` is at
> `core/feeds/espn_cfb_recorder.py:353` and it is a `#:` **comment**, written by 7d this morning,
> describing what `run_making_touch` does. I ran `grep -rln`, got a filename, and promoted it to a
> code path without opening the file — the fifth time today an instrument returned a grep hit
> standing in for a code path, and the second time the thing measured was one of our own comments.
> **No long-running service reads these tables and the fleet-restart argument does not apply.**
>
> The accurate severity sits between what each of us said. Classifying every reference myself:
> 0 code / 1 comment under `core/`, and **13 consumer scripts under `cfb/`** (7d's count, confirmed
> exactly). Six of those thirteen are **on a cron** — `run_ladder_calibration`, `run_making_touch`,
> `run_ladder_rv`, `run_overshoot`, `run_kalshi_dk_lag`, `run_longshot_shadow`, all in
> `prod_weekend_read.sh`. So a rebuilt schema breaks nothing on startup, but it breaks the **daily
> 10:40Z MLB read and the Monday 10:20Z gate** the next time they fire. That is a real scheduled
> dependency and it is not an availability incident.

7d flagged it and put the loss at 44 games. **I doubted the number and I was wrong.** My first check
asked whether each backfill game exists in the live table at all, which gave 36 and looked like an
overstatement. That is the wrong decomposition — the live table can hold a game it never saw finish
(§ESPN recorder stops before post):

| backfill game | n | final score recoverable from live? |
|---|---:|---|
| no live state row at all | 36 | no — predates the recorder |
| live rows, never reached `post` | 8 | no — live has the game but not its end |
| reached `post` in live | 11 | yes |
| **irrecoverable finals** | **44** | — |
| carrying a DraftKings closing spread | **55** | not held anywhere else |

44 and 55, exactly as 7d stated. The refinement that mattered was theirs, not mine.

**Why this outranks everything else queued.** It is the only outstanding item whose loss is
*irreversible*. The other open work — the deployment-drift detector, the close-age follow-ups,
the wide-spread maker question — costs time if delayed. These 44 finals and 55 closing spreads cannot
be reconstructed by any code we could write, because the games finished before the recorder existed.
7d also named the failure mode that would have caused it: an agreed task that keeps losing to newer,
more interesting ones, which is precisely how the meridian-7f rescue nearly went wrong four hours ago.

**Merged and staged, deliberately NOT applied.** `b4e9f1c73d85_cfb_backfill_tables` is on prod's
disk; prod's `alembic_version` is still `a1c7e35b9d20`. I am leaving it that way until the next
rebuild, and the reason is the standing restart trap rather than caution: **advancing the DB head
past what the running images contain is what makes a container crash-loop on restart** with
`Can't locate revision`. Every container on the box was built before this migration existed. On prod
the migration is a pure no-op for data — the tables are already there with their 55 and 9,537 rows
and it is `CREATE TABLE IF NOT EXISTS` — so its *only* effect on this box would be to move
`alembic_version` forward and widen the blast radius of the next restart for nothing. It lands with
the images, or not at all.

**It also retires an honesty caveat.** The post-beats-backfill precedence is currently "verified on
prod, not tested," because the query reads a table a migrated schema does not have. The migration makes
that test writable.

## 0au. The drift detector works, and its first answer retires the belief that justified building it

I asked 7d to build an instrument reporting where the **running** code differs from `origin/main`,
because that class cost us five times today. Its first run says the fleet is current.

| | |
|---|---|
| containers scored | 28, plus 1 UNKNOWN (`meridian-postgres`, no python in the image) |
| drift | **exactly 1 of 214 files**, on all 28 |
| the file | `core/quote/adverse_selection.py` — my `MERIDIAN_QUOTE_MAX_SPREAD` change |
| merged | 05:36Z, against images built **00:25–00:27Z** — five hours earlier |

**So "six fixes written and inert" was true when I said it and had expired by the time it was
measured.** I verified that independently rather than taking it: images built 00:25–00:27Z, and my
own `markets_seen` fix is present inside the *running* recorder. The four fixes we both believed were
inert are all live.

**And the detector's only finding is the evidence for the one deployment decision still open.** The
single drifting file is the wide-spread maker experiment (§0ao). It is staged, it is not running, and
it cannot be until a rebuild — which is exactly what the instrument now says, in one line, instead of
me asserting it.

**Why hashing file contents was forced, not chosen.** `MERIDIAN_ENGINE_COMMIT` is empty in **all 28**
containers, the image tags carry no version, and — the fact neither of us had — **no container
bind-mounts its code**. Every service runs its image's own copy, so `/opt/meridian` is never what
runs. That is why "the checkout looked right" was actively misleading rather than merely unhelpful.
Stamp, tag and mount all carry nothing; content is the only thing left that can answer.

**Three bugs inside the instrument, each producing clean confident wrong output**, and what caught
each is the useful part: *stderr* ("file 1 is not in sorted order" — two files sorted on different
keys, reporting 210 of 214 drifted everywhere); *an independent grep* (`/opt/meridian` is root-owned,
so `git cat-file` wrote nothing for `ubuntu` while `sha256sum` cheerfully hashed empty input — every
entry became `sha256("")`, everything looked 100% drifted, and the header still printed a confident
reference line); and *an implausible row* (a pipeline's exit status is its last command's, so `if !`
tested `sort` rather than `docker`, and postgres came back `DIFFERS` with a file called `OCI`). None
would have been caught by reading the code. The script now refuses to run against a reference it
cannot validate — exit 2, cause named — and I confirmed that fires.

**Deployment, my decision: nightly at 09:30Z, not the deploy path.** A post-rebuild check confirms a
rebuild worked; it cannot see the failure this exists for, which is a fix merged and then *not*
deployed while everyone believes it is live. Only something that looks when nobody is deploying sees
that. `scripts/nightly_code_drift.sh` wraps it and **pushes only when the drifting file set changes** —
steady-state "N files inert" is true every night and is not news; a merge making something inert, or a
rebuild clearing it, is. Keyed on files rather than containers, since all 28 share one set and a
restart would otherwise push. Six tests, three mutations each verified to have *landed* before its
result was believed and checked in both directions. Verified end to end on prod: first run records
state and stays silent, second run says no change and stays silent. Suite 2281.

## 0av. Prod is a two-core box, and I have been running analysis on it as if it were not

Checked while chasing a load spike: **`nproc` = 2**, 7.8 GB RAM. Load average went 1.24 → 2.81 →
5.65 → 9.04 over about half an hour, which is **4.5× oversubscription** on two cores.

**Nothing is being lost, and I checked rather than assuming.** The live recorders are keeping up —
`live_recorder` cycling in 0.3s and `live_recorder_cfb` in 1.5s against 120s intervals. Memory is
fine (4.3 GB available). The thing that looked alarming, *MLB having written nothing for an hour*,
is `pregame_recorder_mlb` on a **3600s interval** with its last beat 3467s ago: the hourly cadence,
not a fault. I nearly reported that as a stall.

What the box is actually spending itself on is structural rather than anomalous:

| service | interval | measured cycle | duty |
|---|---:|---:|---:|
| pregame_recorder_cfb | 3600s | **2331s** | 65% |
| pregame_recorder_nfl | 3600s | **1850s** | 51% |
| pregame_recorder_mlb | 3600s | 173s | 5% |
| live_recorder | 120s | 0.3s | — |

Two pregame sweeps each occupy a core for more than half of every hour, on a two-core machine that
also runs 28 containers and a 0.5s feed. **The headroom for anything else is roughly one core,
intermittently.**

**This is a constraint on how I have been working, not just a fact about the host.** Tonight I ran a
`market_slug ~ 'setka'` regex over a partitioned 62M-row table with no month boundary; it spawned
three parallel workers, timed out on my side, and kept running on prod after I had stopped waiting
for it — I only noticed because I went looking for the load. Every heavy read I have issued, and the
wide-spread maker analysis I just assigned, competes directly with the recorders. The rule that
follows: **bound every analysis read by a month boundary so the partition prunes, and expect one
core, not two.** `partition-pruning-needs-a-boundary` already says the first half; the second half
is new and is why it matters.

## 0aw. §0ag's "flat at −1¢" is an artefact of the estimator, and the per-game version is not flat

7d, working the wide-spread question, derived that the adverse-selection module's arithmetic is an
identity: a resting bid at half-spread `h` fills iff the mid move `d ≤ −h`, and the mark-to-mid P&L is
then `d + h`. So **net = h − |d| conditioned on |d| ≥ h, which is ≤ 0 in every band by construction** —
the fill rule and the P&L mark are the same variable. That raised a serious question about §0ag, the
programme's headline negative: *is "the spread IS the adverse-selection premium" measuring anything?*

**It is. I checked, and the concern was unfounded.** §0ag's net is marked to **settlement**, not to mid.
Recomputing from `shadow_quote_fills` reproduces its published columns to the cent:

| band | fills | earned | adverse | §0ag published net | net to **mid** |
|---|---:|---:|---:|---:|---:|
| < 2¢ | 102,144 | +0.50 | −3.65 | −1.56 | −3.15 |
| 2–4¢ | 58,118 | +1.18 | −4.42 | −1.07 | −3.24 |
| 4–8¢ | 43,474 | +2.56 | −6.26 | −0.73 | −3.70 |
| 8¢+ | 23,536 | +5.29 | −9.98 | −1.02 | −4.69 |

Earned and adverse match exactly; the net column tracks settlement, not the mid. **But note what the
identity does implicate: `earned` is `h`, which is the band's own definition, and `adverse` is the
mark-to-mid move. The earned/adverse *decomposition* is largely algebra. Only the settlement net is a
measurement**, and any argument built on the earned-to-adverse *ratio* — including my own
extrapolation that 1.88× predicts a 23.5¢ loss at 12.5¢ earned — is built on the algebra. **I withdraw
that extrapolation.**

**And the headline does not survive the estimator.** §0ag is fills-weighted. Equal-weight game means,
which is the estimator this clustered design calls for:

| band | G | net per **fill** (§0ag) | net per **game** | t (per game) |
|---|---:|---:|---:|---:|
| < 2¢ | 164 | −1.66 | **−2.65** | −3.86 |
| 2–4¢ | 159 | −1.17 | **−1.53** | −1.90 |
| 4–8¢ | 158 | −0.82 | **−1.11** | −1.64 |
| **8¢+** | 156 | −1.07 | **−0.78** | **−0.98** |

Per fill it is flat at about −1¢, which is what §0ag says and what the phrase "the spread is *exactly*
the adverse-selection premium" rests on. **Per game it is not flat: it improves monotonically, −2.65 →
−0.78, and the widest band no longer excludes zero (t = −0.98).** The divergence is the usual one — the
sub-2¢ band carries 623 fills per game against 151 in the widest, so fills-weighting lets the
heavily-traded games dominate.

**What survives and what does not.** *Making still loses* — every band is negative on both estimators,
and these are gross, before fees, with no maker rebate on this venue. What does **not** survive is the
stronger claim that the net is *flat*, i.e. that the spread is priced to exactly offset adverse
selection at every width. On the per-game estimator the loss shrinks by a factor of three as the
spread widens and the widest band is statistically indistinguishable from break-even. That is a
different statement with a different implication: it points the wide-spread question (§0ao) toward
"possibly break-even above 8¢" rather than "ruinous", and the 15¢ cap means we have never looked past
the point where the trend is heading.

**Neither estimator is a result yet, because the null is unmeasured.** 7d's other finding is that a
geometry-only null — one pooled move distribution, bands differing only through `h` — produces
*opposite* gradients depending on the tail: on 200,000 draws, a normal move distribution gives net
*improving* with width (−3.65 → −1.09¢) and a fat-tailed one gives net *collapsing* (−5.27 → −26.02¢).
So a net-versus-spread gradient read without its null is uninterpretable **in principle**, not merely
underpowered: the same picture supports opposite operational decisions. The monotone improvement in my
per-game column is exactly the shape a thin-tailed geometry null produces on its own. **It is a
hypothesis, not a finding, until it is measured against the null on this tape.**

## 0ax. The wide book closes — not on edge, but because it never comes to you

7d ran the measurement §0ao asked for. Two Saturdays of CFB, the module's own bounds, cap raised to
0.50, 94,752 windows on 09-13 across 39 games.

**First, the threat to my §0aw column is refuted.** The worry was that my monotone-improving per-game
net was just a thin-tailed geometry null. **The CFB tail is heavy**: e(h) = E[|d| − h | |d| ≥ h] *rises*
with width on both Saturdays (5.00 → 7.03¢ on 09-13, 3.03 → 6.92¢ on 09-06). A heavy tail makes pure
geometry produce net *collapsing* with width, the opposite of −2.65 → −0.78. So that specific artefact
is not what my column is.

**Second, and it supersedes the first: the instrument carries almost no information anyway.**

| spread band | windows | fills | fill rate | net/game | **geometry null** |
|---|---:|---:|---:|---:|---:|
| 0.01–0.02 | 26,865 | 2,687 | **10.0%** | −4.74 | −4.10 |
| 0.02–0.05 | 11,781 | 1,839 | 15.6% | −4.83 | −4.76 |
| 0.05–0.10 | 7,717 | 938 | 12.2% | −5.87 | −5.62 |
| 0.10–0.15 | 5,739 | 366 | 6.4% | −6.82 | −6.26 |
| 0.15–0.25 | 8,058 | 272 | 3.4% | −5.59 | −6.41 |
| **0.25–0.50** | **32,828** | **145** | **0.44%** | −9.09 | −6.89 |

**Observed net tracks the null within about a cent in almost every band.** One pooled move distribution
reproduces the entire net-versus-width shape, so the mark-to-mid instrument is measuring its own
geometry. Only the widest band is meaningfully worse than its null — and in the losing direction.

**Third, the operational answer, which is not about edge at all.** The fill rate falls **10.0% → 0.44%**,
a 23-fold collapse, while 0.25–0.50 is the **second most quoted band in the sample** — 32,828 windows,
more than any band except the tightest. The wide book is not neglected. It is heavily quoted and it
almost never comes to you. On top of that, **85–90% of all windows show a mid that did not move at all
in 30 seconds**, and a still window never fills.

**That is confirmed by a route neither of us designed for it.** §0ao measured traded volume from
`market_trade_stats`: median 2,682 shares in sub-2¢ markets against 131 at 25¢+, a ratio of **20.5×**.
7d's fill-rate ratio, from mid-move windows in a different table by a different method, is **22.7×**.
Two independent instruments agreeing to within 10% on how much less the wide book trades.

**So §0ao closes, and on a firmer basis than a P&L sign.** The hypothesis was that quoting above 15¢
earns more than the adverse selection it attracts. The answer is that you cannot be filled often enough
for the question to matter: 145 fills in a full Saturday's widest band, against 2,687 in the tightest.
An edge you touch twice a week is not a strategy, whatever its sign. **This is a better reason than the
one I expected to find**, because it does not depend on the estimator, the mark, or the tail — all three
of which moved under us tonight.

**Three limits carried deliberately, all 7d's.** §0ag marks to **settlement** and this run marks to
**mid** — different instruments on different populations, so this tests my hypothesis rather than
validating my §0aw column by a second route. A tail heavy at 30 seconds need not be heavy at a
settlement horizon; the tail belongs to the horizon as much as to the market. And 09-06 carries **G = 3**
— three numbers wearing a mean — printed only as a sign check on the gradient, never as an estimate.

**And a correction to §0aw's provenance.** I wrote there that 7d's null direction came from a test that
failed and whose failure was the finding. That account was wrong, and they withdrew it: the test built
its sample with a fresh `random.Random(1)` inside the comprehension, so all 2,000 draws were identical,
and it failed on a degenerate sample rather than on any tail. The same bug was in the file twice. The
*numbers* are unaffected and now re-verified on 400,000 draws per distribution with distinctness
asserted — but the story I repeated about how they were obtained was not true, and it was load-bearing
in the way I quoted it.

## 0ay. The instrument catalogue, and a stale branch that would have re-published a retraction

7d's closing artefact is `docs/infra/the-tell-is-cleanliness.md`: **22 instrument-failure rows,
mine and theirs, grouped into five mechanisms** (written as "nineteen" here and in the doc itself
until 09-15, when the tables were counted: 21 at the first commit, one added since) — the instrument appearing in its own
measurement; a failure producing a valid-looking value; a proxy standing in for the thing; the status
measured not being the status that matters; and a control testing something adjacent to its name.

The tally is the part worth acting on. What caught them: **an implausible number 5, an independent
second route 5, mutating in both directions 3, stderr already printed 2, verifying the intervention
landed 2 — and reading the code, 0.** Nothing tonight was found by review. That is not an argument
against review; it is an argument about where the next hour goes.

**And clearing the branch list turned up a live hazard.** 7d reported `debugger/bounds` as a no-op
whose content had reached main by another route, and asked for nothing. I checked before letting it go
and the first check *disagreed*: `git diff --stat main...debugger/bounds` showed 1,778 insertions. That
is the wrong comparison — three-dot diffs against the merge base, so a stale branch's own history still
shows. The two-dot tip-to-tip diff is the right one, and it confirmed their claim: all nine test files
byte-identical on main, all five `Query(..., ge=, le=)` bounds present, `Query` imported.

But the two-dot diff also showed **141 lines the branch has and main lacks**, which is not what a no-op
looks like, so I went and read them. They are **superseded text** — thinly spread across files main has
since rewritten — and among them is this, in `docs/math/the-rebate.md`:

> *"Polymarket US pays a maker 0.31¢… Switching venues would be the most expensive decision available
> to us."*

**There is no maker rebate on this venue.** θ_maker = 0, never observed; that claim was retracted after
it was traced to a web search rather than the venue. **Merging `debugger/bounds` would have silently
re-published a retracted falsehood** into the document that exists to record the fee facts — and it
would have arrived wearing a commit message about query-parameter bounds.

> **CORRECTED by 7d, same night — I had the mechanism backwards.** I wrote above that merging
> `debugger/bounds` *would have* re-published a retracted falsehood. It would not have introduced
> anything: **`origin/main` has been asserting the maker rebate for eleven days.** `docs/math/the-rebate.md`
> opens, on main, with *"Polymarket US PAYS makers … the rebate is roughly the size of our whole loss"*,
> sourced to *"the venue's published schedule (docs.polymarket.us/fees), not an estimate and not inferred
> from our own fills"* — the strongest possible provenance framing, for the fact later traced to exactly
> that web page and retracted. The branch carried the text **because main does**, not the other way round.
> Neither of us grepped main for the string, because the branch was the suspect.
>
> **The real defect is worse than the one I reported, and it is live.** The retraction reached every
> *consumer* — `core/backtest/fills.py` sets `THETA_MAKER = 0.0` with the rebate behind an explicit
> `assume_rebate` flag, `core/quote/wallet.py` and `core/pulse/tight_game_reversion.py` both document
> θ_maker = 0, and STATUS says "no maker rebate on this venue" — and **never reached the record**, the one
> document whose job is to hold the fee facts. Nothing downstream disagreed with it loudly enough for
> anyone to look. Fixed in 5f25872: the retraction is now the first thing a reader meets, the episode is
> kept verbatim beneath it, and a guard mutated in three directions enforces **placement**, not just
> presence — moving the retraction below the claim fails two tests.
>
> *One thing in that correction does not hold.* 7d glossed the branch's 141 insertions as "about one line
> per file, a whitespace artefact". The count is 141 insertions across 141 files *against main at
> `022eed3`* — the insertions are fixed at 141, the file count moves with main (142 by 09-15 02:38), so
> only the insertion side of that pair is quotable later — but they are
> concentrated — the top ten files carry 105 of them, only nine files have exactly one, and seven of the
> eight lines in `the-rebate.md` contain prose. My "141 lines" was right; "whitespace" is not. That
> matters for the standing instruction below, which is unchanged and now rests on 7d's own better reason:
> **not that the branch adds nothing, but that nobody has audited the 141 insertions of superseded prose
> across 29 files that it carries — eight of them in the retracted rebate document.** Stated that way on
> purpose: the earlier phrasing rested on "the other 140 files", which is a count of files changed and
> therefore a property of when you looked, three lines after this same block says so. How far behind main
> the branch is grows with every commit and is not quotable as a fixed number.

So the branch is not merely a no-op, it is one that must stay unmerged, and the rule from
`a-cherry-pick-can-be-a-revert` needs a second clause: **on a stale branch the "additions" are the old
world, and the older it is the more of your corrections it carries backwards.** Check what a merge
*re-adds*, not only what it removes.

## 0az. The three unmerged branches, and why none of them should be merged as-is

Every branch from tonight is an ancestor of main at 73f8822. Three remain unmerged, all predating
tonight, and the stale-branch lesson from §0ay applies to each:

| branch | commits ahead | last commit | disposition |
|---|---:|---|---|
| `debugger/bounds` | 1 | 2026-09-13 | **never merge** — its content is already on main, and it carries 141 insertions of superseded prose across 29 files, eight in the retracted rebate document |
| `debugger/green-the-suite` | 22 | 2026-09-06 | **audit, do not merge** — nine days stale |
| `debugger/recorder-plays-regression` | 2 | 2026-09-06 | **audit, do not merge** — nine days stale |

The two from 09-06 may hold work worth having; nobody has looked. What tonight established is that the
way to find out is **not** a merge. A branch that old carries the whole world as it stood nine days
ago, and its *additions* are that old world — including any claim corrected since. `debugger/bounds`
is the worked example: a single commit, an honest message about query-parameter bounds, and eight lines
of a retracted fee claim riding along underneath it.

**So the disposition is: cherry-pick what a diff shows is genuinely new, after reading it, or leave
them.** `git diff --shortstat` before touching either — and per §0ay, note that a count of *files
changed* moves with main and is not quotable later; the insertion count is the branch's own property.

**One instrument note, since it is the same family.** My first sweep for this printed blank commit
counts rather than zeros, because the branch names did not resolve against local refs — a blank that
reads exactly like "nothing there". Re-run against `origin/` refs it gave 1, 22 and 2. A count that
comes back empty is not a count of zero.

## 0ba. My own check-in monitor cries wolf on the two heaviest recorders, by construction

A heartbeat came up overdue this cycle. It was not an outage: `meridian-nfl-recorder` was mid-sweep,
having woken at 07:22:23 after a clean `sleeping 3600` at 06:22:19, on a sweep that takes ~31 minutes.
Healthy, and the alarm was mine.

**`interval_seconds` is the SLEEP, not the PERIOD.** A recorder beats at the end of a cycle, then
sleeps `interval_seconds`, so its true period is `interval + cycle`. The rule I have been running in
these check-ins — `age > interval_seconds * 1.5` — therefore fires on any service whose sweep exceeds
half its sleep:

| service | sleep | cycle | true period | my alarm at | |
|---|---:|---:|---:|---:|---|
| pregame_recorder_cfb | 3600 | 2331 | **5931** | 5400 | **fires every cycle** |
| pregame_recorder_nfl | 3600 | 1850 | **5450** | 5400 | **fires every cycle** |
| pregame_recorder_mlb | 3600 | 208 | 3808 | 5400 | ok |
| pregame_recorder_tabletennis | 600 | 147 | 747 | 900 | ok |
| live_odds_recorder | 300 | 4 | 304 | 450 | ok |

It is guaranteed to alarm, forever, on exactly the two recorders whose real failure would cost the
most — which after a few nights is how a channel earns being ignored before it carries the one message
that matters.

**The shipped rule is sound and I checked before writing any of this.** `core/heartbeat.py`
`stale_after_seconds()` uses **`3.0 × interval`** with a 30s floor: 10,800s for these two against true
periods of 5,931 and 5,450, so roughly 2× headroom. No code change is needed and none was made. The
defect was in an ad-hoc query I invented for these check-ins and never validated against the services'
measured periods — `configured-is-not-measured` applied to my own monitor, and the fourth time tonight
that the instrument rather than the subject was the thing at fault.

**Correct form, for whoever runs this next:** compare against `interval_seconds + cycle_seconds`, both
of which the heartbeat table already stores, plus a margin — never a multiple of the interval alone.
And the latent bound worth knowing: the shipped 3× rule breaks if a sweep ever exceeds **2× its sleep**
(7,200s here). CFB is the closest at 2,331s and has been growing; it is the one to watch.

## 0bb. The 10:40Z MLB read, and the away-confound shape turning up in baseball

First fully unattended daily MLB read: both steps `exit 0`, settlement cache refreshed, 30,981 rows
over 77 games. The scored slate is **11 games**, up from 9, and **every one of the 14 MLB arms is
`UNDERPOWERED (G<25)`** — nothing can nominate and nothing did.

One arm's interval excludes zero and it should be read with the confound in mind, not as a lead:

| arm | bets | G | mean bet | 95% CI |
|---|---:|---:|---:|---|
| `mlb_spread_yes_70_100` | 15 | 11 | +15.51¢ | **[+2.65, +28.38]** |
| `mlb_spread_no_00_30` (its twin) | 8 | 7 | −2.27¢ | [−45.61, +41.06] |

**That is the same shape as §2b's WNBA line**: YES at a heavy-favourite price is the *away* side on
this venue, its home-referenced twin does not carry the sign, and the pair is the away-team confound
rather than a favourite effect. It is also at G = 11 against a floor of 25, so the paper book's gate
correctly refuses it — the gate requires `G >= 25 AND excludes 0`, and prints the twin beside rather
than gating on it. **Recorded here so it is not rediscovered as a finding in a week when G crosses 25;
at that point the twin split is what decides it, not the interval.**

## 0bc. The table-tennis cost bar is NOT 2.22¢ — and not the ~2.4¢ this section was corrected to either (§0bd)

Before waiting two more days for the Elo to become fittable, I sized the bar it has to clear. I had
written in §0al that *"table tennis quotes ~8¢ wide, so the half-spread alone is ~4¢ before the
0.06·p·(1−p) taker fee."* **That is wrong for the book you would actually trade**, and the error is a
population one.

| population | quotes/markets | median spread |
|---|---:|---:|
| **all** pregame quotes, mid 0.2–0.8 | 42,375 | **17.0¢** |
| pregame quotes in the price tail | 447 | 1.0¢ |
| in-play / after start | 877 | 1.0¢ |
| **LAST pregame quote, mid 0.2–0.8** | **724 markets** | **2.0¢** |

**The book tightens as the match approaches.** Pooled across all pregame quotes the median is 17¢,
because a match listed hours early sits on a stale two-sided quote nobody is defending. At the last
quote before start — median **8.3 minutes** before — the median is **2¢**, and raw rows confirm it by
eye: 0.45/0.46, 0.43/0.44, 0.47/0.48, 0.34/0.35, 0.49/0.50. Most are **one cent wide**.

**So the cost of a bet-and-hold entry is the half-spread plus the taker fee, and nothing else:**

| | ¢ |
|---|---:|
| median half-spread at the last pregame quote | 1.00 |
| ~~median taker fee `0.06·p·(1−p)` at that mid~~ **1.22 is not reproducible — see below** | ~~1.22~~ 1.41 |
| **total cost per contract** | ~~2.39–2.41~~ **2.26¢ (median) to 3.73¢ (mean) — §0bd** |

> **SUPERSEDED AGAIN, 09-15, and this line is where a reader meets it.** The 2.39¢ below is median
> half-spread 1.000 + **mean** fee 1.388 — a median crossed with a mean, which is the same error as the
> 1.22¢ it replaced, in a new costume. The coherent totals are **median 2.260¢ and mean 3.728¢** (p25
> 1.962, p90 4.923); the mean half-spread is 2.339¢ against a median of 1.000¢, so a long tail of
> wide-quoted matches is the whole gap. Third revision of one number by two of us, so §0bd publishes the
> RANGE. Everything from here to the end of this section reads 2.39¢ and should be read as 2.26–3.73¢.

> **CORRECTED 09-15 by 7d, at the table rather than below it.** The 724 markets and the 2.00¢ median
> spread reproduce exactly. The fee term does not: on that same population the mean is 1.411¢ at the mid
> and 1.388¢ at the ask, the median 1.462¢ and 1.451¢. The median mid is 0.500 and the mean 0.504, so
> p(1−p) ≈ 0.25 and ~1.5¢ is what the formula must give — **1.22¢ is not reproducible there by either
> statistic at either price.** The nearest figure 7d could produce is 1.266¢, the mean at the ask over
> the 42,485 all-quotes population, printed as the nearest candidate and NOT as a diagnosis (7d first
> published that reading as the explanation and this table refuted it). ~~Bar: 2.39¢ at the ask, 2.41¢
> at the mid~~ — **both crossed a median with a mean and are superseded by the range above; only the fee
> statistics in this paragraph survive.** Registered in `docs/math/tabletennis-elo-harness.md` §7, where it is a sizing
> constant only — every bet is charged `fee_per_contract` at its own entry price.

**What this does and does not change.** It does **not** revive §0al's price-bucket result: that pooled
−3.60¢ with an interval of [−8.67, +1.47] spanning zero, and an effect that does not exclude zero is
dead regardless of what it would have cost to trade. But *the reason I gave was wrong.* I wrote that
"the mispricing is smaller than the cost of acting on it" — 3.60¢ against a real cost of 2.26–3.73¢ (§0bd), the
mispricing was **larger** than the cost. I offered a supporting figure that argued against the
conclusion it was attached to, which is worse than offering none. The conclusion stands on its
interval alone.

**What it changes is the Elo outlook, materially.** A rating model must beat the venue price by more
than **2.26–3.73pp per contract** (§0bd), not the ~5.4pp my §0al figure implied. For reference, 7d's measured
pooled gap between price and realised outcome across 357 settled matches is **−4.36pp** (|t| ≈ 1.7,
not significant on its own). If even half of that is systematic and a model can capture it, that is
~2pp against a bar of **2.26–3.73pp** — below both coherent statistics, so **negative rather than
marginal**. The sign moved with every revision and the largest single step was 0.17¢, less than one
tick: the programme's last live path rests on a difference smaller than the grid it trades on, which
argues for measuring the money arm rather than believing any of the words, mine included. Registered in
`docs/math/tabletennis-elo-harness.md` §7 with its floor as a FORMULA — n = (1.96·49.1/X)², X named:
1,814 matches at 2.260¢ (~21 days at setkameua's rate) or 667 at 3.728¢ (~8 days). At the 200-match
signal floor the money interval is ±6.80¢ against a bar of 2.26–3.73¢, wider than the bar by 1.8× even
at its generous end, so NOT YET is the arm's only reachable verdict on day one.

**The trap, recorded because I nearly fell in it twice in one hour.** My first query returned a 2¢
median and looked wrong against my published 8¢; my second returned 17¢ and looked like it confirmed
the 8¢. Both were correct computations of different populations, and neither is "the spread" — the
tradeable number requires naming **three** axes at once: *last quote*, *before start*, *mid 0.2–0.8*.
Pooling all pregame quotes would have closed the last live path in the programme on a number that
describes stale listings nobody trades.

## 0bd. The TT cost bar, third revision: publish the range, because 2.39¢ is a median plus a mean

This number has now been revised three times by two people and every version was a different mixture
of the same 724 markets. Per `three-revisions-is-the-signal` the honest output is the range with its
populations named, not a fourth point estimate.

| statistic, entering at the ask, 724 markets, mid 0.2–0.8 | ¢ |
|---|---:|
| median half-spread | 1.000 |
| **mean** half-spread | **2.339** |
| median fee `0.06·p·(1−p)` | 1.451 |
| mean fee | 1.388 |
| **MEDIAN of the total** | **2.260** |
| **MEAN of the total** | **3.728** |

**Every published figure so far was a cross-statistic sum.** Mine — "1.00 half-spread + 1.22 fee =
2.22" — took the median of the *sum* and back-derived a fee by subtraction; medians do not add, so
**1.22¢ never existed as a quantity**. 7d's correction to 2.39 is "median half-spread 1.00 + **mean**
fee 1.388", which mixes a median with a mean and is likewise not a statistic of anything. Both numbers
are close to the median total by luck rather than construction.

**The coherent pair is 2.26¢ (median) and 3.73¢ (mean), and the gap between them is the finding.** The
mean half-spread is 2.34¢ against a median of 1.00¢ — the distribution has a long right tail of
wide-quoted matches. **Which one is the bar depends on which matches you bet.** Bet every match and you
pay the mean, 3.73¢. Bet only typical ones and you pay near the median, 2.26¢. A rating model bets
where it disagrees with the price, which is not a random subset of either, so the honest statement is:
**the bar is between 2.26¢ and 3.73¢ and its position inside that range is a property of the strategy's
selection, which does not exist yet.**

**This worsens the outlook and does not settle it.** Against 7d's ~2pp of potentially capturable gap:
2pp is below 2.26¢ and far below 3.73¢, so on both coherent statistics **the money arm is negative,
not marginal.** My §0bc "marginal, not hopeless" was resting on 2.22¢, a number that never existed.
What survives is 7d's own conclusion from the other direction: the sign turned on less than one tick,
so the argument for measuring the arm rather than believing any of these words is stronger than
before, not weaker.

**And the power floor inherits the mixture.** 1,618 matches was computed as the n at which the interval
excludes a 2.39¢ effect. At 2.26¢ it is 1,813; at 3.73¢ it is 666. The floor is a choice of target
effect, so it must be stated as *"to detect a net edge of X¢ takes n = (1.96·49.1/X)²"* with X named —
not as a bare match count that looks measured.

## 0be. The money arm was registered, tested, green — and had no caller

Ninety minutes after registering the money criterion "before the sample exists", I checked whether it
would actually run. **It would not.** `core/tt/money.py` shipped with 20 passing tests and **nothing
calling it**: `cfb/run_tt_elo.py` imported `elo, rule`, and its `PRICE_SQL` selected only the mid, so
the arm had neither an entry point nor the bid/ask it needs. Grepping the repo, the only importer
outside the module was its own test file.

**The suite was green throughout — 2,326 tests — because the tests exercise the module directly.** A
library with thorough tests and no caller passes everything and does nothing. I merged it, approved
it, and told the operator the criterion was registered; that was true of the code and false of the
behaviour, which is the only sense that matters for something whose whole purpose is to fire
automatically in ~19 days when nobody is watching.

**Fixed and verified live.** `PRICE_SQL` now carries `best_bid`/`best_ask` — you buy YES at the ask
and NO at `1 − bid`, so a mid understates the bar by exactly the half-spread, which is the quantity
§0bd spent three revisions pinning down. `report()` prints a MONEY line per competition on every run.
On prod now:

```
setkameua   256  113  0  NOT YET  0 predicted matches < 200
    MONEY   NOT YET  0 eligible predictions
```

**It prints in all four states rather than skipping any**: no book loaded, no eligible predictions,
eligible but nothing clears its own price, and a scored result. Silence at zero is precisely how a
criterion goes a month without anyone noticing it never ran — which is the defect this section exists
to record. It is **not gated on the signal verdict** (conditioning on a signal PASS selects on the
same outcomes the signal was read from) and is reported as a separate verdict, never collapsed into
it. Realised cost — mean and median of what the bet matches actually paid — is on the line, because a
model that prefers wide-quoted matches pays the tail and neither published bar would describe it.

**Five tests assert the WIRING, which is the only thing that was ever missing**, with four mutations
each verified to have *landed* before its result was believed: dropping the import, reverting the SQL
to mid-only, not printing, and gating on the signal verdict. Suite 2,331.

**The general form, and it is the sharpest instance of tonight's family.** Every other instrument
failure tonight produced a *wrong* answer that looked clean. This one produced **no answer at all**,
and looked cleanest of the lot: a module, a test file, twenty green tests, a registered criterion in a
pre-registration document, and a commit message describing it working. Nothing in the suite can
distinguish "this runs and is correct" from "this is correct and never runs" — only asking *what
calls it* can, and that question is not one any test we own asks by default.


**7d's review, 09-15 — three of the four decisions stand; one had a sign error.**

1. Printing in all four states: keep. Silence at zero is how the defect survived a merge and a review.
2. Not gated on the signal verdict: keep, for the reason it was written.
3. **The X choice was the smaller problem. The line did not call the registered rule at all** — it
   decided inline, and `"PASS" if (lo > 0 or hi < 0)` returns **PASS on an interval entirely below
   zero**, i.e. a strategy that reliably loses, printed as a pass. It also tested "excludes zero"
   BEFORE the sample-size gate, so a degenerate interval at n=5 could PASS. So `rule.money_verdict`
   was itself callerless one level down, and its 28 tests protected the copy that never ran. The line
   now reads the registered rule and prints BOTH ends of the bar range. On the X itself: `BAR_MEDIAN`
   is the **stricter** gate, not the optimistic end — in `money_verdict` X plays only the resolution
   role (the cost is inside each bet's P&L), and the tighter bar demands a narrower interval, so it
   needs ~1,814 matches against ~667. The instinct to flag an unstated choice was right; the
   direction was inverted.
4. Entry at ask / 1−bid: keep, verified charged once.

**And the same defect was already on disk, earlier the same night, in my own build.** `core/drift.py`
was never imported either: the nightly cron runs `scripts/code_drift.sh`, which carries its own
complete classification, and `docs/infra/what-is-actually-running.md` credited the Python module with
pinning "UNKNOWN is not a pass". The guarantee belonged to the implementation that never executed.
The duplicate is deleted, its two rules are now comments at the branches that implement them, and the
doc is corrected — with a test that drives the SHELL script named as the open option, since a test of
a parallel implementation asserts a guarantee about code that does not run.

**Swept the family: 22 of 111 `core/` modules have no caller in code, compose, shell or cron.** Most
are legitimately hand-run, so the registered guard is scoped to `core/tt/` — the package that must
fire unattended at 09:00Z. Two defects in that sweep were mine and both are in the catalogue: a regex
that missed `from core.tt import elo, money, rule`, and a second pass that counted
`.pytest_cache/v/cache/nodeids` as an external caller. Catalogue now carries mechanism 6, "the
instrument is not connected to anything", 25 rows. Suite 2,334.
## 0bf. Fixing the callerless arm, I wrote a callerless rule with a sign error in it

7d reviewed §0be's fix and found three more instances of the same defect, one of them mine and serious.

**My verdict line returned PASS on a reliably losing strategy.** I wrote
`"PASS" if (lo > 0 or hi < 0)` — which fires on an interval lying entirely *below* zero. An arm losing
a confident 3–5¢ per contract would have printed **PASS**:

| interval | n | my line | corrected |
|---|---:|---|---|
| [−0.050, −0.030] reliably losing | 3,000 | **PASS** | FAIL |
| [+0.030, +0.050] reliably winning | 3,000 | PASS | PASS |
| [−0.50, +0.50] degenerate | 5 | **PASS** (width untested first) | NOT YET |
| [−0.020, −0.020] zero width | 3,000 | **PASS** | NOT YET |

**And the deeper fault is that I wrote the rule at all.** `rule.money_verdict` already existed —
registered, documented, 28 tests — and I did not call it. I inlined my own logic instead. **So while
fixing a module that had no caller, I created a registered function with no caller one level down, and
put a sign error in the copy that ran.** Its 28 tests protected the version nobody executed. That is
§0be's mechanism reproduced by the fix for §0be, inside ninety minutes.

**A third instance was already on disk, 7d's:** `core/drift.py` was never imported either — the nightly
runs `scripts/code_drift.sh`, which carries its own complete classification — while
`what-is-actually-running.md` credited the Python module with guaranteeing "UNKNOWN is not a pass". The
guarantee belonged to an implementation that never ran. Deleted, its two rules moved into the shell at
the branches that implement them.

**And my characterisation of the bar choice was inverted.** I flagged that I had picked `BAR_MEDIAN`
"to get a printable line" and called it the optimistic end. In `money_verdict` the bar plays the
*resolution* role: a **tighter** bar demands a **narrower** interval, so `BAR_MEDIAN` (2.26¢) requires
**1,814** matches against `BAR_MEAN`'s (3.73¢) **667**. It is the stricter gate, not the looser one.
Flagging an unstated choice was right; the direction I gave it was backwards. The line now prints both
ends.

**The sweep, and why the guard is narrow.** 22 of 111 `core/` modules have no caller in code, compose,
shell or cron. Most are legitimately hand-run analysis, so a repo-wide guard would emit 22 lines its
reader learns to skip — the alarm-that-always-fires failure. It is scoped to `core/tt/`, the package
that must fire unattended in ~19 days with nobody watching. 7d's own sweep produced two defects it
caught itself: a regex that missed `from core.tt import elo, money, rule` and so called the arm unwired
*after* it was wired, and a second pass that counted `.pytest_cache` node ids as callers.

**STANDING RULE, because the scope is deliberate and the trigger will otherwise be forgotten.** The
callerless guard covers `core/tt/` only. The other 21 uncalled `core/` modules are outside it on
purpose — a guard that is read beats a guard that is complete, and 22 lines a reader learns to skip is
the same failure as an alarm that always fires. **The moment any of those 21 acquires a schedule — a
cron line, a compose service, a step inside one of the nightly scripts — it must come inside the
fence.** Inertness only matters for code that is supposed to fire unattended; adding a schedule is
exactly the event that converts a harmless hand-run module into the defect this section records.
Whoever adds that schedule owns bringing it in, and this is the line that says so.

**Sixth mechanism, now in the catalogue: the instrument that is not connected to anything.** It breaks
the document's own opening claim that every instance produced tidy output — this class produces *no*
output, and the intro said otherwise until mechanism 6 contradicted it from below. Suite 2,334.

## 0bg. MLB crosses the nomination gate tonight, and the push will carry a number instead of a name

MLB stands at **23 settled games** against the paper book's `G >= 25` floor. Tonight's slate (first
pitch 22:40Z) crosses it. The arm closest to nominating is the one §0bb flagged:

| arm | mean bet | 95% CI | G |
|---|---:|---|---:|
| `mlb_spread_yes_70_100` | **+15.51¢** | [+2.65, +28.38] | 11 |
| `mlb_spread_no_00_30` (home twin) | −2.27¢ | [−45.61, +41.06] | 7 |

**YES is the AWAY side on this venue**, so a YES-side price-bucket nomination is the away-team
confound until its home twin says otherwise — and three "excludes 0" headlines have already been
exactly this. **The push named the arm and nothing else**, so the first thing to arrive would have been
a strategy name with no number and no warning.

It now reads, simulated against the real paper book:

```
strategies 35 tested, 1 excluding zero: wnba_spread_yes_80_100 +5.78
[+2.96,+8.60] [YES-side = AWAY: read the home twin before believing]
```

137 of the 480-character cap.

**The caution keys on the shape (`_yes_`), never on a named arm**, so it fires for arms that do not
exist yet; a caution listing today's suspects silently stops applying. **The gate itself is untouched** —
nomination remains `G >= 25 AND excludes 0`, with the twin printed beside rather than gated on. Tuning
a decision rule around the arm you can watch approaching it is how a rule stops being pre-registered,
and the twin-gating question is a decision for the operator, not a patch to make tonight's output
prettier.

*Offsets pinned by test: I counted the awk columns by hand first and was off by one, which would have
printed the interval and the word POSITIVE in place of the mean.* Suite 2,340.

## 0bh. The MLB arm killed on its own four-way split, before it could nominate

The operator read §0bg's flagged arm as a finding, which is the correct reading of a `+15.51¢` with a
clean interval if you have not seen the split. So here is the split, on the 44 settled MLB spread
markets with a pregame close, entering at the executable side with the taker fee charged:

| bet | games | price paid | won | net |
|---|---:|---:|---:|---:|
| **away** team as heavy favourite (YES ≥ 0.70) | 15 | 0.768 | 0.933 | **+15.51¢** |
| **home** team as heavy favourite (NO ≥ 0.70) | 8 | 0.762 | 0.750 | −2.27¢ |
| away underdog | 8 | 0.244 | 0.250 | −0.54¢ |
| **home** underdog (NO ≤ 0.30) | 15 | 0.239 | 0.067 | **−18.27¢** |

**Same bet, same price, opposite sign by side of the field.** Backing a heavy favourite pays only when
it is the away team. That is side-dependence, not a favourite effect, and it is the fourth time this
confound has produced a clean-looking interval.

**Rows 1 and 4 are the same 15 games counted twice.** +15.51 and −18.27 sum to **−2.76¢**, which is the
round-trip cost — the identity from `a-fade-is-not-a-new-hypothesis`. There is one bet in that table,
not two, and its two faces differ by exactly what it costs to trade.

**Sized as what it is:** away favourites covered **14 of 15** against a price implying 11.5 — a surplus
of 2.5 games. One-sided `P(≥14 | n=15, p=0.768) = 0.105`, before any multiplicity, against 35
registered strategies of which ~1.8 are expected to clear 95% by chance. **Two and a half lucky games
in fifteen.**

**Why this is recorded now rather than when it trips.** MLB crosses `G ≥ 25` tonight. When the paper
book prints `POSITIVE, excludes 0` for this arm, the split above is the answer, already written, with
its sample size and its binomial attached. A confound explained after it has been broadcast is a
retraction; explained before, it is a gate. The gate itself is still untouched — the arm will nominate
and the push will carry its number and the YES-side caution (§0bg), which is the design.

## 0bi. Ladder inconsistency: the first thing in this programme with money attached, and it is small

Every test until now asked whether the venue *misprices a sport*. This one asks something the market
cannot argue with: **are its own prices consistent with each other?** Within one game, covering −17.5
is strictly harder than covering −10.5, and winning sits strictly between them. Buy the easier rung and
sell the harder one and the position **cannot lose** — it pays +1 when the margin lands between the two
lines and 0 otherwise. If you are paid to hold it, that is arbitrage, no model required.

**MLB, one day, 57 ladders including the winner rung as line 0.0:**

| | |
|---|---:|
| pairs tested | 570 |
| free-money pairs, net of both taker fees | **4** |
| quote gap between the two legs | **0.0 min — simultaneous** |
| episodes / median duration | 23 / **34.5 min** |
| **size available at those quotes** | **median 0, max 4 contracts** |
| **total value, every opportunity taken** | **$0.23** |

**The frame was validated on the population before any of this was believed**: mean YES mid rises
0.266 → 0.358 → **0.501** → 0.638 → 0.736 across the five rungs, the winner landing on a coin flip
exactly where it must, and 91.2% of within-game adjacent pairs correctly ordered.

**And the depth is the whole story.** Median depth across *all* MLB quotes is 100 contracts; at the
quotes that are mispriced it is **zero**. That also explains the 34-minute persistence — a price with
no size behind it can sit at an impossible level indefinitely, which is why it survives. A funded
arbitrage is taken in seconds.

**CFB, three days, where the books are deeper** — 2,633 ladders, 1,041,685 pairs, depth present on 90%:

| | |
|---|---:|
| free-money pairs (edge 0–15¢; above 15¢ is a stale rung, not a market) | 1,107 |
| distinct (game, pair) opportunities | 350 |
| $ available: median / p90 / max | **$0.01 / $3.84 / $162.38** |
| worth ≥ $10 / ≥ $100 | 17 / 3 |
| ~~total if every pair were taken~~ **double-counts shared legs — see below** | ~~$1,024.95~~ |
| **best single trade per game, summed — defensible lower bound** | **$413.90** |

> **CORRECTED, my own double-count.** Summing 350 *pairs* counts the same mispriced rung many times.
> In `uk-txam` one rung generated six "opportunities" by pairing against six others — they share a leg
> and compete for the same depth, so you can take one, not six. Per game, counting only the single best
> trade: **$413.90 across 23 games in three days**, median **$0.55**, max $162.38. **Five of 23 games
> carry $400.70 of the $413.90 — 97%.** The truth lies between $414 and $1,025 and closer to the floor,
> because overlapping pairs mostly cannot both be filled.



**That is roughly $340 a CFB day, and ~70% of it sits in 17 of the 350 opportunities.** The median is a
penny. This is real and it is not a confound — but it is a handful of events, not a stream.

**VERIFIED AGAINST OUTCOMES, by a route that touches no prices at all.** The whole thing rests on one
claim: that covering +14.5 is *strictly easier* than covering +8.5, so the position cannot lose. That is
testable on settled games without quotes, without my parser's sign convention, and without any
assumption about which side YES is — **whenever the harder rung settled YES, the easier one must have
too.** Across **128 settled CFB spread ladders and 74,775 pairs: zero violations.**

That is the strongest check available and it passes cleanly. It confirms three separate things at once:
the `neg`/`pos` line parsing is right, the domination logic is right, and the payoff really is
non-negative in every state. **The arbitrage logic is sound. What remains unproven is entirely
execution.**

**What is not established, and it is what matters.** Quoted size is not fillable size; none of this has
been executed. Both legs must be hit together or you hold a naked position. Our sampling is 18-minute
snapshots, so a live scanner is required to see these at all. **The honest status is: a measured,
model-free, non-confounded inefficiency of about $1,000 per three CFB days in quoted terms, with
execution entirely unproven.**

*Method note.* I validated the sign convention on MLB and then applied the same parser to CFB **without
re-validating it**, which produced an 88¢ "arbitrage" (USC −17.5 quoted above USC −10.5). Checking that
found the convention is in fact correct for CFB too — 85.4% of within-game pairs correctly ordered — but
the population mean *also* rises under an inverted reading, because a +34.5 line is only offered when
the away team is a huge underdog. **The population mean cannot validate a within-game constraint; only
the within-game ordering can.** The extremes are stale deep rungs, excluded above at 15¢.

## 0bj. The ladder quotes are never consumed — which is the limit of what observation can decide

The open question on §0bi was whether quoted size is fillable. I cannot answer it by placing an order,
so I asked the observable version: **while a violation stands, does its size get eaten?** A funded
arbitrage is consumed within seconds; one nobody can take sits unchanged.

97 violating pairs observed in three or more consecutive snapshots:

| what happened to the size across the episode | pairs |
|---|---:|
| **shrank** (someone taking it) | 23 |
| grew | 33 |
| **flat — untouched** | **41** |
| **median change** | **+0 contracts** |

**No systematic consumption.** Size is flat or growing more often than shrinking, and the median change
across an episode is exactly zero. Combined with §0bi's 95% same-pair persistence and 34-minute median
duration: these are **standing quotes at impossible prices that nobody touches.**

**Two readings, and observation cannot separate them.**

1. *Nobody else is scanning for this.* Plausible — it is a small venue, the inconsistency is only visible
   if you build the ladder across three market types, and the money is a few hundred dollars a Saturday.
   Under this reading the size is real and we could take it.
2. *The displayed size is not actually executable.* Equally consistent with everything measured.

**Every test I can run from the tape has been run.** The domination logic is verified on 74,775 settled
pairs with zero violations. The frame is verified three ways. The legs are simultaneous. The violations
persist and are the same standing quote. The value is $414 over three CFB days by the defensible count,
97% of it in five games. **The single remaining unknown is whether an order would fill, and that cannot
be learned by looking.**

**So this is a decision for the operator, not a measurement for me.** Testing it costs one small order
on one leg of one violating pair, to see whether it fills at the displayed size. That is the only
experiment that discriminates, it is the operator's to authorise, and **I will not place it.** Until
then the honest label on this lead is: *verified inconsistency, unverified executability.*

## 0bk. The ladder scan across every family: NFL doubles it, totals are clean, and the defect is spread-specific

Extended §0bi past CFB spreads. All figures are *best single trade per game, summed* — the defensible
count that does not double-count shared legs.

| family | window | pairs tested | within-game ordering | free-money pairs | value |
|---|---|---:|---:|---:|---:|
| MLB spread + winner | 1 day | 570 | 91.2% | 4 | **$0.23** |
| CFB spread + winner | 3 days | 1,041,685 | 85.4% | 1,107 | **$413.90** |
| **NFL spread + winner** | 6 days | **2,495,330** | **79.6%** | **6,517** | **$283.49** |
| CFB game totals (1q/2q/3q/4q/1h/2h) | 3 days | 96,620 | 94.0% | 13 | **$1.01** |

**The defect is specific to spread ladders and it worsens with ladder depth.** Totals ladders are the
cleanest thing measured (94.0%, thirteen violations in 96,620 pairs, one dollar) despite being the same
kind of object. Ordering degrades MLB 91.2% → CFB 85.4% → NFL 79.6%, in the same order as the number of
rungs quoted per game. **Deep spread rungs are where the venue's own consistency breaks** — which is the
same conclusion as §0bi's depth finding from a different direction: the rungs nobody trades are the
rungs nobody keeps honest.

**NFL's domination is outcome-verified too, which is what lets the $283 stand.** NFL has the worst
ordering of the three (79.6%), so its sign convention needed the same settlements-only check CFB got —
no prices, no parser assumptions: **16 settled NFL ladders, 9,871 pairs, zero violations.** With CFB's
74,775 that is **84,646 settled pairs and not one case where the harder rung paid while the easier one
did not.** The logic under both figures is sound; only executability is open.

**NFL is the opposite shape to CFB and that matters for whether this is a strategy.** CFB is $414 with
97% in five games — a few bad quotes. NFL is $283 spread across **40 of 48 games**, seven worth ≥$10.
A recurring few-dollars-per-game inefficiency is a far better basis for a repeatable process than five
lucky rungs, even though the headline is smaller.

**Consolidated, in quoted terms: roughly $700 per football week** (a CFB Saturday plus an NFL week),
against the operator's $1k/week threshold. **Every caveat from §0bj still binds unchanged** — quoted
size is not fillable size, the consumption test found no systematic take-up (23 shrank / 33 grew /
41 flat, median +0 contracts), and nothing here has been executed.

*Data note: `book_levels` holds duplicate rows at `level_index = 0` for some snapshots — worst case 27
on NFL, 12 on CFB, mean 1.00 so it is rare. A scalar subquery errors on them; the NFL figures above use
`max(quantity)`. The MLB and CFB numbers were computed before this surfaced and their queries succeeded,
so those row sets contained none.*

## 0bl. Both venues, every ladder family, 8.1 million pairs: the defect is Polymarket spreads and nothing else

Completed the scan. Every ladder family on both venues, same method, fees at each venue's own rate
(0.06 Polymarket, 0.07 Kalshi). Value is *best single trade per game/event, summed*.

| venue | family | pairs tested | within-ladder ordering | free-money pairs | value |
|---|---|---:|---:|---:|---:|
| Polymarket | MLB spread+winner | 570 | 91.2% | 4 | $0.23 |
| Polymarket | **CFB spread+winner** | 1,041,685 | 85.4% | 1,107 | **$413.90** |
| Polymarket | **NFL spread+winner** | 2,495,330 | **79.6%** | 6,517 | **$283.49** |
| Polymarket | CFB game totals | 96,620 | 94.0% | 13 | $1.01 |
| **Kalshi** | **totals** | 2,244,340 | **97.4%** | 24 | **$0.00** |
| **Kalshi** | **spreads** | 2,216,220 | **96.8%** | 38 | **$0.01** |
| | **total** | **8,094,765** | | | |

**The inefficiency is Polymarket spread ladders and nothing else.** Three independent controls now say
so. *Totals on the same venue are clean* (94.0%, one dollar) — so it is not Polymarket generally. *Both
Kalshi families are cleaner still* (96.8–97.4%, one cent across 4.5M pairs) — so it is not the market
structure, since Kalshi quotes the same object with the same arithmetic. And *ordering degrades with
ladder depth within Polymarket* — 91.2% MLB → 85.4% CFB → 79.6% NFL, in the order of rungs quoted.

**Kalshi is the control that matters most, because it fails the obvious alternative explanation.**
Kalshi's books are one to two orders of magnitude deeper — bid sizes of 80,000 contracts against
Polymarket's 100 — and it is *more* consistent, not less. So the defect is not "thin venues are sloppy".
It is that **Polymarket's deep spread rungs are unpoliced because nobody trades them**, which is the
same conclusion §0bi reached from depth and §0bj reached from non-consumption, now reached a third time
from a cross-venue control.

**What this changes about the lead.** It is narrower than it looked and better understood: not a venue
inefficiency, not a market-structure inefficiency, but a specific dead corner of one venue's spread
board. **It does not change the economics** — still ~$700 a football week in quoted terms, still 97%
concentrated in five CFB games, still resting entirely on whether an unconsumed quote would fill.
**And it closes Kalshi as a second source**: there is nothing there to find, measured on 4.5M pairs.

## 0bm. The ladder scanner, built and firing nightly — and it had no caller until I checked

`core/ladder/scan.py` plus `cfb/run_ladder_scan.py` plus `scripts/nightly_ladder.sh` at **11:30Z**.
Places nothing; that is asserted on the imports rather than promised.

**Validated by independent reimplementation.** The module was written from the *reasoning*, not derived
from the throwaway analysis script, then run against the same CFB tape: **1,089 violations,
best-per-game total $413.90 over 23 games — identical to the ad-hoc measurement to the cent.** Two
implementations from one spec agreeing is the check that matters; a module that merely re-runs the
script that produced the number proves nothing.

**Every knob is a defect that actually occurred, not a hypothetical.**

| knob | the defect it encodes |
|---|---|
| `MAX_PLAUSIBLE_EDGE = 0.15` | USC −17.5 at 0.930 against −10.5 at 0.040 — an 88¢ "edge" on a rung with no size. Including these inflates the total ~2.5× |
| fee netted at **both** legs' traded prices | without it, pairs that merely cross the spread qualify and none are tradeable |
| size = **min** of the two legs | an arbitrage is only as large as its smaller side; Polymarket routinely shows depth on one leg and nothing on the other |
| `best_per_game` takes **max**, never the sum | one mispriced rung violates against every rung it pairs with and they share a leg — summing overstated CFB 2.5× ($1,024.95 vs $413.90) |
| legs keyed on `(game, captured_at)` | a ladder assembled across timestamps is not an arbitrage, it is two prices that never coexisted |
| depth via `max(quantity)` | `book_levels` holds duplicate `level_index = 0` rows — worst 27 on NFL, 12 on CFB. A scalar subquery raises *more than one row returned*, which is how it surfaced |

**It had no caller, and I caught that only because I had just written §0be about the same thing.** The
module shipped with eight green tests and nothing importing it outside its own package — the exact
shape of the money-arm defect from ninety minutes earlier. `tests/test_ladder_runner_is_wired.py`
now asserts a caller exists outside `core/ladder/`, which is the check no test of a module can make
about itself.

**Why it accrues nightly and why it will almost never speak.** §0bi's $413.90 spans three CFB days;
whether that recurs weekly or was one weekend is **unknown**, and only a record answers it — so the
artifact is written every night regardless. The push fires only above a **$50 single-opportunity
floor**: the median is $0.01, and a nightly "found 350 things worth a penny" is how a channel earns
being skipped before it carries the one message that matters. Measured, 3 of 350 cleared $100 and about
ten cleared $50, so this speaks a few times a season. A state file stops the same standing quote paging
twice, since these persist for hours. **First live run under a cron environment: found $162, cleared
the floor, pushed once.**

**Four jobs now run unattended**: settle 04:40Z, Elo fit 09:00Z, drift 09:30Z, ladder 11:30Z — each
silent unless it has something, each verified to run under cron's own stripped environment rather than
only under mine.

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
| mlb-recorder | venue boards, event limit 500 since 10:28Z | **MLB — 13,302 rows today alone, a flat 525/hour every hour** (8,781/62 at 17:30Z 09-14; +18,528 rows, +15 games overnight, accruing unattended) |
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
| **Table tennis Elo** (`docs/math/tabletennis-rating-preregistration.md`) | **prerequisite measured 09-15: identity is NOT the blocker, volume is.** Extraction is 356/356 — every settled slug yields exactly two player tokens, zero failures of any shape, nothing filtered. The tokens are a machine 3+3 abbreviation, so there is no transliteration, casing or given/family-order variance to resolve: the 20 closest non-identical pairs ALL sit at 0.833, which is one character of six and is structurally expected over ~180 players in a fixed 6-char scheme (`korole`/`kurole`/`karole` are three families sharing a given name, not three spellings of one player). Both collision tests return zero — no token on both sides of a match (0/356), no token in two leagues (0/180). League list confirmed exhaustive from the data: setkameua, setkamecz, setkamemd, setkawoua, 750 board slugs, one market per match. The binding constraint is the pre-registration's OWN `>=10 prior matches` filter: **the busiest player has 9 and nobody qualifies today.** 8 of 712 appearances break the 6-char scheme (`mars` 4 chars, `demciva` 7) and are reported rather than dropped. Frame confirmed by CALIBRATION rather than by a mean — realized rises 0.333, 0.318, 0.385, 0.446, 0.652, 0.704, 1.000 across price buckets, where an inverted frame would fall; the mean gap is frame-invariant and cannot separate the two. `docs/math/tabletennis-player-identity.md` | **fittable as written in ~3 days**: at 334 settled matches on the one COMPLETE day (09-14; do not use the 118.7/day window mean, 94% of the set is one day) and 3.82 appearances per player per day, `>=10 prior` covers 44% of future appearances at +1 day, 70% at +2, **94% at +3**. Mean gate −4.36pp on 357 (|t|≈1.7, and that SE is too small because players repeat across matches) |
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
