r"""Longshot-NO shadow lister. SHADOW ONLY: this script PLACES NOTHING.

The bet (docs/math/longshot-no-candidate.md, section 1): before kickoff, on every
CFB full-game spread rung whose YES mid = (best_bid + best_ask) / 2 is in
[0.20, 0.30), buy NO at 1 - best_bid (taking the resting YES bid), hold to
settlement, net of the 0.06 * p * (1 - p) taker fee. That rule is a HYPOTHESIS
under a registered read on 2026-09-19 (doc section 4), not a result. This lists
what the rule would have done (replay) or would do now (live) so timing, depth
and the rung set a live process sees can be checked against the backtest.
Imports nothing from core.executor / core.polymarket; SELECT only.

MODE=replay DATE=YYYY-MM-DD (default 2026-09-12): every mapped CFB game whose
venue date (event_slug suffix) is DATE; per spread rung the LAST snapshot in
[kickoff - 60 min, kickoff - 5 min]; rungs with YES mid in the bucket; settled
from ESPN finals (spread YES = (away - home) + line > 0, push skipped); buy-NO
P&L in cents with a game-clustered interval; plus the same games under the
calibration scan's rule (cfb/run_ladder_calibration.py: last quote within 6h of
kickoff, bucket int(mid*10) == 2) with the differences explained.

    H=$(tr -d '[:space:]' < ~/.meridian-server)
    ssh -i ~/.ssh/meridian-aws.pem -o BatchMode=yes ubuntu@$H 'sudo -n docker run --rm -i \
      --network meridian_default \
      -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
      -e MODE=replay -e DATE=2026-09-12 \
      -v /opt/meridian/cfb:/app/cfb -w /app meridian-trainer python3 -' < cfb/run_longshot_shadow.py

MODE=live: CFB games kicking off in the next 90 min (venue game_start_time),
latest snapshot per rung from the last 3h of tape, no settlement. Prints the
intended orders and APPENDS them to /app/artifacts/reads/longshot_shadow_orders.csv
-- the only thing written anywhere, and only with the artifacts mount:

    ssh ... 'sudo -n docker run --rm -i --network meridian_default \
      -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
      -e MODE=live -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts \
      -w /app meridian-trainer python3 -' < cfb/run_longshot_shadow.py

Kickoff anchor (replay): first ESPN play wall_clock (espn_cfb_live_plays, else
espn_cfb_backfill_plays), else the venue's game_start_time; the anchor and its
gap to the venue start print per game (first play vs venue start: median 3 min,
p90 30 min on 77 games). Live mode has no plays: venue start. Depth: book_levels
level 0 side 'bid' joined on market_snapshots.id (run_making_touch.py's QUEUE_SQL
source), fetched for the selected rungs only. Only ~7% of pregame snapshots carry
a depth row, so the LATEST sample in the window is shown with its age; '*' = its
level price is not the quote's bid; 'n/a' = no sample. Never assumed.
"""
import csv
import datetime as dt
import os
from collections import defaultdict

from sqlalchemy import create_engine, event, text

MODE, DATE = os.environ.get("MODE", "replay"), os.environ.get("DATE", "2026-09-12")
FEE, LO, HI = 0.06, 0.20, 0.30
T_EARLY, T_LATE, SIX_H = dt.timedelta(minutes=60), dt.timedelta(minutes=5), dt.timedelta(hours=6)
SPREAD = "football_team_full_game_spread"
CSV_PATH = "/app/artifacts/reads/longshot_shadow_orders.csv"

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _no_parallel(dbapi_conn, _rec):  # 64MB /dev/shm: parallel workers die on big scans
    cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close()
    dbapi_conn.commit()

