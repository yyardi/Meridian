"""WNBA player-based pregame winner model, scored against the venue. Never traded.

Registered in docs/math/wnba-player-model-preregistration.md BEFORE this file was
run against a price; the constants below are that document's, by name. What it
does, once per ESPN game with a Polymarket US winner market:

    rating   r_i  = sum(plus_minus) / (sum(minutes) + RATING_SHRINK_MINUTES)   per player, visible logs
    minutes  m_i  = mean minutes over the team's last RECENT_TEAM_GAMES, zero-filled; 'Out' -> 0
    strength S    = (1/5) * sum_i m_i * r_i        with m rescaled to TEAM_MINUTES
    margin   mu   = S_first - S_second +- HOME_EDGE_POINTS   (ESPN says who is home)
    P(first) = fraction of MC_DRAWS normal(mu, sigma_k) draws > 0, sigma_k walk-forward

scored by Brier and log loss against the venue's LAST quote in [tip-6h, tip-1h]
and against 0.5, one row per game, game-clustered intervals, playoffs as their own
row. A paper line (EDGE_THRESHOLD at the ask, fee at each row's own coefficient)
is scored only if the Brier gate passes.

Point-in-time: a player log is visible iff game_date + LOG_LAG_SECONDS <= tip -
PREDICTION_OFFSET_SECONDS; an injury row iff captured_at <= that instant. YES is
the slug's first team; home/away comes from ESPN, never from the slug.

    python cfb/run_wnba_player_model.py --dry-run                # fixtures, no DB
    python cfb/run_wnba_player_model.py [--settlement venue|espn] [--days 90]

Read-only: SELECTs on DATABASE_URL, the venue's public settlement endpoint, and
nothing else. Pure functions at module level are tested in
tests/test_wnba_player_model.py; the run is under main().
"""
import argparse
import datetime as dt
import math
import os
import random
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd())  # run bare: the api image mounts core/ and cfb/ alone
from core import fees  # noqa: E402
from core.fees import recorded_fee  # noqa: E402  the row's own coefficient; None raises (core/fees.py)

UTC = dt.timezone.utc

# ----------------------------------------------------------------- registered constants
# Every number here is named in docs/math/wnba-player-model-preregistration.md.
# Changing one is a new registration, not a tune.
TEAM_MINUTES = 200                  # 5 slots x 40 minutes; expected minutes are rescaled to this
RECENT_TEAM_GAMES = 10              # window for expected minutes, zero-filled
RATING_SHRINK_MINUTES = 400         # pseudo-minutes of league-average play added to every rating
HOME_EDGE_POINTS = 3.0              # fixed, not fitted; the realised home margin is printed beside it
SIGMA_PRIOR_POINTS = 12.0           # walk-forward sigma prior ...
SIGMA_PRIOR_GAMES = 20              # ... and its weight in games
MC_DRAWS = 20000                    # normal margins per game
MC_SEED = 20260922                  # so a re-run prints the same number
LOG_LAG_SECONDS = 3 * 3600          # a box score exists three hours after its own tip
PREDICTION_OFFSET_SECONDS = 3600    # predict at T-1h
QUOTE_WINDOW_SECONDS = 6 * 3600     # the last quote in [tip-6h, tip-1h] is the venue's price
EDGE_THRESHOLD = 0.05               # buy when |model - price| clears this, at the ask / 1-bid
POWER_FLOOR_GAMES = 50              # no verdict word below this many settled games
MIN_PRIOR_TEAM_GAMES = 5            # both teams need this many visible games with player rows
LOGLOSS_CLIP = 1e-6
WINNER_TYPE = "basketball_team_full_game_winner"
SLUG_PREFIX = "aec-wnba-"
INJURY_OUT = "Out"                  # the ESPN designation that zeroes minutes; Day-To-Day does not
PLAYOFFS = 3                        # ESPN season_type; core.config.SEASON_TYPE_POSTSEASON
#: Measured 2026-09-23 on prod: team_game_logs and player_game_logs stamp every
#: 2026-09-14..09-22 game season_type 2, so the ESPN field alone left the playoff
#: row empty on a 106-game run. The same date cut the PULSE live scorecard uses.
PLAYOFFS_START = dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc)


def is_playoff(r: dict) -> bool:
    """ESPN's season_type when it says so, the date when it does not."""
    return r["season_type"] == PLAYOFFS or r["tip"] >= PLAYOFFS_START


