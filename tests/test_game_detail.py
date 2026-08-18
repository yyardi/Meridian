"""The per-game deep dive, and the one rule it exists to keep.

Every context field on a shadow trade is read **as of the decision** — the
latest snapshot at or before `decided_at`. The tempting alternative (newest
snapshot per market) is one word of SQL shorter and silently attaches a
fourth-quarter score to a decision made two hours before tip, which on a page
whose entire purpose is judging decisions is the one error that cannot ship.

`test_context_never_reads_the_future` is the test that fails if that word
changes.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.api import _human_market, app
from core.game_detail import build_game_detail, game_label
from core.storage import MarketSnapshot, Prediction, ShadowOrder, get_engine, get_sessionmaker

UTC = dt.timezone.utc

EVENT = "wnba-sea-tor-2099-07-04"
MARKET = f"aec-{EVENT}"
TIP = dt.datetime(2099, 7, 4, 23, 0, tzinfo=UTC)

_Session = get_sessionmaker(get_engine())


def _snap(*, at, live, score, period, bid, ask):
    return MarketSnapshot(
        captured_at=at, market_slug=MARKET, event_slug=EVENT,
        sports_market_type="basketball_team_full_game_winner",
        best_bid=Decimal(bid), best_ask=Decimal(ask),
        game_start_time=TIP, is_live=live, event_score=score, event_period=period,
    )


@pytest.fixture
def one_game():
    """A pregame decision, an in-play decision, and a game that ran away after.

    The pregame decision is made at 0-0; by the fourth quarter the score is
    88-70. A view that reads the newest snapshot would label BOTH decisions
    88-70 and Q4.
    """
    with _Session() as s:
        for tbl, col in (("shadow_orders", "event_slug"), ("predictions", "event_slug"),
                         ("market_snapshots", "event_slug")):
            s.execute(text(f"delete from {tbl} where {col} = :e"), {"e": EVENT})

        s.add_all([
            _snap(at=TIP - dt.timedelta(hours=3), live=False, score="0-0",
                  period=None, bid="0.50", ask="0.52"),
            _snap(at=TIP + dt.timedelta(minutes=20), live=True, score="18-15",
                  period="Q1", bid="0.60", ask="0.62"),
            _snap(at=TIP + dt.timedelta(minutes=95), live=True, score="88-70",
                  period="Q4", bid="0.97", ask="0.98"),
        ])
        s.flush()

        preds, orders = [], []
        for i, (at, price, outcome) in enumerate((
            (TIP - dt.timedelta(hours=3), "0.52", 1),
            (TIP + dt.timedelta(minutes=25), "0.62", 0),
        )):
            p = Prediction(
                predicted_at=at, market_slug=f"{MARKET}-{i}", event_slug=EVENT,
                model_version="test", strategy="test",
                sports_market_type="basketball_team_full_game_winner",
                model_probability=Decimal("0.60"), resolved_outcome=outcome,
            )
            preds.append(p)
        s.add_all(preds)
        s.flush()

        for i, (p, at, price) in enumerate((
            (preds[0], TIP - dt.timedelta(hours=3), "0.52"),
            (preds[1], TIP + dt.timedelta(minutes=25), "0.62"),
        )):
            orders.append(ShadowOrder(
                decided_at=at, idempotency_key=f"gd-test-{i}", prediction_id=p.id,
                market_slug=MARKET, event_slug=EVENT,
                sports_market_type="basketball_team_full_game_winner",
                side="buy", limit_price=Decimal(price), quantity=Decimal("2.0"),
                model_probability=Decimal("0.60"), market_bid=Decimal("0.50"),
                market_ask=Decimal(price), edge_net=Decimal("0.08"),
                would_rest=True, mode="SHADOW",
            ))
        s.add_all(orders)
        s.commit()

    yield

    with _Session() as s:
        for tbl in ("shadow_orders", "predictions", "market_snapshots"):
            s.execute(text(f"delete from {tbl} where event_slug = :e"), {"e": EVENT})
        s.commit()


def _detail():
    with _Session() as s:
        return build_game_detail(s, EVENT, league="wnba", human_label=_human_market)


def test_context_never_reads_the_future(one_game):
    """THE test. The pregame decision must see 0-0 and no period, even though
    the same market later shows 88-70 in Q4."""
    d = _detail()
    pregame, inplay = d.trades

    assert pregame.context.is_live is False
    assert pregame.context.score == "0-0"
    assert pregame.context.period is None

    assert inplay.context.is_live is True
    assert inplay.context.score == "18-15"      # NOT 88-70
    assert inplay.context.period == "Q1"        # NOT Q4


def test_margin_is_in_the_first_team_frame(one_game):
    """`parse_score` orders (first, second) and the YES side is quoted from the
    first team, so a positive margin and a rising price move together."""
    _, inplay = _detail().trades
    assert inplay.context.margin == 3          # 18-15


def test_minutes_left_is_flagged_as_an_estimate(one_game):
    """There is no game clock in the feed — it is interpolated from wall-clock
    since the period was first seen. A number presented as exact would be a
    confident wrong one."""
    _, inplay = _detail().trades
    assert inplay.context.minutes_left is not None
    assert inplay.context.minutes_left_is_estimate is True


def test_context_age_is_reported(one_game):
    """Pregame polling is 15-60 minutes apart. A three-hour-old quote behind a
    decision has to be visible, or the reading looks instantaneous."""
    pregame, _ = _detail().trades
    assert pregame.context.context_age_seconds == 0.0


def test_pnl_is_conditional_on_a_fill_that_never_happened(one_game):
    """Shadow orders were never sent and mostly would have rested. The winning
    one pays (1 − limit) per contract; the loser pays −limit."""
    pregame, inplay = _detail().trades

    assert pregame.bet_won is True
    assert pregame.pnl_if_filled == pytest.approx((1.0 - 0.52) * 2.0)

    assert inplay.bet_won is False
    assert inplay.pnl_if_filled == pytest.approx(-0.62 * 2.0)


def test_unresolved_trades_have_no_outcome(one_game):
    """A game in progress must not be scored. None, never zero — a zero would
    be summed into a P&L as a loss."""
    with _Session() as s:
        s.execute(text("update predictions set resolved_outcome = null "
                       "where event_slug = :e"), {"e": EVENT})
        s.commit()
    for t in _detail().trades:
        assert t.bet_won is None
        assert t.pnl_if_filled is None


def test_the_timeline_is_after_and_is_separate(one_game):
    """The game's own path is context for the reader. Every point in it is
    later than every decision, and it is delivered as its own field so the UI
    cannot accidentally read it as decision context."""
    d = _detail()
    assert d.timeline, "expected the live path"
    assert all(p.at > d.trades[0].decided_at for p in d.timeline)
    assert d.final_score == "88-70"


def test_labels_do_not_assert_home_and_away():
    """Polymarket flipped slug order in the season's first week, so the slug
    cannot say who is home. "vs", never "@"."""
    assert game_label("wnba-ny-chi-2026-08-18", league="wnba") == "NY vs CHI"
    assert "@" not in game_label("wnba-ny-chi-2026-08-18", league="wnba")


def test_the_endpoint_serves_the_deep_dive(one_game):
    c = TestClient(app)
    body = c.get(f"/api/game/{EVENT}").json()
    assert body["n_trades"] == 2
    assert body["n_live_decisions"] == 1
    assert body["trades"][0]["context"]["score"] == "0-0"
    assert body["trades"][1]["context"]["score"] == "18-15"


def test_a_game_with_no_shadow_trades_is_a_404():
    """Better than an empty page that looks like a load failure."""
    c = TestClient(app)
    assert c.get("/api/game/wnba-sea-tor-2099-12-31").status_code == 404


def test_a_slug_from_no_known_league_is_refused():
    c = TestClient(app)
    assert c.get("/api/game/cricket-a-b-2099-01-01").status_code == 400
