"""The WNBA player model's registered properties, on fixtures. No database, no venue.

    pytest --noconftest tests/test_wnba_player_model.py

What is pinned, and why each is a registered kill condition rather than a nicety
(docs/math/wnba-player-model-preregistration.md):

  * point-in-time  -- a log dated after the game, and one inside the 4h blind
                      window before it, change NOTHING; a log just outside it does;
  * orientation    -- YES is the slug's first team, the home edge lands on YES
                      exactly when ESPN says the first team is home, and for
                      equal teams P(YES) < 0.5 when the first team is away;
  * fee            -- a pre-change and a post-change row in ONE run are each an
                      expression in their own coefficient, and NULL is refused;
  * estimator      -- duplicating every row leaves the naive interval narrower
                      and the game-clustered one unchanged in width per game,
                      i.e. clustering does not reward copies; G/(G-1) is carried;
  * MC             -- the 20k-draw probability agrees with Phi(mu/sigma) to 1pp.
"""
import datetime as dt
import importlib.util
import pathlib
import random
import sys
from decimal import Decimal

import pytest

_CFB = pathlib.Path(__file__).resolve().parent.parent / "cfb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load("wnba_player_model_under_test", _CFB / "run_wnba_player_model.py")
UTC = dt.timezone.utc

#: The venue's coefficient before and after it raised the fee at 2026-09-17
#: 04:07Z. Spelled here, not imported: they are HISTORY and core/fees.py holds
#: only the current one (same convention as tests/test_fee_per_row_closing.py).
PRE, POST = Decimal("0.060000"), Decimal("0.069500")

#: Fewer draws than the registered 20,000 keep the suite fast; the MC-vs-Phi
#: test below runs the registered count once.
FAST = 2000


def _fixture():
    return m.fixture_dataset()


def _predict(game, logs, injuries, draws=FAST):
    pred, why = m.predict_game(game, logs, injuries, [], draws=draws)
    assert pred is not None, why
    return pred


# ------------------------------------------------------------------ importable without a DB
def test_the_script_loads_with_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mod = _load("wnba_player_model_reload", _CFB / "run_wnba_player_model.py")
    assert callable(mod.main)


# ------------------------------------------------------------------ point-in-time
def test_a_log_dated_after_the_game_changes_nothing():
    """THE leakage test. The prediction for game e0 is computed; then a huge
    plus-minus log for the first team is added (a) after the game, (b) inside
    the blind window (tip - 1h - 3h < t), and the prediction must be bit-identical.
    A log just OUTSIDE the window must change it, or the test tests nothing."""
    games, logs, injuries = _fixture()
    g = games[0]
    base = _predict(g, logs, injuries)
    t_pred = m.prediction_instant(g["tip"])
    lag = dt.timedelta(seconds=m.LOG_LAG_SECONDS)

    def loud(when):
        return [{"espn_game_id": f"leak-{when.isoformat()}", "game_date": when, "season": g["season"],
                 "season_type": 2, "team_id": g["first_team_id"], "athlete_id": f"{g['first_team_id']}p{j}",
                 "minutes": 40, "plus_minus": 200, "did_not_play": False} for j in range(8)]

    after = _predict(g, logs + loud(g["tip"] + dt.timedelta(days=1)), injuries)
    blind = _predict(g, logs + loud(t_pred - lag + dt.timedelta(seconds=1)), injuries)
    assert after == base and blind == base, "a future or blind-window log moved the prediction"

    visible = _predict(g, logs + loud(t_pred - lag), injuries)
    assert visible["p"] > base["p"] + 0.05 and visible["mu"] > base["mu"], \
        "the control did not move: a log at the visibility boundary must be seen, or the test is inert"