# ----------------------------------------------------------------- point-in-time visibility
def prediction_instant(tip):
    return tip - dt.timedelta(seconds=PREDICTION_OFFSET_SECONDS)


def visible_logs(logs, t_pred):
    """Player rows whose box score existed at t_pred. The game being predicted is
    never visible to itself (its own tip is after t_pred); an earlier same-night
    game is visible only if it tipped LOG_LAG_SECONDS + offset before this one."""
    lag = dt.timedelta(seconds=LOG_LAG_SECONDS)
    return [r for r in logs if r["game_date"] + lag <= t_pred]


def injured_out(injuries, t_pred):
    """Athletes whose LATEST injury row at t_pred says Out. Rows are a change log
    (core/feeds/espn_injuries.py), so the latest row IS the state."""
    latest = {}
    for r in injuries:
        if r["captured_at"] <= t_pred and (r["athlete_id"] not in latest or r["captured_at"] >= latest[r["athlete_id"]][0]):
            latest[r["athlete_id"]] = (r["captured_at"], r["status"])
    return {a for a, (_, s) in latest.items() if (s or "").strip().lower() == INJURY_OUT.lower()}


# ----------------------------------------------------------------- the model, pure
def player_ratings(vis, season):
    """r_i = sum(pm) / (sum(min) + K) over visible rows of this season and the one
    before. DNP rows carry NULL minutes/plus_minus and are skipped."""
    pm, mn = defaultdict(float), defaultdict(float)
    for r in vis:
        if r["season"] not in (season, season - 1) or r.get("did_not_play"):
            continue
        if r["minutes"] is None or r["plus_minus"] is None:
            continue
        pm[r["athlete_id"]] += r["plus_minus"]; mn[r["athlete_id"]] += r["minutes"]
    return {a: pm[a] / (mn[a] + RATING_SHRINK_MINUTES) for a in pm}


def expected_minutes(vis, team_id):
    """Mean minutes over the team's last RECENT_TEAM_GAMES visible games, zero-filled:
    a game the team played without her is 0 for her. Returns ({athlete: minutes},
    n_team_games_in_window)."""
    games = sorted({(r["game_date"], r["espn_game_id"]) for r in vis if r["team_id"] == team_id})[-RECENT_TEAM_GAMES:]
    if not games:
        return {}, 0
    gids = {g for _, g in games}
    tot = defaultdict(float)
    for r in vis:
        if r["team_id"] == team_id and r["espn_game_id"] in gids and r["minutes"] and not r.get("did_not_play"):
            tot[r["athlete_id"]] += r["minutes"]
    return {a: m / len(games) for a, m in tot.items()}, len(games)


def team_strength(minutes, ratings, out):
    """(1/5) * sum m~_i r_i with m~ rescaled to TEAM_MINUTES after Out players are
    zeroed. Returns (S, n_players_with_minutes, n_out_with_minutes)."""
    avail = {a: m for a, m in minutes.items() if a not in out and m > 0}
    n_out = sum(1 for a, m in minutes.items() if a in out and m > 0)
    total = sum(avail.values())
    if total <= 0:
        return 0.0, 0, n_out
    scale = TEAM_MINUTES / total
    return sum(m * scale * ratings.get(a, 0.0) for a, m in avail.items()) / 5.0, len(avail), n_out


def expected_margin(s_first, s_second, first_is_home):
    return s_first - s_second + (HOME_EDGE_POINTS if first_is_home else -HOME_EDGE_POINTS)


def sigma_walkforward(prior_residuals):
    """Prior pooled with the squared residuals of every EARLIER evaluated game."""
    ss = SIGMA_PRIOR_POINTS ** 2 * SIGMA_PRIOR_GAMES + sum(e * e for e in prior_residuals)
    return math.sqrt(ss / (SIGMA_PRIOR_GAMES + len(prior_residuals)))


def mc_win_prob(mu, sigma, draws=MC_DRAWS, seed=MC_SEED):
    """Fraction of normal(mu, sigma) margins above zero. Basketball has no ties."""
    rng = random.Random(seed)
    return sum(1 for _ in range(draws) if rng.gauss(mu, sigma) > 0) / draws


def closed_form(mu, sigma):
    return 0.5 * (1.0 + math.erf(mu / (sigma * math.sqrt(2.0))))


