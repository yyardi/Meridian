# analysis/archive — one-off investigations, kept for reproducibility

**These scripts are not imported by anything.** Each answered one question once;
the *findings* live in `docs/math/` and `docs/findings.md`, which are what you
should read. They are kept because a result nobody can reproduce is a rumour.

Archived 2026-09-05 during the simplification the operator asked for: the repo
was 283 files and ~68,000 lines, and the trading decision is ~20 of them
(`sandbox/strategy.py` is the readable version).

**Before running one, check whether its finding still stands** — several were
retracted the same week they were written:

| script | status |
|---|---|
| `quote_v2_*` (4) | mixed — the phantom classifier they use tests the wrong condition |
| `nba_*` (10) | surveys and r1–r5 harnesses, superseded by live recording |
| `nfl_day_one_survey.py` | survey, superseded by live recording |
| `pulse_loss_map.py`, `pulse_execution_decomposition.py` | the 09-01 loss map and its execution split |
| everything else (17) | one question each; read the finding in `docs/math/`, not the script |

Three rows were removed on 2026-09-13 — capture_is_not_a_proxy,
placement_curve_real_fills and flattening_book_insertion (named without
backticks here, so that "every file this README names in backticks exists"
stays a checkable claim). No such files are in this directory, anywhere in the
repo, or in git's record of deletions. The findings they described may still
stand; this table was never their home, `docs/math/` is.

The load-bearing code is elsewhere: `core/` runs in production, `sandbox/` is
what you run to test a strategy, `analysis/guards.py` enforces the standard's
rules and **stays out of this folder** because it is imported.
