# A green suite that measured an ordering

Measured 2026-09-14, at `origin/main` e3d1ccc, in a clean worktree with a
dedicated per-run database.

## The report, and the two things it got right

A peer pushed a red suite (the `pytest | tail && push` line again — the exit
status comes from `tail`) and reported that `tests/test_pulse_live.py` failed
4 tests before a merge and 6 after, while **every one of them passed in
isolation**. The diagnosis offered was shared database state: earlier tests
leaving rows behind.

Right that a green run of that file was evidence about an ordering rather
than about the code. Wrong about the mechanism, and the mechanism matters
because it changes the fix.

## It is not state. Earlier tests consume TIME

Eleven test modules do `NOW = dt.datetime.now(UTC)` **at import**, which is
collection — once, at the start of the run. They then insert snapshots at
`NOW - 30s`. The engine's own predicate is

```sql
captured_at > now() - make_interval(secs => MAX_OBSERVATION_AGE_SECONDS)   -- 60
```

evaluated at **execution**. So every such module carries a silent budget of
`60 - worst_offset` seconds of suite elapsed time, after which its own
fixtures age out of the window it is testing. The suite runs ~35s, so
whether a file passes depends on its POSITION in the run.

Reproduced by shuffling the FILE order (119 files, four seeds):

```
seed=1  2186 passed          seed=3  2 failed, 2184 passed
seed=2  2186 passed          seed=4  2186 passed
```

Seed 3's two failures were `test_pulse_daily_budget`'s Wednesday shape and
its withdrawn-entry release — the two tests that use the file's largest
offset, `NOW - 30s`, and it ran 114th of 119.

Bisecting the 113 predecessors found no culprit: neither half reproduced it
alone. That is the tell that nothing is being left behind. The decisive
experiment is one file, alone, with its `NOW` shifted back:

| simulated elapsed | result |
|---|---|
| 0s | 7 passed |
| 20s | 7 passed |
| **32s** | **2 failed**, 5 passed |

Same two tests, no other test in the process. The threshold is where the
arithmetic puts it: 60 − 30 = 30 seconds.

## Which tests, exactly

Shifting each module's `NOW` back 32s and running each file ALONE — the only
measurement that separates elapsed time from ordering:

| file | failures at +32s |
|---|---|
| `test_pulse_daily_budget.py` | 2 |
| `test_pulse_reprice.py` | 1 |
| `test_pulse_shadow_min_bankroll.py` | 1 |
| the other 8 modules with a module-level `NOW` | 0 |

**Four tests in three files** — which is exactly the "4 tests fail before the
merge" that was reported, from a different direction.

`test_pulse_live.py` is NOT among them, despite using offsets up to 300s: its
old rows are meant to be excluded, and a row that is already outside the
window stays outside. A naive "worst offset" scan flagged it; the probe
cleared it. The scan was the wrong instrument because it never asked which
side of the predicate each row was supposed to land on.

## The fix, and the instrument it must not blind

`tests/conftest.py` grows `module_now_is_per_test`: an autouse fixture that
re-pins an **opted-in** module's `NOW` to the instant its test runs, so the
offsets mean "N seconds ago" rather than "N seconds before collection".
Three modules opt in with `NOW_PER_TEST = True`.

Opt-in, not automatic, and that is not caution — the first version re-pinned
any module global named `NOW` that happened to be a datetime and clobbered
two modules whose `NOW` is a deliberately FIXED calendar timestamp
(`test_kalshi_events_recorder`, `test_espn_cricket_recorder`): 9 tests red.
The matcher was broader than the measurement that justified it.

A fix like this deletes its own evidence: once `NOW` is re-pinned per test,
editing the module's `NOW` line no longer simulates anything. So the shift
became an input — `MERIDIAN_TEST_NOW_SHIFT` — and `scripts/elapsed_probe.sh`
walks it upward per file to print the budget each one still has:

```
tests/test_pulse_daily_budget.py               2 test(s) fail at +30s
tests/test_pulse_reprice.py                    1 test(s) fail at +20s
tests/test_pulse_shadow_min_bankroll.py        1 test(s) fail at +30s
tests/test_pulse_live.py                       none (>=60s, or not time-sensitive)
```

Those thresholds are what `60 - worst_offset` predicts (30, 20, 30), which is
the check that the instrument measures what it claims. **They are no longer
reachable by a slow suite** — only by the shift — because real elapsed time
no longer enters `NOW`. What the table is for is the regression: a budget
that DROPS after someone edits fixtures, or a file that reports no budget
because it quietly stopped being opted in.

Note what the probe does NOT say. "All green at +30s" would be the wrong
acceptance line to write down, since three files are designed to sit 30s from
the edge; the invariant is that the suite is green at shift 0 in every file
order, and that each file's budget matches its own worst offset.

## What is still true

The suite's isolation from OTHER suites is structural (a per-run
`meridian_test_<pid>` database, created and dropped by `conftest`). Its
isolation WITHIN a run is per-file cleanup fixtures, and `_observations` has
no slug filter — it reads the whole table — so a module that inserts a live
snapshot and does not delete it would pollute every engine test after it.
Two files insert without cleanup. `test_picks_tipoff`'s rows are
`is_live=False`, which the engine's predicate excludes outright, so they are
inert. `test_game_detail`'s can be live and carry a PULSE market type, and
running it immediately before `test_pulse_daily_budget` changed nothing —
but "did not fire once" is the weakest kind of evidence, and it is the one
file where the trap is real rather than ruled out.

`pytest_report_header` used to print "(dedicated per-run database)"
unconditionally — an assertion it had not checked, which is precisely how a
green run becomes uninterpretable when someone sets
`MERIDIAN_TEST_DATABASE_URL`. It now names the regime, and says so when a
`NOW` shift is in force.