def predict_game(game, logs, injuries, prior_residuals, draws=MC_DRAWS):
    """One game from what was knowable at T-1h. Returns the prediction and the
    inputs the report counts; None with a reason when a team is cold."""
    t_pred = prediction_instant(game["tip"])
    vis = visible_logs(logs, t_pred)
    out = injured_out(injuries, t_pred)
    ratings = player_ratings(vis, game["season"])
    m1, g1 = expected_minutes(vis, game["first_team_id"])
    m2, g2 = expected_minutes(vis, game["second_team_id"])
    if g1 < MIN_PRIOR_TEAM_GAMES or g2 < MIN_PRIOR_TEAM_GAMES:
        return None, f"cold: {g1}/{g2} visible team games < {MIN_PRIOR_TEAM_GAMES}"
    s1, n1, o1 = team_strength(m1, ratings, out)
    s2, n2, o2 = team_strength(m2, ratings, out)
    mu = expected_margin(s1, s2, game["first_is_home"])
    sigma = sigma_walkforward(prior_residuals)
    p = mc_win_prob(mu, sigma, draws=draws)
    return {"p": p, "p_closed": closed_form(mu, sigma), "mu": mu, "sigma": sigma,
            "s_first": s1, "s_second": s2, "n_players": (n1, n2), "n_out": o1 + o2,
            "n_visible_logs": len(vis)}, None


# ----------------------------------------------------------------- scoring, pure
def brier(p, y):
    return (p - y) ** 2


def logloss(p, y):
    q = min(max(p, LOGLOSS_CLIP), 1.0 - LOGLOSS_CLIP)
    return -(y * math.log(q) + (1 - y) * math.log(1 - q))


def clustered(vals, keys):
    """Mean, 1.96*SE (cluster sandwich with G/(G-1)), n, G. As cfb/run_paper_book.py."""
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res)
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G


def naive(vals):
    """The row-level interval. Printed only so the size of the lie is visible."""
    n = len(vals); m = sum(vals) / n
    if n < 2:
        return m, float("inf")
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    return m, 1.96 * sd / math.sqrt(n)


def paper_side(p, bid, ask):
    """'yes' at the ask, 'no' at 1-bid, or None. The registered rule, nothing else.

    The edge is rounded before the comparison: 0.45 - 0.40 is 0.04999999999999999
    in binary floats, and the test's boundary case (p exactly a threshold above
    the ask) returned None until it was. Prices are 1c ticks and p is a multiple
    of 1/MC_DRAWS, so six decimals lose nothing and keep the boundary inclusive.
    """
    if round(p - ask, 6) >= EDGE_THRESHOLD:
        return "yes"
    if round(bid - p, 6) >= EDGE_THRESHOLD:
        return "no"
    return None


def paper_pnl(side, y, bid, ask, fee_coefficient):
    """Net $ on one $1 contract at the coefficient the venue carried ON THIS ROW.
    None is refused by core.fees.recorded_fee, never charged at today's."""
    if side == "yes":
        return y - ask - recorded_fee(ask, fee_coefficient)
    return (1 - y) - (1 - bid) - recorded_fee(bid, fee_coefficient)


def evaluate(games, logs, injuries, draws=MC_DRAWS):
    """Walk-forward over games in tip order. Returns (rows, skipped) where each row
    carries p, v, y and the per-game scores; sigma for game k sees residuals of
    games before k only."""
    rows, skipped, residuals = [], [], []
    for g in sorted(games, key=lambda x: (x["tip"], x["espn_game_id"])):
        pred, why = predict_game(g, logs, injuries, residuals, draws=draws)
        if pred is None:
            skipped.append((g["espn_game_id"], why)); continue
        v = (g["bid"] + g["ask"]) / 2.0
        y = g["y"]
        row = {**g, **pred, "v": v, "brier_model": brier(pred["p"], y), "brier_venue": brier(v, y),
               "brier_coin": brier(0.5, y), "ll_model": logloss(pred["p"], y),
               "ll_venue": logloss(v, y), "ll_coin": logloss(0.5, y),
               "side": paper_side(pred["p"], g["bid"], g["ask"])}
        rows.append(row)
        if g.get("first_score") is not None and g.get("second_score") is not None:
            residuals.append((g["first_score"] - g["second_score"]) - pred["mu"])
    return rows, skipped


