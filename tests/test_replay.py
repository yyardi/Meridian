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
    _stream,
    _tick_stmt,
    format_report,
    load_ticks,
    recorded_coefficient,
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


# ------------------------------------------------------------------ #
# 4. Every tick carries the coefficient the venue charged on its row
# ------------------------------------------------------------------ #
# The venue raised its taker coefficient on 2026-09-17 04:07Z and the recorder
# stores the value in force on every market_snapshots row. A replay charges a
# fee at the tick's own coefficient; a tick with none is refused, never
# priced at today's constant.


def test_a_synthetic_tick_has_no_coefficient_and_charging_it_is_refused():
    t = _tick(0, 0.40, 0.42)
    assert t.fee_coefficient is None
    with pytest.raises(ValueError, match="fee_coefficient"):
        recorded_coefficient(t)


def test_the_recorded_coefficient_is_the_ticks_own():
    t = Tick(captured_at=T0, event_slug="g", market_slug="m", sports_market_type=None,
             line=None, bid=0.4, ask=0.42, is_live=True, score=None, period=None,
             fee_coefficient=0.06)
    assert recorded_coefficient(t) == 0.06


def test_the_tick_query_selects_the_rows_coefficient():
    assert "fee_coefficient" in str(_tick_stmt(event_slug="g"))


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, *args, **kwargs):
        return _Result(self.rows)


def _row(at, coef):
    from decimal import Decimal
    from types import SimpleNamespace
    return SimpleNamespace(
        captured_at=at, event_slug="g", market_slug="m", sports_market_type=None,
        line=None, best_bid=Decimal("0.40"), best_ask=Decimal("0.42"), is_live=True,
        event_score=None, event_period=None,
        fee_coefficient=None if coef is None else Decimal(coef))


def test_streamed_ticks_carry_the_rows_coefficient_as_a_float_and_null_as_none():
    """The column is Numeric(8, 6): a pre-change row reads 0.060000, a
    post-change row 0.069500, and a NULL stays None so the charge site can
    refuse it rather than a fabricated zero slipping through."""
    rows = [_row(T0, "0.060000"), _row(T0 + dt.timedelta(days=40), "0.069500"),
            _row(T0 + dt.timedelta(days=41), None)]
    ticks = list(_stream(_Session(rows), _tick_stmt(event_slug="g")))
    assert [t.fee_coefficient for t in ticks] == [0.06, 0.0695, None]
    assert all(isinstance(t.fee_coefficient, float) for t in ticks[:2])


def test_load_ticks_reads_the_coefficient_the_recorder_stored():
    """Against the test database: two rows either side of the venue's raise,
    read back at the coefficients they were written with."""
    from decimal import Decimal

    from sqlalchemy import text

    from core.storage import MarketSnapshot, get_engine, get_sessionmaker

    event = "wnba-feetest-2026-09-16"
    market = "aec-" + event
    rows = [
        (dt.datetime(2026, 9, 16, 23, 0, tzinfo=UTC), Decimal("0.060000")),
        (dt.datetime(2026, 9, 18, 23, 0, tzinfo=UTC), Decimal("0.069500")),
    ]
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(text("delete from market_snapshots where event_slug = :e"), {"e": event})
        s.add_all([MarketSnapshot(
            captured_at=at, market_slug=market, event_slug=event,
            sports_market_type="basketball_team_full_game_winner",
            best_bid=Decimal("0.40"), best_ask=Decimal("0.42"), is_live=True,
            fee_coefficient=coef) for at, coef in rows])
        s.commit()
    try:
        with Session() as s:
            ticks = load_ticks(s, event_slug=event)
        assert [t.fee_coefficient for t in ticks] == [0.06, 0.0695]
    finally:
        with Session() as s:
            s.execute(text("delete from market_snapshots where event_slug = :e"), {"e": event})
            s.commit()