def test_an_injury_row_captured_after_the_prediction_instant_is_not_seen():
    """Same rule on the change log: captured_at is the only timestamp used."""
    games, logs, _ = _fixture()
    g = games[2]                                            # first team 4, second team 1
    t_pred = m.prediction_instant(g["tip"])
    star = f"{g['second_team_id']}p0"
    base = _predict(g, logs, [])
    late = _predict(g, logs, [{"athlete_id": star, "captured_at": t_pred + dt.timedelta(minutes=1), "status": "Out"}])
    seen = _predict(g, logs, [{"athlete_id": star, "captured_at": t_pred, "status": "Out"}])
    assert late == base
    assert seen["n_out"] == 1 and seen["mu"] > base["mu"], "the strong team lost its star, so first's margin must rise"
    d2d = _predict(g, logs, [{"athlete_id": star, "captured_at": t_pred, "status": "Day-To-Day"}])
    assert d2d == base, "Day-To-Day is registered as no change"


def test_expected_minutes_are_zero_filled_over_the_teams_games():
    """A player absent from 5 of the team's last 10 games carries half her minutes."""
    day = dt.datetime(2026, 7, 1, tzinfo=UTC)
    logs = []
    for k in range(10):
        logs.append({"espn_game_id": f"g{k}", "game_date": day + dt.timedelta(days=k), "season": 2026, "season_type": 2,
                     "team_id": "A", "athlete_id": "always", "minutes": 30, "plus_minus": 0, "did_not_play": False})
        if k % 2 == 0:
            logs.append({"espn_game_id": f"g{k}", "game_date": day + dt.timedelta(days=k), "season": 2026, "season_type": 2,
                         "team_id": "A", "athlete_id": "half", "minutes": 30, "plus_minus": 0, "did_not_play": False})
    mins, n = m.expected_minutes(logs, "A")
    assert n == 10 and mins["always"] == 30 and mins["half"] == 15


# ------------------------------------------------------------------ orientation
def test_yes_is_the_first_team_and_the_home_edge_lands_where_espn_says():
    """Equal teams, no history difference: P(YES) is below 0.5 when the first
    team is away and above when ESPN says it is home. The same slug order, two
    answers, decided by is_home alone."""
    assert m.expected_margin(0.0, 0.0, first_is_home=False) == -m.HOME_EDGE_POINTS
    assert m.expected_margin(0.0, 0.0, first_is_home=True) == +m.HOME_EDGE_POINTS
    games, logs, injuries = _fixture()
    g = dict(games[0], first_team_id="1", second_team_id="1")   # a team against itself: strengths cancel exactly
    away = _predict(dict(g, first_is_home=False), logs, injuries)
    home = _predict(dict(g, first_is_home=True), logs, injuries)
    assert away["mu"] == -m.HOME_EDGE_POINTS and home["mu"] == +m.HOME_EDGE_POINTS
    assert away["p"] < 0.5 < home["p"]


def test_orient_reads_home_from_espn_not_from_slug_order():
    """The early-May 2026 case in core/team_mapping.py: 18 of 285 markets had the
    slug's first team at HOME. `orient` must return first_is_home=True there and
    the ids in slug order either way."""
    from core.team_mapping import parse_market_slug
    home_row = {"espn_game_id": "x", "team_abbrev": "NY", "opponent_abbrev": "CON", "team_id": "9", "opponent_id": "18"}
    f, s, fh = m.orient(parse_market_slug("aec-wnba-conn-ny-2026-05-10"), home_row)
    assert (f, s, fh) == ("18", "9", False)                     # first = conn = away
    f, s, fh = m.orient(parse_market_slug("aec-wnba-ny-conn-2026-05-10"), home_row)
    assert (f, s, fh) == ("9", "18", True)                      # first = ny = HOME


def test_match_slug_needs_exactly_one_espn_game():
    from core.team_mapping import parse_market_slug
    parsed = parse_market_slug("aec-wnba-gsv-sea-2026-08-10")   # gsv -> GS, the mapping that .upper() breaks
    row = lambda gid, at: {"espn_game_id": gid, "team_abbrev": "SEA", "opponent_abbrev": "GS", "team_id": "1",
                           "opponent_id": "2", "game_date": at}
    at = dt.datetime(2026, 8, 11, 2, 0, tzinfo=UTC)             # 7pm PT is the next UTC day
    assert m.match_slug(parsed, [row("a", at)])[0]["espn_game_id"] == "a"
    assert m.match_slug(parsed, [])[1] == "no_espn_game"
    assert m.match_slug(parsed, [row("a", at), row("b", at + dt.timedelta(hours=3))])[1] == "ambiguous"
    assert m.match_slug(parsed, [row("a", at + dt.timedelta(days=3))])[1] == "no_espn_game"


