"""E5 — ladder relative value. Long-K / short-(K+7) pairs, held to settlement.

WHY THIS AND NOT THE MONEYLINE. A pair across two rungs pays on the SHAPE of
the margin distribution -- whether the final margin lands inside (K, K+7) --
not on its direction. That is the one thing the winner market cannot express
and the one place the moneyline's adverse-selection mechanism does not reach:
a fill on the pair is not "the market moving against the side we are about to
hold", because the pair has no side.

PRE-REGISTERED BEFORE THE FIRST RUN. Written here, then run once.
  pairs        (K, K+7), K on the half-point grid, both rungs within +-14 of
               the expected margin (-spread) so we trade where the book is.
  instant      play wall_clock + 30s (feed lag). First snapshot of EACH rung at
               or after that, within 5 min; older is STALE: excluded, counted.
  entry        TAKER at the touch on both legs. Fee 0.06*p*(1-p) per leg.
               No maker rebate (findings.md C7). This is the conservative cost;
               a maker could only do better, so a loss here is a real loss.
  direction    long the interval when model_interval - market_cost > TAU;
               short when market_receipt - model_interval > TAU.
  TAU          0.05 PRIMARY. 0.03 and 0.08 reported as sensitivity, secondary.
  leg filter   either leg's spread > 6c -> skip (untradeable), counted.
  one shot     ONE position per (game, pair): the first qualifying instant,
               held to settlement. Otherwise every play re-enters the same
               bet and the cluster count is a lie.
  settlement   from final scores. Never from prices.
  estimator    game-clustered, G and G_eff printed, 25-game floor.
  model        v2 (near-line K), chosen on the 813-game CFBD holdout -- NOT on
               the 2026 tape this is scored on.

FRAME. YES on a spread rung with line L pays iff (first-team margin + L) > 0.
First team on the slug is the AWAY team (verified 196/196 on this venue), so
YES <=> home_margin < L. Long the interval (K, K+7) is therefore
  SELL YES(K) + BUY YES(K+7):  payoff = [home<K+7] - [home<K] = 1 iff K<home<K+7.
The frame is CHECKED, not assumed: at each rung's last live snapshot the price
must sit on the side the outcome says. An inverted frame fails that on nearly
every rung, which is a control that can fire.

DECOMPOSITION, because "loses" has two very different causes:
  mid-to-mid, no fees   does the model disagree with the market USEFULLY at all?
  net of spread + fees  does that survive the cost of expressing it?
If the first is <= 0 the model has nothing the market lacks. If the first is
positive and the second negative, the spread is the killer and the answer is
"maker, not taker" -- which is E6's question, not this one.
"""
import bisect
import datetime as dt
import math
import os
import sys
from collections import defaultdict

import xgboost as xgb
from sqlalchemy import create_engine, text

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, REGULATION_SECONDS, game_seconds_remaining, half_seconds_remaining  # noqa: E402

FEED_LAG = 30
STALE_S = 300
PAIR_W = 7.0
BAND = 14.0
TAU_PRIMARY = 0.05
TAUS = (0.03, 0.05, 0.08)
MAX_LEG_SPREAD = 0.06
TAKER_THETA = 0.06
LEAGUE = os.environ.get("LEAGUE", "cfb")
MODEL = os.environ.get("COVER_MODEL",
                       f"/app/artifacts/{LEAGUE}_cover_regulation.json")   # follows the league
COLS = ["home_margin", "K", "sld", "gsr", "hsr", "exp_margin", "margin_time",
        "exp_margin_time", "home_has_ball", "down", "distance", "ytg", "period"]

booster = xgb.Booster()
booster.load_model(MODEL)
# print WHICH model, from its meta on disk -- the E3 artifact paths got
# crossed once (v2 saved over v1), so identity is read, not assumed.
import json  # noqa: E402
try:
    with open(MODEL.replace(".json", ".meta.json")) as fh:
        _m = json.load(fh)
    print(f"model {MODEL}: k_near_line={_m.get('k_near_line')} "
          f"train_games={_m.get('train_games')} holdout={_m.get('holdout_games')}")
except Exception as e:
    print(f"model {MODEL}: META UNREADABLE ({e}) -- identity unverified")
eng = create_engine(os.environ["DATABASE_URL"])

# The postgres container's /dev/shm is 64MB (Docker default). Parallel workers
# put dynamic shared memory there, and the second-phase queries died with
# "could not resize shared memory segment ... No space left on device" on
# 2026-09-11 once the tape grew. Session-scoped, no config change.
from sqlalchemy import event  # noqa: E402
@event.listens_for(eng, "connect")
def _no_parallel_workers(dbapi_conn, _rec):
    # psycopg3 opens a transaction on the first execute; an uncommitted SET is
    # undone by the pool's first ROLLBACK. Commit it so it is session-wide.
    cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close()
    dbapi_conn.commit()


