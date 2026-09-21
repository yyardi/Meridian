"""Pregame ladder calibration: is any rung of the venue's football ladders soft?

LADDER STUDY, football and MLB only. Cricket and table tennis have ONE market per
event with no line, so there is no ladder to calibrate -- not a routing gap.

The well-known test, run broadly and model-free. For every full-game spread,
total, team-total and winner market on a settled CFB/NFL game: the LAST quote
before kickoff (kickoff = the first ESPN play's wall clock when we have plays,
else the venue's game_start_time, and the two are compared where both exist),
settled from ESPN finals under the venue's frames:

    winner      YES = the slug's first team (away) wins
    spread      YES = (away - home) + line > 0          (196/196 in the tape)
    total       YES = home + away > line
    team total  YES = that team's points > line         (tt-<team> names the side)

Frames are cross-checked against the venue's own settlement endpoint on a sample
by the caller (public, unauthenticated) -- a derived settlement is a claim.

Reported per market type x pregame-mid bucket: n markets, G games, the
calibration gap E[settle - mid] in cents with a game-clustered 95% interval,
and the TAKER P&L of buying YES at the ask and of buying NO at 1-bid, each net
of the taker fee c*p*(1-p) at the coefficient recorded on that close's own row
(the venue raised c on 2026-09-17; a close from before then is charged what it
was charged, never today's). Both sides are printed for every bucket; nothing is
selected on the outcome. EXPLORATORY: nothing here is pre-registered. A bucket
whose taker P&L is positive, excludes zero, G >= 25, and clears fee + half
spread is a HYPOTHESIS for the next weekend's games, which are held out.

    ssh ubuntu@$H "$D meridian-trainer python3 -" < cfb/run_ladder_calibration.py
"""
import datetime as dt
import os
import sys
from collections import defaultdict

from sqlalchemy import create_engine, event, text
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # run bare: the trainer image mounts cfb/ alone
from core.fees import recorded_fee  # noqa: E402  the row's own coefficient; None raises (core/fees.py)

TYPES = ("football_team_full_game_winner", "football_team_full_game_spread",
         "football_team_full_game_total", "football_team_points_full_game_total")
SHORT = {"football_team_full_game_winner": "winner", "football_team_full_game_spread": "spread",
         "football_team_full_game_total": "total", "football_team_points_full_game_total": "team_tot"}

# --------------------------------------------------------------------------- #
# MLB. Settlement comes from the VENUE's own endpoint, not from a scoreboard,
# so this league needs no game map, no ESPN feed and no derived frame -- which
# is why it can run from day one on nothing but the price tape.
#
# Spreads are only +-1.5 / +-2.5 (the run line), so the useful rung dimension
# is the SIGN, not the distance: YES is always the away team on this venue, so
#
#     neg  ->  away is giving points   -> away FAVOURITE  (home is the dog)
#     pos  ->  away is getting points  -> away UNDERDOG   (home is the fav)
#
# That sign is the home/away split. Pooling a rung with its opposite-sign twin
# is how a bucket produces a spurious "excludes zero": the two halves of one
# game sit on opposite sides of the same mispricing and cancel, or one drags
# the pooled mean. Totals have no twin (YES = over, one market per line), and
# a winner market is one row per game, so the split is reported only where it
# exists and is named "-" where it does not.
# --------------------------------------------------------------------------- #
MLB_TYPES = ("baseball_team_full_game_winner", "baseball_team_full_game_spread",
             "baseball_team_full_game_total", "baseball_team_first_five_spread",
             "baseball_team_first_five_total")
MLB_SHORT = {"baseball_team_full_game_winner": "winner",
             "baseball_team_full_game_spread": "spread",
             "baseball_team_full_game_total": "total",
             "baseball_team_first_five_spread": "f5_spread",
             "baseball_team_first_five_total": "f5_total"}