# ----------------------------------------------------------------- slug -> ESPN game
def match_slug(parsed, home_rows):
    """The one ESPN home row for a parsed slug: unordered pair + 30h UTC window
    (core.team_mapping.resolve_orientation). Returns (row, reason)."""
    from core.team_mapping import UnknownTeamError, utc_window
    try:
        a, b = parsed.first_espn, parsed.second_espn
    except UnknownTeamError:
        return None, "unknown_team"
    lo, hi = utc_window(parsed.local_date)
    hits = [r for r in home_rows if {r["team_abbrev"], r["opponent_abbrev"]} == {a, b} and lo <= r["game_date"] < hi]
    if len(hits) != 1:
        return None, "no_espn_game" if not hits else "ambiguous"
    return hits[0], None


def orient(parsed, home_row):
    """(first_team_id, second_team_id, first_is_home) from ESPN's home row."""
    first_is_home = home_row["team_abbrev"] == parsed.first_espn
    home_id, away_id = home_row["team_id"], home_row["opponent_id"]
    return (home_id, away_id, True) if first_is_home else (away_id, home_id, False)


# ----------------------------------------------------------------- report
def _row(name, rows, keys):
    d = [r["brier_model"] - r["brier_venue"] for r in rows]
    m, h, n, G = clustered(d, keys)
    nm, nh = naive(d)
    bm = sum(r["brier_model"] for r in rows) / n; bv = sum(r["brier_venue"] for r in rows) / n
    bc = sum(r["brier_coin"] for r in rows) / n
    lm = sum(r["ll_model"] for r in rows) / n; lv = sum(r["ll_venue"] for r in rows) / n
    lc = sum(r["ll_coin"] for r in rows) / n
    if G < POWER_FLOOR_GAMES:
        verdict = f"UNDERPOWERED (G={G} < {POWER_FLOOR_GAMES})"
    elif m + h < 0:
        verdict = "MODEL BEATS VENUE on Brier, excludes 0"
    elif m - h > 0:
        verdict = "VENUE BEATS MODEL on Brier, excludes 0"
    else:
        verdict = "spans 0"
    print(f"{name:<16}{G:>6}{bm:>9.4f}{bv:>9.4f}{bc:>9.4f}{'%+.4f [%+.4f, %+.4f]' % (m, m - h, m + h):>40}"
          f"{'%+.4f +-%.4f' % (nm, nh):>20}{lm:>9.4f}{lv:>9.4f}{lc:>9.4f}   {verdict}")
    return {"G": G, "delta": m, "half": h, "brier_model": bm, "brier_venue": bv, "verdict": verdict}


