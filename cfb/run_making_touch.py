"""E1 — making JOINED TO THE TOUCH, with the model as a shield, not a location.

WHY THIS SUPERSEDES run_making.py. That harness centred quotes on model fair
value at a half-width, AWAY from the market. That is not making. A quote at FV
when FV differs from the market is a passive directional bet with a limit
trigger: it rests only on the side the market is walking toward, so it is
filled precisely when the market is right and we are wrong. Its losses grew
monotonically with half-width (-8.93c at 1c to -18.61c at 5c) because a wider
half-width is a LARGER directional bet, not a wider spread. My conclusion from
it — that a better model cannot fix making — measured my execution rule, not
making.

Avellaneda-Stoikov and Cartea-Wang: a maker with an alpha signal SKEWS AND
WITHDRAWS around the touch. It does not relocate the mid. This implements that.

THREE ARMS, and the comparison between them is the entire finding:

  A  NAIVE   quote both sides at the touch, always, no model at all.
             Glosten-Milgrom says this must lose to informed flow. It is the
             CONTROL, and its loss is the adverse-selection cost to beat.
  B  SHIELD  identical quotes, but withdraw the side the model says is
             mispriced, and size the surviving side by the model's confidence.
             The model NEVER moves a quote's price -- only its presence.
  C  BOTH    withdraw AND skew one tick when the model is emphatic, still
             never through the touch.

The finding is B - A. That is the model's contribution to MAKING, isolated
from where the quotes sit, because A and B post at the same prices. If B ~ A
the model has no shielding value; if B > A it does, and by how much.

FILLS COME FROM TRADE PRINTS, NOT FROM THE BOOK MOVING. The old rule (a bid at
B fills when the ask falls to B) can only register fills where the book moved
THROUGH us, which is the adverse subset by construction -- it cannot see a
benign fill even in principle, so it could only ever return "making is adverse".
Here a resting bid fills when volume actually prints at our price, after the
size queued ahead of us at that price is consumed.

QUEUE IS MODELLED BY SIZE, which the earlier note in docs/math/fill-rule-bias
said was impossible. That note reasoned from the venue exposing no ORDER COUNT
per level. Order count is not what queue priority depends on in a size-priority
FIFO book -- being behind 400 shares is the same wait whether it is one order
or ten -- and book_levels does record quantity per level. So queue position is
correctable from tape after all, and this no longer needs an upper-bound
caveat on that axis.

WHAT IS STILL NOT MODELLED, stated rather than buried:
  * The print tape is SAMPLED, not complete. market_trade_stats carries the
    LAST trade at each poll, so trades between polls are invisible in PRICE.
    Volume survives via shares_traded deltas, so the queue drain is right and
    the fill PRICES are a subset. Reported as coverage, not assumed benign.
  * Our own quote would have changed the book. Unmodellable from any tape.
  * We assume full FIFO priority behind the resting size at post time; size
    that joins after us is behind us, which is correct, but cancellations
    ahead of us would help us and are not observable.
"""
import bisect
import datetime as dt
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, build_features  # noqa: E402
from cfb_train import REG_FEATURES  # noqa: E402

import xgboost as xgb  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

FEED_LAG = 30          # seconds; we cannot post before we have seen the play
REST_WINDOW = 90       # seconds a quote rests before we pull it
MARKOUT = 60           # seconds after a fill, for the benign/adverse split
MARKOUTS = (120, 300)  # MAKER P&L horizons: fill price vs mid at +2/+5 min; ~1/10 the variance of settlement
MAKER_THETA = 0.0      # THERE IS NO MAKER REBATE. findings.md C7
# (RESOLVED 2026-08-25) and V24: the credits that looked like one were
# TAKER_FEE_REBATE, a 50% refund of our OWN taker fees, promo window
# 2026-03-29 -> 05-10, ended, nothing since. The advertised 25%-of-
# matched-taker-fee rebate has NEVER been observed in this account.
# The core code has defaulted theta_maker=0 everywhere since 08-05
# (wallet.py:143, fills.py:21, engine.py:179); these two CFB scripts
# were the last place still booking it as certain income.
WITHDRAW_EDGE = 0.03   # model must disagree by this much to pull a side
SKEW_EDGE = 0.06       # and by this much before arm C skews a tick
TICK = 0.01
# E6 -- DEAD_WINDOW=1. ONE pre-registered stratum, verbatim from the plan:
#   "no play in the last 45s AND no score change in the last 120s"
# evaluated on OBSERVED plays (we see a play FEED_LAG after it happens, so a
# play inside the last 30s is invisible -- that is the lag risk a maker bears
# and it is correctly left in). Quote instants are generated every 15s
# between plays instead of AT plays; everything downstream -- arms, fill rule,
# queue, clustering, guards -- is E1's, untouched. One stratum. No search.
DEAD_WINDOW = bool(os.environ.get("DEAD_WINDOW"))
# E8 -- LEAGUE=nfl (or cfb). Reads the LIVE recorder tables, which are
# football-shaped and hold both leagues under `league`, instead of the CFB-only
# backfill tables. Settlement from the last recorded game_state score; spread
# from the recorded live line, which may be ABSENT (CFB had it on 19/55 games).
# A play with no line still gets arm A -- the naive maker needs no model --
# and is counted out of B/C, where the shield has nothing to decide with.
LEAGUE = os.environ.get("LEAGUE")
DEAD_NO_PLAY_S = 45
DEAD_NO_SCORE_S = 120
DEAD_STEP_S = 15
# H1c -- MOVE_STRATUM=1. Quote ONLY in the minute after a >=1c one-minute mid
# move on the winner market, ONLY on the side of the move (bid after up, ask
# after down), rest 2 minutes. Everything else is E1's. Exploratory on CFB,
# registered for NFL (docs/math/e8-nfl-preregistration.md, H1c).
MOVE_STRATUM = bool(os.environ.get("MOVE_STRATUM"))
MOVE_MIN_C = 0.01
MOVE_REST_S = 120

