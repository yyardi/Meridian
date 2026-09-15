"""The drift detector's classification, and the rule it exists to enforce.

Every failure it targets looked correct from the image tag and from the
checkout on disk. The one way to get this instrument wrong is to let
"I could not look" read as "it matches".
"""

from __future__ import annotations

from core.drift import DIFFERS, MATCHES, UNKNOWN, classify, summarise

REF = {"core/a.py": "aaa", "core/b.py": "bbb", "tests/t.py": "ttt"}


def test_identical_code_matches():
    assert classify({"core/a.py": "aaa", "core/b.py": "bbb"}, REF) == (MATCHES, [])


def test_a_changed_file_differs_and_is_named():
    v, files = classify({"core/a.py": "aaa", "core/b.py": "CHANGED"}, REF)
    assert v == DIFFERS and files == ["core/b.py"]


def test_an_unreadable_container_is_unknown_not_matches():
    """★ THE RULE. A probe that could not run must not report agreement — that
    would be the whole class of bug this tool exists to detect, inside the
    tool."""
    assert classify(None, REF) == (UNKNOWN, [])


def test_a_container_with_no_python_is_unknown_not_matches():
    """An empty result is the same epistemic state as a failed probe. Read as
    MATCHES it would give every non-Python container a clean bill."""
    assert classify({}, REF) == (UNKNOWN, [])


def test_a_file_the_reference_lacks_is_drift():
    """The running image carrying code main has DELETED is drift in the
    direction nobody checks, so a missing reference entry counts as differing
    rather than as agreement."""
    v, files = classify({"core/a.py": "aaa", "core/gone.py": "zzz"}, REF)
    assert v == DIFFERS and files == ["core/gone.py"]


def test_files_the_container_lacks_are_not_drift():
    """Images legitimately exclude tests/ and the analysis runners, so the
    comparison is one-directional BY DESIGN. Asserted so the asymmetry is a
    decision with a test rather than an accident of the loop."""
    assert classify({"core/a.py": "aaa"}, REF) == (MATCHES, [])


def test_the_summary_cannot_hide_an_unknown():
    """★ "20 of 21 up to date" would let an UNKNOWN read as a pass. The three
    counts are printed separately and an UNKNOWN adds a line saying it is not
    one."""
    s = summarise([("a", MATCHES, []), ("b", DIFFERS, ["x.py"]),
                   ("c", UNKNOWN, [])])
    assert "1 match, 1 DIFFER, 1 UNKNOWN" in s
    assert "UNKNOWN is not a pass" in s

    clean = summarise([("a", MATCHES, [])])
    assert "UNKNOWN is not a pass" not in clean, (
        "the caveat fires when there is nothing to caveat, which trains "
        "readers to ignore it")