def report(rows, skipped, counts, settlement_label):
    print(f"\nsettlement: {settlement_label}")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  cold games skipped: {len(skipped)}")
    for gid, why in skipped[:10]:
        print(f"    {gid}: {why}")
    if not rows:
        print("\nno games to score."); return None
    keys = [r["espn_game_id"] for r in rows]
    print(f"\nn_games scored: {len(set(keys))}  (rows {len(rows)}; a duplicate slug would make these differ)")
    n_home = sum(1 for r in rows if r["first_is_home"])
    print(f"n_first_is_away: {len(rows) - n_home}   n_first_is_home: {n_home}   (YES = slug's first team; home/away from ESPN)")
    touched = sum(1 for r in rows if r["n_out"] > 0)
    print(f"games where an Out designation zeroed a rotation player: {touched}")
    with_scores = [r for r in rows if r.get("first_score") is not None and r.get("second_score") is not None]
    if with_scores:
        hm = [(r["first_score"] - r["second_score"]) * (1 if r["first_is_home"] else -1) for r in with_scores]
        print(f"realised mean home margin: {sum(hm) / len(hm):+.2f} on {len(hm)} games (HOME_EDGE_POINTS = {HOME_EDGE_POINTS}, fixed)")
    print(f"mean sigma: {sum(r['sigma'] for r in rows) / len(rows):.2f}   max |MC - closed form|: "
          f"{max(abs(r['p'] - r['p_closed']) for r in rows):.4f}   MC_DRAWS={MC_DRAWS} seed={MC_SEED}")
    print(f"\n{'row':<16}{'G':>6}{'B_model':>9}{'B_venue':>9}{'B_coin':>9}{'delta model-venue [95% game-clustered]':>40}"
          f"{'naive (WRONG)':>20}{'LL_model':>9}{'LL_venue':>9}{'LL_coin':>9}   verdict")
    out = {"all": _row("all", rows, keys)}
    for name, pred in (("regular", lambda r: not is_playoff(r)), ("playoffs", is_playoff),
                       ("first_is_away", lambda r: not r["first_is_home"]), ("first_is_home", lambda r: r["first_is_home"])):
        sub = [r for r in rows if pred(r)]
        if len({r["espn_game_id"] for r in sub}) >= 2:
            out[name] = _row(name, sub, [r["espn_game_id"] for r in sub])
        else:
            print(f"{name:<16}{len(sub):>6}   (fewer than 2 games; not a row)")
    gate = out["all"]["verdict"].startswith("MODEL BEATS VENUE") and out["all"]["brier_model"] <= 0.25
    bets = [r for r in rows if r["side"]]
    print(f"\npaper line (EDGE_THRESHOLD={EDGE_THRESHOLD}, at the ask / 1-bid, fee at each row's own coefficient):")
    print(f"  would take {len(bets)} bets on {len({r['espn_game_id'] for r in bets})} games "
          f"({sum(1 for r in bets if r['side'] == 'yes')} YES, {sum(1 for r in bets if r['side'] == 'no')} NO)")
    if not gate:
        print("  NOT SCORED: Brier gate failed (or underpowered). No P&L is printed, so there is nothing to quote.")
    elif bets:
        pnl = [100 * paper_pnl(r["side"], r["y"], r["bid"], r["ask"], r["fee_coefficient"]) for r in bets]
        m, h, n, G = clustered(pnl, [r["espn_game_id"] for r in bets])
        print(f"  P&L ${sum(pnl) / 100:+.2f} on {n} $1 contracts, {G} games; mean {m:+.2f}c [{m - h:+.2f}, {m + h:+.2f}] game-clustered"
              f"{'  G<25' if G < 25 else ''}")
    print("\nNothing here is placed, sized or armed. A row is read only with its G; UNDERPOWERED rows are counts, not verdicts.")
    return out


# ----------------------------------------------------------------- fixtures (the dry run and the tests)
#: A second period's coefficient for the dry run's pre-change row. SYNTHETIC and
#: deliberately not a value the venue ever carried: the point of the dry run is
#: that two rows in one run are charged differently, and the tests supply the
#: venue's real historical pair themselves.
OTHER_PERIOD_COEF = Decimal("0.050000")


def fixture_dataset():
    """Four teams, deterministic history, six priced games. Team quality is
    +6 / +2 / -2 / -6 points; player plus-minus is the team margin spread over
    minutes so the model has something to find. Returns (games, logs, injuries)."""
    quality = {"1": 6.0, "2": 2.0, "3": -2.0, "4": -6.0}
    mins = [34, 32, 30, 28, 24, 20, 18, 14]                  # sums to 200
    logs, gid = [], 0
    day = dt.datetime(2026, 7, 1, 23, 0, tzinfo=UTC)
    pairs = [("1", "2"), ("3", "4"), ("1", "3"), ("2", "4"), ("1", "4"), ("2", "3")]
    for k in range(12):                                     # 12 history games per pair-set
        home, away = pairs[k % 6] if k % 2 == 0 else pairs[k % 6][::-1]
        gid += 1
        margin = quality[home] - quality[away] + HOME_EDGE_POINTS + ((k * 7) % 5 - 2)
        for team, sign in ((home, 1), (away, -1)):
            for j, m in enumerate(mins):
                logs.append({"espn_game_id": f"h{gid}", "game_date": day + dt.timedelta(days=2 * k), "season": 2026,
                             "season_type": 2, "team_id": team, "athlete_id": f"{team}p{j}",
                             "minutes": m, "plus_minus": round(sign * margin * m / 40), "did_not_play": False})
    injuries = [{"athlete_id": "1p0", "captured_at": dt.datetime(2026, 8, 9, 12, tzinfo=UTC), "status": INJURY_OUT}]
    tip0 = dt.datetime(2026, 8, 10, 23, 0, tzinfo=UTC)
    spec = [  # (first, second, first_is_home, bid, ask, coef, first_score, second_score, season_type)
        ("2", "1", False, 0.38, 0.40, fees.POLYMARKET_TAKER, 78, 84, 2),
        ("3", "4", True, 0.60, 0.62, OTHER_PERIOD_COEF, 88, 80, 2),      # first team at HOME (the early-May case)
        ("4", "1", False, 0.20, 0.22, fees.POLYMARKET_TAKER, 70, 92, 2),
        ("1", "3", False, 0.66, 0.68, fees.POLYMARKET_TAKER, 81, 79, 2),
        ("2", "3", False, 0.52, 0.54, fees.POLYMARKET_TAKER, 75, 77, 3),   # playoffs
        ("4", "2", False, 0.30, 0.33, OTHER_PERIOD_COEF, 69, 90, 3),       # playoffs
    ]
    games = []
    for i, (f, s, fh, bid, ask, coef, fs, ss, st) in enumerate(spec):
        games.append({"espn_game_id": f"e{i}", "market_slug": f"aec-wnba-t{f}-t{s}-2026-08-{10 + i:02d}",
                      "tip": tip0 + dt.timedelta(days=i), "first_team_id": f, "second_team_id": s,
                      "first_is_home": fh, "season": 2026, "season_type": st, "bid": bid, "ask": ask,
                      "fee_coefficient": coef, "y": 1 if fs > ss else 0, "first_score": fs, "second_score": ss})
    return games, logs, injuries