def away_side(market_slug, mtype):
    """Which half of the home/away pair this rung is. '-' where there is no twin.

    Read off the slug, never off the price: `asc-mlb-col-det-2026-09-13-pos-1pt5`
    is the away team +1.5. A price-based guess would be circular in a
    calibration study, which is the whole point of this file.
    """
    if "spread" not in mtype:
        return "-"
    toks = market_slug.split("-")
    if "neg" in toks:
        return "away_fav"
    if "pos" in toks:
        return "away_dog"
    return "-"


def _engine():
    eng = create_engine(os.environ["DATABASE_URL"])
    @event.listens_for(eng, "connect")
    def _np(dbapi_conn, _rec):
        cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); dbapi_conn.commit()
    return eng

# Settled games with a venue id: finals from backfill (CFB) or the live
# game_state table (CFB live-only + NFL); kickoff from the first play if any.
#
# `period >= 4` WAS THROWING AWAY THE FINAL. ESPN drops `period` on the final
# row: of 107 CFB games observed at `post`, 101 carry period NULL, and 9 of 10
# NFL. So `WHERE period >= 4` excluded the post row for ~94% of games that had
# one, and DISTINCT ON then took the last IN-GAME row instead — a pre-whistle
# score for a game whose true final was sitting in the same table. Measured
# 2026-09-14 on the games reaching this query by the live route: 89 CFB and 8
# NFL games had reached `post` and were being read from an `in` row anyway.
#
# A pre-whistle score is too LOW, which settles a total UNDER when the real
# total may have cleared, and `cfb_total_under_all` is a registered strategy
# this flatters. So the ordering now PREFERS `state = 'post'` and, among post
# rows, takes the LAST — the rule on CfbGameState's own docstring — and falls
# back to a period>=4 row only when no post row exists.
#
# `src` says which route each final came from so the caller can count them.
# Whether an unconfirmed game should be settled from the proxy AT ALL is a
# strategy decision and is NOT taken here; `collect_mlb` in this same file
# already skips-and-counts rather than guessing, which is the precedent.
#: The live-table final, extracted so it can be TESTED. GAMES_SQL as a whole
#: cannot be: it reads `espn_cfb_backfill_games`, which has no Alembic
#: migration and no model — it is created by `archive/cfb/backfill_cfb.py`
#: and exists only where that was run, so a migrated schema does not have it.
LIVE_FINALS_SQL = """
  SELECT DISTINCT ON (game_id) game_id eg, home_score h, away_score a, league lg,
         CASE WHEN state = 'post' THEN 'post' ELSE 'proxy' END src
  FROM espn_cfb_game_state WHERE home_score IS NOT NULL AND league IN ('cfb','nfl')
    AND (state = 'post' OR period >= 4)
  ORDER BY game_id, (state = 'post') DESC, first_seen_at DESC
"""

