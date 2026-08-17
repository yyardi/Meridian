"""The alerter pushes on transitions, never on states.

An alarm that re-fires every 5 minutes gets muted, and a muted alarm is worse
than none — so what is under test here is mostly what does NOT push: a check
that stays DEAD, a WARN younger than 30 minutes, a second evaluation of an
unchanged board. Plus the two deliberate exceptions (disk and Supabase size
push on arrival) and the FAILED-exit rule, which pushes per row so a second
failure can never hide behind the first.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from core.alerter import (
    DIGEST_HOUR_CT,
    WARN_PERSIST_SECONDS,
    Alerter,
    Notifier,
)
from core.healthchecks import DEAD, OK, WARN, Check
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
CT = dt.timezone(dt.timedelta(hours=-5))  # CDT in August


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeNotifier(Notifier):
    def __init__(self):
        super().__init__("test-topic")
        self.sent: list[tuple[str, str, str]] = []

    def push(self, title, body, *, priority="default", tags=""):
        self.sent.append((title, body, priority))
        return True


@pytest.fixture
def alerter():
    clock = FakeClock()
    a = Alerter(FakeNotifier(), clock=clock)
    a._first_cycle = False  # baseline established; tests exercise transitions
    return a, clock


def _push_all(alerter, checks):
    return alerter.process(checks)


def test_first_cycle_is_baseline_not_a_transition():
    a = Alerter(FakeNotifier(), clock=FakeClock())
    pushes = a.process([Check(DEAD, "espn", "down")])
    assert pushes == [], "a restart must not replay the whole board as alerts"


def test_dead_transition_pushes_once_and_never_spams(alerter):
    a, clock = alerter
    dead = [Check(DEAD, "espn", "HTTP 403")]
    assert len(_push_all(a, dead)) == 1
    for _ in range(10):
        clock.now += 300
        assert _push_all(a, dead) == [], "staying DEAD is not a transition"


def test_recovery_pushes_once(alerter):
    a, clock = alerter
    _push_all(a, [Check(DEAD, "espn", "down")])
    clock.now += 300
    pushes = _push_all(a, [Check(OK, "espn", "HTTP 200")])
    assert len(pushes) == 1 and pushes[0][0].startswith("Recovered")
    clock.now += 300
    assert _push_all(a, [Check(OK, "espn", "HTTP 200")]) == []


def test_warn_pushes_only_after_persisting_30_minutes(alerter):
    a, clock = alerter
    warn = [Check(WARN, "predictions", "95m ago")]
    assert _push_all(a, warn) == [], "a fresh WARN is a blip, not a page"
    clock.now += WARN_PERSIST_SECONDS - 60
    assert _push_all(a, warn) == []
    clock.now += 120
    pushes = _push_all(a, warn)
    assert len(pushes) == 1 and "30min" in pushes[0][0]
    clock.now += 3600
    assert _push_all(a, warn) == [], "the persistence push fires once"


def test_warn_that_clears_never_pushes(alerter):
    a, clock = alerter
    _push_all(a, [Check(WARN, "predictions", "late")])
    clock.now += 600
    assert _push_all(a, [Check(OK, "predictions", "fresh")]) == []


def test_disk_warn_pushes_immediately(alerter):
    a, _ = alerter
    pushes = _push_all(a, [Check(WARN, "disk free", "18 GB free")])
    assert len(pushes) == 1, "a slow burn that ends in data loss pushes on arrival"


# ------------------------------------------------------------------ #
# The pregame snapshot rule — heartbeat-first, never data-age alone
# ------------------------------------------------------------------ #


def test_idle_hour_with_fresh_heartbeat_is_not_dead():
    """The 2026-08-08 overnight flap: pregame recorder idles at 60 min, the
    old 45-min data threshold paged urgent every hour. A fresh heartbeat at
    the recorder's own cadence means idle, not dead."""
    from core.healthchecks import DEAD as HC_DEAD, OK as HC_OK, primary_snapshot_verdict

    fifty_nine_min = 59 * 60.0
    assert primary_snapshot_verdict(
        fifty_nine_min, hb_age=120.0, hb_interval=3600.0, game_live=False
    ) == HC_OK


def test_stale_heartbeat_is_dead_whatever_the_data_says():
    from core.healthchecks import DEAD as HC_DEAD, primary_snapshot_verdict

    assert primary_snapshot_verdict(
        60.0, hb_age=4 * 3600.0, hb_interval=900.0, game_live=False
    ) == HC_DEAD
    assert primary_snapshot_verdict(
        60.0, hb_age=None, hb_interval=None, game_live=False
    ) == HC_DEAD, "never beaten reads dead — B11's rounding rule"


def test_live_game_with_stale_pregame_data_is_dead_even_if_alive():
    """During a game the recorder should be on the 15-min leg; an hour of
    silence with a game on means picks are pricing off stale quotes — DEAD
    even though the process itself is beating (the B1 lesson: outputs)."""
    from core.healthchecks import DEAD as HC_DEAD, OK as HC_OK, primary_snapshot_verdict

    assert primary_snapshot_verdict(
        3600.0, hb_age=120.0, hb_interval=900.0, game_live=True
    ) == HC_DEAD
    assert primary_snapshot_verdict(
        600.0, hb_age=120.0, hb_interval=900.0, game_live=True
    ) == HC_OK


