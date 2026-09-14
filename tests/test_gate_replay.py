"""The gate replay's interval arithmetic.

The aggregate it produces was checked end to end against an independent SQL
implementation over the same 09-13 segments: 13 games, 40.62 live hours,
0.23% of live time, per game 0.09% to 0.40% — identical to the decimal from
both routes. These tests pin the arithmetic itself, which is the part a
future edit can break silently.
"""

from __future__ import annotations

from cfb.run_gate_replay import passing_seconds

MAX = 30.0


def test_a_fresh_play_passes_for_the_whole_segment():
    """Arrives 5s old, next arrival 10s later: the age never reaches 30, so
    every second of the segment passes."""
    assert passing_seconds(10.0, 5.0, 15.0, MAX) == 10.0


def test_a_play_already_stale_on_arrival_passes_for_nothing():
    """★ THE MEASURED CASE. A play arrives a median 52.8s old on NFL, so its
    window [wall_clock, wall_clock+30) is ENTIRELY IN THE PAST and the
    segment contributes zero — which is why the gate passes 0.23% of live
    time rather than merely a small fraction."""
    assert passing_seconds(44.0, 53.0, 97.0, MAX) == 0.0


def test_a_fresh_play_stops_passing_when_the_window_closes():
    """Arrives 10s old into a 90s gap: 20 seconds of window remain, not 90."""
    assert passing_seconds(90.0, 10.0, 100.0, MAX) == 20.0


def test_a_zero_length_segment_passes_for_nothing():
    """Two rows sharing one first_seen_at — 133 of 2,239 stamps on the 09-13
    slate carry two rows, so this is the common case, not a degenerate one."""
    assert passing_seconds(0.0, 5.0, 5.0, MAX) == 0.0


def test_a_future_stamped_play_contributes_no_passing_time():
    """★ The hole `age < -1.0` closed, from the replay's side. 85 NFL plays
    carry a wall_clock 24 hours ahead, which makes the age NEGATIVE. A
    negative age is not freshness, so it must contribute zero here — if it
    contributed the pre-window seconds instead, the replay would credit the
    gate for time spent holding a corrupt row.
    """
    assert passing_seconds(10.0, -86400.0, -86390.0, MAX) == 0.0


# There is deliberately NO test that the passing time never exceeds the
# segment. I wrote one, and mutation testing showed that removing the clamp it
# guarded broke nothing: `top - lo <= age_at_t1 - max(0, age_at_t0) <=
# age_at_t1 - age_at_t0 = secs`, so the bound holds by construction. The clamp
# was dead code and the test could not fail. Both are gone.