def featurize(hs, spread_home, K):
    m, gsr, hsr, hb, down, dist, ytg, per = hs
    elapsed = REGULATION_SECONDS - gsr
    E = -spread_home
    return [m, K, m - K, gsr, hsr, E, m * math.exp(4.0 * elapsed / REGULATION_SECONDS),
            E * math.exp(-4.0 * elapsed / REGULATION_SECONDS), hb, down, dist, ytg, per]


def fee(p):
    return TAKER_THETA * p * (1.0 - p)


# ------------------------------------------------------------------ data
with eng.connect() as c:
    games, plays = {}, []
    if LEAGUE == "cfb":                      # backfill exists for CFB only
      games = {r.game_id: dict(r._mapping) for r in c.execute(text(
        "SELECT b.game_id, m.venue_game_id, b.home_score, b.away_score, b.spread::float AS spread "
        "FROM espn_cfb_backfill_games b JOIN cfb_game_map m ON m.espn_game_id = b.game_id "
        "WHERE b.spread IS NOT NULL AND b.home_score IS NOT NULL AND b.away_score IS NOT NULL "
        "AND m.venue_game_id IS NOT NULL"))}
      plays = [dict(r._mapping) for r in c.execute(text(
        "SELECT game_id, play_id, wall_clock, period, clock_minutes, clock_seconds, down, distance, "
        "yards_to_goal, pos_team_score, def_pos_team_score, drive_is_home_offense "
        "FROM espn_cfb_backfill_plays WHERE wall_clock IS NOT NULL AND down IS NOT NULL AND down > 0 "
        "AND period IS NOT NULL AND NOT is_overtime ORDER BY game_id, wall_clock"))]
    # POOL the live tables (Saturday's slate, which backfill never reached).
    # A live game needs a recorded line to price a rung; without one it is
    # counted and skipped. Dedup by game, backfill wins.
    live_games = {r.game_id: dict(r._mapping) for r in c.execute(text(
        "WITH final AS (SELECT DISTINCT ON (game_id) game_id, home_score, away_score "
        "  FROM espn_cfb_game_state WHERE league=:lg AND home_score IS NOT NULL "
        "  ORDER BY game_id, first_seen_at DESC), "
        "line AS (SELECT game_id, avg(live_spread)::float AS spread FROM espn_cfb_game_state "
        "  WHERE league=:lg AND live_spread IS NOT NULL GROUP BY 1) "
        "SELECT f.game_id, m.venue_game_id, f.home_score, f.away_score, l.spread "
        "FROM final f JOIN cfb_game_map m ON m.espn_game_id = f.game_id AND m.venue_game_id IS NOT NULL "
        "JOIN line l ON l.game_id = f.game_id WHERE f.home_score <> f.away_score"), {"lg": LEAGUE})}
    new_g = {g: v for g, v in live_games.items() if g not in games}
    no_line = c.execute(text(
        "SELECT count(DISTINCT p.game_id) FROM espn_cfb_live_plays p JOIN cfb_game_map m ON m.espn_game_id=p.game_id "
        "AND m.venue_game_id IS NOT NULL WHERE p.league=:lg AND p.game_id NOT IN (SELECT game_id FROM "
        "espn_cfb_game_state WHERE league=:lg AND live_spread IS NOT NULL)"), {"lg": LEAGUE}).scalar()
    if new_g:
        lp = [dict(r._mapping) for r in c.execute(text(
            "SELECT game_id, play_id, wall_clock, period, clock_minutes, clock_seconds, down, distance, "
            "yards_to_goal, pos_team_score, def_pos_team_score, drive_is_home_offense "
            "FROM espn_cfb_live_plays WHERE league=:lg AND game_id = ANY(:g) AND wall_clock IS NOT NULL "
            "AND down IS NOT NULL AND down > 0 AND period IS NOT NULL AND NOT is_overtime "
            "ORDER BY game_id, wall_clock"), {"g": list(new_g), "lg": LEAGUE})]
        plays += lp
        games.update(new_g)
    print(f"POOLED: backfill games {len(games) - len(new_g)}  + live-only games with a line {len(new_g)}"
          f"  (live games with NO recorded line, skipped: {no_line})")
    vids = sorted({g["venue_game_id"] for g in games.values()})
    lo = min(p["wall_clock"] for p in plays)
    hi = max(p["wall_clock"] for p in plays) + dt.timedelta(seconds=FEED_LAG + STALE_S + 3600)
    ladder = [dict(r._mapping) for r in c.execute(text(
        "SELECT game_id, line::float AS line, captured_at, best_bid::float AS bid, best_ask::float AS ask, is_live "
        "FROM market_snapshots WHERE game_id = ANY(:g) AND sports_market_type = 'football_team_full_game_spread' "
        "AND best_bid IS NOT NULL AND best_ask IS NOT NULL AND line IS NOT NULL "
        "AND captured_at BETWEEN :lo AND :hi ORDER BY game_id, line, captured_at"),
        {"g": vids, "lo": lo, "hi": hi})]
