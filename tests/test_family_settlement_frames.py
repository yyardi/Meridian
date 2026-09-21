"""Validate the cross-family relations WITHOUT looking at a single price.

This is the check that licensed the spread result: 84,646 settled pairs, zero
cases where the harder rung paid and the easier one did not (STATUS 0bi/0bk).
It touches no quote, so it cannot be confounded by the YES frame, the slug
parse or the fee -- it asks only whether the venue's own SETTLEMENTS obey the
arithmetic the scanner assumes. A relation that fails here is not a trade, it
is a misunderstanding of what the market pays.

Each check below is stated so that it fails loudly on the one defect that would
be invisible to `tests/test_ladder_families.py`: that YES on a totals market is
UNDER rather than OVER. Two independent settlement routines in this repo say it
is OVER (`cfb/run_ladder_calibration.py:settle`, `core/api.py`'s OVER/UNDER
label) and `core/live_totals_fv.py` prices it that way, but all three are the
same author's reading of the same convention. Only settlements are evidence.

REQUIRES POSTGRES. Skipped without DATABASE_URL, which is every environment
except the operator's box and the prod container -- so it has NOT been run as
of 2026-09-18 and nothing in docs/math/consistency-families.md may be read as
having passed it.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="settlement frames need the recorded database")

if not os.environ.get("DATABASE_URL"):  # pragma: no cover - collection guard
    pytest.skip("no DATABASE_URL", allow_module_level=True)

from sqlalchemy import create_engine, text  # noqa: E402

#: One row per settled market: the event, the family, the line and what the
#: VENUE paid. `resolved_outcomes.game_id` is NULL on every row by design, so
#: the join is on market_slug and the grouping key is event_slug.
SETTLED = """
SELECT DISTINCT ms.event_slug, ms.sports_market_type, ms.line, ro.settlement
FROM resolved_outcomes ro
JOIN market_snapshots ms ON ms.market_slug = ro.market_slug
WHERE ms.sports_market_type = ANY(:types)
  AND ms.event_slug IS NOT NULL
"""


def _rows(types):
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        return c.execute(text(SETTLED), {"types": list(types)}).all()


def _by_event(rows):
    out: dict[str, dict[str, dict[float, int]]] = {}
    for event, mtype, line, settlement in rows:
        key = 0.0 if line is None else float(line)
        out.setdefault(event, {}).setdefault(mtype, {})[key] = int(settlement)
    return out


def test_a_higher_totals_line_never_paid_while_a_lower_one_did_not():
    """P(Over N) non-increasing in N, in its only falsifiable form.

    If YES were UNDER this fails on roughly half of all pairs, which is why it
    is the check and the code convention is not.
    """
    types = ("football_team_full_game_total", "basketball_team_full_game_total",
             "baseball_team_full_game_total")
    events = _by_event(_rows(types))
    pairs = bad = 0
    for fams in events.values():
        for rungs in fams.values():
            lines = sorted(rungs)
            for i, lo in enumerate(lines):
                for hi in lines[i + 1:]:
                    pairs += 1
                    bad += int(rungs[hi] == 1 and rungs[lo] == 0)
    assert pairs > 0, "no settled totals ladders found -- widen the window"
    assert bad == 0, f"{bad} of {pairs} settled totals pairs are inverted"


def test_the_winner_settled_exactly_as_the_zero_line_spread():
    """The moneyline IS the spread at line 0. A disagreement means the venue
    treats a draw differently on the two, and the identity must then be scanned
    only in leagues where a draw is impossible."""
    events = _by_event(_rows(("football_team_full_game_winner",
                              "football_team_full_game_spread")))
    compared = disagreed = 0
    for fams in events.values():
        winner = fams.get("football_team_full_game_winner", {}).get(0.0)
        zero = fams.get("football_team_full_game_spread", {}).get(0.0)
        if winner is None or zero is None:
            continue
        compared += 1
        disagreed += int(winner != zero)
    assert compared > 0, "the venue lists no 0.0 spread rung in this window"
    assert disagreed == 0, f"{disagreed} of {compared} games disagree"


def test_a_segment_total_never_paid_while_the_whole_at_a_lower_line_did_not():
    """P(segment > n) <= P(whole > N) for N <= n, on settlements."""
    events = _by_event(_rows(("football_game_first_half_total",
                              "football_game_second_half_total",
                              "football_team_full_game_total")))
    checked = bad = 0
    for fams in events.values():
        whole = fams.get("football_team_full_game_total", {})
        for part_type in ("football_game_first_half_total",
                          "football_game_second_half_total"):
            for n, paid in fams.get(part_type, {}).items():
                for big_n, whole_paid in whole.items():
                    if big_n > n:
                        continue
                    checked += 1
                    bad += int(paid == 1 and whole_paid == 0)
    assert checked > 0, "no settled segment/whole pairs in this window"
    assert bad == 0, f"{bad} of {checked} segment-in-whole pairs are inverted"
