#!/usr/bin/env bash
# HOW MUCH ELAPSED TIME CAN EACH TEST MODULE TAKE?
#
# Test modules pin `NOW = datetime.now(UTC)` at IMPORT -- collection, once,
# at the start of the run -- then insert snapshots at `NOW - 30s`. The
# engine's predicate is `captured_at > now() - MAX_OBSERVATION_AGE_SECONDS`
# (60s), evaluated at EXECUTION. So a module carries a budget of
# `60 - worst_offset` seconds, after which its OWN fixtures age out of the
# window it is testing -- and whether it passes depends on its POSITION in a
# ~35s suite. Measured 2026-09-14: shuffling the file order gave 2 failures
# in 1 of 4 seeds, and those tests passed alone.
#
# tests/conftest.py's `module_now_is_per_test` re-pins NOW per test for
# modules that set `NOW_PER_TEST = True`, so REAL elapsed time no longer
# accumulates. MERIDIAN_TEST_NOW_SHIFT then simulates it on purpose: this
# script walks the shift upward per file and prints the budget it finds.
#
#   scripts/elapsed_probe.sh                 # every module with a NOW
#   scripts/elapsed_probe.sh tests/test_pulse_reprice.py
#
# READ IT LIKE THIS. `budget>=60s` means the file does not care. A budget of
# 25-30s is a file whose fixtures sit near the window's edge: fine now, and
# the number to look at if it ever goes red in a longer suite. A budget that
# DROPS after someone edits fixtures is the regression this catches.
#
# A file that reports no budget at all (green at every shift) either has no
# time-sensitive rows or has stopped being measured -- check it is opted in.
set -u
PY=${PY:-python}
SHIFTS=${SHIFTS:-"10 20 25 30 40 55"}

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  files=($(grep -lE '^NOW = (dt\.)?datetime\.now' tests/test_*.py))
fi

printf '%-46s %s\n' "module" "first shift that breaks it"
for f in "${files[@]}"; do
  budget="none (>=60s, or not time-sensitive)"
  for shift in $SHIFTS; do
    n=$(MERIDIAN_TEST_NOW_SHIFT="$shift" "$PY" -m pytest "$f" -q -p no:cacheprovider 2>&1 \
        | grep -oE '^[0-9]+ failed' | grep -oE '^[0-9]+' || true)
    if [ -n "${n:-}" ]; then budget="$n test(s) fail at +${shift}s"; break; fi
  done
  printf '%-46s %s\n' "$f" "$budget"
done
