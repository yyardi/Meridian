"""Does core.fees still match what the venue recorded?

    python3 scripts/fee_drift.py            # DATABASE_URL from the environment

The venue raised its taker coefficient by 16 % at 2026-09-17 04:07Z
(docs/math/fee-coefficient.md). The recorder stored the new value on every snapshot from that minute
on, and nothing compared the tree's constant to the column for four days:
every fee was charged 16 % light with every log green. Configured is not
measured. This script is the measurement, run in the nightly slate verdict:
the distinct coefficients recorded in the last day against the constant.

Exit 0 and `FEE OK` when every recorded coefficient equals the constant;
exit 2 and `FEE DRIFT` when any does not; exit 1 and `FEE UNKNOWN` when the
last day recorded no coefficient at all (a silent recorder is not agreement).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.fees import POLYMARKET_TAKER  # noqa: E402

#: The month-boundary floor prunes partitions; the day floor is the window.
#: A mid-month floor alone filters rows and costs MORE (memory: partition
#: pruning needs a boundary).
SQL = """
SELECT fee_coefficient, count(*) AS n, min(captured_at) AS first_seen, max(captured_at) AS last_seen
FROM market_snapshots
WHERE captured_at >= date_trunc('month', now() - interval '1 day')
  AND captured_at >= now() - interval '1 day'
  AND fee_coefficient IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
"""


def verdict(rows: list[tuple], constant: float = POLYMARKET_TAKER, tol: float = 1e-9) -> tuple[str, int]:
    """`rows` are (coefficient, n, first_seen, last_seen). One line and an exit
    code; the line starts with `FEE ` so the verdict script can grep it."""
    if not rows:
        return "FEE UNKNOWN: no snapshot in the last day carried a coefficient", 1
    total = sum(int(r[1]) for r in rows)
    off = [r for r in rows if abs(float(r[0]) - constant) > tol]
    if off:
        seen = ", ".join(f"{float(r[0]):.4f} on {int(r[1]):,} rows ({r[2]}..{r[3]})" for r in rows)
        return (f"FEE DRIFT: core.fees.POLYMARKET_TAKER = {constant} but the venue recorded "
                f"{seen} in the last day; the fee has changed, update core/fees.py"), 2
    return f"FEE OK: {constant} on all {total:,} snapshots in the last day", 0


def main() -> int:
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as c:
        rows = [tuple(r) for r in c.execute(text(SQL))]
    line, code = verdict(rows)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
