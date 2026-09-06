# Pre-registration: what the 2026-09-12 slate must show

Written before the slate. "One slate settles it" is only true if the pass
condition is fixed first.

## ★ FIRST, A CORRECTION: THE CONFIDENCE FLOOR IS NOT DOING REAL WORK

I chose floor 0.90 out of caution because every `cfb_game_map` row is
`slug_fuzzy_date_pm1` — fuzzy slug on a ±1-day window, the method that pairs
wrong games silently. **Checked for correctness rather than coverage** by
matching each row's ESPN home/away names against the venue team names its slug
codes resolve to:

    floor 0.00   n 55   OK 53   MISMATCH 2   precision 96%
    floor 0.80   n 41   OK 39   MISMATCH 2   precision 95%
    floor 0.90   n 29   OK 28   MISMATCH 1   precision 97%

**Both residual "mismatches" are correct pairings my matcher cannot verify** —
`LIU` vs "Long Island University Sharks", and "Merrimack College" vs "Merrimack
Warriors". **On inspection the map is 55/55 correct.**

**So floor 0.90 costs 46% of coverage and buys one percentage point of
unverified precision. Use floor 0.00.** My earlier recommendation of 0.90 was
caution unsupported by measurement, and it would have discarded half the games.

**And my first correctness check was itself broken**: it compared full strings
by ratio, so "Toledo" vs "Toledo Rockets" scored 0.63 and failed. It reported
51 of 55 as mismatches — **it would have condemned a working map at "7%
precision."** ESPN appends mascots and the venue does not; containment before
ratio fixes it. A correctness checker that fails on correct rows is the same
family as a join that succeeds on a row counter.

## THE MEASUREMENT

**Stage:** games with fills on 09-12 whose ESPN game state is present for their
fill window. Chain: `fills.game_id -> cfb_game_map.venue_game_id ->
espn_game_id -> espn_cfb_game_state.game_id`, floor 0.00.

**Denominator:** games with at least one fill on 09-12 **whose entire fill
window lies inside state-recorder uptime.** Not all games with fills.

**Uptime, defined from the recorder's own rows, not from a status signal:**
uptime is any interval between consecutive `espn_cfb_game_state.first_seen_at`
values with a gap **≤ 10 minutes**. A gap over 10 minutes is downtime. This is
the defence against re-measuring a startup artifact: the 32% figure arose
because state's first row was 22:08:57Z while that day's fills ended at 20:51,
so every earlier hour was 0/N **by construction**. Games outside uptime cannot
enter the denominator.

## ★ WHAT IS REPORTED IF A RECORDER IS DOWN FOR PART OF THE DAY

This is the likely case, not the exception, and it is fixed now so it cannot
become a post-hoc exclusion:

1. **Uptime fraction is reported first**, before any capture number.
2. Games whose fill window falls partly or wholly in downtime are **excluded
   from the denominator and reported as their own line with a count.**
3. **If uptime covers under 50% of the slate's fill hours, the slate does not
   settle the question** and the verdict is "not measured", regardless of what
   the surviving games show. A high capture rate on the 20% of the day the
   recorder happened to be up is the 32% error again.

## THE BRANCHES

| verdict | capture | reasoning |
|---|---|---|
| **PASS** | **>= 80%** | CFB captured/week 46 against the 54 assumed at 94%; every date in the accrual table moves by under 20%. The plan stands. |
| **MARGINAL** | **50-79%** | 28-45/week; dates stretch 1.2x-1.9x. Plan survives with a re-date, and the gap is worth a fix. |
| **FAIL** | **< 50%** | Under 28/week; dates more than double. The live model cannot see most football games and the input stage is the binding constraint, not accrual. |

**Distinguishing the three diagnoses:**

* **Works** — PASS, and the missing games are scattered rather than clustered in
  time or by division.
* **Needs a fix** — capture is materially below uptime, i.e. state was up and
  the games still did not land. That points at the map or at ESPN's own game
  coverage, and it is repairable.
* **Cannot see football at all** — capture near zero *while uptime is high*.
  Distinct from FAIL-through-downtime, which is an ops problem, not a
  capability one.

## BRANCH REACHABILITY, PROJECTED BEFORE FIXING