GAMES_SQL = """
WITH bf AS (
  SELECT g.game_id eg, g.home_score h, g.away_score a, 'cfb' lg, 'backfill' src
  FROM espn_cfb_backfill_games g WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL),
lv AS (""" + LIVE_FINALS_SQL + """),
-- PRECEDENCE: a CONFIRMED post row beats the backfill (decision 2026-09-14).
-- The two sources overlap on 11 games and disagree on 1 total and 0 winners.
-- Game 401856660 holds 31-3 (total 34) in the backfill against 51-10 (61) in
-- the post row, and truncation settles which is wrong: a game cut short
-- cannot score MORE than its final, and the higher number here is the POST
-- row rather than an in-game one, so the backfill is low by 27 points. The
-- error direction matters as much as the fix -- a low total settles a totals
-- market UNDER, and `cfb_total_under_all` is registered.
-- `lv` is DISTINCT ON (game_id), so it holds exactly one row per game and
-- these three arms are disjoint by construction.
fin AS (
  SELECT * FROM lv WHERE src = 'post'
  UNION ALL
  SELECT * FROM bf WHERE eg NOT IN (SELECT eg FROM lv WHERE src = 'post')
  UNION ALL
  SELECT * FROM lv WHERE src = 'proxy' AND eg NOT IN (SELECT eg FROM bf)),
ko AS (
  SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_backfill_plays WHERE wall_clock IS NOT NULL GROUP BY 1
  UNION ALL
  SELECT game_id, min(wall_clock) FROM espn_cfb_live_plays WHERE wall_clock IS NOT NULL
    AND game_id NOT IN (SELECT game_id FROM espn_cfb_backfill_plays WHERE wall_clock IS NOT NULL) GROUP BY 1)
-- LEFT JOIN, not JOIN. A mapped game with NO score source at all -- no post
-- row, no backfill row, not even a proxy -- used to vanish from the result
-- entirely, so the printed route mix summed to LESS than the mapped games and
-- nothing said so. One game today (401872931, nfl-den-kc-2026-09-14, zero
-- state rows: it has not been played yet). Harmless now, silent always.
-- `usable_games` drops 'none' along with 'proxy'.
SELECT m.venue_game_id vg, m.espn_game_id eg, m.event_slug, f.h, f.a,
       coalesce(f.lg, 'unknown') lg, coalesce(f.src, 'none') src, k.ko
FROM cfb_game_map m LEFT JOIN fin f ON f.eg = m.espn_game_id
LEFT JOIN ko k ON k.eg = m.espn_game_id
WHERE m.venue_game_id IS NOT NULL
"""

# Last pregame quote per market for ONE game (bounded window, DISTINCT ON).
CLOSE_SQL = """
SELECT DISTINCT ON (market_slug) market_slug, sports_market_type, line::float line,
       best_bid::float bid, best_ask::float ask, fee_coefficient::float fee_coefficient,
       captured_at, game_start_time
FROM market_snapshots
WHERE game_id = :vg AND captured_at BETWEEN :lo AND :ko
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND sports_market_type = ANY(:types)
ORDER BY market_slug, captured_at DESC
"""
START_SQL = """
SELECT min(game_start_time) FROM market_snapshots
WHERE game_id = :vg AND captured_at > now() - interval '60 days' AND game_start_time IS NOT NULL
"""

def settle(slug, mtype, line, h, a):
    """Derived settlement under the venue's frames; None = push / undecidable."""
    if mtype == "football_team_full_game_winner":
        return None if a == h else int(a > h)
    if line is None:
        return None
    if mtype == "football_team_full_game_spread":
        v = (a - h) + line
        return None if abs(v) < 1e-9 else int(v > 0)
    if mtype == "football_team_full_game_total":
        v = (h + a) - line
        return None if abs(v) < 1e-9 else int(v > 0)
    if mtype == "football_team_points_full_game_total":
        toks = slug.split("-")
        try:
            i = toks.index("tt")
        except ValueError:
            return None
        team = toks[i + 1]
        pts = a if team == toks[2] else (h if team == toks[3] else None)
        if pts is None:
            return None
        v = pts - line
        return None if abs(v) < 1e-9 else int(v > 0)
    return None


def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


def bucket(mid):
    return min(int(mid * 10), 9)


def taker_net(r):
    """(buy YES at the ask, buy NO at 1-bid) P&L in cents, net of the fee AT THIS ROW's coefficient.

    `r["fee_coefficient"]` is market_snapshots.fee_coefficient on the close's own row. The
    venue raised it on 2026-09-17, so a close from before then is charged what it was
    charged; a row without the column is a KeyError and a NULL a ValueError, never
    today's constant. 1-bid pays the same fee as the bid: p(1-p) is symmetric.
    """
    fy = recorded_fee(r["ask"], r["fee_coefficient"])
    fn = recorded_fee(r["bid"], r["fee_coefficient"])
    return 100 * (r["y"] - r["ask"] - fy), 100 * ((1 - r["y"]) - (1 - r["bid"]) - fn)