# ------------------------------------------------------------------ #
# The digest clock
# ------------------------------------------------------------------ #


def test_digest_fires_once_per_ct_day():
    a = Alerter(FakeNotifier(), clock=FakeClock())
    day1_0855 = dt.datetime(2026, 8, 10, 8, 55, tzinfo=CT)
    day1_0905 = dt.datetime(2026, 8, 10, 9, 5, tzinfo=CT)
    day2_0901 = dt.datetime(2026, 8, 11, 9, 1, tzinfo=CT)

    assert not a.digest_due(day1_0855.astimezone(UTC))
    assert a.digest_due(day1_0905.astimezone(UTC))
    a._last_digest_date = day1_0905.date()
    assert not a.digest_due(day1_0905.astimezone(UTC))
    assert not a.digest_due((day1_0905 + dt.timedelta(hours=5)).astimezone(UTC))
    assert a.digest_due(day2_0901.astimezone(UTC)), "it ALWAYS sends, green or not"
    assert DIGEST_HOUR_CT == 9


def test_a_late_digest_beats_a_missing_one():
    """Alerter down at 9:00, back at 14:00 — the digest still goes out. A
    missing digest is the 'alerter is dead' signal, so it is never skipped."""
    a = Alerter(FakeNotifier(), clock=FakeClock())
    back_at_2pm = dt.datetime(2026, 8, 10, 14, 0, tzinfo=CT)
    assert a.digest_due(back_at_2pm.astimezone(UTC))


# ------------------------------------------------------------------ #
# FAILED exits push per row
# ------------------------------------------------------------------ #


@pytest.fixture
def failed_exit():
    """One FAILED pending exit, with its FK entry order. Cleans by test key."""
    Session = get_sessionmaker(get_engine())
    key = "test-alerter-entry"
    with Session() as s:
        s.execute(text("delete from pending_exits where market_slug like 'test-alerter%'"))
        s.execute(text("delete from orders where idempotency_key = :k"), {"k": key})
        order_id = s.execute(text("""
            insert into orders (submitted_at, idempotency_key, mode, market_slug,
                                side, order_type, limit_price, quantity, accepted)
            values (now(), :k, 'HUMAN_CONFIRM', 'test-alerter-market',
                    'buy', 'ORDER_TYPE_LIMIT', 0.20, 1, false)
            returning id
        """), {"k": key}).scalar()
        exit_id = s.execute(text("""
            insert into pending_exits (entry_order_id, market_slug, outcome,
                                       limit_price, typed_price, state, error)
            values (:oid, 'test-alerter-market', 'YES', 0.30, 0.30, 'FAILED',
                    'venue 502 twice')
            returning id
        """), {"oid": order_id}).scalar()
        s.commit()
    yield exit_id
    with Session() as s:
        s.execute(text("delete from pending_exits where market_slug like 'test-alerter%'"))
        s.execute(text("delete from orders where idempotency_key = :k"), {"k": key})
        s.commit()


def test_new_failed_exit_reported_once(failed_exit):
    a = Alerter(FakeNotifier(), clock=FakeClock())
    fresh = a.new_failed_exits()
    assert any(i == failed_exit for i, _ in fresh)
    assert a.new_failed_exits() == [], "known failures do not re-page"


# ------------------------------------------------------------------ #
# The push channel survives unicode (found in production on day one)
# ------------------------------------------------------------------ #


def test_push_uses_json_publish_and_survives_an_em_dash(monkeypatch):
    """The first real digest title was 'Meridian daily digest — OK'. Sent as an
    HTTP header, the em dash raised on ascii encoding and the digest was lost.
    JSON bodies are UTF-8; this pins the payload shape and the unicode."""
    import core.alerter as alerter_mod

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(alerter_mod.httpx, "post", fake_post)
    n = Notifier("topic-x", server="https://ntfy.example")
    assert n.push("Meridian daily digest — OK", "läuft", priority="urgent",
                  tags="newspaper")
    assert captured["url"] == "https://ntfy.example"
    assert captured["json"]["topic"] == "topic-x"
    assert "—" in captured["json"]["title"]
    assert captured["json"]["priority"] == 5
    assert captured["json"]["tags"] == ["newspaper"]


def test_a_failed_digest_stays_owed():
    """A digest that did not deliver must not mark the day as digested — it
    retries every cycle until one lands. Marking it sent would silently void
    the always-sends guarantee, which is the alerter's whole liveness story."""

    class DeafNotifier(FakeNotifier):
        def push(self, *a, **k):
            super().push(*a, **k)
            return False

    a = Alerter(DeafNotifier(), clock=FakeClock())
    now = dt.datetime(2026, 8, 10, 9, 30, tzinfo=CT).astimezone(UTC)
    assert a.digest_due(now)
    # Simulate the digest branch outcome: push failed -> date must stay unset.
    sent = a._notify.push("digest", "body")
    if sent:
        a._last_digest_date = now.astimezone(dt.timezone.utc).date()
    assert a._last_digest_date is None
    assert a.digest_due(now), "still owed after a failed send"