# ----------------------------------------------------------------- database (read-only)
QUOTES_SQL = """
WITH g AS (
  SELECT market_slug, min(game_start_time) ko FROM market_snapshots
  WHERE market_slug LIKE :pat AND sports_market_type = :mtype AND game_start_time IS NOT NULL
    AND captured_at > :since GROUP BY 1)
SELECT DISTINCT ON (s.market_slug) s.market_slug, g.ko,
       s.best_bid::float bid, s.best_ask::float ask, s.fee_coefficient, s.captured_at
FROM market_snapshots s JOIN g ON g.market_slug = s.market_slug
WHERE s.captured_at > :since AND s.captured_at <= now()
  AND s.captured_at >= g.ko - CAST(:window_s AS interval) AND s.captured_at <= g.ko - CAST(:offset_s AS interval)
  AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL AND s.fee_coefficient IS NOT NULL
  AND g.ko < now() - interval '4 hours'
ORDER BY s.market_slug, s.captured_at DESC
"""
COUNTS_SQL = """
SELECT count(DISTINCT market_slug) markets,
       count(*) FILTER (WHERE captured_at > now()) future_stamped_rows
FROM market_snapshots WHERE market_slug LIKE :pat AND sports_market_type = :mtype AND captured_at > :since
"""
TEAM_SQL = """
SELECT espn_game_id, game_date, season, season_type, team_id, team_abbrev, opponent_id, opponent_abbrev,
       points_scored, points_allowed, is_completed
FROM team_game_logs WHERE is_home AND season >= :season_lo
"""
PLAYER_SQL = """
SELECT espn_game_id, game_date, season, season_type, team_id, athlete_id, minutes, plus_minus, did_not_play
FROM player_game_logs WHERE season >= :season_lo
"""
INJURY_SQL = "SELECT athlete_id, captured_at, status FROM injury_reports ORDER BY captured_at"