# ------------------------------------------------------------------ fee: the row's own coefficient
def test_two_rows_in_one_run_are_charged_at_their_own_coefficients():
    """A pre-change and a post-change row, same run, each an expression in its
    own coefficient -- never pinned cents, so the venue's next move cannot break
    a test that is right."""
    from core.fees import recorded_fee
    pre = {"bid": 0.48, "ask": 0.50, "fee_coefficient": PRE}
    post = {"bid": 0.48, "ask": 0.50, "fee_coefficient": POST}
    yes_pre = m.paper_pnl("yes", 1, pre["bid"], pre["ask"], pre["fee_coefficient"])
    yes_post = m.paper_pnl("yes", 1, post["bid"], post["ask"], post["fee_coefficient"])
    assert yes_pre == 1 - 0.50 - recorded_fee(0.50, PRE)
    assert yes_post == 1 - 0.50 - recorded_fee(0.50, POST)
    assert yes_pre != yes_post, "the two periods must not collapse to one charge"
    no_pre = m.paper_pnl("no", 0, pre["bid"], pre["ask"], pre["fee_coefficient"])
    assert no_pre == 1 - (1 - 0.48) - recorded_fee(0.48, PRE)


def test_a_row_without_a_coefficient_is_refused_not_charged_at_todays():
    with pytest.raises(ValueError):
        m.paper_pnl("yes", 1, 0.48, 0.50, None)


def test_the_fixture_run_carries_two_periods_and_the_paper_line_charges_each():
    games, logs, injuries = _fixture()
    coefs = {g["fee_coefficient"] for g in games}
    assert len(coefs) == 2, "the dry run must show two coefficients charged differently"
    rows, skipped = m.evaluate(games, logs, injuries, draws=FAST)
    assert not skipped and len(rows) == 6
    for r in rows:
        if r["side"]:
            m.paper_pnl(r["side"], r["y"], r["bid"], r["ask"], r["fee_coefficient"])   # must not raise


# ------------------------------------------------------------------ the decision rule
def test_paper_side_is_the_registered_rule_and_nothing_else():
    """Inclusive at the boundary despite float subtraction (0.45 - 0.40 is
    0.04999999999999999), and exclusive one MC quantum (1/MC_DRAWS) below it --
    the smallest shortfall a real p can have, since prices are 1c ticks."""
    t, q = m.EDGE_THRESHOLD, 1 / m.MC_DRAWS
    assert 0.45 - 0.40 < t                                       # the trap this rule rounds past
    assert m.paper_side(0.40 + t, 0.38, 0.40) == "yes"
    assert m.paper_side(0.40 + t - q, 0.38, 0.40) is None
    assert m.paper_side(0.38 - t, 0.38, 0.40) == "no"
    assert m.paper_side(0.38 - t + q, 0.38, 0.40) is None
    assert m.paper_side(0.39, 0.38, 0.40) is None


# ------------------------------------------------------------------ estimator: clustered by game
def test_duplicated_rows_do_not_shrink_the_clustered_interval():
    """Copy every row once more with the same game key: the naive interval
    shrinks by ~sqrt(2) (it counts copies as evidence) while the clustered
    interval's half-width does not shrink -- copies within a cluster are summed
    before squaring, so the sandwich sees the same G games."""
    vals = [1.0, -0.5, 2.0, 0.5, -1.0, 1.5, 0.0, -2.0]
    keys = [f"g{i}" for i in range(8)]
    m1, h1, n1, G1 = m.clustered(vals, keys)
    m2, h2, n2, G2 = m.clustered(vals + vals, keys + keys)
    _, nh1 = m.naive(vals); _, nh2 = m.naive(vals + vals)
    assert (n1, G1, n2, G2) == (8, 8, 16, 8) and m1 == m2
    assert nh2 < nh1 * 0.8, "the naive interval must fall for copies, or this test cannot tell the two apart"
    assert h2 == pytest.approx(h1, rel=1e-9), "the clustered interval must not reward copies"