def report(title, sel, key=lambda r: bucket((r["bid"] + r["ask"]) / 2), labels=None):
    print(f"\n=== {title} ===")
    print(f"  {'bucket':<10}{'n':>6}{'G':>5}{'G_eff':>7}   {'gap E[y-mid] c':>16}{'95% CI':>18}   "
          f"{'buy YES @ask net':>17}{'95% CI':>18}   {'buy NO @1-bid net':>18}{'95% CI':>18}   {'half-sprd':>9}")
    groups = defaultdict(list)
    for r in sel: groups[key(r)].append(r)
    for k in sorted(groups):
        rs = groups[k]
        if len(rs) < 20:
            print(f"  {str(labels[k] if labels else k):<10}{len(rs):>6}   too few"); continue
        keys = [r["vg"] for r in rs]
        gap, gh, n, G, ge = clustered([100 * (r["y"] - (r["bid"] + r["ask"]) / 2) for r in rs], keys)
        nets = [taker_net(r) for r in rs]
        by, byh, *_ = clustered([x[0] for x in nets], keys)
        bn, bnh, *_ = clustered([x[1] for x in nets], keys)
        hs = 100 * sum((r["ask"] - r["bid"]) / 2 for r in rs) / n
        lab = str(labels[k] if labels else k)
        flag = ""
        if G >= 25 and ((by - byh > 0) or (bn - bnh > 0)):
            flag = "  <- positive taker side, excludes 0: HYPOTHESIS for the held-out weekend"
        print(f"  {lab:<10}{n:>6}{G:>5}{ge:>7.1f}   {gap:>+16.2f}{'[%+.2f, %+.2f]' % (gap-gh, gap+gh):>18}   "
              f"{by:>+17.2f}{'[%+.2f, %+.2f]' % (by-byh, by+byh):>18}   "
              f"{bn:>+18.2f}{'[%+.2f, %+.2f]' % (bn-bnh, bn+bnh):>18}   {hs:>9.2f}{flag}")

BL = {i: f"{i/10:.1f}-{(i+1)/10:.1f}" for i in range(10)}


# `market_snapshots` has NO league column -- the league lives in the slug, and
# `run_paper_book` filters the same way (`market_slug LIKE '%-mlb-%'`). Writing
# `WHERE league = 'mlb'` here would have been a SQL error on the first prod run.
MLB_GAMES_SQL = """
SELECT game_id vg, min(game_start_time) ko, min(event_slug) event_slug
FROM market_snapshots
WHERE market_slug LIKE :pat AND game_start_time IS NOT NULL
  AND game_start_time < now() - interval '4 hours'
  AND game_start_time > now() - (:days || ' days')::interval
GROUP BY 1
"""
MLB_CLOSE_SQL = """
SELECT DISTINCT ON (market_slug) market_slug, sports_market_type, line::float line,
       best_bid::float bid, best_ask::float ask, fee_coefficient::float fee_coefficient,
       captured_at, game_start_time
FROM market_snapshots
WHERE game_id = :vg AND captured_at BETWEEN :lo AND :ko
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND sports_market_type = ANY(:types)
ORDER BY market_slug, captured_at DESC
"""


