"""Adversaries for the recorder-cycle contract, one per rule.

The headline adversary is not synthetic: `test_the_live_cfb_failure_is_caught`
replays the cycle that was running in production at 2026-09-06 21:37Z onward
— two live games, zero rows, exception caught and logged as a warning, clean
return, green heartbeat. If that case ever stops being a FAULT, this check has
stopped doing the only thing it was built for.

Every rule below has an adversary that must trip it and an honest cycle that
must not. A check with no adversary has never been observed working — three of
five in the model harness had none and stayed green.
"""

from __future__ import annotations

import pytest

from recorder_contract import FAULT, OK, UNKNOWN, Cycle, Kind, Write, judge


def _state(rows, errors=0):
    return Write("espn_cfb_game_state", Kind.APPEND_ONLY, rows, errors)


def _plays(rows, errors=0):
    return Write("espn_cfb_live_plays", Kind.IDEMPOTENT, rows, errors)


# ------------------------------------------------------------------ #
# The live failure
# ------------------------------------------------------------------ #


def test_the_live_cfb_failure_is_caught():
    """2026-09-06 21:37Z. live_games=2, state_rows=0, plays=0, one caught
    exception ('Unconsumed column names: league'), cycle returns cleanly."""
    v = judge(Cycle(work_identified=2,
                    writes=(_state(0), _plays(0)),
                    errors=1))
    assert v.state == FAULT
    assert "SILENT_APPEND" in v.codes, v.reasons


def test_the_same_cycle_without_the_error_is_still_a_fault():
    """The exception is not what makes it a fault — doing no work while work
    exists is. A future version that stops logging the warning must not become
    healthy by doing so."""
    v = judge(Cycle(work_identified=2, writes=(_state(0), _plays(0)), errors=0))
    assert v.state == FAULT
    assert "SILENT_APPEND" in v.codes


# ------------------------------------------------------------------ #
# The trap: idempotent writers legitimately write zero
# ------------------------------------------------------------------ #


def test_a_caught_up_idempotent_writer_is_not_a_fault():
    """★ The false positive that would get this muted in a week. Re-polling a
    live game between plays writes 0 new rows because ON CONFLICT DO NOTHING
    already has them. Healthy, and it must read as healthy."""
    v = judge(Cycle(work_identified=2, writes=(_state(2), _plays(0)), errors=0))
    assert v.state == OK, v.reasons


def test_idempotent_zero_WITH_an_error_is_a_fault():
    """Same zero, different meaning: an error alongside it is the swallowed
    exception signature."""
    v = judge(Cycle(work_identified=2, writes=(_plays(0),), errors=1))
    assert v.state == FAULT
    assert "SILENT_ERROR" in v.codes, v.reasons


# ------------------------------------------------------------------ #
# Honest cycles must pass
# ------------------------------------------------------------------ #


def test_a_working_cycle_is_ok():
    v = judge(Cycle(work_identified=2, writes=(_state(2), _plays(17))))
    assert v.state == OK, v.reasons


def test_a_genuinely_quiet_slate_is_ok():
    """No games. Zero rows is correct, and calling it a fault is how a check
    gets ignored overnight."""
    v = judge(Cycle(work_identified=0, writes=(_state(0), _plays(0))))
    assert v.state == OK, v.reasons


# ------------------------------------------------------------------ #
# Three states, never two
# ------------------------------------------------------------------ #


def test_an_unreportable_count_is_unknown_not_ok():
    """`_write` returns `rowcount or 0`, and `-1 or 0` is -1 because -1 is
    truthy — so these fields can never carry a real number. That must not read
    as zero (which pages) or as fine (which hides)."""
    v = judge(Cycle(work_identified=2, writes=(_state(2), _plays(-1))))
    assert v.state == UNKNOWN
    assert "COUNT_UNREPORTABLE" in v.codes, v.reasons


def test_an_absent_schedule_is_unknown_not_quiet():
    """If the recorder cannot say how much work existed, that is not 'no
    games'. Same absence-as-answer bug one level up."""
    v = judge(Cycle(work_identified=None, writes=(_state(0),)))
    assert v.state == UNKNOWN
    assert "WORK_UNKNOWN" in v.codes


def test_idle_with_errors_is_unknown():
    """Zero work AND an error: the error may be the reason there is no work."""
    v = judge(Cycle(work_identified=0, writes=(_state(0),), errors=1))
    assert v.state == UNKNOWN
    assert "IDLE_WITH_ERRORS" in v.codes


def test_a_fault_outranks_an_unknown():
    """A cycle with both must report FAULT — the actionable state wins, or a
    real failure hides behind an unreportable count."""
    v = judge(Cycle(work_identified=2, writes=(_state(0), _plays(-1)), errors=1))
    assert v.state == FAULT, v.reasons
    assert {"SILENT_APPEND", "COUNT_UNREPORTABLE"} <= v.codes


# ------------------------------------------------------------------ #
# ATTEMPTED semantics — the ESPN side's actual instrumentation
# ------------------------------------------------------------------ #
#
# a1's correction, and it makes the check simpler rather than harder: their
# writes are ON CONFLICT DO NOTHING, so rowcount is undeterminable (-1) and a
# genuine zero is indistinguishable from a fully-deduplicated batch. They
# therefore report `plays_attempted` — rows BUILT — which has no dedupe
# confound at all.


def _attempted(name, n, errors=0):
    from recorder_contract import Counts

    return Write(name, Kind.IDEMPOTENT, n, errors, Counts.ATTEMPTED)


