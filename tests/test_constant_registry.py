"""Adversaries for the constant registry, one per gate rule.

Seeded green on purpose: every registered constant passes today, so the gate
catches the NEXT one rather than complaining about the last. The adversaries
below are what prove it can catch anything at all.
"""

from __future__ import annotations

import pytest

from constant_registry import (
    REGISTRY,
    UNSOURCED_CEILING,
    Constant,
    Kind,
    assigned_value,
    gate,
    report,
)

TRACKED = {"core/pulse/live_report.py", "core/quote/engine.py",
           "core/pulse/win_curve.py", "fake/tracked.py"}


def test_the_registry_passes_today():
    """Green on the current repo. If this ever fails, a registered constant
    has drifted from the code and the registry is the thing to trust last."""
    assert gate() == [], gate()


# ------------------------------------------------------------------ #
# One adversary per rule
# ------------------------------------------------------------------ #


def test_a_constant_in_an_untracked_file_fails():
    """★ THE RULE THE FILE EXISTS FOR. scripts/alarm_v5.py is in exactly this
    state today, which is why its constants are not registered."""
    c = Constant("MIN_MARKETS", 12, "scripts/alarm_v5.py", Kind.MEASURED,
                 dataset="market_snapshots", method="fp budget", n=182)
    bad = gate((c,), tracked=TRACKED)
    assert any("not tracked by git" in b for b in bad), bad


def test_a_registry_that_drifts_from_the_code_fails():
    """The strongest gate: the doc and the code cannot disagree silently."""
    c = Constant("FLOOR_GAMES", 99, "core/pulse/live_report.py", Kind.POLICY,
                 changes_if="x")
    bad = gate((c,), tracked=TRACKED)
    assert any("has drifted from the code" in b for b in bad), bad


def test_a_measured_claim_without_n_fails():
    c = Constant("FLOOR_GAMES", 10, "core/pulse/live_report.py", Kind.MEASURED,
                 dataset="market_snapshots", method="counted them")
    bad = gate((c,), tracked=TRACKED)
    assert any("without dataset+method+n" in b for b in bad), bad


def test_a_provisional_claim_without_a_registration_fails():
    """Provisional is a promise to settle it. Without a registration it is
    just an unsourced constant with a nicer label."""
    c = Constant("RULE_OF_THUMB_SIGMA", 2.0, "core/pulse/win_curve.py",
                 Kind.PROVISIONAL, caveat="an NBA number")
    bad = gate((c,), tracked=TRACKED)
    assert any("without a caveat and a registration" in b for b in bad), bad


def test_a_policy_claim_that_cannot_say_what_would_change_it_fails():
    c = Constant("FLOOR_GAMES", 10, "core/pulse/live_report.py", Kind.POLICY)
    bad = gate((c,), tracked=TRACKED)
    assert any("without saying what would change it" in b for b in bad), bad


def test_an_unsourced_constant_without_an_owner_fails():
    c = Constant("X", 1.0, "core/quote/engine.py", Kind.UNSOURCED)
    bad = gate((c,), tracked=TRACKED)
    assert any("UNSOURCED with no owner" in b for b in bad), bad


def test_the_unsourced_count_may_not_rise():
    """The ratchet ce asked for: a count that can only go down. 14 to 11 to 9
    gets attention where a list does not."""
    c = Constant("X", 1.0, "core/quote/engine.py", Kind.UNSOURCED,
                 owner="somebody")
    bad = gate((c,), tracked=TRACKED)
    assert any(f"ceiling of {UNSOURCED_CEILING}" in b for b in bad), bad


# ------------------------------------------------------------------ #
# The value comes from the code, not from a comment about the code
# ------------------------------------------------------------------ #


