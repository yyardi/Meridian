# Test-suite baseline — the failures that are already there

**As of 2026-09-03, on clean `origin/main`**, the full suite reports:

```
10 failed, 8 skipped, 7 errors, ~1374 passed
```

Verified by checking out `origin/main` into a **separate worktree** and
running the same command against the same throwaway postgres — not by
assuming, and not by reasoning about which failures "look unrelated".

Failing/erroring areas at that commit: `tests/test_wallet_depth_join.py`
(7 errors), plus failures including `tests/test_retention.py` and
`tests/test_human_confirm_orders.py`.

## Why this file exists

A branch that reports "10 failed" is not necessarily a branch that broke
anything, and the next person to run the suite would otherwise spend an
hour rediscovering that. **Compare against this baseline before
attributing a failure to your change** — and if the counts differ, run
`origin/main` in a worktree yourself rather than trusting this file,
because the baseline moves as main does.

The cheap procedure:

```bash
git worktree add /tmp/mainchk origin/main
cd /tmp/mainchk && .venv/bin/python -m pytest tests/ -q | tail -3
```

Delete the worktree afterwards (`git worktree remove /tmp/mainchk --force`).
