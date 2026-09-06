# Possession, down, distance and yard line are already recorded — in the other table

**The build was already done. Nothing needs adding, no migration, no
backfill.** The four features are in the payload, parsed by the shipped
recorder, stored in a table with columns for them, and the recorder ran across
the 09-05/09-06 slate.

What is missing is an **export**, not a feature.

## The premise, and why it looked true

`espn_cfb_game_state` genuinely does not carry possession, down, distance or
yard line. That is correct by design: it is **one row per poll**, holding what
is game-level — timeouts, the live line, ESPN's win probability.

Down and distance are **play-level**. They live in the sibling table,
`espn_cfb_live_plays`, which already has:

```
down · distance · yards_to_goal · pos_team · def_pos_team · drive_is_home_offense
```

`core/feeds/espn_cfb_storage.py` says so in its own docstring — basketball's
table "cannot be widened to hold this … needs down, distance, yards-to-goal
and possession." Looking at the state table and concluding the features are
absent is reading the wrong one of two tables written by the same poll.

## Verified at four levels

| level | check | result |
|---|---|---|
| ESPN payload | real CFB summary, game 401867866 | **128 of 128 plays** carry down + distance + yardsToEndzone + team.id |
| parser | `core/feeds/espn_cfb_recorder.py:140-144` | reads `start.down`, `start.distance`, `start.yardsToEndzone`, `start.team.id` |
| **live end-to-end** | `python -m core.feeds.espn_cfb_recorder --probe` | `77 plays parsed`; last play `down 1, distance 10, yards_to_goal 81, pos_team '264'` |
| production | `espn_cfb_game_state` export | **18,775 rows, 50 games**, 09-05 22:08 → 09-06 16:08 |

The probe is read-only and writes nothing. `poll_game()` writes plays, win
probability and state from **one** payload in one call, so a slate that
produced 18,775 state rows produced play rows on the same polls.

## The actual gap: no export exists

`backups/exports/` holds `espn_cfb_game_state_…csv.gz` and **no
`espn_cfb_live_plays` export**. That is almost certainly why the features look
absent — nobody outside the database has seen them.

Two things are needed, both operator-side and both one line:

1. `select count(*), min(first_seen_at), max(first_seen_at) from espn_cfb_live_plays;`
   — confirms rows landed, which I cannot check (SSH publickey denied for me).
2. An export of that table alongside the state export, so the model can be
   built against it.

**If step 1 returns zero**, the diagnosis changes completely: the schema and
parser are right, so an empty table would mean the writer path failed
silently — and *that* is the scenario worth the alarm, not a missing feature.

## What I did build: the missing regression test

The CFB recorder has **no tests and no fixtures** — none on any branch. Its
failure mode is documented and silent: `docker-compose.cfb-live.yml` warns
that for football `summary.plays` is empty (plays live under `drives`), so a
basketball-shaped parser "writes nothing while every heartbeat stays green."
State rows would keep landing from the same poll, so nothing would look wrong.

Staged in `analysis/staged/` with a real trimmed fixture (3 drives, 17 plays,
`plays: []` exactly as ESPN serves football). Six tests: plays come from
`drives` not `summary.plays`; all four features present **per play** rather
than in aggregate; values in range, not merely non-null; possession is a real
competitor and never on both sides; `yards_to_goal` maps to `yardsToEndzone`
and not the raw `yardLine` (they coincide on one half of the field, so a wrong
pick is invisible in half the data).

**Verified and mutation-checked**, because a test that cannot fail is worth
nothing:

| mutation | result |
|---|---|
| plays moved to `summary.plays`, `drives` emptied | 0 parsed → **suite fails** |
| `yardsToEndzone` removed | 17/17 null → **suite fails** |

6 passed against the recorder on `main`.

## Cost of deploying

**Nothing to deploy for the features.** No migration, no code change, no
backfill question — the table and parser have been shipped and running.

The test is test-only: no schema, no runtime path, no container change. It
lands wherever `core/feeds/espn_cfb_recorder.py` lives.

## What this does not tell us

Whether `espn_cfb_live_plays` has rows in production. That is one SELECT and
it is the only open question here. Everything above says it *should* — the
parser works live, the recorder ran, the write is in the same call as a write
that demonstrably succeeded 18,775 times — but "should" is the word that has
cost this project the most, so it stays flagged until someone runs the count.