eng.dispose()
print(f"games {len(games)}   plays {len(plays):,}   ladder snapshots {len(ladder):,}")

# per (venue_game, line): parallel sorted arrays
tape = defaultdict(lambda: ([], []))
last_live = {}
for r in ladder:
    ts, rows = tape[(r["game_id"], r["line"])]
    ts.append(r["captured_at"]); rows.append(r)
    if r["is_live"]:
        last_live[(r["game_id"], r["line"])] = r
v2e = {g["venue_game_id"]: gid for gid, g in games.items()}


def quote_at(vg, line, t):
    """First snapshot at or after t within STALE_S, else None. Returns (row, stale)."""
    ts, rows = tape.get((vg, line), ((), ()))
    i = bisect.bisect_left(ts, t)
    if i >= len(ts):
        return None, True
    if (ts[i] - t).total_seconds() > STALE_S:
        return None, True
    return rows[i], False


# -------------------------------------------------------------- frame guard
# At each rung's last LIVE snapshot, the mid must sit on the side the outcome
# says: YES <=> home_margin < L. Inverted frame -> nearly every rung fails.
agree = disagree = 0
for (vg, L), r in last_live.items():
    gid = v2e.get(vg)
    if gid is None:
        continue
    g = games[gid]
    hm = g["home_score"] - g["away_score"]
    yes_won = hm < L
    mid = (r["bid"] + r["ask"]) / 2
    if abs(mid - 0.5) < 0.15:
        continue                                     # uninformative late price
    if (mid > 0.5) == yes_won:
        agree += 1
    else:
        disagree += 1
print(f"\n=== FRAME GUARD: YES <=> home_margin < line, at last live snapshot ===")
print(f"  agree {agree}   disagree {disagree}   "
      f"{'OK' if agree > 5 * max(disagree, 1) else 'FRAME SUSPECT -- do not read the P&L below'}")
if agree <= 5 * max(disagree, 1):
    sys.exit(1)

# -------------------------------------------------------------- the pairs
def hstate(p):
    st = GameState(period=p["period"], clock_minutes=p["clock_minutes"] or 0,
                   clock_seconds=p["clock_seconds"] or 0, down=p["down"], distance=p["distance"],
                   yards_to_goal=p["yards_to_goal"], pos_team_score=p["pos_team_score"] or 0,
                   def_pos_team_score=p["def_pos_team_score"] or 0,
                   drive_is_home_offense=bool(p["drive_is_home_offense"]),
                   pos_team_timeouts=3, def_pos_team_timeouts=3)
    gsr, hsr = game_seconds_remaining(st), half_seconds_remaining(st)
    if gsr is None or hsr is None:
        return None
    m = st.pos_team_score - st.def_pos_team_score
    if not st.drive_is_home_offense:
        m = -m
    return (m, gsr, hsr, int(bool(st.drive_is_home_offense)), st.down or 0,
            st.distance or 0, st.yards_to_goal or 0, st.period)


