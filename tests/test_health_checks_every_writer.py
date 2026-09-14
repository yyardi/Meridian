"""The health check must check every writer that beats, not only a list.

On 2026-09-14 `service_heartbeats` carried 22 writers and `APP_DB_SERVICES`
named 5. Seventeen processes beat every cycle and were never checked, including
the PULSE engine and both paper-scalp engines. A service absent from the list is
not absent from production: if one stopped, the script reported healthy.

The list is not removed, because it does the one job presence cannot -- asserting
that an EXPECTED writer is there, so a service that never starts reads DEAD
rather than merely not appearing. Presence comes from the table, expectation from
the list, and neither substitutes for the other. Both directions are tested here.
"""
from __future__ import annotations

from unittest.mock import patch

import core.healthchecks as hc
from core import heartbeat as hb


def _rows(*triples):
    """(service, age_seconds, interval_seconds) -> the shape the query returns."""
    return [(s, age, interval, 0, 1.0) for s, age, interval in triples]


def _run(rows):
    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k):
            class R:
                def all(_self): return rows
            return R()

    class _Eng:
        def connect(self): return _Conn()

    with patch("core.storage.base.get_engine", return_value=_Eng()):
        return hc.check_app_heartbeats()


def _by_name(checks):
    return {c.name.removeprefix("beat: "): c for c in checks}


def test_a_stale_writer_absent_from_the_list_is_still_reported_dead():
    """The defect, stated directly. scalp_engine_nfl is not in APP_DB_SERVICES."""
    assert "scalp_engine_nfl" not in hb.APP_DB_SERVICES
    got = _by_name(_run(_rows(*[(s, 1.0, 5.0) for s in hb.APP_DB_SERVICES],
                              ("scalp_engine_nfl", 600.0, 2.0))))
    assert "scalp_engine_nfl" in got, "an unlisted writer must be checked at all"
    assert got["scalp_engine_nfl"].status == hc.DEAD


def test_a_healthy_unlisted_writer_is_reported_ok_not_omitted():
    """Guards the guard: reporting every unlisted writer as DEAD would pass the
    test above while making the output useless."""
    got = _by_name(_run(_rows(*[(s, 1.0, 5.0) for s in hb.APP_DB_SERVICES],
                              ("pulse_engine", 1.0, 1.0))))
    assert got["pulse_engine"].status == hc.OK


def test_an_expected_writer_that_never_beat_is_still_dead():
    """The job only the list can do. If presence alone drove the check, a writer
    that never started would simply not appear and nothing would notice."""
    missing = hb.APP_DB_SERVICES[0]
    rest = [(s, 1.0, 5.0) for s in hb.APP_DB_SERVICES[1:]]
    got = _by_name(_run(_rows(*rest, ("pulse_engine", 1.0, 1.0))))
    assert got[missing].status == hc.DEAD


def test_every_beating_writer_appears_exactly_once():
    """A writer in both the list and the table must not be checked twice."""
    rows = _rows(*[(s, 1.0, 5.0) for s in hb.APP_DB_SERVICES],
                 ("quote_engine_cfb", 1.0, 5.0))
    names = [c.name for c in _run(rows)]
    assert len(names) == len(set(names))
    assert len(names) == len(hb.APP_DB_SERVICES) + 1