def test_the_sandwich_carries_the_small_sample_correction():
    """With one row per cluster the clustered SE is the naive SE (population sd
    over n) times sqrt(G/(G-1)); pinned so the correction cannot be dropped."""
    vals = [3.0, 1.0, 4.0, 1.0, 5.0]
    mean = sum(vals) / 5
    ss = sum((v - mean) ** 2 for v in vals)
    expected = 1.96 * (ss ** 0.5 / 5) * (5 / 4) ** 0.5
    _, h, _, G = m.clustered(vals, list("abcde"))
    assert G == 5 and h == pytest.approx(expected)
    assert m.clustered([1.0, 2.0], ["same", "same"])[1] == float("inf"), "one cluster is no interval"


def test_evaluate_scores_every_game_against_venue_and_coin_walk_forward():
    games, logs, injuries = _fixture()
    rows, skipped = m.evaluate(games, logs, injuries, draws=FAST)
    assert not skipped
    tips = [r["tip"] for r in rows]
    assert tips == sorted(tips)
    assert rows[0]["sigma"] == m.SIGMA_PRIOR_POINTS, "the first game sees the prior alone"
    assert rows[1]["sigma"] != rows[0]["sigma"], "the second game sees the first residual"
    for r in rows:
        assert r["brier_coin"] == 0.25 and abs(r["ll_coin"] - 0.6931471805599453) < 1e-12
        assert 0.0 <= r["p"] <= 1.0 and r["v"] == (r["bid"] + r["ask"]) / 2
    assert sum(1 for r in rows if r["season_type"] == m.PLAYOFFS) == 2


def test_a_cold_team_is_skipped_and_counted_not_guessed():
    games, logs, injuries = _fixture()
    g = dict(games[0], first_team_id="nobody")
    pred, why = m.predict_game(g, logs, injuries, [], draws=FAST)
    assert pred is None and why.startswith("cold")


# ------------------------------------------------------------------ Monte Carlo
def test_mc_agrees_with_the_closed_form_at_the_registered_draw_count():
    for mu, sigma in ((0.0, 12.0), (4.5, 11.0), (-9.0, 13.0)):
        assert abs(m.mc_win_prob(mu, sigma) - m.closed_form(mu, sigma)) < 0.01


def test_mc_is_reproducible_under_the_registered_seed():
    """Against an INDEPENDENT reference (this test's own walk of the seeded
    generator), not against a second call to the same function -- that shape
    passes whatever the code does (tests/test_no_self_comparing_assertions.py).
    The control: a different seed must move the number, or the seed pins nothing."""
    rng = random.Random(m.MC_SEED)
    ref = sum(1 for _ in range(FAST) if rng.gauss(2.0, 12.0) > 0) / FAST
    assert m.mc_win_prob(2.0, 12.0, draws=FAST) == ref
    assert m.mc_win_prob(2.0, 12.0, draws=FAST, seed=m.MC_SEED + 1) != ref


# ------------------------------------------------------------------ the dry run prints counts before any result
def test_dry_run_prints_populations_then_rows_then_gate(capsys):
    sys.argv = ["run_wnba_player_model.py", "--dry-run", "--draws", str(FAST)]
    m.main()
    out = capsys.readouterr().out
    assert "FIXTURE" in out and "n_games scored: 6" in out
    assert out.index("FIXTURE dataset") < out.index("B_model"), "counts print before any Brier"
    assert "UNDERPOWERED" in out and "NOT SCORED" in out, "six fixture games cannot pass a 50-game floor"
    assert "n_first_is_home: 1" in out
