"""The PULSE live engine, its tape, and its scoring.

What is defended:

* an order is never filled by the observation it was born from, and fills are
  judged at the resting price (the quote engine's rule, both legs);
* the moment an entry fills, a profit-target exit rests — and when the exit
  fills the market may be re-entered (the roll);
* the stop is the model's own estimate crossing back through the entry, it
  reprices the exit to the touch as a LIMIT, and a withdrawn exit says so;
* a resting entry whose edge is gone stands down with `withdrawn_at` set;
* no bankroll reading means no entries — never a default;
* decision rows carry the full game context (score, margin, period, clock,
  tempo, book, fair value, edge, size, bankroll) and the tape's join keys,
  with the in-play phase marker;
* period starts are loaded from the database so a restart mid-quarter does
  not reset the clock;
* scoring is money-at-price, clustered by game, silent below the registered
  floors;
* and the structural claim: no code path from the engine to an order.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from core.pulse import live as pl
from core.pulse import live_report as pr
from core.pulse import storage as ps
from core.pulse.live import EventAnchors, PulseEngine, spread_fair_value
from core.pulse.storage import ENTER, EXIT, HOLD, IN_PLAY, NO, YES, PulseDecision
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG = "test-pulse-market"
EVENT = "test-pulse-event-1"

_Session = get_sessionmaker(get_engine())

NOW = dt.datetime.now(UTC)


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from market_snapshots where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _snap(s, *, bid, ask, at, slug=SLUG, event=EVENT, live=True,
          mtype=pl.MARKET_WINNER, line=None, score="55-45", period="Q4",
          game="pulse-game-1"):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type, line,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, :g, :ty, :ln, :t, :b, :a, :l, :sc, :p, 0.01)
    """), {"m": slug, "e": event, "g": game, "ty": mtype, "ln": line,
           "t": at, "b": bid, "a": ask, "l": live, "sc": score, "p": period})
    s.commit()


def _engine(*, bankroll=200.0, anchors=True, settled=(), **kw):
    settled = dict(settled)
    eng = PulseEngine(
        _Session,
        settle_every_seconds=10 ** 9,
        bankroll_reader=(lambda: bankroll),
        settlement_lookup=lambda slug: settled.get(slug),
        **kw,
    )
    if anchors:
        eng._anchors[EVENT] = EventAnchors(winner_mid=0.50, totals_mu=165.0)
    return eng


def _rows(action=None):
    with _Session() as s:
        q = s.query(PulseDecision).filter(
            PulseDecision.market_slug.like(SLUG + "%"))
        if action:
            q = q.filter(PulseDecision.action == action)
        return q.order_by(PulseDecision.id).all()


# --------------------------------------------------------------------- #
# The spread fair value and its verified frame
# --------------------------------------------------------------------- #


def test_spread_fv_is_the_win_curve_at_the_rung():
    """A team up 10 with 10 minutes left nearly always beats +7.5 and rarely
    beats −13.5 — the frame that agreed with 196/196 recorded settlements."""
    up = spread_fair_value(margin=10, minutes_left=10.0, line=7.5,
                           pregame_price=0.5)
    down = spread_fair_value(margin=10, minutes_left=10.0, line=-13.5,
                             pregame_price=0.5)
    assert up is not None and down is not None
    assert up > 0.95
    assert down < 0.5
    # Winner consistency: the spread at line -0.5/+0.5 brackets the moneyline.
    ml_ish = spread_fair_value(margin=3, minutes_left=10.0, line=-0.5,
                               pregame_price=0.5)
    assert 0.5 < ml_ish < 0.95


def test_spread_fv_refuses_whole_number_lines():
    """Push semantics are unverified — every recorded line is a half-point.
    A whole-number line gets no number, not a guess."""
    assert spread_fair_value(margin=10, minutes_left=10.0, line=7.0,
                             pregame_price=0.5) is None


def test_spread_fv_needs_a_pregame_price_and_steps_at_zero_minutes():
    assert spread_fair_value(margin=10, minutes_left=10.0, line=7.5,
                             pregame_price=None) is None
    assert spread_fair_value(margin=10, minutes_left=0.0, line=-7.5,
                             pregame_price=0.5) == 1.0
    assert spread_fair_value(margin=-10, minutes_left=0.0, line=7.5,
                             pregame_price=0.5) == 0.0


# --------------------------------------------------------------------- #
# Entering
# --------------------------------------------------------------------- #