def collect_mlb(c, settlement, days=30):
    """Rows for MLB: last pregame quote per market, settled BY THE VENUE.

    `settlement(slug) -> 0|1|None` is injected so this is testable without a
    network, and so the caller owns the caching. A market the venue has not
    settled is skipped and counted -- never guessed, and never derived from a
    box score, because no scoreboard join exists for this league yet.
    """
    from sqlalchemy import text
    games = [dict(r._mapping) for r in
             c.execute(text(MLB_GAMES_SQL), {"days": str(days), "pat": "%-mlb-%"})]
    rows, unsettled, no_quote = [], 0, 0
    for g in games:
        q = c.execute(text(MLB_CLOSE_SQL),
                      {"vg": g["vg"], "lo": g["ko"] - dt.timedelta(days=3), "ko": g["ko"],
                       "types": list(MLB_TYPES)})
        got = 0
        for r in q:
            r = dict(r._mapping)
            got += 1
            y = settlement(r["market_slug"])
            if y is None:
                unsettled += 1
                continue
            r.update(vg=g["vg"], lg="mlb", y=y, event_slug=g["event_slug"],
                     ttk_min=(g["ko"] - r["captured_at"]).total_seconds() / 60,
                     side=away_side(r["market_slug"], r["sports_market_type"]))
            rows.append(r)
        if not got:
            no_quote += 1
    return rows, games, unsettled, no_quote


def main_mlb():
    from core import settlements
    from core.polymarket.client import PolymarketGatewayClient

    cache = settlements.load(); hits = len(cache)
    settlement = settlements.settler(PolymarketGatewayClient(), cache)
    days = int(os.environ.get("DAYS", "30"))
    with _engine().connect() as c:
        rows, games, unsettled, no_quote = collect_mlb(c, settlement, days)
    fetched = len(cache) - hits
    settlements.save(cache)
    print(f"MLB games with a venue start time in the last {days}d: {len(games)}  "
          f"(no pregame quote for {no_quote})")
    print(f"settlement: {hits:,} reused from cache, {fetched:,} fetched, "
          f"{unsettled:,} market-rows unsettled and skipped")
    print(f"markets with a pregame close and a VENUE settlement: {len(rows):,}")
    if not rows:
        print("\nNOTHING TO REPORT. The recorder overlay may not be on tape yet; this is an")
        print("empty run, not a null result -- no bucket was measured.")
        return
    close = [r for r in rows if r["ttk_min"] <= 360]
    print(f"\nPRIMARY population: last quote within 6h of first pitch: {len(close):,} markets")
    for t in MLB_TYPES:
        sel = [r for r in close if r["sports_market_type"] == t]
        report(f"{MLB_SHORT[t]} -- by pregame mid, close within 6h", sel, labels=BL)
    # the home/away split, which is the sign of the run line: see away_side()
    for t in ("baseball_team_full_game_spread", "baseball_team_first_five_spread"):
        for sd in ("away_fav", "away_dog"):
            sel = [r for r in close if r["sports_market_type"] == t and r["side"] == sd]
            report(f"{MLB_SHORT[t]} {sd} -- by pregame mid", sel, labels=BL)
    print("\n=== WHAT THIS CANNOT SAY ===")
    print("  Exploratory, no pre-registration. Settlement is the VENUE's own label, so there is no")
    print("  derived frame to be wrong about -- but a bucket is still one of many looks, and a rung")
    print("  pooled with its opposite-sign twin can show an edge that the pair does not have.")
    print("  Read away_fav and away_dog beside each other before believing either.")
    print("\n### CSV")
    print("lg,vg,event_slug,type,slug,line,side,bid,ask,ttk_min,y")
    for r in rows:
        print(f"{r['lg']},{r['vg']},{r['event_slug']},{MLB_SHORT[r['sports_market_type']]},"
              f"{r['market_slug']},{'' if r['line'] is None else r['line']},{r['side']},"
              f"{r['bid']},{r['ask']},{r['ttk_min']:.0f},{r['y']}")


#: Routes whose final is CONFIRMED. An allowlist rather than a blocklist, on
#: purpose: a route nobody has vetted should cost a smaller sample (visible in
#: the excluded count) rather than a biased one (invisible). 'none' — a mapped
#: game with no score source at all — is exactly the category that fell
#: through when this was `!= "proxy"`.
CONFIRMED_ROUTES = ("post", "backfill")


