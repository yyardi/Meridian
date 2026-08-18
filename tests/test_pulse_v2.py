"""PULSE v2 inputs: point-in-time form, fitted volatility, version labelling,
and the offline replay evaluator.

What is defended:

* team form is point-in-time — a game dated at or after the as-of instant
  never feeds it;
* stale form refuses (None) rather than degrading silently, and the shrunk
  sigma multiplier stays between the team moment and the league baseline;
* a v2-mode engine prices with the matchup sigma when form allowed it and
  the rows say 'v2'; when form refused, it prices with the v1 constants and
  the rows say 'v1' — model generations never blend (the era-separation
  lesson);
* the report scores each version separately;
* the replay simulator applies the registered rule symmetrically — identical
  estimates produce identical trades — and scores outcomes in the verified
  frames;
* and the structural claim extends to the new modules: no path to an order.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from core.pulse import live as pl
from core.pulse import replay_eval as re_
from core.pulse import team_form as tf
from core.pulse.live import EventAnchors, PulseEngine
from core.pulse.storage import ENTER, PulseDecision
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
SLUG = "test-pulse-v2-market"
EVENT = "test-pulse-v2-event"

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
        s.execute(text("delete from team_game_logs where espn_game_id like 'tpv2-%'"))
        s.execute(text("delete from service_heartbeats where service = 'pulse_engine'"))
        s.commit()


def _log(s, *, game, date, team, opp, tid, oid, pts, opp_pts,
         quarters=(20, 20, 20, 20), opp_quarters=(15, 15, 15, 15)):
    for abbrev, other, my_id, other_id, mine, theirs, q, oq in (
        (team, opp, tid, oid, pts, opp_pts, quarters, opp_quarters),
        (opp, team, oid, tid, opp_pts, pts, opp_quarters, quarters),
    ):
        s.execute(text("""
            insert into team_game_logs
                (game_date, season, espn_game_id, team_id, team_abbrev,
                 opponent_id, opponent_abbrev, is_home, points_scored,
                 points_allowed, is_completed, season_type,
                 q1, q2, q3, q4, fga, fta, oreb, turnovers)
            values (:d, 2026, :g, :tid, :t, :oid, :o, true, :pf, :pa, true, 2,
                    :q1, :q2, :q3, :q4, 70, 20, 8, 12)
        """), {"d": date, "g": game, "tid": my_id, "t": abbrev,
               "oid": other_id, "o": other, "pf": mine, "pa": theirs,
               "q1": q[0], "q2": q[1], "q3": q[2], "q4": q[3]})
    s.commit()


def _seed_form(s, *, days_ago=1.0, n=3, quarters=(20, 20, 20, 20),
               opp_quarters=(15, 15, 15, 15)):
    for i in range(n):
        _log(s, game=f"tpv2-{i}",
             date=NOW - dt.timedelta(days=days_ago + i * 2),
             team="AAA", opp="BBB", tid="9001", oid="9002",
             pts=sum(quarters), opp_pts=sum(opp_quarters),
             quarters=quarters, opp_quarters=opp_quarters)


# --------------------------------------------------------------------- #
# Point-in-time form
# --------------------------------------------------------------------- #


def test_form_is_point_in_time():
    """A game at or after the as-of instant never feeds the form."""
    with _Session() as s:
        _seed_form(s, days_ago=1.0, n=2)
        as_of = NOW - dt.timedelta(days=2)           # BEFORE the newest game
        form = tf.team_form(s, "AAA", as_of=as_of)
    assert form is not None
    assert form.n_games == 1                         # only the older game


def test_stale_form_refuses():
    with _Session() as s:
        _seed_form(s, days_ago=10.0, n=3)            # newest game 10 days old
        form = tf.matchup_form(s, first_abbrev="AAA", second_abbrev="BBB",
                               as_of=NOW)
        assert form is None                          # the guard, not a caveat
        # The offline eval may disable the guard — labelled, not silent.
        form2 = tf.matchup_form(s, first_abbrev="AAA", second_abbrev="BBB",
                                as_of=NOW, max_staleness_days=None)
    assert form2 is not None
    assert form2.staleness_days > 5


def test_sigma_multiplier_is_shrunk_toward_the_league():
    """Flat quarter swings (zero within-game variance) cannot drag the
    matchup sigma to zero: K_SHRINK pseudo-games of league prior bound it."""
    with _Session() as s:
        _seed_form(s, days_ago=1.0, n=3)             # identical quarters: var 0
        form = tf.matchup_form(s, first_abbrev="AAA", second_abbrev="BBB",
                               as_of=NOW)
    assert form is not None
    expected_sq = (tf.K_SHRINK * tf.LEAGUE_SIGMA_SQ_PER_MIN) / (3 + tf.K_SHRINK)
    assert form.sigma_multiplier == pytest.approx(
        (expected_sq / tf.LEAGUE_SIGMA_SQ_PER_MIN) ** 0.5, rel=1e-6)
    assert 0.0 < form.sigma_multiplier < 1.0
    assert form.sigma == pytest.approx(
        tf.DEFAULT_SIGMA * form.sigma_multiplier, rel=1e-9)


def test_blended_anchor_rules():
    form = tf.MatchupForm(
        first=None, second=None, form_total=150.0,          # type: ignore[arg-type]
        sigma_multiplier=1.0, sigma=tf.DEFAULT_SIGMA)
    # W_BLEND is measured at 1.0 right now, so blend == v4 — asserted against
    # the constant rather than a literal so a legitimate refit updates one place.
    assert tf.blended_total_anchor(160.0, form) == pytest.approx(
        tf.W_BLEND * 160.0 + (1 - tf.W_BLEND) * 150.0)
    assert tf.blended_total_anchor(160.0, None) == 160.0     # v4 alone: v1's own
    assert tf.blended_total_anchor(None, form) is None       # form alone: refuse


# --------------------------------------------------------------------- #
# The engine in v2 mode
# --------------------------------------------------------------------- #


def _snap(s, *, bid, ask, at, slug=SLUG, event=EVENT):
    s.execute(text("""
        insert into market_snapshots
            (market_slug, event_slug, game_id, sports_market_type,
             captured_at, best_bid, best_ask, is_live, event_score,
             event_period, min_trade_qty)
        values (:m, :e, 'pulse-v2-game', :ty, :t, :b, :a, true, '55-45',
                'Q4', 0.01)
    """), {"m": slug, "e": event, "ty": pl.MARKET_WINNER,
           "t": at, "b": bid, "a": ask})
    s.commit()


def _engine(version, anchors):
    eng = PulseEngine(
        _Session,
        estimates_version=version,
        settle_every_seconds=10 ** 9,
        bankroll_reader=lambda: 200.0,
        settlement_lookup=lambda slug: None,
    )
    eng._anchors[EVENT] = anchors
    return eng


def _enter_rows():
    with _Session() as s:
        return s.query(PulseDecision).filter(
            PulseDecision.market_slug.like(SLUG + "%"),
            PulseDecision.action == ENTER).all()


def test_v2_mode_prices_with_the_matchup_sigma_and_labels_rows_v2():
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    # A wider-than-league matchup: same margin is worth less certainty.
    eng = _engine(pl.ESTIMATES_V2, EventAnchors(
        winner_mid=0.50, totals_mu=165.0, matchup_sigma=3.5))
    eng.cycle()
    rows = _enter_rows()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v2"
    fv_v2 = float(rows[0].fair_value)
    # v1 on the identical game state, for comparison.
    with _Session() as s:
        s.execute(text("delete from pulse_decisions where market_slug like :m"),
                  {"m": SLUG + "%"})
        s.commit()
    eng1 = _engine(pl.ESTIMATES_V1, EventAnchors(
        winner_mid=0.50, totals_mu=165.0, matchup_sigma=3.5))
    eng1.cycle()
    rows1 = _enter_rows()
    assert len(rows1) == 1
    assert rows1[0].estimates_version == "v1"
    fv_v1 = float(rows1[0].fair_value)
    # Wider sigma pulls a big favourite toward the coin flip; and v1 mode
    # must ignore the matchup sigma even though the anchors carry one.
    assert fv_v2 < fv_v1


def test_v2_mode_with_refused_form_prices_v1_and_says_so():
    """The engine mode is not the row label — what PRICED the row is."""
    with _Session() as s:
        _snap(s, bid=0.60, ask=0.62, at=NOW - dt.timedelta(seconds=10))
    eng = _engine(pl.ESTIMATES_V2, EventAnchors(
        winner_mid=0.50, totals_mu=165.0))           # no matchup sigma: refused
    eng.cycle()
    rows = _enter_rows()
    assert len(rows) == 1
    assert rows[0].estimates_version == "v1"


def test_report_scores_versions_separately():
    from decimal import Decimal

    from core.pulse import live_report as prr
    from core.pulse.storage import IN_PLAY, YES
    with _Session() as s:
        for version, price in (("v1", "0.60"), ("v2", "0.40")):
            row = PulseDecision(
                decided_at=NOW - dt.timedelta(hours=6),
                event_slug=EVENT, market_slug=f"{SLUG}-{version}",
                sports_market_type=pl.MARKET_WINNER, strategy="winner",
                phase=IN_PLAY, action=ENTER, side=YES,
                limit_price=Decimal(price), contracts=Decimal(1),
                stake_usd=Decimal(price), minutes_left_is_estimate=True,
                filled_at=NOW - dt.timedelta(hours=5),
                settlement=1, estimates_version=version,
            )
            s.add(row)
        s.commit()
    with _Session() as s:
        reports = prr.build_report(s)
    assert set(reports) == {"v1", "v2"}
    assert reports["v1"].ride_staked == pytest.approx(0.60)
    assert reports["v2"].ride_staked == pytest.approx(0.40)
    text_out = prr.format_report(reports)
    assert "[estimates v1]" in text_out and "[estimates v2]" in text_out


# --------------------------------------------------------------------- #
# The replay evaluator
# --------------------------------------------------------------------- #


def _tick(seconds_ago, bid, ask, score="55-45", period="Q4"):
    return re_.Tick(at=NOW - dt.timedelta(seconds=seconds_ago),
                    bid=bid, ask=ask, score=score, period=period)


def test_market_outcomes_use_the_verified_frames():
    assert re_.market_outcome(pl.MARKET_WINNER, None, (88, 95)) == 0
    assert re_.market_outcome(pl.MARKET_TOTAL, 160.5, (88, 95)) == 1
    assert re_.market_outcome(pl.MARKET_SPREAD, 7.5, (88, 95)) == 1   # −7 + 7.5
    assert re_.market_outcome(pl.MARKET_SPREAD, -7.5, (95, 88)) == 0  # +7 − 7.5
    assert re_.market_outcome(pl.MARKET_SPREAD, 7.0, (88, 95)) is None   # whole line


def test_simulator_is_symmetric_between_arms():
    """Identical estimates must trade identically — any asymmetry here would
    put a thumb on the scale of the whole comparison."""
    ticks = [_tick(60, 0.60, 0.62), _tick(45, 0.55, 0.59),
             _tick(30, 0.66, 0.70), _tick(15, 0.60, 0.62)]
    fvs = [0.88, 0.88, 0.88, 0.88]
    a = re_.simulate_market(ticks, fvs, 1, min_edge=0.03)
    b = re_.simulate_market(ticks, list(fvs), 1, min_edge=0.03)
    assert (a.n_entries, a.n_entry_fills, a.n_round_trips, a.rois) == \
           (b.n_entries, b.n_entry_fills, b.n_round_trips, b.rois)


def test_simulator_runs_the_registered_rule():
    """Enter at the touch, fill on the mid crossing, exit at +5c, and the
    market may re-enter — the engine's own scenario, replayed."""
    ticks = [_tick(60, 0.60, 0.62),                  # enter yes, bid 0.60
             _tick(45, 0.55, 0.59),                  # mid 0.57 <= 0.60: fill
             _tick(30, 0.66, 0.70),                  # mid 0.68 >= 0.65: exit
             _tick(15, 0.66, 0.68)]                  # re-enter (the roll)
    fvs = [0.88] * 4
    r = re_.simulate_market(ticks, fvs, 1, min_edge=0.03)
    assert r.n_entries == 2
    assert r.n_entry_fills == 1
    assert r.n_round_trips == 1
    assert r.rois == [pytest.approx(0.05 / 0.60)]


def test_simulator_rides_unexited_fills_to_settlement():
    ticks = [_tick(60, 0.60, 0.62), _tick(45, 0.55, 0.59)]
    r = re_.simulate_market(ticks, [0.88, 0.88], 1, min_edge=0.03)
    assert r.n_entry_fills == 1 and r.n_round_trips == 0 and r.n_rides == 1
    assert r.rois == [pytest.approx(1.0 / 0.60 - 1.0)]   # settled yes at 0.60


def test_arm_params_fall_back_to_v1_without_form():
    data = re_.EventData(event_slug=EVENT, final_score=(88, 95),
                         winner_mid=0.5, mu_v4=160.0, form=None,
                         form_fresh=False)
    v1, v2 = re_.arm_params(data)
    assert v2.sigma == v1.sigma == re_.DEFAULT_SIGMA
    assert v2.totals_mu == v1.totals_mu == 160.0


# --------------------------------------------------------------------- #
# The structural claim extends to the new modules
# --------------------------------------------------------------------- #


def test_the_v2_modules_cannot_place_modify_or_cancel_anything():
    import ast
    import inspect

    for module in (tf, re_):
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
        assert not {"submit_limit_order", "cancel_order", "fetch", "refresh"} & calls
