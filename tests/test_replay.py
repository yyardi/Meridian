"""Replay engine tests.

Two guarantees carry all the weight, and both are about not flattering
ourselves: a strategy must not be able to see the future, and a resting order
must not fill unless the book actually traded through it. Everything else here
is bookkeeping.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.replay import (
    MIN_GAMES_FOR_VERDICT,
    GameReplay,
    ReplayContext,
    Tick,
    format_report,
    replay_game,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 2, 19, 30, tzinfo=UTC)


def _tick(sec: float, bid: float | None, ask: float | None, *,
          slug: str = "m1", score: str = "10-8", period: str = "Q1") -> Tick:
    return Tick(
        captured_at=T0 + dt.timedelta(seconds=sec),
        event_slug="wnba-test-2026-08-02", market_slug=slug,
        sports_market_type="basketball_team_full_game_total", line=170.5,
        bid=bid, ask=ask, is_live=True, score=score, period=period,
    )


class _Recorder:
    """Records what it was shown, so lookahead is testable."""

    def __init__(self) -> None:
        self.seen: list[Tick] = []

    def on_tick(self, tick, ctx):
        self.seen.append(tick)


class _BuyOnce:
    def __init__(self, price: float) -> None:
        self.price = price
        self.placed = None

    def on_tick(self, tick, ctx):
        if self.placed is None:
            self.placed = ctx.place(
                market_slug=tick.market_slug, side="buy",
                limit_price=self.price, quantity=1.0,
            )


# ------------------------------------------------------------------ #
# 1. No lookahead
# ------------------------------------------------------------------ #


def test_a_strategy_sees_ticks_one_at_a_time_in_order():
    ticks = [_tick(0, 0.40, 0.42), _tick(1, 0.41, 0.43), _tick(2, 0.44, 0.46)]
    s = _Recorder()
    replay_game(ticks, s, event_slug="g")
    assert [t.captured_at for t in s.seen] == [t.captured_at for t in ticks]


def test_the_context_exposes_no_future():
    """Lookahead should be unexpressible, not merely discouraged."""
    ctx = ReplayContext()
    public = {a for a in dir(ctx) if not a.startswith("_")}
    for forbidden in ("ticks", "future", "remaining", "all_ticks", "history"):
        assert forbidden not in public


def test_now_tracks_the_current_tick_only():
    seen: list[dt.datetime] = []

    class S:
        def on_tick(self, tick, ctx):
            seen.append(ctx.now)
            assert ctx.now == tick.captured_at

    replay_game([_tick(0, 0.4, 0.42), _tick(5, 0.4, 0.42)], S(), event_slug="g")
    assert seen == [T0, T0 + dt.timedelta(seconds=5)]


# ------------------------------------------------------------------ #
# 2. Fills must be earned
# ------------------------------------------------------------------ #


def test_an_order_never_fills_on_the_tick_that_placed_it():
    """Otherwise a maker order is a taker order with better branding.

    The ask is 0.42 and we bid 0.45, so it *would* fill on price — the only
    thing stopping it is that this is the tick that created it.
    """
    ticks = [_tick(0, 0.40, 0.42)]
    s = _BuyOnce(0.45)
    r = replay_game(ticks, s, event_slug="g")
    assert r.fills == []
    assert s.placed.is_open


def test_a_buy_fills_when_the_ask_falls_to_the_limit():
    ticks = [_tick(0, 0.40, 0.42), _tick(1, 0.33, 0.35)]
    s = _BuyOnce(0.35)
    r = replay_game(ticks, s, event_slug="g")
    assert len(r.fills) == 1
    assert r.fills[0].fill_price == pytest.approx(0.35)
    assert r.fills[0].filled_at == T0 + dt.timedelta(seconds=1)


def test_a_buy_does_not_fill_while_the_ask_stays_above():
    ticks = [_tick(0, 0.40, 0.42), _tick(1, 0.41, 0.43), _tick(2, 0.44, 0.46)]
    r = replay_game(ticks, _BuyOnce(0.35), event_slug="g")
    assert r.fills == []


def test_a_sell_fills_when_the_bid_rises_to_the_limit():
    class SellOnce:
        def __init__(self):
            self.done = False

        def on_tick(self, tick, ctx):
            if not self.done:
                ctx.place(market_slug=tick.market_slug, side="sell",
                          limit_price=0.60, quantity=1.0)
                self.done = True

    ticks = [_tick(0, 0.40, 0.42), _tick(1, 0.61, 0.63)]
    r = replay_game(ticks, SellOnce(), event_slug="g")
    assert len(r.fills) == 1


def test_fills_only_match_their_own_market():
    """A price move on market B must not fill an order resting on market A."""
    ticks = [
        _tick(0, 0.40, 0.42, slug="m1"),
        _tick(1, 0.01, 0.02, slug="m2"),   # would fill any bid, wrong market
        _tick(2, 0.40, 0.42, slug="m1"),
    ]
    r = replay_game(ticks, _BuyOnce(0.35), event_slug="g")
    assert r.fills == []


def test_a_cancelled_order_stops_being_eligible():
    class PlaceThenCancel:
        def __init__(self):
            self.order = None

        def on_tick(self, tick, ctx):
            if self.order is None:
                self.order = ctx.place(market_slug=tick.market_slug, side="buy",
                                       limit_price=0.35, quantity=1.0)
            else:
                ctx.cancel(self.order)

    ticks = [_tick(0, 0.40, 0.42), _tick(1, 0.40, 0.42), _tick(2, 0.30, 0.32)]
    r = replay_game(ticks, PlaceThenCancel(), event_slug="g")
    assert r.fills == []


def test_a_missing_quote_cannot_fill_anything():
    ticks = [_tick(0, 0.40, 0.42), _tick(1, None, None)]
    r = replay_game(ticks, _BuyOnce(0.99), event_slug="g")
    assert r.fills == []


# ------------------------------------------------------------------ #
# 3. Tick parsing
# ------------------------------------------------------------------ #


def test_score_and_total_are_parsed():
    t = _tick(0, 0.4, 0.42, score="43-37")
    assert t.points == (43, 37)
    assert t.total_points == 80


def test_an_unparseable_score_is_none_not_a_guess():
    assert _tick(0, 0.4, 0.42, score="HT").points is None
    assert _tick(0, 0.4, 0.42, score="").points is None


def test_mid_and_spread_need_both_sides():
    assert _tick(0, 0.40, 0.44).mid == pytest.approx(0.42)
    assert _tick(0, 0.40, 0.44).spread == pytest.approx(0.04)
    assert _tick(0, None, 0.44).mid is None


# ------------------------------------------------------------------ #
# 4. Sample size is games
# ------------------------------------------------------------------ #


def test_a_thin_run_refuses_a_verdict():
    replays = [GameReplay(event_slug=f"g{i}", n_ticks=200_000) for i in range(3)]
    text = format_report(replays)
    assert "NO VERDICT" in text
    assert str(MIN_GAMES_FOR_VERDICT) in text


def test_a_million_rows_across_three_games_is_still_three_observations():
    """The trap this engine exists to avoid stating out loud."""
    replays = [GameReplay(event_slug=f"g{i}", n_ticks=400_000) for i in range(3)]
    text = format_report(replays)
    assert "Rows are not the sample" in text


def test_no_games_reports_no_data_rather_than_zero():
    assert "NO DATA" in format_report([])


def test_replay_counts_markets_and_duration():
    ticks = [_tick(0, 0.4, 0.42, slug="a"), _tick(60, 0.4, 0.42, slug="b")]
    r = replay_game(ticks, _Recorder(), event_slug="g")
    assert r.n_ticks == 2
    assert r.n_markets == 2
    assert r.duration_minutes == pytest.approx(1.0)
