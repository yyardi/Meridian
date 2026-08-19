"""The in-game moneyline replay, and chiefly what its CLV is measuring.

The bug these pin
-----------------
CLV's whole value is that it is an *independent* signal that converges faster
than outcomes. The first draft took the reference price from the market's LAST
observed tick — by which time 87% of markets had effectively settled (mid above
0.95 or below 0.05). The resulting "CLV" correlated **+0.980** with realised
P&L: not a second measurement, the same one wearing a different name, and
reporting the two side by side would have implied corroboration that did not
exist.

The fix is a fixed horizon after entry that must still be in play. Correlation
falls to +0.240 and the mean from +2.45¢ to +0.96¢ — the inflation was the
outcome leaking in.

The general form is worth more than the instance: **a metric that cannot
disagree with the metric beside it is not evidence.**
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.backtest.ingame_replay import (
    CLV_HORIZON_SECONDS,
    _reference_mid,
    replay,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 18, 23, 0, tzinfo=UTC)


class _Tick:
    def __init__(self, *, secs, bid, ask, live=True, period="Q3", score="50-45",
                 slug="aec-wnba-ny-phx-2026-08-18", event="wnba-ny-phx-2026-08-18"):
        self.market_slug = slug
        self.event_slug = event
        self.captured_at = T0 + dt.timedelta(seconds=secs)
        self.event_period = period
        self.event_score = score
        self.is_live = live
        self.best_bid = bid
        self.best_ask = ask


# ------------------------------------------------------------------ #
# The CLV reference
# ------------------------------------------------------------------ #


def test_reference_is_a_later_price_not_the_last_one():
    """The market keeps trading after the horizon; the reference is the price
    AT the horizon, not wherever the market ended up."""
    live = [
        _Tick(secs=0, bid=0.50, ask=0.52),
        _Tick(secs=CLV_HORIZON_SECONDS + 1, bid=0.60, ask=0.62),
        _Tick(secs=5000, bid=0.99, ask=1.00),      # effectively settled
    ]
    assert _reference_mid(live, after=T0) == pytest.approx(0.61)


def test_no_reference_when_the_horizon_falls_past_the_whistle():
    """An entry struck two minutes before the end has no later price that is
    not simply the result. None is the honest answer."""
    live = [_Tick(secs=0, bid=0.50, ask=0.52),
            _Tick(secs=60, bid=0.55, ask=0.57)]
    assert _reference_mid(live, after=T0) is None


def test_a_settled_reference_is_refused():
    """The exact contamination: if the only price past the horizon has
    resolved, there is no market movement to measure."""
    live = [_Tick(secs=0, bid=0.50, ask=0.52),
            _Tick(secs=CLV_HORIZON_SECONDS + 1, bid=0.995, ask=1.0)]
    assert _reference_mid(live, after=T0) is None


# ------------------------------------------------------------------ #
# Entry mechanics
# ------------------------------------------------------------------ #


def _rows(*, pregame_mid=0.50, live_bid=0.30, live_ask=0.32, final="70-50"):
    """A market with a pregame prior and a live run that ends decided."""
    rows = [_Tick(secs=-600, bid=pregame_mid - 0.01, ask=pregame_mid + 0.01,
                  live=False, period=None, score="0-0")]
    for i in range(40):
        rows.append(_Tick(secs=i * 60, bid=live_bid, ask=live_ask,
                          period="Q3", score="50-45"))
    rows.append(_Tick(secs=3000, bid=0.99, ask=1.0, period="Q4", score=final))
    return rows


def test_entry_crosses_the_spread_and_pays_the_far_touch():
    """Pessimistic by design: a resting order would usually do better, but it
    also sometimes does not fill, and assuming the good half of that is how a
    replay flatters itself."""
    r = replay(min_edge=0.01, decision_seconds=30, rows=_rows())
    assert r.entries, "expected an entry at a 0.30/0.32 book with a 50-45 lead"
    e = r.entries[0]
    if e.side == "YES":
        assert e.entry_price == pytest.approx(0.32)      # the ask
    else:
        assert e.entry_price == pytest.approx(0.70)      # 1 - bid


def test_at_most_one_entry_per_market():
    """Compounding within a market turns one disagreement into a position
    size, which is a sizing question rather than a signal question."""
    r = replay(min_edge=0.01, decision_seconds=30, rows=_rows())
    assert len(r.entries) <= 1
    assert r.markets_seen == 1


def test_market_without_a_pregame_prior_is_skipped_not_defaulted():
    """A coin-flip prior on a 0.68/0.30 matchup is the assumption that made
    hypothesis #16 look like a 6.8c edge before the confound check inverted."""
    live_only = [t for t in _rows() if t.is_live]
    r = replay(min_edge=0.01, rows=live_only)
    assert r.entries == []
    assert r.markets_no_pregame == 1


def test_overtime_is_skipped_rather_than_approximated():
    """Past regulation the pregame edge is spent and the 40-minute denominator
    describes nothing. `Clock.usable` is False and the tick is not traded."""
    rows = [_Tick(secs=-600, bid=0.49, ask=0.51, live=False, period=None, score="0-0")]
    rows += [_Tick(secs=i * 60, bid=0.30, ask=0.32, period="OT", score="80-80")
             for i in range(20)]
    rows.append(_Tick(secs=3000, bid=0.99, ask=1.0, period="OT", score="95-90"))
    r = replay(min_edge=0.01, rows=rows)
    assert r.entries == []


def test_money_at_price_settles_zero_or_one():
    r = replay(min_edge=0.01, decision_seconds=30, rows=_rows(final="70-50"))
    e = r.entries[0]
    expected = (1 - e.entry_price) if e.won else -e.entry_price
    assert e.pnl == pytest.approx(expected)
