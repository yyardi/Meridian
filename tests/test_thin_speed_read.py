"""The thin-league speed read (analysis/thin/speed_read.py) scores what the registration says.

docs/math/thin-league-speed-preregistration.md fixes the event (one team's points rise by
1-3 between two live polls), the side (YES iff the scorer is the market's yes_team_id), the
entry (the side's ask as visible 1 s after our receipt; NO's ask = 1 - YES bid), the mark-out
(the side's mid 60 s later minus the entry and the taker fee), the exclusion (a book tape
quiet for more than 60 s during play) and the direction check. These pin each one on a
synthetic tape, so the instrument cannot drift from its registration unnoticed.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import math
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "speed_read", pathlib.Path(__file__).resolve().parents[1] / "analysis" / "thin" / "speed_read.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

T0 = 1_790_000_000.0


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="milliseconds")


def score(t, sc, prev=None, live=True, period="Q1"):
    return {"recv": iso(t), "prev_recv": None if prev is None else iso(prev), "score": sc, "period": period,
            "live": live, "state_updated_at": iso(t - 3), "competitors": ["A", "B"], "yes_team_id": "A"}


def book(t, bid, ask, state="MARKET_STATE_OPEN"):
    return {"recv": iso(t), "slug": "aec-x-a-b-2026-09-29", "bid": bid, "ask": ask,
            "bid_size": 100, "ask_size": 200, "state": state}


def test_a_simple_score_is_one_event_on_the_scorers_side_and_a_skipped_poll_is_compound():
    evs = S.events_of([score(T0, "0-0"), score(T0 + 10, "2-0", T0), score(T0 + 20, "2-3", T0 + 10),
                       score(T0 + 30, "6-5", T0 + 20)])
    assert [(e["simple"], e["side"]) for e in evs] == [(True, "YES"), (True, "NO"), (False, "YES")]
    assert evs[0]["t_R"] == pytest.approx(T0 + 10)


def test_a_score_across_a_non_live_line_is_not_an_event():
    evs = S.events_of([score(T0, "40-40", live=False, period="HT"), score(T0 + 10, "42-40", T0)])
    assert evs == []


def test_the_markout_enters_at_the_ask_visible_at_entry_and_charges_the_fee():
    b = S.Book([book(T0, 0.49, 0.51), book(T0 + 10.5, 0.55, 0.57), book(T0 + 60, 0.55, 0.57)])
    v, ask, size = S.markout(b, T0 + 11.0, "YES")         # repriced at +10.5, before our entry at +11
    assert ask == pytest.approx(0.57) and size == 200
    assert v == pytest.approx(0.56 - 0.57 - 0.02)          # 0.0695*0.57*0.43 = 1.70c -> 2c
    v, ask, size = S.markout(b, T0 + 11.0, "NO")           # NO's ask = 1 - YES bid
    assert ask == pytest.approx(0.45) and size == 100
    assert v == pytest.approx(0.44 - 0.45 - 0.02)


def test_a_closed_book_at_entry_is_not_scored():
    b = S.Book([book(T0, 0.49, 0.51, state="MARKET_STATE_SUSPENDED"), book(T0 + 100, 0.49, 0.51)])
    assert S.markout(b, T0 + 1, "YES") is None


def test_the_tape_gap_counts_every_push_including_one_sided_books():
    b = S.Book([book(T0, 0.49, 0.51), book(T0 + 30, None, 0.51), book(T0 + 120, 0.49, 0.51)])
    assert b.max_gap(T0, T0 + 150) == pytest.approx(90)    # 30 -> 120, the one-sided push counts
    assert len(b.rows) == 2                                # but only two-sided touches are priced


def test_the_direction_check_compares_the_score_winner_with_where_the_book_settled():
    assert S.score_winner([score(T0, "80-75", period="Q4")]) == "YES"
    assert S.score_winner([score(T0, "70-75", period="Q4")]) == "NO"
    assert S.Book([book(T0, 0.95, 0.97)]).settled_toward() == "YES"
    assert S.Book([book(T0, 0.40, 0.60)]).settled_toward() is None


def test_one_cluster_has_no_interval():
    m, se, g = S.clustered([("g1", 0.01), ("g1", -0.03)])
    assert g == 1 and math.isnan(se) and m == pytest.approx(-0.01)
    m, se, g = S.clustered([("g1", 0.02), ("g2", -0.02)])
    assert g == 2 and se == pytest.approx(0.02)            # sqrt((0.02^2 + 0.02^2) / 4 * 2)
