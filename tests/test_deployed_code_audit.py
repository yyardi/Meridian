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