2026-09-12 carries **113 CFB games** (measured previously for poll load). Our
09-05 slate produced fills on 37 of ~57. Scaling, 09-12 should produce fills on
roughly **60-75 games**. At that denominator:

* PASS needs >= ~50 of them in state — reachable.
* FAIL needs < ~33 — reachable.
* MARGINAL is the 33-50 band — reachable.

**All three branches are reachable at the expected game count**, so the
registration is not defective. The one branch that could be unreachable is
"cannot see football at all", which requires near-zero capture at high uptime;
that is reachable only if the map or state genuinely fails, which is the point.

---

# ★ AMENDMENT: the venue-tape pre-flight condition, added 2026-09-06

**This registration was silent on the venue tape because we all assumed it was
running. It is not.** Added before the slate, not after, and stated as a
condition to check **in advance** rather than a caveat to apply afterwards.

## What broke, verified in the repo

Two compose files claim the same container name:

    docker-compose.nfl.yml:108   container_name: meridian-cfb-live-recorder
                                 command: python -m core.live_recorder --interval 1.0
    docker-compose.cfb-live.yml:20  container_name: meridian-cfb-live-recorder
                                    command: python -m core.feeds.espn_cfb_recorder

Docker container names are unique. **Bringing up the ESPN one destroyed the
venue one silently** — no error, no gap in any status signal, and the survivor
is the ESPN feed. CFB venue live recording stopped **2026-09-05 22:08Z**.

## Why the registration would have landed in the wrong bucket

The uptime denominator measures `espn_cfb_game_state`, and **that recorder is
the one that survived** — so the ESPN condition would pass. But fills and prices
come from the **venue** tape, which would be at ~35-minute sweep cadence rather
than ~1s.

So the registration would answer *"can the live model see football"* on a tape
that **cannot support a live model at all**, and return **FAIL for an
infrastructure reason.** The registration already separates "needs a fix" from
"cannot see football" — and without this amendment the result would land in the
wrong one of those two, which is precisely the diagnosis the separation exists
to prevent.

## ★ THE PRE-FLIGHT CONDITION, checked BEFORE the slate

**A CFB venue live recorder must be writing `market_snapshots` at sub-10s
cadence during the slate.** Verified by the tape itself, not by a status signal
or a container listing:

> On the slate day, distinct `captured_at` stamps per hour for CFB markets must
> imply a median inter-stamp gap **under 10 seconds**. Saturday 09-05 at peak
> ran **967 distinct stamps in one hour — ~3.7s.** The 900s sweep produces
> **one stamp per ~35-minute cycle** and is trivially distinguishable.

**If that condition fails, 09-12 does not measure the question and the honest
output is to say so in advance rather than run it and report FAIL.** This is
recorded now so that saying so is a pre-commitment rather than an excuse
constructed after an unwelcome number.

## Why a status signal would not have caught it

`rows_written` on the snapshot writer counts **only rows returned by
`ON CONFLICT DO NOTHING ... RETURNING`** — newly inserted ones. A recorder whose
rows all collide reports zero while running normally, and a dead recorder also
reports zero. **The metric cannot separate the two**, which is why the condition
above is defined on the tape's own timestamps.

## One thing this makes better, not worse

`core/live_recorder.py` carries **no band filter** — no `MIN_MID`, `MAX_MID` or
`MAX_SPREAD`, unlike `core/quote/depth_signal.py` which gates at 0.15. So if the
venue recorder is restored, **the whole slate is captured, not just the quotable
band.** The 43.24% of the CFB board that the quote engine gates out by policy is
present on the venue tape.

---

# ★ THE PRE-FLIGHT CONDITION I JUST ADDED IS BROKEN. REPLACED.

Debugger tested it against known-bad days **before it mattered**, which is the
only way this gets caught. It passes the one day it existed to catch.

    09-06, recorder dead all day        25 stamps   median gap 2,076s   FAIL (right)
    09-05 whole day, died 22:08Z    13,175 gaps     median gap  2.72s   PASS  <-- wrong
    09-05 slate window 16:00-24:00Z  6,099 gaps     median gap  3.16s   PASS  <-- wrong

09-05 is the day CFB venue recording died mid-slate: **372 of 480 slate minutes
covered, ~110 minutes with no tape at all**, and my condition reports PASS.

