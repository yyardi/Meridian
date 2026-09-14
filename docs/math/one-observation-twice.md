# One observation, two decisions

Measured 2026-09-14 against live `public.pulse_decisions` (19,333 rows,
2026-08-23 → 08-31). This finishes the natural-key characterisation and
**retracts** the writer-defect claim made with it.

## What the 60 duplicate exit pairs are

`market_slug, decided_at, action` collides 84 times. Sixty of those are
`action='exit'`, and every one is a `profit_target` row and an `ev_stop` row
with the same `decided_at`. `decided_at = ob.captured_at` — the OBSERVATION's
timestamp, not the decision's — so any two decisions taken on one snapshot
collide by construction.

Five identities, each of which could have disagreed, hold at 60/60:

| check | result |
|---|---|
| the target row was written first (`id`) | 60/60 |
| the entry's `filled_at` equals the pair's `decided_at` | 60/60 |
| target limit = entry ± `PROFIT_TARGET` (0.05) | 60/60 |
| stop limit = the touch on the exit side (ask for yes, bid for no) | 60/60 |
| fair value at/through the entry price — the #9 stop trigger | 60/60 |

So the sequence is the registered one, in one cycle: `_check_entry_fill`
opens the position and rests the profit target ("the exit rests the moment
the entry exists — that IS the strategy"); `_manage_position`, later in the
same iteration on the **same** observation, finds fair value already through
the entry, withdraws the target and rests the stop at the touch. The suite
has defended that supersession since it was written
(`test_adverse_fv_moves_the_exit_to_the_touch_as_a_limit`); what it did not
cover is the case where both rows land on one tick.

**Not one decision written twice.** Two decisions, correctly sequenced.

## Which price governs — it is already written down

| row | rows | live | withdrawn | filled |
|---|---|---|---|---|
| `profit_target` | 60 | **0** | **60** | 0 |
| `ev_stop` | 60 | 50 | 10 | **50** |

`withdrawn_at` is set on the target in 60 of 60 and `filled_at` on the stop
in 50 of 60. No group has two live rows. The governing price is therefore
selected by `withdrawn_at IS NULL`, never by row order, and no `ORDER BY`
has to be invented. A dedupe that picked a row would be strictly worse than
the status quo: it would delete a limit that really rested and really stood
down, and it could pick the wrong price — the two differ by a mean **2.28c** signed
(the stop conceding), worst 9.00c, and in 9 of 60 the stop is the *better*
price. Mean |gap| is 3.18c over all 60, 3.67c over the 52 that differ.

PULSE is shadow-only (`note="shadow only — no order exists behind anything
this writes"`), so no order was placed at either price. The question is
live-mode design, not a live exposure.

## The defect this uncovered: no watermark on the observation

Seven of the sixty were **not** one cycle. Their two rows differ in
`created_at` by 13–28s in separate transactions, against one snapshot:

```
tsc-wnba-la-sea-2026-08-30-161pt5  decided_at 22:11:29.450732
  profit_target  created 22:11:29.63  minutes_left 15.80  fv 0.8114  limit 0.79
  ev_stop        created 22:11:58.02  minutes_left 15.22  fv 0.7208  limit 0.76
next snapshot for that market: 22:11:59.55  (bid 0.70 / ask 0.74)
```

`_observations` takes `DISTINCT ON (market_slug) … WHERE captured_at > now()
- MAX_OBSERVATION_AGE_SECONDS (60) ORDER BY captured_at DESC` — the newest
snapshot in the window, re-served every cycle **whether or not it is new**,
and nothing records that it was already acted upon.

Re-serving would be harmless if the price were a function of the
observation. It is not. `_estimate(ob)` also reads `self._venue_clocks` and
`self._event_flags`, both **rebuilt from the database every cycle**. All
seven rows are `v4` with `minutes_left_is_estimate = false`: the ESPN clock.
Between the two evaluations of one frozen snapshot the clock advanced
0.20–0.58 min in six of them and fair value moved a mean **5.05c** (max
9.75c) — the whole 5c profit target — on an unchanged book. The seventh
moved fv 1.1c with `minutes_left` identical, which is the v4
availability-flag cache moving instead.

Consequences beyond the seven rows:

* the stop rested at 0.7600, the stale ask; the live ask was 0.7400;
* `decided_at` is the data's time, not the decision's. The only witness to
  the gap is `created_at − decided_at`: hold p90 **20.4s**, p99 30.1s, max
  **59.5s** (= the configured 60s window), **23.7%** of 13,680 hold rows
  over 10s; enter p99 27.6s, exit p99 19.1s;
* cadence is not uniform, so this is not a rare stall. In one hour of one
  WNBA game, `161pt5` had 6,520 snapshots (median gap 0.2s) and `185pt5`
  had 26 (median gap **30.0s**) — two writers, two cadences, same game. A
  sub-30s cycle re-prices the slow markets several times per snapshot.

The fix is a per-market floor: remember the last `captured_at` acted upon
and skip an observation that is not newer. `tests/test_pulse_live.py::
test_an_observation_is_evaluated_once` is `xfail(strict=True)` and XPASSes
when it lands. Routed to the engine's owner — it changes when stops fire.

## What the 24 enter pairs are

A yes and a no entry on one market at one microsecond, each with its own
price, size and positive edge. Legitimate; the key omitted `side`. The key
in `deploy/aws/merge_history.sh` is now
`market_slug,decided_at,action,side,limit_price` (75 of 84 resolved;
`reason` deliberately refused — it is NULL on all 2,974 enter rows and the
script joins with plain equality).

## The error in the first characterisation

I reported the 60 as "identical in side, price, contracts and `created_at`,
differing only in `reason`". Price differs in 52 of 60 and `created_at` in 7
of 60 — and those 7 are the second mechanism, so the field I got wrong was
the one that mattered.

The cause was not an unmeasured field. This query had already run over all
84 groups and printed:

```
 limit_price        |               76
 reason             |               60
 created_at         |               31
 stake_usd          |               24
 side               |               24
 contracts          |               24
```

76 − 24 = **52**. 31 − 24 = **7**. Both numbers were on the screen, in the
same thirteen-row table, one subtraction away. I read the 24s as "the enter
groups are the ones that vary", narrated the exits as the complement, and
never reconciled the two rows that did not fit.

**A per-column count over a mixed population is not a per-cause claim.**
Every row of that table is a mixture of two causes; a claim about one cause
needs a query whose `WHERE` names that cause. Attributing each row to
whichever cause its magnitude resembles is narration, and it will agree
with itself.