def load_from_db(engine, *, days, settlement_mode, season_lo):
    """(games, logs, injuries, counts). Every exclusion is counted, none is silent."""
    from sqlalchemy import text
    from core.team_mapping import parse_market_slug
    since = dt.datetime.now(UTC) - dt.timedelta(days=days)
    binds = {"pat": SLUG_PREFIX + "%", "mtype": WINNER_TYPE, "since": since,
             "window_s": f"{QUOTE_WINDOW_SECONDS} seconds", "offset_s": f"{PREDICTION_OFFSET_SECONDS} seconds"}
    with engine.connect() as c:
        tape = dict(c.execute(text(COUNTS_SQL), binds).mappings().one())
        quotes = [dict(r) for r in c.execute(text(QUOTES_SQL), binds).mappings()]
        home_rows = [dict(r) for r in c.execute(text(TEAM_SQL), {"season_lo": season_lo}).mappings()]
        logs = [dict(r) for r in c.execute(text(PLAYER_SQL), {"season_lo": season_lo}).mappings()]
        injuries = [dict(r) for r in c.execute(text(INJURY_SQL)).mappings()]
    counts = {"winner markets on tape (last %d days)" % days: tape["markets"],
              "future-stamped rows excluded": tape["future_stamped_rows"],
              "markets with a quote in [tip-6h, tip-1h]": len(quotes),
              "team_game_logs home rows (season >= %d)" % season_lo: len(home_rows),
              "player_game_logs rows": len(logs), "injury_reports rows": len(injuries)}
    reasons = defaultdict(int)
    matched = {}
    for q in quotes:
        parsed = parse_market_slug(q["market_slug"])
        if parsed is None:
            reasons["unparseable slug"] += 1; continue
        row, why = match_slug(parsed, home_rows)
        if row is None:
            reasons[why] += 1; continue
        f, s, fh = orient(parsed, row)
        gid = row["espn_game_id"]
        if gid in matched:
            reasons["duplicate slug for one game (latest quote kept)"] += 1
            if q["captured_at"] <= matched[gid]["captured_at"]:
                continue
        hs, as_ = row["points_scored"], row["points_allowed"]
        fs, ss = (hs, as_) if fh else (as_, hs)
        matched[gid] = {"espn_game_id": gid, "market_slug": q["market_slug"], "tip": q["ko"],
                        "first_team_id": f, "second_team_id": s, "first_is_home": fh,
                        "season": row["season"], "season_type": row["season_type"],
                        "bid": q["bid"], "ask": q["ask"], "fee_coefficient": q["fee_coefficient"],
                        "captured_at": q["captured_at"], "first_score": fs, "second_score": ss,
                        "espn_y": (1 if fs > ss else 0) if (fs is not None and ss is not None and row["is_completed"]) else None}
    for k, v in reasons.items():
        counts[k] = v
    counts["games matched to one ESPN game"] = len(matched)
    games = []
    if settlement_mode == "venue":
        from core import settlements
        from core.polymarket.client import PolymarketGatewayClient
        cache = settlements.load(); settle = settlements.settler(PolymarketGatewayClient(), cache)
        unsettled = disagree = 0
        for g in matched.values():
            y = settle(g["market_slug"])
            if y not in (0, 1):
                unsettled += 1; continue
            if g["espn_y"] is not None and g["espn_y"] != y:
                disagree += 1
            games.append({**g, "y": y})
        settlements.save(cache)
        counts["venue-unsettled (excluded)"] = unsettled
        counts["venue vs ESPN final disagree"] = disagree
    else:
        no_final = 0
        for g in matched.values():
            if g["espn_y"] is None:
                no_final += 1; continue
            games.append({**g, "y": g["espn_y"]})
        counts["no ESPN final (excluded)"] = no_final
    counts["games with a settlement (the sample)"] = len(games)
    return games, logs, injuries, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="run the whole pipeline on the fixture dataset, no database")
    ap.add_argument("--settlement", choices=("venue", "espn"), default="venue",
                    help="venue: the paper book's route (primary); espn: ESPN finals, every line labelled espn-settled")
    ap.add_argument("--days", type=int, default=90, help="snapshot window; the WNBA tape starts 2026-07-31")
    ap.add_argument("--season-lo", type=int, default=2024, help="first season of logs to load (player logs start 2024)")
    ap.add_argument("--draws", type=int, default=MC_DRAWS)
    a = ap.parse_args()
    print(f"registered: docs/math/wnba-player-model-preregistration.md   constants: K={RATING_SHRINK_MINUTES} N={RECENT_TEAM_GAMES} "
          f"home={HOME_EDGE_POINTS} sigma0={SIGMA_PRIOR_POINTS}/{SIGMA_PRIOR_GAMES} threshold={EDGE_THRESHOLD} floor={POWER_FLOOR_GAMES}")
    if a.dry_run:
        games, logs, injuries = fixture_dataset()
        counts = {"FIXTURE dataset": f"{len(games)} priced games, {len(logs)} player rows, {len(injuries)} injury rows"}
        label = "FIXTURE (synthetic scores; nothing here is a measurement)"
    else:
        from sqlalchemy import create_engine, event
        eng = create_engine(os.environ["DATABASE_URL"])

        @event.listens_for(eng, "connect")
        def _np(dbapi_conn, _rec):
            cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); dbapi_conn.commit()
        games, logs, injuries, counts = load_from_db(eng, days=a.days, settlement_mode=a.settlement, season_lo=a.season_lo)
        label = "venue endpoint via core.settlements (primary)" if a.settlement == "venue" else "espn-settled (ESPN finals; NOT the primary)"
    rows, skipped = evaluate(games, logs, injuries, draws=a.draws)
    report(rows, skipped, counts, label)


if __name__ == "__main__":
    main()