## Why no threshold on a median fixes it

**An outage of any length contributes exactly ONE gap.** In the slate window
there were 6,099 gaps and exactly three exceeded 60s. A median is the 3,050th
value; three outliers cannot move it, and p99 lands at 10s — on my boundary by
coincidence rather than by design.

**The statistic measures the spacing of stamps that EXIST and is nearly blind to
stamps that are ABSENT**, which is the thing being tested. That is arithmetic,
not an empirical accident, and it holds at every threshold.

**And my second criterion does not save it either**: "<50% uptime = not
measured" passes at 77.5% minute-coverage. **On the exact day the recorder died
mid-slate, both stated criteria pass and the slate would have been reported as
measured.**

## ★ THE REPLACEMENT — three conditions, each doing a different job

All computed on the slate window (16:00–24:00Z) from the venue tape's own
`captured_at` stamps for CFB markets. **All three must hold.**

1. **CADENCE — median inter-stamp gap < 10s.** Distinguishes the ~1s live tape
   from the ~900s sweep. This is what the original condition was actually good
   for, and it is kept for that job only.
2. **CONTINUITY — maximum inter-stamp gap <= 60s.** Fires on any outage over a
   minute. On 09-05 the max was **2,487s against ~4s healthy — a 600x
   separation**, so the test is not delicate.
3. **COVERAGE — minutes containing at least one stamp >= 95% of slate minutes.**
   Catches an accumulation of short outages that no single maximum would flag.
   09-05 was 77.5%.

**Any one of (2) or (3) separates 09-05 from a healthy slate.** Both are kept
because they fail on different shapes: one long hole versus many small ones.

## What I could not verify, stated rather than implied

**I could not reproduce Debugger's test on my own data.** My only local
substrate with `captured_at` is `book_trade_joined` — **810 distinct stamps
against their 13,175**, already containing a ten-hour overnight gap, and my
injected-outage mutation moved nothing because the injection landed inside that
existing gap. It is the wrong table: the book/trade join, not the raw snapshot
tape.

**So I am accepting their measurement on the mechanism rather than on my
reproduction.** The mechanism needs no data — one outage is one gap, and a
median over thousands cannot see it. But the specific figures above are theirs,
not mine, and I have not independently confirmed them.

## Provenance note

Debugger could not locate this registration and tested a paraphrase. It **is**
pushed — `analysis/slate_0912_preregistration.md` on
`origin/quant-b/live-regime-cuts` — and I have confirmed the paraphrase matched
my literal wording ("median inter-stamp gap under 10 seconds"), so their result
transfers. Worth knowing that a pushed non-main branch was not findable by
search.

---

# ★ DRY RUN: NFL, 2026-09-09 — three days early, not two

The pre-flight is now **executable**: `analysis/tape_preflight.py`. A prose
condition gets paraphrased — Debugger had to test a paraphrase of the last one
because they could not find the file. This one is code and takes a CSV.

## The first NFL game is WEDNESDAY, not Thursday

Checked against the venue rather than assumed — open `KXNFLGAME` events by game
date:

    2026-SEP-09   1 game    <- first live exercise of core.live_recorder since it died
    2026-SEP-10   1 game
    2026-SEP-13  13 games

**So the dry run is Wednesday 09-09, giving three days of margin before the CFB
slate rather than two.**

## Why this matters beyond convenience

**The live-recorder code path cannot be verified on a quiet day.** Both
`meridian-nfl-live-recorder` and `meridian-live-recorder` correctly report
`cycles: 0` right now — NFL has not started and the WNBA season ended 08-31 — so
a check today proves nothing in either direction. **The last demonstrable proof
that `core.live_recorder` produces a dense tape is the 09-05 CFB slate**, which
is also the day it died.

The NFL recorder is already running, already configured, and is **not blocked on
the operator's CFB fix**. So Wednesday exercises the path for free.

## What Wednesday tests, and what it does NOT

**Tests:** the code path, and the pre-flight condition itself — against real
live data rather than a reconstruction, while both a known-good (09-05 peak) and
a known-bad (09-05 slate, 09-06) comparison are still available.

