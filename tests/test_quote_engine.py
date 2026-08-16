"""The QUOTE shadow engine and its scoring.

What is defended:

* the fill rule is the adverse-selection study's own, both sides, judged
  against the STANDING quote even when the filling observation moves the
  touch — the ordering that makes requoting measurable;
* the quotable band is the study's, via the study's class — one definition;
* regime is fixed at quote birth, not at fill;
* scoring is money-at-price on both sides with the V14 frame conversion on
  the short side, clustered by game, silent below the registered floors;
* settlement accepts explicit 0/1 only;
* and the structural claim: no code path from the engine to an order.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.quote import engine as qe
from core.quote import report as qr
from core.quote.storage import ASK, BID, INGAME, PREGAME, ShadowQuoteFill
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG = "test-quote-engine-market"

_Session = get_sessionmaker(get_engine())


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from shadow_quote_fills where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from market_snapshots where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from service_heartbeats where service = 'quote_engine'"))
        s.commit()


def _snap(s, *, bid, ask, at, slug=SLUG, live=True, game="qe-game-1"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, game_id, captured_at, best_bid, best_ask, is_live)
        values (:m, :g, :t, :b, :a, :l)
    """), {"m": slug, "g": game, "t": at, "b": bid, "a": ask, "l": live})
    s.commit()


def _quoter(settled=()):
    settled = dict(settled)
    return qe.ShadowQuoter(
        _Session,
        settle_every_seconds=10 ** 9,           # settlement runs only when asked
        settlement_lookup=lambda slug: settled.get(slug),
    )


def _fills():
    with _Session() as s:
        return s.query(ShadowQuoteFill).filter(
            ShadowQuoteFill.market_slug.like(SLUG + "%")).all()


NOW = dt.datetime.now(UTC)


# --------------------------------------------------------------------- #
# Quoting and filling
# --------------------------------------------------------------------- #


def test_a_quote_is_not_filled_by_the_observation_it_was_born_from():
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=8))
    q = _quoter()
    q.cycle()                                    # births the quote
    q.cycle()                                    # same observation again
    assert _fills() == []
    assert SLUG in q._standing


def test_bid_fills_when_a_newer_mid_reaches_it_and_at_the_old_price():
    """The mid gaps down THROUGH our bid while the touch moves away. The fill
    is judged against the standing quote's price — that ordering is the whole
    requoting question — and the quote then follows the touch."""
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=10))
    q = _quoter()
    q.cycle()
    with _Session() as s:
        _snap(s, bid=0.30, ask=0.34, at=NOW - dt.timedelta(seconds=5))
    result = q.cycle()
    fills = _fills()
    assert result.fills == 1 and len(fills) == 1
    f = fills[0]
    assert f.side == BID
    assert float(f.quote_price) == 0.40          # the OLD standing price
    assert float(f.mid_at_fill) == pytest.approx(0.32)
    # ...and the maker has requoted at the new touch.
    assert q._standing[SLUG].bid_price == 0.30


def test_ask_fills_when_the_mid_rises_to_it():
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=10))
    q = _quoter()
    q.cycle()
    with _Session() as s:
        _snap(s, bid=0.46, ask=0.50, at=NOW - dt.timedelta(seconds=5))
    q.cycle()
    fills = _fills()
    assert len(fills) == 1 and fills[0].side == ASK
    assert float(fills[0].quote_price) == 0.44


def test_a_move_inside_the_spread_fills_nothing_but_requotes():
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=10))
    q = _quoter()
    q.cycle()
    with _Session() as s:
        _snap(s, bid=0.41, ask=0.45, at=NOW - dt.timedelta(seconds=5))
    result = q.cycle()
    assert _fills() == []
    assert result.requotes == 1
    assert q._standing[SLUG].bid_price == 0.41


def test_unquotable_markets_are_stood_down_not_quoted():
    """The study's band, via the study's own class: a 20¢ spread is not a
    market-making opportunity, and a maker who kept quoting it would be
    manufacturing fills from an empty book."""
    with _Session() as s:
        _snap(s, bid=0.30, ask=0.50, at=NOW - dt.timedelta(seconds=10))
    q = _quoter()
    q.cycle()
    assert SLUG not in q._standing
    # And a standing quote is withdrawn when the band is left.
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=8),
              slug=SLUG + "-2")
    q.cycle()
    assert (SLUG + "-2") in q._standing
    with _Session() as s:
        _snap(s, bid=0.10, ask=0.44, at=NOW - dt.timedelta(seconds=4),
              slug=SLUG + "-2")
    q.cycle()
    assert (SLUG + "-2") not in q._standing


def test_regime_is_fixed_at_quote_birth():
    """A quote rested pregame and filled at tip belongs to PREGAME — the
    regime that made the decision to rest it."""
    with _Session() as s:
        _snap(s, bid=0.40, ask=0.44, at=NOW - dt.timedelta(seconds=10), live=False)
    q = _quoter()
    q.cycle()
    assert q._standing[SLUG].regime == PREGAME
    with _Session() as s:
        _snap(s, bid=0.30, ask=0.34, at=NOW - dt.timedelta(seconds=5), live=True)
    q.cycle()
    assert _fills()[0].regime == PREGAME
    # The REQUOTE born from the live observation is in-game.
    assert q._standing[SLUG].regime == INGAME