GAMES_SQL = """
WITH g AS (SELECT venue_game_id vg, espn_game_id eg, event_slug FROM cfb_game_map
           WHERE venue_game_id IS NOT NULL AND event_slug LIKE 'cfb-%' AND right(event_slug, 10) = :d),
bf AS (SELECT game_id eg, home_score h, away_score a FROM espn_cfb_backfill_games
       WHERE home_score IS NOT NULL AND away_score IS NOT NULL),
lv AS (SELECT DISTINCT ON (game_id) game_id eg, home_score h, away_score a FROM espn_cfb_game_state
       WHERE period >= 4 AND home_score IS NOT NULL AND game_id IN (SELECT eg FROM g)
       ORDER BY game_id, first_seen_at DESC),
kl AS (SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_live_plays
       WHERE wall_clock IS NOT NULL AND game_id IN (SELECT eg FROM g) GROUP BY 1),
kb AS (SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_backfill_plays
       WHERE wall_clock IS NOT NULL AND game_id IN (SELECT eg FROM g) GROUP BY 1)
SELECT g.vg, g.event_slug, COALESCE(bf.h, lv.h) h, COALESCE(bf.a, lv.a) a, kl.ko ko_live, kb.ko ko_bf
FROM g LEFT JOIN bf ON bf.eg = g.eg LEFT JOIN lv ON lv.eg = g.eg
       LEFT JOIN kl ON kl.eg = g.eg LEFT JOIN kb ON kb.eg = g.eg ORDER BY g.event_slug
"""
# Every market_snapshots query is bounded on captured_at (monthly partitions) and on game_id / slug.
# The venue carries DIFFERENT game_start_time values on different markets of the same game
# (09-12: 19:30Z on 25,961 rows and 16:00Z on 3,098 for one game; ESPN's first play was 16:00Z),
# so every value is kept, the earliest is used, and a game with more than one is flagged.
START_SQL = """
SELECT DISTINCT game_id vg, game_start_time FROM market_snapshots
WHERE game_id = ANY(:gids) AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND game_start_time IS NOT NULL
"""
SNAPS_SQL = """
SELECT game_id vg, event_slug, market_slug, line::float line, best_bid::float bid, best_ask::float ask,
       captured_at, game_start_time
FROM market_snapshots
WHERE game_id = ANY(:gids) AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
ORDER BY game_id, market_slug, captured_at
"""
LIVE_GAMES_SQL = """
SELECT DISTINCT game_id FROM market_snapshots
WHERE event_slug LIKE 'cfb-%' AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND game_start_time BETWEEN :hi AND :hi + interval '90 minutes'
"""
DEPTH_SQL = """
SELECT s.market_slug, s.captured_at, b.price::float price, b.quantity::float qty
FROM market_snapshots s JOIN book_levels b ON b.snapshot_id = s.id AND b.level_index = 0 AND b.side = 'bid'
WHERE s.market_slug = ANY(:slugs) AND s.captured_at BETWEEN :lo AND :hi
ORDER BY s.market_slug, s.captured_at
"""


def clustered(vals, keys):
    """Fills-weighted mean, cluster-robust sandwich SE (identical to the calibration scan)."""
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


def settle(line, h, a):
    v = (a - h) + line
    return None if abs(v) < 1e-9 else int(v > 0)


def mid(s): return round((s["bid"] + s["ask"]) / 2, 4)
def mins(a, b): return (a - b).total_seconds() / 60


def depth_for(slugs, lo, hi):
    """Level-0 bid samples for the selected rungs only, keyed by slug."""
    out = defaultdict(list)
    with eng.connect() as c:
        for r in c.execute(text(DEPTH_SQL), {"slugs": sorted(slugs), "lo": lo, "hi": hi}):
            out[r.market_slug].append(dict(r._mapping))
    return out


def depth_at(samples, w_lo, t_quote, bid):
    """Latest sample for the rung in [w_lo, t_quote]; '*' if its level price is not the quote's bid."""
    d = [x for x in samples if w_lo <= x["captured_at"] <= t_quote]
    if not d:
        return "n/a", None
    x = d[-1]; flag = "" if abs(x["price"] - bid) < 1e-9 else "*"
    return f"{flag}{x['qty']:.0f}@{x['price']:.2f} {mins(x['captured_at'], t_quote):+.0f}m", x


HDR = f"    {'rung':<44}{'line':>6}{'bid':>6}{'ask':>6}{'mid':>7}{'NO@':>6}  {'depth@bid(age)':<22}{'T-min':>6}"
def rung_line(s, dep, t_ko):
    return (f"    {s['market_slug']:<44}{s['line']:>+6.1f}{s['bid']:>6.2f}{s['ask']:>6.2f}{mid(s):>7.4f}"
            f"{1 - s['bid']:>6.2f}  {dep:<22}{mins(t_ko, s['captured_at']):>6.1f}")