**Does NOT test:** the capture *rate*. **One game cannot estimate a rate.** NFL
runs ~15 games a week against CFB's ~57 and Wednesday is a single game. **A
clean Wednesday must not become "capture is fine"** — that would be the
one-observation-is-not-a-measurement error, and it is pre-committed here as
inadmissible.

## Registered outcomes

* **Dense NFL tape** → the path is proven before Saturday needs it, and the
  condition has been exercised on live data. Saturday proceeds as registered.
* **No dense tape** → three days to find out why, rather than discovering it on
  Saturday night with the slate gone.

Either way the *rate* question stays open until a full slate runs.

---

# ★ THE DENOMINATOR GATES ON THE WRONG RECORDER. FIXED.

## First, the discrepancy: nobody misread. Both predicates are in this file.

    line  43  uptime from `espn_cfb_game_state.first_seen_at`, gap <= 10 MINUTES
    line 139  venue tape, median inter-stamp gap under 10 SECONDS

**Debugger read §4, the original denominator. ce paraphrased the amendment.
Both are mine and I never reconciled them** — I bolted a venue pre-flight onto a
registration whose denominator still ran on ESPN state, and left two conditions
on two tables with thresholds 60x apart in one document.

**Consequence for the evidence:** Debugger's three-window test was against the
amendment, so **the three-condition replacement at 2202b48 keeps its evidence
and stands.** What was never tested is the denominator, and that is the
dangerous one.

## ★ AND THE DENOMINATOR IS THE MOST EXPENSIVE VERSION OF TODAY'S PATTERN

`espn_cfb_game_state` is written by the recorder that **SURVIVED** the
container-name collision. The dead one feeds `market_snapshots`, which is where
**fills and prices** come from — and the quote engine only uses observations
newer than `MAX_OBSERVATION_AGE_SECONDS = 600`, so a 35-minute sweep yields
nothing usable.

So on 09-12 as things stand:

    ESPN uptime gate        -> HIGH (that recorder is alive)
    venue tape              -> ABSENT
    capture                 -> near zero
    my diagnostic tree      -> "capture near zero WHILE uptime is high"
                            -> "CANNOT SEE FOOTBALL AT ALL — a capability failure"

**A dead container would have been reported as a verdict about the model.**
That is the failure shape of the entire day, one level up, and at the most
expensive possible point.

It also invalidates the reachability projection: 60–75 games with fills was
scaled from 09-05's 37 of ~57 — **a slate on which the venue recorder was
alive.**

## THE FIX: two recorders, two conditions, both required

The gate was letting one recorder's health stand in for the other's.

**CONDITION A — VENUE TAPE (`market_snapshots`, CFB, distinct `captured_at`).
Required, and it is the one fills depend on.** Evaluated by
`analysis/tape_preflight.py`: cadence median < 10s, continuity max <= 60s,
coverage >= 95%.

**CONDITION B — GAME STATE (`espn_cfb_game_state.first_seen_at`). Required only
for the game-state join**, on the same three conditions, computed by the same
script on that table's timestamps.

**The denominator — games whose entire fill window lies inside uptime — is
defined on CONDITION A, not B.** Fills come from the venue tape.

**If A fails, the slate is NOT MEASURED and no verdict about the model is
issued, whatever B shows.** That is pre-committed here, not decided on the
night.

## ★ AND THE REHEARSAL WINDOW IN UTC

I wrote "Wednesday 09-09". **The venue's own stamp says otherwise**, and this
programme has been caught by ET/UTC twice already:

    KXNFLGAME-26SEP09NESEA-NE   occurrence_datetime  2026-09-10T03:20:00Z
    minus the verified +3h convention  ->  KICKOFF 2026-09-10 00:20Z

**The ticker date is US-local; the UTC kickoff is the 10th.** Same moment —
Wednesday evening US time — but **the rehearsal window is 2026-09-10 00:00Z to
04:00Z**, and stating it as "09-09" would have someone run the check a day
early. Third instance of this trap in the programme; the fix is that every
window in this file is UTC and says so.

---

# ★ VALIDATING THE PRE-FLIGHT IN THE PASSING DIRECTION — declared before the data

**The three-condition pre-flight has never been observed to PASS.** Every
exercise so far has been against known-BAD windows:

    09-06, dead all day        FAIL  (correct)
    09-05, mid-slate death     the ORIGINAL passed and should not have
                               — which is why it was rewritten