def test_an_enter_decision_carries_the_full_game_context():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    result = eng.cycle()
    assert result.entries == 1
    rows = _rows(ENTER)
    assert len(rows) == 1
    r = rows[0]
    # Tape join keys and phase seam.
    assert r.event_slug == EVENT and r.market_slug == SLUG
    assert r.phase == IN_PLAY
    # The game as of the decision.
    assert r.score == "55-45" and r.margin == 10 and r.period == "Q4"
    assert float(r.minutes_left) == pytest.approx(10.0)
    assert r.minutes_left_is_estimate is False       # period's first sighting
    assert r.total_so_far == 100
    # The market and the model.
    assert float(r.market_bid) == 0.60 and float(r.market_ask) == 0.62
    assert r.side == YES
    assert float(r.limit_price) == 0.60              # joins the touch, maker
    assert 0.85 < float(r.fair_value) < 0.92
    assert float(r.edge_net) > 0.20
    # The size, against the REAL bankroll, with its binding constraint.
    assert float(r.bankroll_usd) == 200.0
    assert float(r.stake_usd) == pytest.approx(5.0)  # max_position_dollars cap
    assert float(r.contracts) == pytest.approx(5.0 / 0.60, rel=1e-3)
    assert r.binding_constraint == "max_position_dollars"
    assert r.filled_at is None and r.withdrawn_at is None


def test_no_bankroll_reading_means_no_entries():
    """A missing balance refuses entries — a fabricated bankroll produces a
    plausible stake on a plausible ticket, which is the bug PR #11 deleted."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(bankroll=None)
    eng.cycle()
    assert _rows() == []


def test_the_per_event_position_cap_binds():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
        _snap(s, slug=SLUG + "-sp", mtype=pl.MARKET_SPREAD, line=7.5,
              bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(max_open_per_event=1)
    eng.cycle()
    assert len(_rows(ENTER)) == 1


def test_totals_decisions_carry_the_tempo_context():
    with _Session() as s:
        _snap(s, slug=SLUG + "-tot", mtype=pl.MARKET_TOTAL, line=160.5,
              score="75-65", bid=0.60, ask=0.62,
              at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    rows = _rows(ENTER)
    assert len(rows) == 1
    r = rows[0]
    assert r.strategy == ps.STRAT_TOTAL
    assert r.total_so_far == 140
    # Q4 start, elapsed 30: projected = 165 + 1.128*(140 - 165*0.7566) ≈ 182
    assert 175 < float(r.projected_total) < 190
    assert float(r.total_sigma) == pytest.approx(9.67, abs=0.5)
    assert r.side == YES                             # heavily over the rung


# --------------------------------------------------------------------- #
# Filling, exiting, rolling
# --------------------------------------------------------------------- #


def test_an_entry_is_not_filled_by_the_observation_it_was_born_from():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    eng.cycle()                                      # same observation again
    rows = _rows(ENTER)
    assert rows[0].filled_at is None


def test_an_entry_fill_immediately_rests_the_profit_target_exit():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    with _Session() as s:                            # mid gaps down through the bid
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=6))
    result = eng.cycle()
    assert result.entry_fills == 1
    entry = _rows(ENTER)[0]
    assert entry.filled_at is not None
    assert float(entry.mid_at_fill) == pytest.approx(0.57)
    exits = _rows(EXIT)
    assert len(exits) == 1
    x = exits[0]
    assert x.reason == "profit_target"
    assert x.entry_id == entry.id
    assert float(x.limit_price) == pytest.approx(0.65)   # entry + 5c target
    assert x.side == YES and float(x.contracts) == pytest.approx(float(entry.contracts))


def test_an_exit_fill_closes_the_position_and_the_market_rolls():
    """Capitalize repeatedly: the exit fills at the target and the SAME market
    may be re-entered on the same edge — that is the operator's model."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    with _Session() as s:
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=6))
    eng.cycle()                                      # entry fills, exit rests at 0.65
    with _Session() as s:                            # mid rises through the exit
        _snap(s, bid=0.66, ask=0.70, at=NOW - dt.timedelta(seconds=2))
    result = eng.cycle()
    assert result.exit_fills == 1
    exits = _rows(EXIT)
    assert len(exits) == 1 and exits[0].filled_at is not None
    # ...and the market re-entered in the same pass: the roll.
    enters = _rows(ENTER)
    assert len(enters) == 2
    assert enters[1].filled_at is None
    assert float(enters[1].limit_price) == pytest.approx(0.66)