# the shield's model follows the league: an NFL-trained head for NFL tape, never
# the CFB one pointed at NFL games. WP_MODEL overrides either.
_default_wp = ("/app/artifacts/nfl_wp_regulation.json" if os.environ.get("LEAGUE") == "nfl"
               else "/app/artifacts/cfb_wp_regulation.json")
WP_MODEL = os.environ.get("WP_MODEL", _default_wp)
booster = xgb.Booster()
booster.load_model(WP_MODEL)
print(f"shield model: {WP_MODEL}")
eng = create_engine(os.environ["DATABASE_URL"])

# ---------------------------------------------------------------- quote rows
# NOT a per-play LATERAL. There is no composite (game_id, captured_at) index on
# market_snapshots, so `game_id = X AND captured_at >= T ORDER BY captured_at
# LIMIT 1` fetches EVERY snapshot for that game across all history, sorts it,
# and keeps one row -- once per play. That ran 4.1 hours against prod before I
# cancelled it. Two bounded bulk queries plus a bisect do the same work in one
# pass, and the cost is something I can predict before running it.
PLAYS_SQL = """
SELECT b.game_id espn_game, b.play_id, b.wall_clock, b.period,
       b.clock_minutes, b.clock_seconds, b.down, b.distance, b.yards_to_goal,
       b.pos_team_score, b.def_pos_team_score, b.drive_is_home_offense,
       m.venue_game_id, g.spread::float AS spread,
       (CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END)::int AS settlement
FROM espn_cfb_backfill_plays b
JOIN cfb_game_map m ON m.espn_game_id = b.game_id
JOIN espn_cfb_backfill_games g ON g.game_id = b.game_id
WHERE b.wall_clock IS NOT NULL AND b.down IS NOT NULL AND b.down > 0
  AND b.period IS NOT NULL AND NOT b.is_overtime AND g.spread IS NOT NULL
  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
  AND g.home_score <> g.away_score
  AND m.venue_game_id IS NOT NULL
"""

# Bounded on BOTH sides so the partitions prune. LIKE '%winner' is the
# production predicate; `= 'winner'` is a different, empty set.
SNAPS_SQL = """
SELECT id AS snapshot_id, game_id, market_slug, captured_at,
       best_bid::float AS bid0, best_ask::float AS ask0
FROM market_snapshots
WHERE game_id = ANY(:gids)
  AND sports_market_type LIKE '%winner'
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND captured_at BETWEEN :t_lo AND :t_hi
ORDER BY game_id, captured_at
"""

# ------------------------------------------------------------- queue at touch
# Size resting AT the touch when we post. We join BEHIND it.
QUEUE_SQL = """
SELECT snapshot_id, side, price::float AS price, quantity::float AS quantity
FROM book_levels WHERE level_index = 0 AND snapshot_id = ANY(:ids)
"""

