# Saturday runbook — 2026-09-12

**Both of this week's failures began MID-SLATE, and a T-30 check passes cleanly
before each.** The venue recorder died at 22:20Z with games in progress (17
hours to notice). The ESPN recorder stopped at 21:37Z with two games live (53
minutes). The start is covered by an instrument; **the middle is covered by a
person noticing**, and this is what makes that a procedure instead of luck.

---

## T-60 · rebuild the map

Saturday's games **cannot** be in any file that exists before Saturday — the
builder matches ESPN events against venue games *on the tape*, and the tape
does not have them yet.

```bash
python3 scripts/build_cfb_game_map.py --days 2 --dry-run   # on main
```

Read-only. Prints matched / unmatched with confidences. **The DB write is the
operator's** — do not run the writing form.

Expect some unmatched. They are reported, never guessed: below
`--min-confidence` the builder writes nothing, because a mispaired game is
silent and unrecoverable while an unmatched one is a visible gap.
**Unmatched games are NOT an FCS problem** — of 16 unmappable in one sample, 0
were FCS-only and 5 were FBS-vs-FBS. Do not scope by division.

---

## T-30 · readiness check

**This file is NOT on main.** It lives only on
`worktree-quant-d-loss-decomposition` (3 commits, local branch, no remote), so
running it from a main checkout is a file-not-found — and `analysis/staged/`
does not exist on main at all. Either check that branch out, or:

```bash
git show worktree-quant-d-loss-decomposition:analysis/staged/slate_readiness.py > /tmp/slate_readiness.py
python3 /tmp/slate_readiness.py
```

Merging it is the operator's call and is on the blocked queue. **The runbook
works either way** — discovering this at T-30 on the one morning it matters is
the failure this note prevents.

**Four lines, never one green/red:**

```
BOARD   n games listed by the venue      (the tradeable set)
MAP     n/n joinable to ESPN
VENUE   n/n covered
ESPN    n/n covered
```

**Scoped to the VENUE BOARD, not ESPN's schedule** — widening the ESPN window
moved its events 132 → 180 while venue games stayed **119 both times**. The
board is the smaller fixed population, and an ESPN game the venue never lists
is not a coverage failure. Scoping to the schedule gives a permanently red
check, which gets ignored by the second Saturday. *Do not "fix" this back.*

| line red | what it means | what to do |
|---|---|---|
| **BOARD** = 0 | venue lists no games, or probe failed | check the probe first — UNKNOWN is not zero |
| **MAP** | the two id spaces cannot be joined | rebuild the map. **Not a recorder fault** |
| **VENUE** | price recorder not covering the board | check `meridian-cfb-live-recorder` |
| **ESPN** | game-state recorder not covering | check `meridian-cfb-espn-recorder` |

**A red MAP is not a red VENUE.** The four-line split exists so nobody spends
T-30 debugging a healthy recorder — which is what a single "VENUE FAIL 19/50"
would have caused when the truth was "31 cannot be checked".

---

## The rule that matters most on Saturday

**Both recorders up and verified BEFORE kickoff, or the slate produces data that
cannot answer anything.**

Every measurement blocked this week reduces to the same requirement: **a
pre-kickoff snapshot and a live tape on the same game.** 09-05 never had both at
once. Detection of a mid-slate failure is worth less than starting correctly,
because a slate that starts wrong yields nothing recoverable.

That is what the T-30 check is for, and it is why it outranks the mid-slate
monitors that are not deployed.

### "First seen" is not "kickoff"

**A time-window pregame selector returns in-game rows on a quoting board, with
no error, no null, and no symptom.**

Measured: an anchor took ladders from a ≤900s window before "kickoff", where
kickoff was inferred as `min(first_seen_at)` for rows in state `in`. **All 14
"kickoffs" resolved to 22:08–22:09Z — the same minute.** That is the recorder
starting, not the games starting. ESPN's own rows show all 14 already in
progress at that instant: P2 14-0, P4 49-3, P4 45-3. **Zero of 14 observed at
0-0.**

It produced correct-looking numbers **only because the board was frozen** — 575
full-game spread markets, median 27 snapshots each, 0.0% with more than one
distinct mid. A frozen board still carries its last *pregame* quotes, so a
pregame ladder came back from a selector asking for mid-game rows.

**On Saturday the board will be quoting, and the same selector returns in-game
ladders under a pregame label.**

> **THE RULE.** Anything selecting a pregame or kickoff population must gate on
> **game state** — `period == 1 AND home_score + away_score == 0` — never on a
> clock, a timestamp, or a window relative to an inferred kickoff. It must
> return **nothing** for a game never observed at 0-0, **with no fallback**. A
> fallback is the same bug wearing a helper's name.

### Three instances, one defect

The next one will not look like the previous two:

| symptom | reality |
|---|---|
| `display_clock` reads 15:00 in period 1 | on rows already scoring 21-0 |
| `reg_left` jumps *backwards* four times | once by a full 900s |
| "first seen in state `in`" | the recorder's start, not the game's |

**All three make a mid-game row look like a kickoff row, and none raises an
error.** The state gate is the only defence — every clock-derived and
timestamp-derived quantity on this substrate has now failed at least once.

## Mid-slate · the uncovered window

**Nothing automated watches this.** Run every ~30 minutes while games are live.
Two checks, because the two failure modes are disjoint and neither sees the
other.

**1 · Venue side — arrival AND movement.** Volume alone stayed green through
the 09-05 freeze; 1.17M rows/hour while prices did not move.

