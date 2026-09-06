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
python3 scripts/build_cfb_game_map.py --days 2 --dry-run
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

`analysis/staged/slate_readiness.py`. **Four lines, never one green/red:**

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

## If something is wrong

**Do not redeploy mid-slate without weighing it.** Two of this week's incidents
were *caused* by deploys. A recorder that is writing is worth more than a
recorder that is correct-but-restarting, and a container restart during live
games costs tape that cannot be recovered.

Record what was lost, in games and minutes, before fixing. That number is the
only thing that makes the next prevention argument concrete.