# ---------------------------------------------------------------- trade tape
# market_slug is NULL on depth-loop rows -- they carry identity through
# snapshot_id -- so filtering on market_slug alone silently drops most of the
# tape. Resolve through the snapshot and COALESCE. Time-bounded: the venue
# writes ~1.17M rows/hour and only the rest+markout window is ever read.
TAPE_SQL = """
SELECT COALESCE(t.market_slug, ms.market_slug) AS market_slug,
       t.captured_at, t.last_trade_px::float AS px,
       t.last_trade_at, t.shares_traded::float AS cum_shares
FROM market_trade_stats t
LEFT JOIN market_snapshots ms
       ON ms.id = t.snapshot_id
      AND ms.captured_at BETWEEN :t_lo AND :t_hi   -- prune partitions.
      -- In the ON clause, not the WHERE: market_snapshots is
      -- partitioned on captured_at, and an unbounded join scans every
      -- partition. Putting it in WHERE would also silently convert this
      -- LEFT JOIN to an inner one and drop the depth-loop rows, which
      -- are 56% of the tape (198,287 NULL-slug vs 154,799 set).
WHERE COALESCE(t.market_slug, ms.market_slug) = ANY(:slugs)
  AND t.last_trade_px IS NOT NULL
  AND t.captured_at BETWEEN :t_lo AND :t_hi
ORDER BY 1, t.captured_at
"""

# ---------------------------------------------------------- mid tape (markout)
MID_SQL = """
SELECT market_slug, captured_at, best_bid::float AS bid, best_ask::float AS ask
FROM market_snapshots
WHERE market_slug = ANY(:slugs) AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND captured_at BETWEEN :t_lo AND :t_hi
ORDER BY market_slug, captured_at
"""

LIVE_PLAYS_SQL = """
WITH final AS (
  SELECT DISTINCT ON (game_id) game_id, home_score, away_score
  FROM espn_cfb_game_state WHERE league = :lg AND home_score IS NOT NULL
  ORDER BY game_id, first_seen_at DESC),
line AS (
  SELECT game_id, avg(live_spread)::float AS sp FROM espn_cfb_game_state
  WHERE league = :lg AND live_spread IS NOT NULL GROUP BY 1)
SELECT p.game_id espn_game, p.play_id, p.wall_clock, p.period, p.clock_minutes,
       p.clock_seconds, p.down, p.distance, p.yards_to_goal, p.pos_team_score,
       p.def_pos_team_score, p.drive_is_home_offense, m.venue_game_id,
       l.sp AS spread,
       (CASE WHEN f.away_score > f.home_score THEN 1 ELSE 0 END)::int AS settlement
FROM espn_cfb_live_plays p
JOIN cfb_game_map m ON m.espn_game_id = p.game_id
JOIN final f ON f.game_id = p.game_id
LEFT JOIN line l ON l.game_id = p.game_id
WHERE p.league = :lg AND p.wall_clock IS NOT NULL AND p.down IS NOT NULL AND p.down > 0
  AND p.period IS NOT NULL AND NOT p.is_overtime AND m.venue_game_id IS NOT NULL
  AND f.home_score <> f.away_score
"""

with eng.connect() as c:
    if LEAGUE == "cfb":
        # POOL: backfill (Wed-Fri, has every game's line) + live tables (adds
        # Saturday's slate, which backfill never reached). Dedup BY GAME, backfill
        # wins, so no game is counted twice and the cluster count is honest.
        bf = [dict(r._mapping) for r in c.execute(text(PLAYS_SQL))]
        lv = [dict(r._mapping) for r in c.execute(text(LIVE_PLAYS_SQL), {"lg": "cfb"})]
        bf_games = {p["espn_game"] for p in bf}
        lv_new = [p for p in lv if p["espn_game"] not in bf_games]
        plays = bf + lv_new
        print(f"LEAGUE=cfb POOLED: backfill {len(bf):,} plays / {len(bf_games)} games  +  live-only "
              f"{len(lv_new):,} plays / {len({p['espn_game'] for p in lv_new})} games  "
              f"(live overlapping backfill dropped: {len({p['espn_game'] for p in lv}) - len({p['espn_game'] for p in lv_new})} games)")
    elif LEAGUE:
        plays = [dict(r._mapping) for r in c.execute(text(LIVE_PLAYS_SQL), {"lg": LEAGUE})]
        print(f"LEAGUE={LEAGUE}: live tables; plays {len(plays):,}  games "
              f"{len({p['espn_game'] for p in plays})}  with a line "
              f"{len({p['espn_game'] for p in plays if p['spread'] is not None})}")
    else:
        plays = [dict(r._mapping) for r in c.execute(text(PLAYS_SQL))]
    if not plays:
        print("no plays joinable to a venue game -- refusing to report.")
        sys.exit(0)
    gids = sorted({p["venue_game_id"] for p in plays})
    p_lo = min(p["wall_clock"] for p in plays)
    p_hi = max(p["wall_clock"] for p in plays)
    snaps = [dict(r._mapping) for r in c.execute(text(SNAPS_SQL), {
        "gids": gids,
        "t_lo": p_lo + dt.timedelta(seconds=FEED_LAG),
        "t_hi": p_hi + dt.timedelta(seconds=FEED_LAG + 300)})]