```sql
SELECT count(*) rows, count(DISTINCT market_slug) markets,
       round(100.0*count(*) FILTER (WHERE dq>1)/count(*),1) pct_moved
FROM (SELECT market_slug, count(DISTINCT (best_bid,best_ask)) dq
      FROM market_snapshots
      WHERE market_slug ~ '-cfb-' AND is_live
        AND captured_at > now() - interval '1 hour'
      GROUP BY 1) s;
```

Healthy CFB: **26–41% moved** (81.8% on a good in-game hour). **`<5% while
games are live` → the venue is frozen.** Dense and frozen looks identical to
dense and healthy on any row count.

**2 · ESPN side — work identified vs rows written.**

```bash
docker logs meridian-cfb-espn-recorder --tail 3 | grep espn_cycle
```

`live_games > 0` with `plays_attempted == 0` is the failure. Both numbers are
on the same line. **On 09-06 that line was correct, printed, and sat there for
53 minutes**, which is the whole reason this runbook exists — visibility
without an evaluator is not detection.

Also check `state_rows == live_games`. The two rules are a **disjunction** and
each is blind to what the other catches: three-of-five games throwing leaves
`plays_attempted > 0`; a parse returning empty leaves `state_rows` intact.

---

## Idle-state cadence — set staleness from the TAIL, not the median

Between slates it is tempting to alarm on "no sweep this hour". **Do not bucket
by clock hour, and do not threshold at ~80 minutes.** Both produce false alarms
on a healthy board.

**Two different quantities, and they are not interchangeable:**

| quantity | idle-window value | what it answers |
|---|---|---|
| global distinct-stamp gap | 77.0 / 80.5 / 80.5 min across three sweeps | *did a sweep fire* |
| **per-market re-sweep interval** | min 3.2 · p25 35.1 · **median 68.5** · p75 80.5 · **max 116.0** (n=57,852 gaps) | ***was this market refreshed*** |

They would coincide only if every sweep touched every market. The 3.2→116 minute
spread says it does not: **the sweep is partial**, so "the sweep ran" and "this
market is fresh" are different facts and a monitor needs to say which one it is
checking.

**Threshold at the tail: 116 minutes.** A monitor set at ~80 fires on the
**quarter of markets that legitimately exceed p75** — 80.5 is a percentile of a
wide distribution, not a cadence.

**And an empty clock-hour bucket is the EXPECTED case, not the alarm.** The
median per-market interval (68.5 min) already exceeds an hour, so consecutive
refreshes routinely straddle an hour boundary and leave one bucket empty. A
sweep at 04:55 and the next at 06:15 empties 05:00 while nothing is wrong.

> Origin: meridian-ce hit exactly this while health-checking an idle board and
> nearly filed a missed sweep. Their global-gap measurement and the per-market
> distribution above are different populations; both are real. The p75 collision
> at 80.5 is what made one look like the other.

---

## What is NOT covered

State this before anyone reads a green T-30 as a guarantee.

- **`3be4ff4` is NOT DEPLOYED, and it must NOT be deployed as-is.** It is on
  main and **not in the running image** (`grep -c scoreboard_failures` in the
  container returns 0). Two separate facts:
  - *What it fixes:* against running code, a total scoreboard failure still
    empties `live_games`, which **silences the ESPN check above** — the recorder
    can hide a write failure by failing one step earlier.
  - *What it breaks:* it also made `parse_game_state` **raise** on a payload
    with no `header.competitions`. That raise escapes `poll_game` **before**
    `parse_plays` and `parse_win_probability` run, so such a game now records
    **nothing** where it previously recorded every play with `state = None`.
    Partial failure turned into total. Invisible to the cycle's own numbers:
    `state_rows` is 0 in both worlds, and `plays_attempted` is a **sum across
    live games**, so one game's rows going to zero is a dip, not a signal.

  **Deploy the call-site fix with it** (`debugger/recorder-plays-regression`,
  `fa24613`) — catch the raise, log `cfb_game_state_unparsed` at error level,
  set `state = None`, let the plays through. Do **not** "fix" this by reverting
  the parser to `return None`; that undoes the hardening and passes three of the
  four tests.
- **NOT_WRITING / COLLAPSED are specs, not running code.** The mid-slate check
  is a person, at 30-minute cadence, with a ~30-minute worst-case detection gap.
- **No off-host deadman.** If the box dies, nothing reports. Blocked on the
  operator and outside our infrastructure.
- **Testing against pinned exports manufactures gaps.** One run showed ESPN
  missing 18 of 37 games; it resolved to 18 kicking off before the export
  opened, 3 after it closed, **0 genuinely absent**. Window-match, or use live
  tables.

---

## Every invocation, with the ref that provides it

**A path without a ref is an instruction that works in exactly one person's
working tree.** Verified 2026-09-06:

| what | path | ref |
|---|---|---|
| map rebuild | `scripts/build_cfb_game_map.py` | **main** |
| readiness check | `analysis/staged/slate_readiness.py` | **`worktree-quant-d-loss-decomposition` only — NOT main** |
| venue movement check | inline SQL, this document | — |
| ESPN check | `docker logs meridian-cfb-espn-recorder` | — |

*Re-verify before Saturday.* Branches merge and move.

**And a warning about how to verify it.** A `for-each-ref` sweep looking for the
file returned **0 refs across 221** — a false zero, for a file that is
demonstrably on one of them. Two people hit this within ten minutes tonight.
Cross-check any "not found anywhere" with `git log --all -- <path>`, which found
the 3 commits the sweep missed. **A search returning nothing is a claim about
your search.**

## If something is wrong

**Do not redeploy mid-slate without weighing it.** Two of this week's incidents
were *caused* by deploys. A recorder that is writing is worth more than a
recorder that is correct-but-restarting, and a container restart during live
games costs tape that cannot be recovered.

Record what was lost, in games and minutes, before fixing. That number is the
only thing that makes the next prevention argument concrete.
