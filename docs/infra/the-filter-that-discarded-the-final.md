# `period >= 4` was throwing away the final score

`cfb/run_ladder_calibration.py` runs daily at 10:40Z. Its live-table final was

```sql
SELECT DISTINCT ON (game_id) ... FROM espn_cfb_game_state
WHERE home_score IS NOT NULL AND league IN ('cfb','nfl') AND period >= 4
ORDER BY game_id, first_seen_at DESC
```

**ESPN drops `period` on the final row.** Of 107 CFB games observed at `post`,
**101 carry `period IS NULL`**; of 10 NFL, 9 do. So `period >= 4` excluded the
post row for ~94% of the games that had one, and `DISTINCT ON` then took the
last **in-game** row instead — a pre-whistle score for a game whose true final
was sitting in the same table.

On the games this query actually feeds (live route, venue id present):

| | reading an `in` row | reading the `post` row |
|---|---|---|
| CFB | **89** had reached post | 5 |
| NFL | **8** had reached post | 1 |

A pre-whistle total is too LOW, which settles a total UNDER when the real
total may have cleared, and `cfb_total_under_all` is registered.

## The fix changes the provenance and not one number

Preferring `state = 'post'` moves **28 CFB + 8 NFL** games from the proxy
route to the post route (of those with a venue id). The totals they carry:

**identical in 36 of 36.**

That is the honest headline. No published calibration figure changes, and
nobody should be told one does. The reason is the census in
[espn-post-is-not-a-final-score](espn-post-is-not-a-final-score.md): games are
abandoned **at the whistle**, so the last in-game row usually already holds
the final score. The defect was reading an unconfirmed row; the cost of it, so
far, is zero.

## The proxy error where it is measurable: exact, on eight games

For games in BOTH `espn_cfb_backfill_games` and the live table, comparing
totals:

| reached post | games | total exact | proxy low | proxy high | mean error |
|---|---|---|---|---|---|
| no | **8** | **8** | 0 | 0 | 0.00 |
| yes | 11 | 10 | 0 | 1 | +2.45 |

Eight of eight exact on the cell that matters — the unconfirmed games — and
the margin agreed too, so the two tables are not orientation-flipped.

**The single disagreement is the backfill's fault, not the proxy's.** Game
401856660: backfill 3-31 (total 34), live row 10-51 (total 61) at period 4,
0:15 remaining. A truncated game cannot score MORE than its final, so the
backfill row is the wrong one. The "truth" source is itself wrong in 1 of 11.

And the validation cannot be made bigger. `espn_cfb_backfill_games` holds
**55 games, all backfilled on 2026-09-06**, while the live tape runs
09-05 → 09-14 — so only 19 games appear in both, 8 of them unconfirmed. That
population is exhausted, not sampled.

## A table with no migration

`espn_cfb_backfill_games` has **no Alembic migration and no model.** It is
created by `archive/cfb/backfill_cfb.py` — in `archive/` — so a migrated
schema does not have it, and `GAMES_SQL` cannot run against a fresh database
at all. That is why the new tests exercise the extracted `LIVE_FINALS_SQL`
rather than `GAMES_SQL`: the part this change touched is the part that can be
tested.

## The decision that is NOT taken here

After the fix, **36 CFB + 6 NFL** games with a venue id still have no `post`
row. For those the proxy is all there is, and nothing on disk can validate
them — the backfill overlap is the eight games above and it is used up.

The query now labels every final `backfill` / `post` / `proxy`, and the run
prints the mix, so the size of the decision is visible before anyone reads a
verdict off it. **Excluding them is a strategy decision and is routed, not
taken.**

For the record, the recommendation and its precedent: **exclude and count.**
An excluded game is a smaller sample; a wrongly settled one is a biased
sample, and here the bias direction is known. `collect_mlb` **in this same
file** already does exactly that — it counts `unsettled` and skips, and its
docstring says "never guessed, and never derived from a box score". CFB is
the inconsistent one.

Which also corrects one thing worth correcting: `mlb_total_under_all` is
**not** flattered by this defect. MLB settles from the venue and skips what
the venue has not settled. Only the CFB/NFL side was ever exposed.