def test_adverse_fv_moves_the_exit_to_the_touch_as_a_limit():
    """The stop is the model's own estimate crossing back through the entry.
    The old exit is withdrawn (and says so), the new one rests at the touch —
    still a limit; nothing ever crosses the spread."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    with _Session() as s:
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=6))
    eng.cycle()                                      # position open, exit at 0.65
    with _Session() as s:                            # the game flips
        _snap(s, bid=0.30, ask=0.34, score="45-55",
              at=NOW - dt.timedelta(seconds=2))
    eng.cycle()
    exits = _rows(EXIT)
    assert len(exits) == 2
    assert exits[0].withdrawn_at is not None         # the target stood down
    stop = exits[1]
    assert stop.reason == "fv_adverse"
    assert float(stop.limit_price) == pytest.approx(0.34)   # the current ask
    assert stop.filled_at is None


def test_a_resting_entry_whose_edge_is_gone_stands_down():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()
    eng.cycle()
    with _Session() as s:
        # The game flips but the mid stays ABOVE our bid: no fill, no edge.
        _snap(s, bid=0.62, ask=0.66, score="45-55",
              at=NOW - dt.timedelta(seconds=5))
    result = eng.cycle()
    assert result.withdrawals == 1
    entry = _rows(ENTER)[0]
    assert entry.withdrawn_at is not None
    assert entry.filled_at is None


def test_holds_are_throttled_and_carry_the_entry_link():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(hold_log_seconds=0.0)
    eng.cycle()
    with _Session() as s:
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=6))
    eng.cycle()                                      # fill; hold clock starts
    with _Session() as s:
        _snap(s, bid=0.56, ask=0.60, at=NOW - dt.timedelta(seconds=2))
    eng.cycle()
    holds = _rows(HOLD)
    assert len(holds) >= 1
    h = holds[0]
    assert h.reason == "position_open"
    assert h.entry_id == _rows(ENTER)[0].id
    assert float(h.stake_usd) == 0.0                 # no new money on a hold


def test_default_hold_throttle_emits_nothing_immediately():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine()                                  # default 60s throttle
    eng.cycle()
    with _Session() as s:
        _snap(s, bid=0.55, ask=0.59, at=NOW - dt.timedelta(seconds=6))
    eng.cycle()
    with _Session() as s:
        _snap(s, bid=0.56, ask=0.60, at=NOW - dt.timedelta(seconds=2))
    eng.cycle()
    assert _rows(HOLD) == []


# --------------------------------------------------------------------- #
# Clock, anchors, restart
# --------------------------------------------------------------------- #


def test_period_starts_load_from_the_database_across_restarts():
    """A restart mid-quarter must not reset the period clock: the first
    sighting is read back from the stream, so minutes-left keeps shrinking."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=300))
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=5))
    eng = _engine()                                  # fresh process
    eng.cycle()
    r = _rows(ENTER)[0]
    assert float(r.minutes_left) == pytest.approx(10.0 - 295 / 60.0, abs=0.1)
    assert r.minutes_left_is_estimate is True


def test_the_winner_anchor_is_read_from_the_pregame_stream():
    with _Session() as s:
        _snap(s, bid=0.48, ask=0.52, live=False, score="0-0", period=None,
              at=NOW - dt.timedelta(hours=3))
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(anchors=False)
    eng.cycle()
    assert eng._anchors[EVENT].winner_mid == pytest.approx(0.50)
    assert len(_rows(ENTER)) == 1


