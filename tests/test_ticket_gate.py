"""The ticket gate is sized to the operator's attempt, not to the venue's display.

    pytest --noconftest tests/test_ticket_gate.py

2026-09-26, the operator: "idk why u have the $25 limit, it dont gotta be that
high if im testing with $20". Right: $25 was edge x the FULL displayed size,
a statistic about what the venue showed. A $20 test needs the thin leg to
show the twenty-odd contracts $20 buys, at an edge worth crossing for.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import intent  # noqa: E402
from core.ladder.scan import Violation  # noqa: E402


def _v(buy=0.41, sell=0.53, edge=0.0259, size=966.0, hi=10.5, lo=7.5):
    return Violation("cfb-x-y-2026-09-26", lo, hi, buy, sell, edge, size)


def test_the_attempt_buys_this_many_contracts_of_the_pair():
    v = _v()                                   # pair cost 0.41 + 0.47 = 0.88
    assert intent.pair_cost(v) == 0.88
    assert intent.qty_for(v, 20.0) == 22 and intent.qty_for(v, 1.0) == 1 and intent.qty_for(v, 0.5) == 1


def test_a_crossing_with_the_attempt_s_contracts_on_the_thin_leg_is_a_ticket_whatever_its_dollars():
    v = _v(size=22.0)                          # 22 x 2.59c = $0.57 at full size, far under $25
    assert intent.clears_ticket_gate(v, 20.0)
    assert v.dollars < 25


def test_a_thin_leg_short_of_the_attempt_is_not_a_ticket_however_rich_the_edge():
    assert not intent.clears_ticket_gate(_v(size=21.0, edge=0.14), 20.0)
    assert intent.clears_ticket_gate(_v(size=21.0, edge=0.14), 18.0)


def test_the_edge_floor_is_two_cents_net_and_is_read_after_rounding_to_tick():
    assert not intent.clears_ticket_gate(_v(edge=0.0199), 20.0)
    assert intent.clears_ticket_gate(_v(edge=0.019999), 20.0), "0.019999 is 2.00c, not a refusal"
    assert intent.clears_ticket_gate(_v(edge=0.02), 20.0)


def test_the_ticket_is_sized_to_the_attempt_and_never_above_the_thin_leg():
    t = intent.ticket_for(_v(), "cfb-x-y-2026-09-26", "12:00:00", 20.0)
    assert t["leg1"]["qty"] == t["leg2"]["qty"] == 22 and t["cost_usd"] == 22 * 0.88
    t = intent.ticket_for(_v(size=5.0), "cfb-x-y-2026-09-26", "12:00:00", 20.0)
    assert t["leg1"]["qty"] == 5


def test_the_defaults_are_the_operator_s_numbers_and_the_desk_and_executors_share_them():
    assert intent.DEFAULT_ATTEMPT_USD == 20.0 and intent.DEFAULT_MIN_EDGE == 0.02
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in ("cfb/run_stream_executor.py", "cfb/run_ladder_executor.py", "core/api.py", "scripts/schedule_slate.py"):
        assert "DEFAULT_ATTEMPT_USD" in (root / f).read_text(), f
        assert "clears_floor(" not in (root / f).read_text() or f == "core/api.py", f