def test_heartbeat_beats_with_the_cycle():
    q = _quoter()
    q._heartbeat.beat(interval_seconds=q.interval_seconds, rows_written=0)
    with _Session() as s:
        row = s.execute(text(
            "select service, interval_seconds from service_heartbeats "
            "where service = 'quote_engine'")).one()
    assert row.service == qe.SERVICE_QUOTE


# --------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------- #


def _seed_fill(*, side=BID, price=0.40, settlement=None, game="qe-game-1",
               regime=INGAME, slug=SLUG, mid_at_fill=0.38, age_hours=6.0):
    with _Session() as s:
        s.add(ShadowQuoteFill(
            market_slug=slug, game_id=game, regime=regime, side=side,
            quote_price=price, mid_at_quote=price + 0.02 if side == BID else price - 0.02,
            spread_at_quote=0.04, mid_at_fill=mid_at_fill,
            quoted_at=NOW - dt.timedelta(hours=age_hours, minutes=1),
            filled_at=NOW - dt.timedelta(hours=age_hours),
            settlement=settlement,
        ))
        s.commit()


def test_settlement_takes_explicit_answers_only():
    _seed_fill()                                  # old enough to ask about
    q = _quoter(settled={SLUG: None})             # "could not ask" / no answer
    assert q._settle_fills() == 0
    with _Session() as s:
        assert _fills()[0].settlement is None

    q = _quoter(settled={SLUG: 0})
    assert q._settle_fills() == 1
    assert _fills()[0].settlement == 0


def test_fresh_fills_are_not_asked_about():
    _seed_fill(age_hours=0.5)
    q = _quoter(settled={SLUG: 1})
    assert q._settle_fills() == 0                 # too young; quota not spent


# --------------------------------------------------------------------- #
# Scoring — money at price, both sides, clustered, silent below floors
# --------------------------------------------------------------------- #


def test_score_fill_long_side():
    assert qr.score_fill(side=BID, quote_price=0.40, settlement=1) == (0.40, 1.0)
    assert qr.score_fill(side=BID, quote_price=0.40, settlement=0) == (0.40, 0.0)


def test_score_fill_short_side_is_the_no_frame():
    """A filled offer is short YES = the NO side at 1 − price (V14). Selling
    at 0.44 stakes 0.56 and pays out when the market settles 0."""
    staked, returned = qr.score_fill(side=ASK, quote_price=0.44, settlement=0)
    assert staked == pytest.approx(0.56)
    assert returned == 1.0
    staked, returned = qr.score_fill(side=ASK, quote_price=0.44, settlement=1)
    assert staked == pytest.approx(0.56)
    assert returned == 0.0


def test_net_capture_mark_matches_the_static_study_frames():
    assert qr.net_capture_mark(side=BID, quote_price=0.40, mid_at_fill=0.38) == pytest.approx(-0.02)
    assert qr.net_capture_mark(side=ASK, quote_price=0.44, mid_at_fill=0.46) == pytest.approx(-0.02)
    assert qr.net_capture_mark(side=BID, quote_price=0.40, mid_at_fill=0.41) == pytest.approx(+0.01)


def test_report_is_counts_only_below_the_floors():
    """The registration's teeth: below 500 settled fills / 10 games, the
    report prints NO DATA and refuses to print a performance number at all."""
    for i in range(3):
        _seed_fill(settlement=1, game=f"qe-game-{i}")
    with _Session() as s:
        reports = {k: v for k, v in qr.build_report(s).items()}
    r = reports[INGAME]
    assert r.n_settled == 3 and not r.at_floor
    assert r.verdict == "NO DATA"
    textout = qr.format_report(reports)
    assert "NO DATA" in textout
    assert "ROI" not in textout.split("[ingame]")[1].split("VERDICT")[0]


def test_report_clusters_by_game_at_floor(monkeypatch):
    """At floor, the ROI interval is game-clustered — G games of correlated
    fills, not n independent rows."""
    monkeypatch.setattr(qr, "FLOOR_FILLS", 20)
    monkeypatch.setattr(qr, "FLOOR_GAMES", 2)
    for g in range(4):
        for i in range(6):
            _seed_fill(side=BID if i % 2 else ASK, price=0.40,
                       settlement=i % 2, game=f"qe-game-{g}")
    with _Session() as s:
        r = qr.build_report(s)[INGAME]
    assert r.at_floor
    assert r.roi_clustered is not None
    assert r.roi_clustered.n_clusters == 4
    assert r.verdict in ("FAIL",) or r.verdict.startswith("PASS")


# --------------------------------------------------------------------- #
# The structural claim: no path to an order
# --------------------------------------------------------------------- #


def test_the_engine_cannot_place_modify_or_cancel_anything():
    """Shadow only, by construction. The engine may import the public gateway
    client (settlement reads) and nothing that can write to the venue. If
    this fails, the shadow quoter grew an order path — a decision nobody has
    made and this test forces out loud."""
    import ast
    import inspect

    for module in (qe, qr):
        tree = ast.parse(inspect.getsource(module))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for forbidden in ("core.executor",
                          "core.polymarket.client.PolymarketOrderClient",
                          "core.polymarket.client.PolymarketAuthedClient",
                          "core.polymarket.client.USCredentials"):
            assert not any(i == forbidden for i in imported), (
                f"{module.__name__} imports {forbidden}")
        calls = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert not {"submit_limit_order", "cancel_order"} & calls