with eng.connect() as c:
    now = c.execute(text("SELECT now()")).scalar()
    print(f"longshot-NO shadow  MODE={MODE}  bucket YES mid [{LO},{HI})  db now {now:%Y-%m-%d %H:%M}Z  "
          f"SHADOW: nothing is placed")
    if MODE == "live":
        lo, hi, games = now - dt.timedelta(hours=3), now, []
        gids = [r[0] for r in c.execute(text(LIVE_GAMES_SQL), {"t": SPREAD, "lo": lo, "hi": hi})]
    else:
        d0 = dt.datetime.fromisoformat(DATE).replace(tzinfo=dt.timezone.utc)
        games = [dict(r._mapping) for r in c.execute(text(GAMES_SQL), {"d": DATE})]
        gids = [g["vg"] for g in games]
        starts = defaultdict(set)
        for r in c.execute(text(START_SQL), {"gids": gids, "t": SPREAD, "lo": d0 - dt.timedelta(hours=12),
                                             "hi": d0 + dt.timedelta(hours=36)}):
            starts[r.vg].add(r.game_start_time)
        for g in games:
            g["start"], g["starts"] = (min(starts[g["vg"]]) if starts[g["vg"]] else None), starts[g["vg"]]
            g["ko"], g["anchor"] = ((g["ko_live"], "live-play") if g["ko_live"] else
                                    (g["ko_bf"], "backfill-play") if g["ko_bf"] else (g["start"], "venue-start"))
        dropped = [g["event_slug"] for g in games if g["ko"] is None]
        games = [g for g in games if g["ko"] is not None]
        if not games:
            raise SystemExit(f"no mapped CFB games with a kickoff anchor on {DATE}")
        lo, hi = min(g["ko"] for g in games) - SIX_H, max(g["ko"] for g in games)
        print(f"mapped CFB games dated {DATE}: {len(games)} with an anchor"
              + (f", dropped (no plays, no venue start): {dropped}" if dropped else "") + "; anchors: "
              + ", ".join(f"{k} {sum(g['anchor'] == k for g in games)}" for k in ("live-play", "backfill-play", "venue-start")))
    snaps = [dict(r._mapping) for r in c.execute(text(SNAPS_SQL), {"gids": gids, "t": SPREAD, "lo": lo, "hi": hi})]
print(f"spread snapshots {len(snaps):,} over {len(gids)} games")
by_slug = defaultdict(list)
for s in snaps: by_slug[s["market_slug"]].append(s)