# nearest snapshot at or AFTER wall_clock + FEED_LAG, within 5 minutes
by_game = defaultdict(lambda: ([], []))
for r in snaps:
    ts, rows_ = by_game[r["game_id"]]
    ts.append(r["captured_at"]); rows_.append(r)

quotes = []
for p in plays:
    ts, rows_ = by_game.get(p["venue_game_id"], ((), ()))
    if not ts:
        continue
    want = p["wall_clock"] + dt.timedelta(seconds=FEED_LAG)
    i = bisect.bisect_left(ts, want)
    if i >= len(ts) or (ts[i] - p["wall_clock"]).total_seconds() > 300:
        continue
    q = dict(p); q.update(rows_[i]); q["t0"] = rows_[i]["captured_at"]
    quotes.append(q)

if DEAD_WINDOW:
    by_g = defaultdict(list)
    for p in plays:
        by_g[p["espn_game"]].append(p)
    dead_quotes, n_inst, n_qual = [], 0, 0
    for gid, ps in by_g.items():
        ps.sort(key=lambda r: r["wall_clock"])
        # home/away score per play, to find score changes
        sc = []
        for r in ps:
            h = r["pos_team_score"] if r["drive_is_home_offense"] else r["def_pos_team_score"]
            a = r["def_pos_team_score"] if r["drive_is_home_offense"] else r["pos_team_score"]
            sc.append((h or 0, a or 0))
        change_t = [ps[0]["wall_clock"]] + [ps[i]["wall_clock"] for i in range(1, len(ps))
                                             if sc[i] != sc[i - 1]]
        wcs = [r["wall_clock"] for r in ps]
        t = wcs[0] + dt.timedelta(seconds=FEED_LAG)
        end = wcs[-1]
        while t <= end:
            n_inst += 1
            seen = t - dt.timedelta(seconds=FEED_LAG)          # what we can see at t
            i = bisect.bisect_right(wcs, seen) - 1
            if i >= 0:
                last = ps[i]
                j = bisect.bisect_right(change_t, seen) - 1
                last_change = change_t[j] if j >= 0 else wcs[0]
                if (t - last["wall_clock"]).total_seconds() >= DEAD_NO_PLAY_S and \
                   (t - last_change).total_seconds() >= DEAD_NO_SCORE_S:
                    n_qual += 1
                    ts, rows_ = by_game.get(last["venue_game_id"], ((), ()))
                    k = bisect.bisect_left(ts, t)
                    if ts and k < len(ts) and (ts[k] - t).total_seconds() <= 300:
                        q = dict(last); q.update(rows_[k]); q["t0"] = rows_[k]["captured_at"]
                        nxt = wcs[i + 1] + dt.timedelta(seconds=FEED_LAG) if i + 1 < len(wcs) else None
                        q["rest_s"] = min(REST_WINDOW, (nxt - q["t0"]).total_seconds()) if nxt else REST_WINDOW
                        if q["rest_s"] > 0:
                            dead_quotes.append(q)
            t += dt.timedelta(seconds=DEAD_STEP_S)
    print(f"E6 DEAD WINDOW: instants {n_inst:,}  qualified (no play {DEAD_NO_PLAY_S}s, "
          f"no score {DEAD_NO_SCORE_S}s) {n_qual:,}  with a book {len(dead_quotes):,}")
    quotes = dead_quotes