def test_the_value_is_read_from_the_assignment_not_the_prose():
    """A regex over the line would be satisfied by a docstring mentioning the
    number. `assigned_value` parses, so it sees what the code DOES."""
    assert assigned_value("core/pulse/win_curve.py", "RULE_OF_THUMB_SIGMA") == 2.0
    assert assigned_value("core/pulse/win_curve.py", "NOT_A_REAL_NAME") is None


# ------------------------------------------------------------------ #
# The report is a standard, not a complaint list
# ------------------------------------------------------------------ #


def test_the_report_points_at_the_template():
    """An unmeasured number is not a defect; one pretending otherwise is. The
    report has to show the difference or it is just a list."""
    out = report()
    assert "correctly-held unmeasured constant" in out
    assert "RULE_OF_THUMB_SIGMA" in out
    assert "1.31x" in out and "0.63 against 0.68" in out


def test_the_report_carries_the_count_and_the_ceiling():
    out = report()
    assert f"UNSOURCED: 0 (ceiling {UNSOURCED_CEILING}, may only fall)" in out


# ------------------------------------------------------------------ #
# The search must work, or a small inventory is a clean bill of health
# ------------------------------------------------------------------ #


def test_the_crawler_actually_finds_things():
    """★ THE SMOKE TEST. A registry of four hand-picked entries reporting
    "0 unsourced" is a pass produced by ABSENCE — the same
    presence-blind-to-absence failure this repo hit all day, inside the
    instrument built to catch provenance failures. If the crawler returns
    nothing, every coverage figure it prints is worthless."""
    from constant_registry import find_candidates

    found = find_candidates()
    assert len(found) > 50, (
        f"crawler found only {len(found)} constants in core/ — a small "
        "inventory is a failure of the SEARCH until shown otherwise")
    assert ("core/pulse/win_curve.py", "RULE_OF_THUMB_SIGMA", 2.0) in found


def test_a_registered_constant_the_crawler_cannot_see_fails():
    """If the search cannot find something we KNOW is there, the search is
    broken and its coverage number means nothing."""
    c = Constant("NOT_A_MODULE_LEVEL_NAME", 1.0, "core/quote/engine.py",
                 Kind.POLICY, changes_if="x")
    bad = gate((c,), tracked=TRACKED | {"core/quote/engine.py"})
    assert any("the search is broken" in b for b in bad), bad


def test_the_report_states_coverage_not_just_the_unsourced_count():
    """The unsourced count is the flattering number. Coverage is the honest
    one, and both have to be on the page."""
    out = report()
    assert "COVERAGE:" in out and "UNREGISTERED" in out
    assert "failure of the SEARCH" in out


# ------------------------------------------------------------------ #
# A number with an unstated predicate
# ------------------------------------------------------------------ #


def test_a_measured_claim_without_a_population_predicate_fails():
    """2026-09-06: a cohort quoted as 18 was 31 under the module's documented
    rule — a 72% swing on an unstated definition. Which rows counted IS the
    definition, and it is more commonly missing than the dataset."""
    c = Constant("FLOOR_GAMES", 10, "core/pulse/live_report.py", Kind.MEASURED,
                 dataset="pulse_decisions", method="counted", n=28)
    bad = gate((c,), tracked=TRACKED)
    assert any("without a POPULATION predicate" in b for b in bad), bad


def test_an_emptied_registry_is_not_perfect_health():
    """★ SOURCE DEATH, and the third instance of this shape in my own work
    today. `gate(registry=())` returned zero failures — a registry with
    nothing in it gates nothing and reports a clean bill of health. Same
    defect as alarm_v5's `for row in rows` and the recorder contract's
    `for w in cycle.writes`."""
    bad = gate(registry=(), tracked=TRACKED)
    assert any("below the floor" in b for b in bad), bad


def test_the_registry_floor_matches_what_is_registered():
    """The floor is a ratchet: it may rise with the registry and must never
    silently exceed it, or the gate fails for the wrong reason."""
    from constant_registry import REGISTRY_FLOOR

    assert len(REGISTRY) >= REGISTRY_FLOOR