**A check seen failing but never seen passing is half-tested.** A rule that
cannot pass is as useless as one that cannot fail, and I have spent two days
finding that shape in other people's instruments. This closes it on mine.

The container was restored 2026-09-06 20:43Z and the tape is dense again —
5,530 rows / 73 distinct stamps / 166 markets in ten minutes, mean gap 2.46s,
against 4,736 rows across ONE stamp in the preceding hour.

## What each outcome means, fixed now

* **All three PASS** → the pre-flight is validated in both directions and
  Wednesday's NFL window becomes a confirmation rather than a first test.
* **CADENCE fails** → the tape is not live-dense and the restore did not work.
  At an observed 2.46s mean gap this would indicate something wrong with my
  computation, not with the tape, and I would check mine first.
* **CONTINUITY fails** → a restart or sweep boundary spiked one gap past 60s.
  **This is the condition I expect to be fragile**, and a failure on a healthy
  recorder means the 60s ceiling is too tight for real operation.
* **COVERAGE fails** → **the most informative failure available.** On a healthy
  recorder it would mean the 95% floor cannot survive normal operation —
  restarts, sweep interleaving, partial hours — and the floor is wrong rather
  than the tape. **Better learnt on a Sunday than on the slate the measurement
  depends on.**

**A failure tonight on a known-healthy recorder revises the CONDITION, not the
verdict about football.** That is pre-committed here so it cannot be decided
after seeing which way it went.

## The two windows

1. **Restored window** — 2026-09-06 20:43Z onward, whatever exists. A partial
   hour, so COVERAGE is measured against the window actually spanned and its
   failure is expected rather than diagnostic.
2. **Tonight's FBS slate, 23:30Z onward** — the first **full-slate healthy
   baseline on football at density**. This is what the 94% capture figure has
   never had: it is a WNBA number applied to football, and tonight replaces the
   assumption with a measurement for every stage downstream of the model.

---

# ★ PRE-FLIGHT VALIDATED IN BOTH DIRECTIONS — and continuity had a blind spot

Run against tonight's live CFB tape (`cfb_prices_tonight_20260906T221035Z`,
146,953 live rows). **Only ONE game was genuinely live** — 122,105 rows across
119 markets over 96.7 minutes; the other 37 "games" are pregame boards for later
dates, exactly as ce warned.

    window 20:35-21:43Z (spans the 20:43Z container restore)
      CADENCE     1.60s    PASS
      CONTINUITY  526.26s  FAIL      <- after the fix below; was 12.26s PASS
      COVERAGE    88.2%    FAIL

    window 20:45-21:42Z (post-restore, healthy)
      CADENCE     1.60s    PASS
      CONTINUITY  12.26s   PASS
      COVERAGE    100.0%   PASS

**All three conditions have now been observed both passing and failing.** That
closes the half-tested gap I flagged on my own instrument.

## ★ THE BLIND SPOT COVERAGE FOUND IN CONTINUITY

The first run reported **CONTINUITY 12.26s PASS while an 8.8-minute outage sat
at the window start.** `s.diff()` measures gaps **between stamps** and is blind
to the hole from window-start to the first stamp, or from the last stamp to
window-end — **which is precisely the truncation the condition exists to
catch.** An outage at the beginning of a slate is invisible to it.

Fixed by anchoring the gap series on the window boundaries. The same data now
reports **526.26s** and fails.

**Coverage caught what continuity missed**, which is the case for keeping both:
they fail on different shapes, and here one covered the other's blind spot on
live data rather than in principle.

## ★ AND MY PRE-DECLARED READING DID NOT APPLY

I registered: *"COVERAGE failing on a healthy recorder means the 95% floor
cannot survive normal operation and the FLOOR is wrong."*

**It does not apply here.** All nine missing minutes were at the edges and
**zero were interior holes** — the gap was the container restore at 20:43Z, a
real outage rather than a floor set too tight. **The floor is fine and the
pre-declared escape hatch is not needed.** Recording that the branch was
available and was not the right one, because it would have been easy to take.

One genuine off-by-one fixed alongside: the window end is exclusive and the
terminal minute was being counted as a window minute.