if MOVE_STRATUM:
    # 1-minute mids per venue game from the winner snapshots already loaded in by_game
    mv_quotes, n_moves = [], 0
    play_by_vg = defaultdict(list)
    for p in plays: play_by_vg[p["venue_game_id"]].append(p)
    for vg, (ts, rows_) in by_game.items():
        ps = sorted(play_by_vg.get(vg, []), key=lambda r: r["wall_clock"])
        if not ps: continue
        ko = ps[0]["wall_clock"]; end = ko + dt.timedelta(hours=3, minutes=40)
        minute, first = {}, {}
        for t_, r in zip(ts, rows_):
            if not (ko < t_ <= end): continue
            k = int((t_ - ko).total_seconds() // 60)
            minute[k] = (r["bid0"] + r["ask0"]) / 2; first.setdefault(k + 1, r)   # the first snapshot of the NEXT minute is where we post
        for k in sorted(minute):
            if k - 1 not in minute or k + 1 not in first: continue
            dm = minute[k] - minute[k - 1]
            if abs(dm) < MOVE_MIN_C: continue
            n_moves += 1
            # state = last observed play before the post instant (feed lag applied)
            r0 = first[k + 1]; t0 = r0["captured_at"]
            seen = t0 - dt.timedelta(seconds=FEED_LAG)
            i = bisect.bisect_right([p_["wall_clock"] for p_ in ps], seen) - 1
            if i < 0: continue
            q = dict(ps[i]); q.update(r0); q["t0"] = t0; q["rest_s"] = MOVE_REST_S
            q["move_side"] = "bid" if dm > 0 else "ask"
            mv_quotes.append(q)
    print(f"H1c MOVE STRATUM: >=1c one-minute moves {n_moves:,}   quotable {len(mv_quotes):,}   (bid after up, ask after down)")
    quotes = mv_quotes

if len(quotes) < 200:
    print(f"only {len(quotes)} quotable instants -- refusing to report.")
    sys.exit(0)
slugs = sorted({q["market_slug"] for q in quotes})
ids = sorted({q["snapshot_id"] for q in quotes})
t_lo = min(q["t0"] for q in quotes)
t_hi = max(q["t0"] for q in quotes) + dt.timedelta(
    seconds=REST_WINDOW + max(MARKOUTS) + 60)
win = {"slugs": slugs, "t_lo": t_lo, "t_hi": t_hi}

with eng.connect() as c:
    queue_rows = [dict(r._mapping) for r in c.execute(text(QUEUE_SQL), {"ids": ids})]
    tape_rows = [dict(r._mapping) for r in c.execute(text(TAPE_SQL), win)]
    mid_rows = [dict(r._mapping) for r in c.execute(text(MID_SQL), win)]

print(f"plays joinable {len(plays):,}   winner snapshots {len(snaps):,}")
print(f"quotable plays {len(quotes):,}   markets {len(slugs):,}   "
      f"games {len({q['espn_game'] for q in quotes}):,}")
print(f"book-depth rows {len(queue_rows):,}   tape rows {len(tape_rows):,}")

queue = {}
for r in queue_rows:
    queue[(r["snapshot_id"], r["side"])] = (r["price"], r["quantity"])

# --- reconstruct prints from the sampled last-trade tape --------------------
# A print is registered when last_trade_at ADVANCES. Size comes from the
# shares_traded delta, which counts the trades we could not see the price of,
# so the queue drains correctly even where the price tape is sparse.
prints = defaultdict(list)
prev = {}
unpriced_vol = priced_vol = 0.0
for r in tape_rows:
    s = r["market_slug"]
    p = prev.get(s)
    if p and r["last_trade_at"] and p["last_trade_at"] \
       and r["last_trade_at"] > p["last_trade_at"]:
        dv = (r["cum_shares"] or 0) - (p["cum_shares"] or 0)
        if dv <= 0:
            dv = 0.0
        prints[s].append({"t": r["last_trade_at"], "px": r["px"], "qty": dv,
                          "seen_at": r["captured_at"]})
        priced_vol += dv
    prev[s] = r
for s in prints:
    prints[s].sort(key=lambda d: d["t"])

mids = defaultdict(lambda: ([], []))
for r in mid_rows:
    ts, vs = mids[r["market_slug"]]
    ts.append(r["captured_at"])
    vs.append((r["bid"] + r["ask"]) / 2)


def mid_at(slug, t):
    """Last mid at or before t, or None if the tape starts after t."""
    ts, vs = mids.get(slug, ((), ()))
    i = bisect.bisect_right(ts, t)
    return vs[i - 1] if i else None



def clustered(vals, keys):
    """Mean, with BOTH intervals, because naming the estimator is the point.

    Returns (mean, half_clustered, half_perfill, n, G, G_eff).

    G_eff is Kish's effective cluster count, (sum n_g)^2 / sum n_g^2. With
    balanced clusters G_eff == G; the more the fills pile into a few markets
    the further G_eff falls below G, and G_eff is the honest denominator. This
    project has been caught by per-fill vs per-game divergence more than by any
    other single thing, so both are computed and both are printed.
    """
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    from collections import defaultdict as _dd
    resid, size = _dd(float), _dd(int)
    for v, k in zip(vals, keys):
        resid[k] += (v - m)
        size[k] += 1
    G = len(resid)
    sd = (sum((x - m) ** 2 for x in vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
    half_iid = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
    g_eff = (n * n) / sum(c * c for c in size.values()) if size else 0.0
    if G < 2:
        return m, 0.0, half_iid, n, G, g_eff
    se = (sum(x * x for x in resid.values()) ** 0.5) / n
    se *= (G / (G - 1.0)) ** 0.5
    return m, 1.96 * se, half_iid, n, G, g_eff


def fee(theta, p):
    return theta * p * (1.0 - p)


# --------------------------------------------------------------- the three arms
ARMS = ("A_naive", "B_shield", "C_shield_skew")
fills = {a: [] for a in ARMS}
withdrawn = {a: 0 for a in ARMS}
posted = {a: 0 for a in ARMS}
no_queue = skipped_feat = with_queue = no_line = 0

for q in quotes:
    st = GameState(period=q["period"], clock_minutes=q["clock_minutes"] or 0,
                   clock_seconds=q["clock_seconds"] or 0, down=q["down"],
                   distance=q["distance"], yards_to_goal=q["yards_to_goal"],
                   pos_team_score=q["pos_team_score"] or 0,
                   def_pos_team_score=q["def_pos_team_score"] or 0,
                   drive_is_home_offense=bool(q["drive_is_home_offense"]),
                   pos_team_timeouts=3, def_pos_team_timeouts=3,
                   is_overtime=False, ot_possession_number=None)
    f = build_features(st, q["spread"])
    if f.get("score_differential") is None:
        skipped_feat += 1
        continue
    if q["spread"] is None or f.get("spread_time") is None:
        fv = None                  # no line: arm A only, shield cannot decide
        no_line += 1
    else:
        vec = [float("nan") if f.get(c) is None else f.get(c) for c in REG_FEATURES]
        p_pos = float(booster.predict(xgb.DMatrix(
            [vec], feature_names=REG_FEATURES, missing=float("nan")))[0])
        p_home = p_pos if q["drive_is_home_offense"] else 1.0 - p_pos
        fv = 1.0 - p_home          # YES = away team = the slug's first team

    bid, ask = q["bid0"], q["ask0"]
    slug, t0, y = q["market_slug"], q["t0"], q["settlement"]
    qb = queue.get((q["snapshot_id"], "bid"))
    qa = queue.get((q["snapshot_id"], "offer"))

    # Queue ahead of us: the size resting at the touch when we arrive. If the
    # recorded top-of-book price has drifted from best_bid/best_ask, the level
    # is not the touch we think it is, so treat it as unusable rather than
    # assuming zero (assuming zero would invent free priority).
    # Depth is usable only if the recorded level IS the touch; if it has
    # drifted, the level is not the price we think it is, and assuming zero
    # would invent free priority.
    if qb is not None and qa is not None \
       and abs(qb[0] - bid) <= 1e-9 and abs(qa[0] - ask) <= 1e-9:
        q_ahead_bid, q_ahead_ask = qb[1], qa[1]
        with_queue += 1
    else:
        q_ahead_bid = q_ahead_ask = 0.0    # OPTIMISTIC: full priority
        no_queue += 1

    # ---- per-arm quote decisions. Prices NEVER leave the touch except the
    # one-tick skew in C, which still rests inside the spread, never through.
    edge = (fv - (bid + ask) / 2.0) if fv is not None else 0.0
    for arm in ARMS:
        if fv is None and arm != "A_naive":
            continue               # counted in no_line; the shield has no view
        want_bid = want_ask = True
        if MOVE_STRATUM:
            want_bid, want_ask = (q["move_side"] == "bid"), (q["move_side"] == "ask")
        bpx, apx = bid, ask
        if arm != "A_naive":
            # withdraw the side the model says is mispriced: if FV is far
            # BELOW the market, buying at the bid is the bad side -- pull it.
            if edge < -WITHDRAW_EDGE:
                want_bid = False
            if edge > WITHDRAW_EDGE:
                want_ask = False
        if arm == "C_shield_skew" and ask - bid > 2 * TICK:
            if edge > SKEW_EDGE:
                bpx = round(bid + TICK, 4)     # lean into the side we like
            elif edge < -SKEW_EDGE:
                apx = round(ask - TICK, 4)
        if not want_bid:
            withdrawn[arm] += 1
        if not want_ask:
            withdrawn[arm] += 1
        posted[arm] += int(want_bid) + int(want_ask)

        # ---- walk the print tape inside the rest window, draining the queue
        rb, ra = q_ahead_bid, q_ahead_ask
        done_b = done_a = False
        for pr in prints.get(slug, ()):
            if pr["t"] <= t0:
                continue
            if (pr["t"] - t0).total_seconds() > q.get("rest_s", REST_WINDOW):
                break
            # a print AT OR BELOW our bid is a seller reaching us; at or above
            # our ask is a buyer. Prints strictly inside do not touch us.
            if want_bid and not done_b and pr["px"] <= bpx + 1e-9:
                if rb > 0:
                    rb -= pr["qty"]
                if rb <= 0:
                    done_b = True
                    fills[arm].append(("buy", bpx, slug, pr["t"], y,
                                       edge < -WITHDRAW_EDGE))
            if want_ask and not done_a and pr["px"] >= apx - 1e-9:
                if ra > 0:
                    ra -= pr["qty"]
                if ra <= 0:
                    done_a = True
                    fills[arm].append(("sell", apx, slug, pr["t"], y,
                                       edge > WITHDRAW_EDGE))
            if done_b and done_a:
                break

print(f"skipped {skipped_feat:,} incomplete state; {no_line:,} quotes had NO LINE "
      f"(arm A only -- B/C cannot decide without a model view)")
print(f"queue modelled from recorded depth on {with_queue:,} quotes; "
f"{no_queue:,} used the OPTIMISTIC no-queue assumption (full priority).")
if with_queue == 0:
    print("  ALL fills are the optimistic arm. A LOSS here is real; a"
          " profit is not evidence, because real queue position can only"
          " make it worse.")

# ------------------------------------------------------------------- scoring
print("\n=== ARMS" + (" -- E6 DEAD-WINDOW STRATUM, one pre-registered, no search" if DEAD_WINDOW else "") + (" -- H1c MOVE STRATUM: post on the side of a >=1c move, rest 2 min (EXPLORATORY on CFB)" if MOVE_STRATUM else "") + " ===")
print(f"  {'arm':<16}{'posted':>8}{'pulled':>8}{'fills':>7}{'fill%':>7}"
      f"{'net c/fill':>12}{'adverse%':>10}")
summary = {}
for arm in ARMS:
    fl = fills[arm]
    if not fl:
        print(f"  {arm:<16}{posted[arm]:>8}{withdrawn[arm]:>8}"
              f"{0:>7}{'--':>7}{'NO FILLS':>12}{'--':>10}")
        summary[arm] = None
        continue
    pnl, adverse, scored = [], 0, 0
    for side, px, slug, t, y, _pulled in fl:
        # settlement P&L in the traded direction. YES settles at y in {0,1}:
        # bought at px -> y - px; sold at px -> px - y. The maker rebate is
        # negative, so subtracting fee() ADDS it.
        gross = (y - px) if side == "buy" else (px - y)
        pnl.append(100.0 * (gross - fee(MAKER_THETA, px)))
        m = mid_at(slug, t + dt.timedelta(seconds=MARKOUT))
        if m is not None:
            scored += 1
            moved = (m - px) if side == "buy" else (px - m)
            if moved < 0:
                adverse += 1
    n = len(pnl)
    mean, half, _hiid, _n, _G, _Geff = clustered(pnl, [f[2] for f in fl])
    mo_lines = []
    for H_ in MARKOUTS:
        vals, keys = [], []
        for side, px, slug, t, y, _p in fl:
            m_ = mid_at(slug, t + dt.timedelta(seconds=H_))
            if m_ is None:
                continue
            vals.append(100.0 * ((m_ - px) if side == "buy" else (px - m_)))
            keys.append(slug)
        if len(vals) >= 20:
            mm, mh, _mi, mn, mG, mGe = clustered(vals, keys)
            # With one cluster the sandwich SE is zero BY CONSTRUCTION: there is no
            # interval, and "EXCLUDES 0" would be a lie. Say so.
            verdict = ("NO INTERVAL (G=1)" if mG < 2 else
                       ("EXCLUDES 0" if (mm-mh) > 0 or (mm+mh) < 0 else "spans 0"))
            mo_lines.append(f"  {'':<16}MARKOUT +{H_//60}min  {mm:+6.2f}c  [{mm-mh:+.2f}, {mm+mh:+.2f}]  "
                            f"n={mn} G={mG} G_eff={mGe:.1f}  {verdict}")
    summary[arm] = (mean, half, n, _G, _Geff)
    fr = 100.0 * n / posted[arm] if posted[arm] else 0.0
    ad = 100.0 * adverse / scored if scored else float("nan")
    print(f"  {arm:<16}{posted[arm]:>8}{withdrawn[arm]:>8}{n:>7}{fr:>6.1f}%"
          f"{mean:>+11.2f}c{ad:>9.1f}%")
    print(f"  {'':<16}GAME-CLUSTERED [{mean-half:+.2f}, {mean+half:+.2f}]c"
          f"   G={_G}  G_eff={_Geff:.1f}")
    for _l in mo_lines:
        print(_l)
    # CONCENTRATION: a positive markout carried by two games is not a prior for
    # anything. Per-game 2-min markout for arm A, and leave-one-game-out range.
    if arm == "A_naive" and MOVE_STRATUM:
        pg = defaultdict(list)
        for side, px, slug, t, y, _p in fl:
            m_ = mid_at(slug, t + dt.timedelta(seconds=MARKOUTS[0]))
            if m_ is not None:
                pg[slug].append(100.0 * ((m_ - px) if side == "buy" else (px - m_)))
        rows_ = sorted(((sum(v)/len(v), len(v), k) for k, v in pg.items()), reverse=True)
        allv = [x for v in pg.values() for x in v]
        loo = []
        for k in pg:
            rest = [x for kk, v in pg.items() if kk != k for x in v]
            if rest: loo.append(sum(rest)/len(rest))
        print(f"  {'':<16}per-game +2min markout: {sum(1 for m_, n_, k in rows_ if m_ > 0)}/{len(rows_)} games positive; "
              f"leave-one-game-out mean range [{min(loo):+.2f}, {max(loo):+.2f}]c")
        for m_, n_, k in rows_[:3] + rows_[-2:]:
            print(f"  {'':<18}{k[:34]:<34} {m_:+7.2f}c on {n_:>3} fills")
    print(f"  {'':<16}per-fill (WRONG here, shown to expose the gap) "
          f"[{mean-_hiid:+.2f}, {mean+_hiid:+.2f}]c   ratio "
          f"{half/_hiid if _hiid else float('nan'):.1f}x wider")

# --------------------------------------------------- the finding, and its guards
print("\n=== THE WITHDRAWN FILLS, measured directly ===")
_a = fills["A_naive"]
_kept = [f for f in _a if not f[5]]
_pull = [f for f in _a if f[5]]
def _pnl(fl):
    out = []
    for side, px, slug, t, y, _p in fl:
        gross = (y - px) if side == "buy" else (px - y)
        out.append(100.0 * (gross - fee(MAKER_THETA, px)))
    return out
for _lab, _set in (("kept by the shield", _kept), ("WITHDRAWN by the shield", _pull)):
    v = _pnl(_set)
    if not v:
        print(f"  {_lab:<26} no fills"); continue
    m, h, hi, _nn, _GG, _GE = clustered(v, [f[2] for f in _set])
    print(f"  {_lab:<26} n={_nn:>5}  {m:+.2f}c  GAME-CLUSTERED "
          f"[{m-h:+.2f}, {m+h:+.2f}]  G={_GG} G_eff={_GE:.1f}")
print("  If the withdrawn set is POSITIVE, the model is selecting against us:")
print("  it is pulling the quotes that make money and keeping the ones that lose.")

print("\n=== COULD THIS HAVE COME OUT THE OTHER WAY? ===")
print(f"  B posts a strict SUBSET of A's sides ({withdrawn['B_shield']:,} of "
      f"{posted['A_naive']:,} withdrawn).")
print("  A subset mean can exceed or fall below the full mean -- nothing in the")
print("  construction fixes the sign. B > A was reachable and did not happen.")
print(f"  The shield demonstrably ACTED: adverse-by-markout moved, and it")
print(f"  withdrew {withdrawn['B_shield']:,} sides rather than 0 or all.")

print("\n=== B - A : what the model adds as a SHIELD ===")
if summary["A_naive"] and summary["B_shield"]:
    a, b = summary["A_naive"][0], summary["B_shield"][0]
    print(f"  naive touch maker {a:+.2f}c   model-shielded {b:+.2f}c   "
          f"difference {b-a:+.2f}c")
else:
    print("  UNDERPOWERED — an arm produced no fills; no difference to report.")

print("\n=== GUARDS (a degenerate design reports a number and means nothing) ===")
deg = False
if withdrawn["B_shield"] == 0:
    print("  DEAD BRANCH: the model never withdrew a side. B is A by "
          "construction and the comparison is empty, not negative.")
    deg = True
if posted["B_shield"] == 0:
    print("  DEAD BRANCH: the model withdrew every side. B never quoted.")
    deg = True
# This guard used to count FILLS (<100). It never fired on 1,115 fills while
# the real independent unit was 33 markets -- a guard that could not fire for
# the failure mode that actually occurred. Count clusters, and check the
# interval directly rather than a proxy for it.
_A = summary["A_naive"]
if _A and _A[3] < 30:
    print(f"  UNDERPOWERED: only {_A[3]} independent markets carry the fills.")
    deg = True
for _arm in ARMS:
    _s = summary[_arm]
    if _s and _s[3] < 2:
        print(f"  NO INTERVAL: {_arm} has G={_s[3]} cluster(s). One game is not a measurement of anything.")
        deg = True
        continue
    if _s and (_s[0] - _s[1]) < 0 < (_s[0] + _s[1]):
        print(f"  SPANS ZERO: {_arm} is {_s[0]:+.2f}c "
              f"[{_s[0]-_s[1]:+.2f}, {_s[0]+_s[1]:+.2f}] on {_s[3]} markets. "
              f"This arm is NOT a measured negative -- it is not measured.")
        deg = True
if priced_vol <= 0:
    print("  NO TAPE: no priced volume was reconstructed at all.")
    deg = True
if not deg:
    print("  none fired — the arms are distinguishable and the tape is live.")

print("\n=== WHAT THIS STILL CANNOT SAY ===")
print("  Our own quote is absent from the book it is measured against, so the")
print("  flow that filled us is flow that existed WITHOUT us. That biases")
print("  toward optimism and no tape can remove it. This is a screen for")
print("  whether the shield has any effect at all, not a P&L forecast.")