def test_no_pregame_anchor_means_no_winner_decisions():
    """A 50/50 prior between unequal teams is a wrong prior, not a neutral
    one (the #16 lesson) — so no anchor, no fair value, no decision."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(anchors=False)
    eng.cycle()
    assert _rows() == []


# --------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------- #


def _seed_entry(s, *, slug=SLUG, event=EVENT, side=YES, price=0.60,
                contracts=2.0, filled_hours_ago=5.0, exit_price=None,
                settlement=None):
    row = PulseDecision(
        decided_at=NOW - dt.timedelta(hours=filled_hours_ago, minutes=1),
        event_slug=event, market_slug=slug, game_id="pulse-game-1",
        sports_market_type=pl.MARKET_WINNER, strategy=ps.STRAT_WINNER,
        phase=IN_PLAY, action=ENTER, side=side,
        limit_price=Decimal(str(price)), contracts=Decimal(str(contracts)),
        stake_usd=Decimal(str(round(price * contracts, 4))),
        minutes_left_is_estimate=True,
        filled_at=NOW - dt.timedelta(hours=filled_hours_ago),
        settlement=settlement,
    )
    s.add(row)
    s.flush()
    if exit_price is not None:
        s.add(PulseDecision(
            decided_at=NOW - dt.timedelta(hours=filled_hours_ago),
            event_slug=event, market_slug=slug, game_id="pulse-game-1",
            sports_market_type=pl.MARKET_WINNER, strategy=ps.STRAT_WINNER,
            phase=IN_PLAY, action=EXIT, side=side,
            limit_price=Decimal(str(exit_price)),
            contracts=Decimal(str(contracts)), stake_usd=0,
            minutes_left_is_estimate=True, entry_id=row.id,
            filled_at=NOW - dt.timedelta(hours=filled_hours_ago - 0.5),
        ))
    return row.id


def test_the_settle_sweep_marks_filled_entries_with_explicit_answers_only():
    with _Session() as s:
        _seed_entry(s, filled_hours_ago=5.0)
        _seed_entry(s, slug=SLUG + "-unknown", filled_hours_ago=5.0)
        s.commit()
    eng = _engine(settled={SLUG: 1})                 # the other market: no answer
    assert eng._settle_filled_entries() == 1
    rows = _rows(ENTER)
    by_slug = {r.market_slug: r for r in rows}
    assert by_slug[SLUG].settlement == 1
    assert by_slug[SLUG + "-unknown"].settlement is None


# --------------------------------------------------------------------- #
# Scoring — money at price, games not rows, floors
# --------------------------------------------------------------------- #


def test_report_is_counts_only_below_the_floors():
    with _Session() as s:
        for g in range(5):                           # 5 games < the 10 floor
            for i in range(10):
                _seed_entry(s, slug=f"{SLUG}-g{g}-m{i}",
                            event=f"{EVENT}-g{g}", exit_price=0.65)
        s.commit()
    with _Session() as s:
        r = pr.build_report(s)["v1"]
    assert r.n_entry_fills == 50 and r.n_games == 5
    assert not r.at_floor
    assert r.verdict == "NO DATA"
    assert "NO DATA" in pr.format_report({"v1": r})


def test_report_scores_round_trips_at_floor_clustered_by_game():
    with _Session() as s:
        for g in range(10):
            for i in range(10):
                _seed_entry(s, slug=f"{SLUG}-g{g}-m{i}",
                            event=f"{EVENT}-g{g}", exit_price=0.65)
        s.commit()
    with _Session() as s:
        r = pr.build_report(s)["v1"]
    assert r.at_floor
    assert r.n_round_trips == 100
    # +5c on a 60c entry, money-at-price: per-$ capture 0.0833..., every game.
    assert r.trip_pnl == pytest.approx(100 * 2.0 * 0.05)
    assert r.trip_roi_clustered.mean == pytest.approx(0.05 / 0.60, rel=1e-6)
    assert r.verdict.startswith("PASS")
    assert "upper bound" in r.verdict                # fills are optimistic twice


def test_report_scores_rides_to_settlement_in_the_v14_frame():
    with _Session() as s:
        _seed_entry(s, side=YES, price=0.60, settlement=1)
        _seed_entry(s, slug=SLUG + "-no", side=NO, price=0.60, settlement=1)
        s.commit()
    with _Session() as s:
        r = pr.build_report(s)["v1"]
    # yes: staked 0.60*2 returned 1*2; no: staked 0.40*2 returned 0.
    assert r.ride_staked == pytest.approx(1.2 + 0.8)
    assert r.ride_returned == pytest.approx(2.0 + 0.0)
    assert r.verdict == "NO DATA"                    # far below the floors


def test_round_trip_capture_signs():
    assert pr.round_trip_capture(side=YES, entry_price=0.60, exit_price=0.65) \
        == pytest.approx(0.05)
    assert pr.round_trip_capture(side=NO, entry_price=0.60, exit_price=0.55) \
        == pytest.approx(0.05)


# --------------------------------------------------------------------- #
# The structural claim: no path to an order
# --------------------------------------------------------------------- #


def test_the_engine_cannot_place_modify_or_cancel_anything():
    """Shadow only, by construction — the quote engine's guarantee, copied.
    The loop may read the public gateway (settlement) and the STORED bankroll
    and nothing that can write to the venue. If this fails, the pulse engine
    grew an order path — a decision nobody has made and this test forces out
    loud."""
    import ast
    import inspect

    for module in (pl, ps, pr):
        tree = ast.parse(inspect.getsource(module))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for forbidden in ("core.executor",
                          "core.fill_watcher",
                          "core.polymarket.client.PolymarketOrderClient",
                          "core.polymarket.client.PolymarketAuthedClient",
                          "core.polymarket.client.USCredentials"):
            assert not any(i == forbidden for i in imported), (
                f"{module.__name__} imports {forbidden}")
        calls = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        # No order verbs, and no bankroll VENUE reads either — the engine may
        # only consume stored account_balances rows (allow_fetch=False).
        assert not {"submit_limit_order", "cancel_order", "fetch", "refresh"} & calls, (
            f"{module.__name__} calls a venue-writing or venue-fetching verb")


# --------------------------------------------------------------------- #
# Schema roundtrip
# --------------------------------------------------------------------- #


def test_the_model_and_the_migration_agree():
    with _Session() as s:
        pid = _seed_entry(s, exit_price=0.65)
        s.commit()
    with _Session() as s:
        row = s.get(PulseDecision, pid)
        assert row.event_slug == EVENT
        assert row.phase == IN_PLAY
        assert float(row.limit_price) == 0.60
        assert row.created_at is not None            # server default fired