taken = {}                        # (gid, K) -> position dict, first qualifying only
stale = wide = nomodel = 0
cands = 0
for p in plays:
    gid = p["game_id"]; g = games.get(gid)
    if not g:
        continue
    hs = hstate(p)
    if hs is None:
        continue
    vg = g["venue_game_id"]; sp = g["spread"]; E = -sp
    t = p["wall_clock"] + dt.timedelta(seconds=FEED_LAG)
    ks = [k + 0.5 for k in range(int(math.floor(E - BAND)), int(math.ceil(E + BAND)))]
    X = [featurize(hs, sp, K) for K in ks] + [featurize(hs, sp, K + PAIR_W) for K in ks]
    pr = booster.predict(xgb.DMatrix(X, feature_names=COLS, missing=float("nan")))
    for i, K in enumerate(ks):
        if all((gid, K, tau) in taken for tau in TAUS):
            continue
        pK, pK7 = float(pr[i]), float(pr[len(ks) + i])
        model_int = pK - pK7
        qa, sa = quote_at(vg, K, t)
        qb, sb = quote_at(vg, K + PAIR_W, t)
        if qa is None or qb is None:
            stale += 1
            continue
        if (qa["ask"] - qa["bid"]) > MAX_LEG_SPREAD or (qb["ask"] - qb["bid"]) > MAX_LEG_SPREAD:
            wide += 1
            continue
        cands += 1
        # long interval: SELL YES(K) at bid_K, BUY YES(K+7) at ask_{K+7}
        cost_long = qb["ask"] - qa["bid"]
        # short interval: BUY YES(K) at ask_K, SELL YES(K+7) at bid_{K+7}
        recv_short = qb["bid"] - qa["ask"]
        mid_int = ((qb["bid"] + qb["ask"]) / 2) - ((qa["bid"] + qa["ask"]) / 2)
        e_long = model_int - cost_long
        e_short = recv_short - model_int
        e_mid = model_int - mid_int                     # sign: + means model says interval is cheap
        hm = g["home_score"] - g["away_score"]
        inside = 1 if (K < hm < K + PAIR_W) else 0
        # each tau is its OWN strategy with its OWN first-qualifying instant.
        # Sharing one entry across taus would let the loosest arm consume the
        # pair before a stricter arm ever saw it qualify.
        for tau in TAUS:
            if (gid, K, tau) in taken:
                continue
            if e_long > tau:
                taken[(gid, K, tau)] = dict(
                    side="long", tau=tau, gid=gid, K=K, edge=e_long, inside=inside,
                    premium=cost_long,
                    pnl=inside - cost_long - fee(qa["bid"]) - fee(qb["ask"]),
                    mid_pnl=inside - mid_int)
            elif e_short > tau:
                taken[(gid, K, tau)] = dict(
                    side="short", tau=tau, gid=gid, K=K, edge=e_short, inside=inside,
                    premium=recv_short,
                    pnl=-inside + recv_short - fee(qa["ask"]) - fee(qb["bid"]),
                    mid_pnl=mid_int - inside)

print(f"\ncandidate (game, pair, instant) evaluations {cands:,}   stale {stale:,}   "
      f"too wide (>{MAX_LEG_SPREAD*100:.0f}c leg) {wide:,}")
for tau in TAUS:
    print(f"positions at tau {tau:.2f}: {sum(1 for k in taken if k[2] == tau):,}  (one per game x pair)")


def clustered(vals, keys):
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys):
        res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    if G < 2:
        return m, float("inf"), n, G, ge      # one cluster: no interval, never a verdict
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5
    return m, 1.96 * se, n, G, ge


def report(label, sel):
    if not sel:
        print(f"  {label:<34} no positions"); return
    keys = [x["gid"] for x in sel]
    m, h, n, G, ge = clustered([x["pnl"] for x in sel], keys)
    mm, mh, *_ = clustered([x["mid_pnl"] for x in sel], keys)
    ins = sum(x["inside"] for x in sel) / n
    verdict = ("NO INTERVAL" if G < 2 else
               "POSITIVE" if m - h > 0 else ("NEGATIVE" if m + h < 0 else "spans zero"))
    flag = "" if G >= 25 else "  UNDERPOWERED (<25 games)"
    print(f"  {label:<34} n={n:>5}  G={G:>3} G_eff={ge:>5.1f}   "
          f"net {100*m:+6.2f}c [{100*(m-h):+6.2f}, {100*(m+h):+6.2f}]  {verdict:<10}"
          f"   mid-to-mid {100*mm:+6.2f}c [{100*(mm-mh):+6.2f}, {100*(mm+mh):+6.2f}]"
          f"   inside-rate {ins:.2f}{flag}")


allp = list(taken.values())
print(f"\n=== P&L per pair, cents per $1 contract, game-clustered, held to settlement ===")
print("  net = after crossing both spreads and 0.06*p*(1-p) taker fee per leg;")
print("  mid-to-mid = same positions priced at mid, no fees (does the model disagree usefully?)\n")
for tau in TAUS:
    tag = "PRIMARY" if tau == TAU_PRIMARY else "secondary"
    report(f"tau {tau:.2f} ({tag})", [x for x in allp if x["tau"] == tau])
print()
report("long interval only  (tau 0.05)", [x for x in allp if x["tau"] == TAU_PRIMARY and x["side"] == "long"])
report("short interval only (tau 0.05)", [x for x in allp if x["tau"] == TAU_PRIMARY and x["side"] == "short"])

sel = [x for x in allp if x["tau"] == TAU_PRIMARY]
if sel:
    prem = sum(x["premium"] for x in sel) / len(sel)
    print(f"\n  at tau 0.05: mean premium paid/received {100*prem:+.2f}c   "
          f"mean model edge claimed {100*sum(x['edge'] for x in sel)/len(sel):+.2f}c")

print("\n=== WHAT THIS CANNOT SAY ===")
print("  Our own order is absent from the book it is priced against; a real taker")
print("  moves the touch. And the 30s lag is charged only as WHEN we quote, not as")
print("  the book having already moved on us -- both bias toward optimism.")