def usable_games(games: list[dict]) -> tuple[list[dict], int]:
    """EXCLUDE AND COUNT, never settle from a proxy (decision 2026-09-14).

    A 'proxy' final is the last in-game row of a game that never reached
    `state = 'post'`. It is a LOWER BOUND on the total, so settling from it
    puts a totals market UNDER more often than the truth, and
    `cfb_total_under_all` is registered. An excluded game is a smaller
    sample; a wrongly settled one is a biased sample.

    `collect_mlb` in this same file has done exactly this since it was
    written — it counts `unsettled` and skips, "never guessed, and never
    derived from a box score". CFB was the inconsistent one, which is why
    this is a consistency fix rather than a new policy.

    Why exclusion rather than repair: on the eight unconfirmed games where a
    backfill final also exists the proxy was exact 8 times out of 8 — but
    eight is the WHOLE overlap population and not a sample of it (the
    backfill is 55 games imported on one day against a live tape spanning
    ten), so it cannot be extrapolated to the games being dropped.

    Returns (kept, excluded_count). The count is half the policy: a game
    dropped silently turns a shrinking sample into an invisible one.
    """
    kept = [g for g in games if g.get("src") in CONFIRMED_ROUTES]
    return kept, len(games) - len(kept)


def main_football():
    eng = _engine()
    with eng.connect() as c:
        all_games = [dict(r._mapping) for r in c.execute(text(GAMES_SQL))]
        games, unsettled = usable_games(all_games)
        rows, ko_gap, no_ko, no_start = [], [], 0, 0
        for g in games:
            start = c.execute(text(START_SQL), {"vg": g["vg"]}).scalar()
            ko = g["ko"]
            if ko is not None and start is not None:
                ko_gap.append(abs((ko - start).total_seconds()) / 60)
            if ko is None:
                if start is None:
                    no_start += 1; continue
                no_ko += 1; ko = start
            q = c.execute(text(CLOSE_SQL), {"vg": g["vg"], "lo": ko - dt.timedelta(days=3), "ko": ko,
                                            "types": list(TYPES)})
            for r in q:
                r = dict(r._mapping)
                y = settle(r["market_slug"], r["sports_market_type"], r["line"], g["h"], g["a"])
                if y is None:
                    continue
                r.update(vg=g["vg"], lg=g["lg"], y=y, ttk_min=(ko - r["captured_at"]).total_seconds() / 60,
                         event_slug=g["event_slug"], final_src=g["src"])
                rows.append(r)

    # `unsettled` games never reach the kickoff logic, so they have to come
    # out of the denominator too — an exclusion that moves a total and not the
    # arithmetic that reports it is how a summary line starts lying.
    kept = len(games)
    print(f"settled mapped games {kept} of {len(all_games)}  "
          f"(kickoff from plays for {kept - no_ko - no_start}, "
          f"from venue start time for {no_ko}, neither {no_start})")
    if ko_gap:
        ko_gap.sort()
        print(f"ESPN first play vs venue game_start_time, minutes: median {ko_gap[len(ko_gap)//2]:.0f}  "
              f"p90 {ko_gap[int(len(ko_gap)*0.9)]:.0f}  max {ko_gap[-1]:.0f}")
    # WHERE EACH FINAL CAME FROM, and what was dropped. 'proxy' finals are
    # EXCLUDED, not settled: a pre-whistle total is a lower bound, so settling
    # from one biases a totals market toward UNDER. Counted here so the loss
    # is visible -- an exclusion nobody can see is how a shrinking sample
    # becomes a silent one.
    # Keyed on the ESPN id, which is the map's identity and the join key to
    # the finals -- not on venue_game_id. Both are unique across the 139
    # mapped games today, and keying on a uniqueness nobody enforces is how a
    # reconciliation line starts disagreeing with itself.
    src_games = defaultdict(set)
    for g in all_games: src_games[g["src"]].add(g["eg"])
    accounted = sum(len(v) for v in src_games.values())
    print("  finals by route: " + "  ".join(
        f"{k} {len(v)}" for k, v in sorted(src_games.items()))
        + f"   (accounted {accounted} of {len(all_games)} mapped games)")
    # LOUD, not fatal. A daily run should say the mix does not reconcile, not
    # die on it -- and it can only fail if two mapped rows share an ESPN id.
    if accounted != len(all_games):
        print(f"  ROUTE MIX DOES NOT RECONCILE: {len(all_games) - accounted} "
              "mapped games unaccounted for -- duplicate espn_game_id in "
              "cfb_game_map?")
    print(f"  EXCLUDED, no confirmed final: {unsettled} games"
          + ("   never settled from a proxy" if unsettled else ""))
    print(f"markets with a pregame close and a derived settlement: {len(rows):,}")
    src_rows = defaultdict(int)
    for r in rows: src_rows[r["final_src"]] += 1
    print("  markets by route: " + "  ".join(
        f"{k} {v:,}" for k, v in sorted(src_rows.items())))
    by_lg = defaultdict(set)
    for r in rows: by_lg[r["lg"]].add(r["vg"])
    print("  games by league: " + "  ".join(f"{k} {len(v)}" for k, v in sorted(by_lg.items())))

    close = [r for r in rows if r["ttk_min"] <= 360]
    print(f"\nPRIMARY population: last quote within 6h of kickoff: {len(close):,} markets "
          f"(all pregame quotes within 3 days: {len(rows):,})")
    for t in TYPES:
        sel = [r for r in close if r["sports_market_type"] == t]
        report(f"{SHORT[t]} -- by pregame mid, close within 6h of kickoff", sel, labels=BL)
    # distance from the line for spreads (rung far from the market's own centre = the venue's 'longshots')
    sp = [r for r in close if r["sports_market_type"] == "football_team_full_game_spread"]
    centre = defaultdict(list)
    for r in sp: centre[r["vg"]].append(r)
    def dist_key(r):
        rs = centre[r["vg"]]
        # the rung whose mid is nearest 0.5 is the market's centre; distance in points
        c0 = min(rs, key=lambda x: abs((x["bid"] + x["ask"]) / 2 - 0.5))
        d = abs(r["line"] - c0["line"])
        return 0 if d < 3.5 else 1 if d < 7.5 else 2 if d < 14.5 else 3
    report("spread -- by distance from the centre rung (points)", sp, key=dist_key,
           labels={0: "<3.5", 1: "3.5-7", 2: "7.5-14", 3: ">14"})
    for lg in ("cfb", "nfl"):
        sel = [r for r in close if r["lg"] == lg and r["sports_market_type"] == "football_team_full_game_spread"]
        report(f"spread, {lg} only -- by pregame mid", sel, labels=BL)

    print("\n=== WHAT THIS CANNOT SAY ===")
    print("  Exploratory, no pre-registration; every bucket is one of ~40 looks. A flagged bucket is a")
    print("  hypothesis to write down BEFORE Saturday's 44 CFB / Sunday's 12 NFL closes, then read there.")
    print("  Settlement is DERIVED from ESPN finals under the venue's frames; the caller spot-checks it")
    print("  against the venue's settlement endpoint before any number travels.")
    print("\n### CSV")
    print("lg,vg,event_slug,type,slug,line,bid,ask,ttk_min,y")
    for r in rows:
        print(f"{r['lg']},{r['vg']},{r['event_slug']},{SHORT[r['sports_market_type']]},{r['market_slug']},"
              f"{'' if r['line'] is None else r['line']},{r['bid']},{r['ask']},{r['ttk_min']:.0f},{r['y']}")


def main():
    lg = os.environ.get("LEAGUE", "cfb").lower()
    if lg == "mlb":
        return main_mlb()
    if lg in ("cfb", "nfl", "both", "football"):
        return main_football()
    raise SystemExit(f"LEAGUE={lg!r} is not one of: cfb (default, CFB+NFL) | mlb")


if __name__ == "__main__":
    main()
