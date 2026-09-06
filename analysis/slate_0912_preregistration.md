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
