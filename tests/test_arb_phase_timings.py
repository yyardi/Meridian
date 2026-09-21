"""The cold ladder ask names its own slow phase.

    pytest --noconftest tests/test_arb_phase_timings.py

Measured 2026-09-21 in the RUNNING container (read-only, the api's own
process and engine), which is the only place the question can be answered:

    candidate_slugs      0.000s   201 strings, no DB -- a pure enumerator
    slugs_for            0.027s min / 0.048s median warm, 2.56-2.85s FIRST call
    client construction  0.006s min / 0.269s max
    sample, 42 rungs     3.216s min / 4.200s median  (the venue)

So a cold ask is about 2.6 + 0.3 + 4.2 = 7.1s of the ~10s measured, and the
"~4s" arithmetic (0.8 listing + 3.2 venue) paired a WARM listing with the
venue's BEST case. Two seconds of the gap are first-call cost in the listing
and about one is the venue's median against its best; the rest needs these
timings from inside a real request, which is what this instrumentation is for.

The leading suspect was `PolymarketGatewayClient` construction. It is not the
cost, and the line that says so stays in the code: a phase ruled out by
measurement should stay measured rather than be ruled out by memory.
"""
from __future__ import annotations

import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import api as api_module          # noqa: E402


class _Recorder:
    """Stands in for the structlog logger and keeps what it was told."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, dict]] = []

    def info(self, event: str, **kw) -> None:
        self.lines.append((event, kw))

    warning = info
    debug = info
    error = info

    def events(self) -> list[str]:
        return [e for e, _ in self.lines]

    def fields(self, event: str) -> dict:
        for e, kw in self.lines:
            if e == event:
                return kw
        raise AssertionError(f"{event} was never logged: {self.events()}")


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr(api_module, "log", r)
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "slugs", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "wake", threading.Event())
    return r


class TestListing:
    def test_a_miss_reports_its_own_seconds(self, rec, monkeypatch):
        monkeypatch.setattr(api_module, "slugs_for",
                            lambda game, eng: ["aec-g", "asc-g-neg-3pt5"])
        got = api_module._arb_slugs("aec-g", "g", 1000.0)
        assert got == ["aec-g", "asc-g-neg-3pt5"]          # unchanged behaviour
        f = rec.fields("arb_phase_listing")
        assert f["cache"] == "miss" and f["n_slugs"] == 2
        assert f["listing_s"] >= 0.0

    def test_a_hit_logs_nothing(self, rec, monkeypatch):
        """A dict lookup per sample would bury the one measurement wanted."""
        calls = []
        monkeypatch.setattr(api_module, "slugs_for",
                            lambda game, eng: calls.append(1) or ["aec-g"])
        api_module._arb_slugs("aec-g", "g", 1000.0)
        rec.lines.clear()
        again = api_module._arb_slugs("aec-g", "g", 1000.5)
        assert again == ["aec-g"] and len(calls) == 1       # served from cache
        assert rec.events() == []


class TestSample:
    def _client(self):
        return object()

    def test_both_phases_on_one_line(self, rec, monkeypatch):
        """The venue leg must be MEASURED, not reported.

        The first version asserted `venue_s >= 0.0`, which a hardcoded
        `venue_s = 0.0` satisfies -- the mutation that replaced the timing with
        a constant passed all five tests. So the fake venue call sleeps, and
        the assertion is against that sleep (`pin-independence-not-the-fact`:
        the mutant worth writing is the one that hardcodes a value and agrees
        with every real observation).
        """
        slept = 0.05
        monkeypatch.setattr(api_module, "slugs_for", lambda g, e: ["aec-g", "asc-g-neg-1pt5"])

        def _slow_sample(c, slugs, prefix, meta, on_error=None):
            time.sleep(slept)
            return ([("r", 1)], 0.5)

        monkeypatch.setattr(api_module, "sample", _slow_sample)
        monkeypatch.setattr(api_module, "_arb_ladder_snapshot",
                            lambda game, rungs, meta, took, now: {"available": True})
        api_module._arb_sample_one(self._client(), "aec-g")
        f = rec.fields("arb_phase_sample")
        assert f["game"] == "g" and f["n_slugs"] == 2 and f["rungs"] == 1
        assert f["venue_s"] >= slept, f"venue_s {f['venue_s']} did not see the sleep"
        assert f["listing_s"] < slept, "the listing must not absorb the venue leg"
        # and the sample still did its job
        assert api_module._ARB_LADDER["cache"]["aec-g"]["available"] is True

    def test_an_empty_listing_still_stores_its_reason_and_logs_no_sample(
            self, rec, monkeypatch):
        monkeypatch.setattr(api_module, "slugs_for", lambda g, e: [])
        api_module._arb_sample_one(self._client(), "aec-g")
        stored = api_module._ARB_LADDER["cache"]["aec-g"]
        assert stored["available"] is False and "no rungs" in stored["reason"]
        assert "arb_phase_sample" not in rec.events()     # there was no venue call

    def test_a_venue_failure_is_still_caught_by_the_handler(self, rec, monkeypatch):
        """The timing must not sit outside the try: a raise here has always been
        stored as the page's reason, and instrumentation may not change that."""
        monkeypatch.setattr(api_module, "slugs_for", lambda g, e: ["aec-g"])
        def _boom(*a, **k):
            raise RuntimeError("venue down")
        monkeypatch.setattr(api_module, "sample", _boom)
        api_module._arb_sample_one(self._client(), "aec-g")
        stored = api_module._ARB_LADDER["cache"]["aec-g"]
        assert stored["available"] is False and "venue down" in stored["reason"]
        assert "arb_sample_failed" in rec.events()