if MODE == "live":
    orders = [ss[-1] for _, ss in sorted(by_slug.items()) if LO <= mid(ss[-1]) < HI]
    gstart = defaultdict(set)
    for s in snaps:
        if s["game_start_time"]: gstart[s["vg"]].add(s["game_start_time"])
    for q in orders:
        q["game_start_time"] = min(gstart[q["vg"]])
    dep_by = depth_for({q["market_slug"] for q in orders}, lo, hi) if orders else {}
    print(f"\n{len(orders)} intended orders (BUY NO at 1-bid, hold to settlement) for kickoffs in the next 90 min")
    print(HDR)
    csv_rows = []
    for q in orders:
        dep, x = depth_at(dep_by.get(q["market_slug"], []), lo, q["captured_at"], q["bid"])
        amb = "  AMBIGUOUS venue start " + "/".join(f"{t:%H:%M}Z" for t in sorted(gstart[q["vg"]])) \
            if len(gstart[q["vg"]]) > 1 else ""
        print(rung_line(q, dep, q["game_start_time"]) + f"  {q['event_slug']}{amb}")
        csv_rows.append([now.isoformat(), q["vg"], q["event_slug"], q["market_slug"], q["line"], q["bid"], q["ask"],
                         mid(q), round(1 - q["bid"], 4), "" if x is None else x["qty"], "" if x is None else x["price"],
                         "" if x is None else round(mins(q["captured_at"], x["captured_at"]), 1),
                         q["captured_at"].isoformat(), round(mins(q["game_start_time"], q["captured_at"]), 1),
                         "venue-start", "BUY_NO", "SHADOW"])
    print("  T-min = minutes from the quote to the EARLIEST venue start of the game (no plays pregame)")
    print(f"  rungs with ask-bid > 0.05: {sum(q['ask'] - q['bid'] > 0.05 for q in orders)} "
          "(bucket is mid-defined; a wide rung is quoted, not priced)")
    try:
        new = not os.path.exists(CSV_PATH)
        with open(CSV_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow("run_at_utc game_id event_slug market_slug line yes_bid yes_ask yes_mid no_price depth_qty "
                           "depth_price depth_age_min quote_at_utc min_to_venue_start anchor side status".split())
            w.writerows(csv_rows)
        print(f"appended {len(csv_rows)} rows to {CSV_PATH}")
    except OSError as e:
        print(f"CSV NOT written ({e}) -- run with -v /opt/meridian/artifacts:/app/artifacts")
    raise SystemExit(0)

# ---------------------------------------------------------------- replay: select, then depth, then print
picked, win_set, cal_set, why = defaultdict(list), set(), set(), defaultdict(int)
for g in games:
    ko, w_lo, w_hi = g["ko"], g["ko"] - T_EARLY, g["ko"] - T_LATE
    for slug, ss in by_slug.items():
        if ss[0]["vg"] != g["vg"]:
            continue
        win = [s for s in ss if w_lo <= s["captured_at"] <= w_hi]
        last6 = [s for s in ss if ko - SIX_H <= s["captured_at"] <= ko]
        q, cq = (win[-1] if win else None), (last6[-1] if last6 else None)
        in_win = q is not None and LO <= mid(q) < HI
        in_cal = cq is not None and min(int(mid(cq) * 10), 9) == 2     # the scan's exact bucket expression
        if in_win: win_set.add(slug)
        if in_cal: cal_set.add(slug)
        if in_cal and not in_win:
            why["scan-only: no quote in [T-60,T-5]" if q is None else
                "scan-only: window quote outside bucket, last quote before kick inside"] += 1
        if in_win and not in_cal:
            why["window-only: last quote before kick left the bucket"] += 1
        if in_win:
            y = settle(q["line"], g["h"], g["a"]) if g["h"] is not None else None
            pnl = None if y is None else 100 * ((1 - y) - (1 - q["bid"]) - FEE * q["bid"] * (1 - q["bid"]))
            picked[g["vg"]].append((q, y, pnl))
dep_by = depth_for(win_set, min(g["ko"] for g in games) - T_EARLY, hi) if win_set else {}

rows = []
for g in games:
    ko, w_lo = g["ko"], g["ko"] - T_EARLY
    gap = f"{mins(ko, g['start']):+.0f}m vs venue start" if g["start"] else "no venue start"
    if len(g["starts"]) > 1:
        gap += " AMBIGUOUS venue start " + "/".join(f"{t:%H:%M}Z" for t in sorted(g["starts"]))
    fin = f"final away {g['a']} home {g['h']}" if g["h"] is not None else "NOT SETTLED"
    pk = picked.get(g["vg"], [])
    print(f"\n{g['event_slug']}  kickoff {ko:%H:%M:%S}Z [{g['anchor']}, {gap}]  {fin}  rungs in bucket: {len(pk)}")
    if pk:
        print(HDR + f"  {'settle':>7}{'NO P&L c':>10}")
    for q, y, pnl in pk:
        dep, _ = depth_at(dep_by.get(q["market_slug"], []), w_lo, q["captured_at"], q["bid"])
        tail = ("  push/skip" if g["h"] is not None and y is None else "" if pnl is None
                else f"  {'YES' if y else 'NO':>7}{pnl:>+10.2f}")
        print(rung_line(q, dep, ko) + tail)
        if pnl is not None:
            rows.append((pnl, g["vg"]))

print("\n=== SUMMARY (buy NO at 1-bid on the LAST quote in [T-60,T-5], fee 0.06*bid*(1-bid)) ===")
print(f"games {len(games)}   games with a bucket rung {len(picked)}   rungs selected {len(win_set)}"
      f"   scored {len(rows)}   (unscored = unsettled or push)")
wide = sum(q["ask"] - q["bid"] > 0.05 for pk in picked.values() for q, _, _ in pk)
print(f"rungs with ask-bid > 0.05: {wide} (bucket is mid-defined; a wide rung is quoted, not priced; included as the rule says)")
if len(rows) >= 2:
    m, h, n, G, ge = clustered([p for p, _ in rows], [v for _, v in rows])
    print(f"mean buy-NO P&L {m:+.2f}c  95% CI [{m - h:+.2f}, {m + h:+.2f}]  n {n}  G {G}  G_eff {ge:.1f}"
          f"   estimator: fills-weighted mean, game-clustered sandwich SE" + ("   UNDERPOWERED (G < 25)" if G < 25 else ""))
else:
    print("fewer than 2 scored rungs: no interval")
print(f"\nselection vs the calibration scan (last quote within 6h of kickoff, same games, same anchor): "
      f"window {len(win_set)}  scan {len(cal_set)}  both {len(win_set & cal_set)}")
for k, v in sorted(why.items()):
    print(f"  {v:>3}  {k}")
print("  the scan additionally drops pushes and unsettled games; those are counted above, not here")
print("  depth legend: qty@price age -- latest level-0 bid sample in the window; '*' level price != quote bid; n/a none")
