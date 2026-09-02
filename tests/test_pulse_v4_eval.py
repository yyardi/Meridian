"""The v4/v3d/v4d eval arms (docs/math/pulse-v4-bundle.md,
docs/math/pulse-v3d-entry-discipline.md).

What is defended, without a database:

* the v3d entry mask gates ONLY new entries — an open position keeps being
  managed (fills, exits) in the ineligible region, per the registration's
  "an open position is always managed";
* the point-in-time pointers mirror the live reads: a player row older than
  180s vanishes (latest_player_rows' own bound), and backfilled
  substitution sequences are re-ordered before the on-floor walk;
* both verdict functions implement their registrations' clauses literally,
  including v3d's asymmetric PASS and the shape its text does not cover
  (flagged, not reinterpreted);
* each arm's gate cohort is cut at ITS OWN registration timestamp — a game
  between the two cutoffs gates v3d but only backtests v4.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from core.pulse.live import DEFAULT_PROFIT_TARGET
from core.pulse.replay_eval import (
    PLAYER_ROW_STALENESS_SECONDS,
    Tick,
    V4GameRead,
    V4Result,
    _PlayerPointer,
    _SubPointer,
    simulate_market,
    v3d_verdict,
    v4_verdict,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 25, 1, 0, tzinfo=UTC)


def _tick(i: int, bid: float, ask: float) -> Tick:
    return Tick(at=T0 + dt.timedelta(seconds=15 * i), bid=bid, ask=ask,
                score="10-8", period="2")


# ------------------------------------------------------------------ #
# The entry mask
# ------------------------------------------------------------------ #


def test_entry_mask_blocks_new_entries():
    ticks = [_tick(0, 0.49, 0.51), _tick(1, 0.45, 0.47), _tick(2, 0.44, 0.46)]
    fvs = [0.80, 0.80, 0.80]           # screaming edge at every tick
    blocked = simulate_market(ticks, fvs, 1, min_edge=0.02,
                              entry_ok=[False, False, False])
    open_gate = simulate_market(ticks, fvs, 1, min_edge=0.02,
                                entry_ok=[True, True, True])
    unmasked = simulate_market(ticks, fvs, 1, min_edge=0.02)
    assert blocked.n_entries == 0 and not blocked.rois
    assert open_gate.n_entries == unmasked.n_entries > 0


def test_open_position_is_managed_through_ineligible_region():
    """Entry at an eligible tick; every later tick is ineligible — the fill,
    the profit-target exit, and the no-re-entry all happen under the mask."""
    exit_mid = 0.49 + DEFAULT_PROFIT_TARGET + 0.01
    ticks = [
        _tick(0, 0.49, 0.51),          # eligible: rest an entry at 0.49
        _tick(1, 0.44, 0.46),          # ineligible: mid <= 0.49 fills it
        _tick(2, exit_mid - 0.01, exit_mid + 0.01),   # exit target fills
        _tick(3, 0.40, 0.42),          # flat again, edge again — masked
    ]
    fvs = [0.80, 0.80, 0.80, 0.80]
    r = simulate_market(ticks, fvs, 1, min_edge=0.02,
                        entry_ok=[True, False, False, False])
    assert r.n_entries == 1            # tick 3's edge never becomes an entry
    assert r.n_entry_fills == 1
    assert r.n_round_trips == 1        # the exit worked while ineligible
    assert len(r.rois) == 1 and r.rois[0] > 0


# ------------------------------------------------------------------ #
# Point-in-time pointers
# ------------------------------------------------------------------ #


def _prow(athlete: str, seconds: float, fouls: int = 0):
    return SimpleNamespace(athlete_id=athlete, team_id="t1", minutes=10,
                           fouls=fouls, starter=True, ejected=False,
                           first_seen_at=T0 + dt.timedelta(seconds=seconds))


def test_player_pointer_staleness_and_latest_wins():
    rows = [_prow("a", 0, fouls=1), _prow("b", 0), _prow("a", 60, fouls=4)]
    ptr = _PlayerPointer(rows)
    at = T0 + dt.timedelta(seconds=90)
    live = ptr.at(at)
    assert {r.athlete_id for r in live} == {"a", "b"}
    assert next(r for r in live if r.athlete_id == "a").fouls == 4
    # At t=200s b's only row (t=0) is beyond the 180s bound — b vanishes,
    # exactly as latest_player_rows would drop them; a's newer row (t=60,
    # age 140s) survives. Past t=240s a goes stale too and the list empties.
    later = ptr.at(T0 + dt.timedelta(seconds=200))
    assert {r.athlete_id for r in later} == {"a"}
    assert ptr.at(T0 + dt.timedelta(
        seconds=60 + PLAYER_ROW_STALENESS_SECONDS + 1)) == []


def test_sub_pointer_reorders_backfilled_sequences():
    def srow(seq: int, seconds: float):
        return SimpleNamespace(sequence=seq, type_text="Substitution",
                               athlete_id_1=str(seq), athlete_id_2=None,
                               first_seen_at=T0 + dt.timedelta(seconds=seconds))
    # Sequence 5 arrives in a LATER batch than sequence 9 — ESPN backfill.
    rows = [srow(9, 10), srow(5, 20), srow(12, 30)]
    ptr = _SubPointer(rows)
    at_25 = ptr.at(T0 + dt.timedelta(seconds=25))
    assert [r.sequence for r in at_25] == [5, 9]      # re-ordered, 12 unknown
    at_35 = ptr.at(T0 + dt.timedelta(seconds=35))
    assert [r.sequence for r in at_35] == [5, 9, 12]


# ------------------------------------------------------------------ #
# Verdicts — the registered clauses, literally
# ------------------------------------------------------------------ #

AFTER_BOTH = dt.datetime(2026, 8, 25, 0, 0, tzinfo=UTC)


def _read(i: int, *, diffs, v3_roi, v4_roi=None, arm="v4",
          n_points=300) -> V4GameRead:
    r = V4GameRead(event_slug=f"g{i}", first_seen=AFTER_BOTH)
    r.n_points = n_points
    r.diffs_v3_v4 = diffs
    r.rois["v3"] = v3_roi
    if v4_roi is not None:
        r.rois[arm] = v4_roi
    return r


def test_v4_verdict_below_floor_is_no_data():
    reads = [_read(i, diffs=[0.01], v3_roi=[0.0], v4_roi=[0.01])
             for i in range(9)]        # 9 games < 10, points 2700 < 3000
    assert v4_verdict(reads) == "NO DATA"


def test_v4_verdict_both_clauses():
    def fleet(diff_sign: float, v4_roi: float):
        return [_read(i, diffs=[diff_sign * (0.010 + 0.001 * (i % 3))],
                      v3_roi=[0.02], v4_roi=[v4_roi + 0.001 * (i % 3)])
                for i in range(12)]
    assert v4_verdict(fleet(+1, 0.03)).startswith("PASS")
    # Brier not separable -> FAIL on clause 1.
    mixed = [_read(i, diffs=[0.01 if i % 2 else -0.01],
                   v3_roi=[0.02], v4_roi=[0.03]) for i in range(12)]
    assert v4_verdict(mixed) == "FAIL"
    # Brier better, money measurably worse -> clause-2 FAIL, said out loud.
    v = v4_verdict(fleet(+1, -0.20))
    assert v.startswith("FAIL") and "second clause" in v


def _v3d_read(i: int, *, v3d_roi, v1_roi, fills=10,
              first_seen=AFTER_BOTH) -> V4GameRead:
    r = V4GameRead(event_slug=f"g{i}", first_seen=first_seen)
    r.rois["v3d"] = v3d_roi
    r.rois["v1"] = v1_roi
    r.fills["v3d"] = fills
    return r


def test_v3d_verdict_branches():
    def jitter(i: int) -> float:
        return 0.001 * (i % 3)

    wins = [_v3d_read(i, v3d_roi=[0.05 + jitter(i)], v1_roi=[-0.02])
            for i in range(12)]
    assert v3d_verdict(wins).startswith("PASS")

    loses = [_v3d_read(i, v3d_roi=[-0.08 + jitter(i)], v1_roi=[0.01])
             for i in range(12)]
    assert v3d_verdict(loses) == "FAIL"

    # The asymmetric clause: paired diff straddles zero AND v3d's own per-$
    # straddles zero — the bleeding measurably stopped, registered PASS.
    stopped = [_v3d_read(i, v3d_roi=[0.03 if i % 2 else -0.03],
                         v1_roi=[-0.03 if i % 2 else 0.03])
               for i in range(12)]
    v = v3d_verdict(stopped)
    assert v.startswith("PASS") and "asymmetric" in v

    # The uncovered shape: own per-$ entirely POSITIVE, paired inconclusive.
    # Strictly better than the clause above, but outside the registration's
    # text — must flag, never reinterpret.
    uncovered = [_v3d_read(i, v3d_roi=[0.02 + jitter(i)],
                           v1_roi=[0.06 if i % 2 else -0.02])
                 for i in range(12)]
    v = v3d_verdict(uncovered)
    assert v.startswith("NO DATA") and "does not cover" in v

    below = [_v3d_read(i, v3d_roi=[0.05], v1_roi=[0.0], fills=1)
             for i in range(12)]       # 12 fills < 100
    v = v3d_verdict(below)
    assert v.startswith("NO DATA") and "below floor" in v

    # The branch that actually fired on 2026-08-27 and had NO test: AT floor,
    # paired-vs-v1 inconclusive, v3d's own per-$ measurably NEGATIVE. The
    # asymmetric clause is unmet, so the registered verdict is NO DATA — but it
    # is a substantive middle state and must not print like an empty cohort.
    # Distinguishing the two strings is the whole point of the branch.
    unmet = [_v3d_read(i, v3d_roi=[-0.04 + jitter(i)],
                       v1_roi=[-0.045 if i % 2 else -0.03])
             for i in range(12)]
    v = v3d_verdict(unmet)
    assert v.startswith("NO DATA") and "at floor" in v
    assert "own per-$ measurably negative" in v
    assert "below floor" not in v, (
        "the substantive middle state must not be reported as a counting "
        "shortfall — they are different facts about the arm")


def test_gate_cohorts_cut_at_each_registration():
    def at(iso: str) -> V4GameRead:
        return V4GameRead(event_slug=iso,
                          first_seen=dt.datetime.fromisoformat(iso))
    before = at("2026-08-23T00:00:00+00:00")    # pre both registrations
    between = at("2026-08-24T00:00:00+00:00")   # v3d-gate, v4-backtest
    after = at("2026-08-25T00:00:00+00:00")     # gates both
    r = V4Result(reads=[before, between, after])
    assert [x.event_slug for x in r.v4_gate] == [after.event_slug]
    assert [x.event_slug for x in r.v3d_gate] == [between.event_slug,
                                                  after.event_slug]
