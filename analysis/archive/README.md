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
| `capture_is_not_a_proxy.py` | **live** — capture is an identity, not a measurement |
| `placement_curve_real_fills.py` | **live** — but "wide is best" was refuted, see rule 25 |
| `flattening_book_insertion.py` | **live** — exclusion ≠ insertion |
| `quote_v2_*` | mixed — the phantom classifier they use tests the wrong condition |
| `nba_*`, `nfl_day_one_survey` | surveys, superseded by live recording |

The load-bearing code is elsewhere: `core/` runs in production, `sandbox/` is
what you run to test a strategy, `analysis/guards.py` enforces the standard's
rules and **stays out of this folder** because it is imported.