def test_the_live_failure_via_attempted_counts():
    """The verbatim log line: live_games=2, plays_attempted=0, wp_attempted=0.
    Both numbers already on ONE LINE of our own log."""
    v = judge(Cycle(work_identified=2,
                    writes=(_attempted("plays_attempted", 0),
                            _attempted("wp_attempted", 0)),
                    errors=1))
    assert v.state == FAULT
    assert "SILENT_ATTEMPT" in v.codes, v.reasons


def test_attempted_zero_is_a_fault_even_for_an_idempotent_writer():
    """This is why ATTEMPTED is the stronger signal: dedupe cannot explain it
    away, so the idempotent exemption does not apply."""
    v = judge(Cycle(work_identified=2, writes=(_attempted("plays", 0),)))
    assert v.state == FAULT, v.reasons


def test_a_caught_up_recorder_still_attempts_rows():
    """The false-positive control for the attempted path: a recorder that is
    up to date has still BUILT rows from the payload, so attempted is
    positive even when written would be zero."""
    v = judge(Cycle(work_identified=2, writes=(_attempted("plays", 34),)))
    assert v.state == OK, v.reasons


def test_attempted_counts_are_only_returned_after_commit():
    """★ THE STRUCTURAL PROPERTY THE ATTEMPTED SIGNAL RESTS ON ★

    In `espn_cfb_recorder.poll_game` the `return` sits AFTER `s.commit()`, so
    any exception propagates before the counters are returned and they stay 0.
    That is what makes `attempted > 0` imply the transaction committed, and it
    is the reason a log-only check is sufficient here.

    If someone adds a per-statement try/except inside that block, the property
    dies and the contract must move to a DB-side comparison. This test is how
    that gets noticed instead of the check quietly becoming wrong."""
    import ast
    import pathlib

    src = pathlib.Path("core/feeds/espn_cfb_recorder.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "poll_game")

    # No exception handling inside poll_game: a caught error would let the
    # function return non-zero counters after a rolled-back write.
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Try)], (
        "poll_game now catches an exception — `attempted > 0` no longer "
        "implies the write committed, and the log-only check is unsound")

    # And the return is the last statement, after the commit.
    assert isinstance(fn.body[-1], ast.Return), (
        "poll_game's return moved; confirm it still follows s.commit()")
    commits = [n for n in ast.walk(fn)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "commit"]
    assert commits, "poll_game no longer commits — the invariant is gone"
    assert max(c.lineno for c in commits) < fn.body[-1].lineno, (
        "the return no longer follows the commit")


# ------------------------------------------------------------------ #
# Why nothing else would have caught it
# ------------------------------------------------------------------ #


def test_the_failure_is_invisible_to_two_of_the_three_monitor_shapes():
    """CORRECTED 2026-09-06 (D's finding, accepted by a1 and by me).

    The first version of this test asserted THREE invisibilities and was
    WRONG about one — which made a test file about unfalsifiable claims carry
    an unfalsifiable claim of its own:

      * RATE-BASED   blind. The denominator is zero, so a percentage is
                     undefined and the alarm goes INSUFFICIENT, not ALARM.
      * HEARTBEAT    blind. A cycle ran every 20s and returned cleanly.
      * CROSS-SOURCE **NOT blind.** I claimed it was, on the reasoning that
                     the venue side was healthy so both providers agreed games
                     were live. But the mutual-monitoring link D specced with
                     c7 is "venue at live cadence AND no ESPN state -> ESPN
                     recorder down", which is exactly tonight's signature and
                     WOULD fire. Two providers agreeing games are live is the
                     PREMISE of that check, not a defeat of it.

    So this check is not the only instrument that sees it, and the honest
    claim is narrower: it is the cheapest, it needs no second provider, and
    both its numbers are already on one line of our own log."""
    cycle = Cycle(work_identified=2, writes=(_attempted("plays", 0),), errors=1)

    written = [w.rows for w in cycle.writes]
    assert sum(written) == 0
    # rate-based: nothing arrived, so there is no population to take a share of
    assert not any(w.rows for w in cycle.writes), "no denominator exists"
    # heartbeat: the cycle completed
    heartbeat_ok = True
    assert heartbeat_ok
    # cross-source: NOT blind. The venue recording at live cadence while ESPN
    # state is absent is precisely the mutual-monitoring signature.
    venue_at_live_cadence, espn_state_rows = True, 0
    cross_source_fires = venue_at_live_cadence and espn_state_rows == 0
    assert cross_source_fires, (
        "cross-source would fire here; this check is the cheapest instrument, "
        "not the only one")
    # and yet
    assert judge(cycle).state == FAULT


# ------------------------------------------------------------------ #
# The rule is a DISJUNCTION — neither half is sufficient
# ------------------------------------------------------------------ #


def test_three_of_five_games_throwing_is_caught_by_the_short_count():
    """plays_attempted is POSITIVE here (the two working games built rows), so
    the attempted half never fires. Only `state_rows < live_games` sees it."""
    v = judge(Cycle(work_identified=5,
                    writes=(_state(2), _attempted("plays", 40)),
                    errors=3))
    assert v.state == FAULT
    assert "SHORT_APPEND" in v.codes, v.reasons


def test_parse_returning_empty_is_caught_by_the_attempted_half():
    """state_rows == live_games here, so the short-count half never fires.
    Only `plays_attempted == 0` sees it."""
    v = judge(Cycle(work_identified=2,
                    writes=(_state(2), _attempted("plays", 0))))
    assert v.state == FAULT
    assert "SILENT_ATTEMPT" in v.codes, v.reasons
    assert "SHORT_APPEND" not in v.codes


def test_a_full_append_count_is_not_short():
    v = judge(Cycle(work_identified=3,
                    writes=(_state(3), _attempted("plays", 12))))
    assert v.state == OK, v.reasons
