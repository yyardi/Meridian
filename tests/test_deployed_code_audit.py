"""The deployed-code audit's pure core: commit-identity provenance.

Pins the classifier both consumers share (scripts/health.py drift-vs-HEAD and
/api/status consistency-vs-api). No DB — provenance is pure commit identity.
"""
from __future__ import annotations

import os

from core.heartbeat import (
    PROVENANCE_DRIFT,
    PROVENANCE_OK,
    PROVENANCE_UNKNOWN,
    provenance_verdict,
)


def test_matching_commit_is_ok():
    assert provenance_verdict("abc123", "abc123") == PROVENANCE_OK


def test_differing_commit_is_drift():
    assert provenance_verdict("oldsha", "newsha") == PROVENANCE_DRIFT


def test_absent_reported_is_unknown_never_ok():
    # an image built without ARG GIT_COMMIT — the state we otherwise can't see.
    assert provenance_verdict(None, "abc123") == PROVENANCE_UNKNOWN
    assert provenance_verdict("", "abc123") == PROVENANCE_UNKNOWN


def test_absent_reference_is_unknown():
    # nothing to judge drift against — never silently OK.
    assert provenance_verdict("abc123", None) == PROVENANCE_UNKNOWN


def test_identity_not_substring():
    # commit IDENTITY, never grep-for-string: a prefix is NOT a match.
    assert provenance_verdict("abc", "abc123") == PROVENANCE_DRIFT


def test_api_status_no_reference_is_unknown_never_ok(monkeypatch):
    """Rule 22, dogfooded: if the API itself has no stamp (no reference to judge
    against), a reporting service must read UNKNOWN, never a comforting OK."""
    from core import api, heartbeat

    monkeypatch.delenv("MERIDIAN_ENGINE_COMMIT", raising=False)
    svc = list(heartbeat.APP_DB_SERVICES)[0]
    r = api._heartbeat_report({
        svc: {"age_seconds": 1.0, "interval_seconds": 5.0, "commit": "somesha"}
    })
    assert r[svc]["provenance"] == PROVENANCE_UNKNOWN


def _fake_git(returncode=0, stdout="HEADSHA", stderr=""):
    return lambda *a: type("R", (), {"returncode": returncode,
                                     "stdout": stdout, "stderr": stderr})()


def test_audit_blind_never_reports_silent_ok(monkeypatch):
    """The deployment checker must not be the purest instance of the rule it
    enforces: when it cannot see (git HEAD fails, or no containers), it reports
    a non-OK check, never an empty/green result."""
    from core.healthchecks import OK
    from scripts import health

    # git HEAD lookup fails -> a WARN, not empty/OK
    monkeypatch.setattr(health, "_git", _fake_git(returncode=1, stdout="", stderr="boom"))
    r = health.check_deployed_code()
    assert r and all(c.status != OK for c in r), r

    # HEAD ok but docker returns no containers -> a WARN, not empty/OK
    monkeypatch.setattr(health, "_git", _fake_git(returncode=0))
    monkeypatch.setattr(health.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "", "returncode": 0})())
    r = health.check_deployed_code()
    assert r and all(c.status != OK for c in r), r


def test_api_status_report_carries_provenance(monkeypatch):
    """/api/status: each service's commit is compared to the API's own commit —
    match=ok, differ=drift, absent=unknown."""
    from core import api, heartbeat

    monkeypatch.setenv("MERIDIAN_ENGINE_COMMIT", "REFSHA")
    svcs = list(heartbeat.APP_DB_SERVICES)
    beats = {
        svcs[0]: {"age_seconds": 1.0, "interval_seconds": 5.0, "commit": "REFSHA"},
        svcs[1]: {"age_seconds": 1.0, "interval_seconds": 5.0, "commit": "OTHER"},
        svcs[2]: {"age_seconds": 1.0, "interval_seconds": 5.0, "commit": None},
    }
    r = api._heartbeat_report(beats)
    assert r[svcs[0]]["provenance"] == PROVENANCE_OK
    assert r[svcs[0]]["commit"] == "REFSHA"
    assert r[svcs[1]]["provenance"] == PROVENANCE_DRIFT
    assert r[svcs[2]]["provenance"] == PROVENANCE_UNKNOWN
