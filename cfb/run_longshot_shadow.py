r"""Longshot-NO shadow lister. SHADOW ONLY: this script PLACES NOTHING.

The bet (docs/math/longshot-no-candidate.md, section 1): before kickoff, on every
CFB full-game spread rung whose YES mid = (best_bid + best_ask) / 2 is in
[0.20, 0.30), buy NO at 1 - best_bid (taking the resting YES bid), hold to
settlement, net of the taker fee coefficient * p * (1 - p) at the coefficient the
venue carried on that snapshot row (fee_coefficient, selected beside the book; the
venue raised it at 2026-09-17 04:07Z, so a replay DATE before then is charged less
than one after). That rule is a HYPOTHESIS
under a registered read on 2026-09-19 (doc section 4), not a result. This lists
what the rule would have done (replay) or would do now (live) so timing, depth
and the rung set a live process sees can be checked against the backtest.
Imports nothing from core.executor / core.polymarket; SELECT only.

Live-safety (doc section 3c), applied in BOTH modes:
  * spread cap: a rung with ask - bid > SPREAD_CAP (0.06) is listed but SKIPPED
    (never an intended order). Replay prints the P&L with and without the cap
    side by side; the registered rule itself has no cap and its line is
    unchanged.
  * venue clock: the venue carries DIFFERENT game_start_time values on
    different markets of the same game (09-12: 19:30Z on 25,961 rows and 16:00Z
    on 3,098 for one game; ESPN's first play was 16:00Z). The EARLIEST non-null
    value per game is the clock (choose_kickoff); games whose values disagree by
    more than START_DISAGREE_MIN (30) minutes are printed.

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

MODE=live: CFB games whose EARLIEST venue game_start_time is in the next 90 min,
latest snapshot per rung from the last 3h of tape, no settlement. Prints the
intended orders and APPENDS them to /app/artifacts/reads/longshot_shadow_orders.csv
-- the only thing written anywhere, and only with the artifacts mount. Header
row once (written when the file is new); columns, and nothing else, ever:
  ts_utc, league, game_id, market_slug, line, bid, ask, no_price, depth_at_bid,
  minutes_to_kickoff, kickoff_source
depth_at_bid is the latest level-0 bid quantity in the window ONLY when its
level price is the quote's bid, else empty; minutes_to_kickoff is from ts_utc
(the run) to the clock; kickoff_source is 'venue-start' (one value seen) or
'venue-start-earliest' (the values disagreed). A file whose header is not this
list is left untouched and the run says so. Cron shape (Saturday, UTC; the
crontab lines live in scripts/prod_weekend_read.sh's header, NOT installed here):

    ssh ... 'sudo -n docker run --rm -i --network meridian_default \
      -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
      -e MODE=live -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts \
      -w /app meridian-trainer python3 -' < cfb/run_longshot_shadow.py

Kickoff anchor (replay): first ESPN play wall_clock (espn_cfb_live_plays, else
espn_cfb_backfill_plays), else the venue clock above; the anchor and its gap to
the venue clock print per game (first play vs venue start: median 3 min, p90 30
min on 77 games). Live mode has no plays: venue clock. Depth: book_levels level
0 side 'bid' joined on market_snapshots.id (run_making_touch.py's QUEUE_SQL
source), fetched for the selected rungs only. Only ~7% of pregame snapshots
carry a depth row, so the LATEST sample in the window is shown with its age;
'*' = its level price is not the quote's bid; 'n/a' = no sample. Never assumed.

The decisions a live process must get right are pure functions at module level
(passes_spread_cap, choose_kickoff, buy_no_pnl_c, rung_pnl_c, write_orders_csv) so
tests/test_longshot_shadow_paper_book.py and tests/test_fee_per_row_closing.py check
them without a database; the run itself is under main() and only executes when the
file is the script.
"""
import csv
import datetime as dt
import os
from collections import Counter, defaultdict

MODE, DATE = os.environ.get("MODE", "replay"), os.environ.get("DATE", "2026-09-12")
try:
    from core.fees import recorded_fee              # the fee at the coefficient the venue carried on THAT row
except ImportError:                                  # run bare (trainer image mounts cfb/ only): the same strict form, no constant
    def recorded_fee(price, coefficient):
        if coefficient is None:
            raise ValueError("row carries no fee_coefficient; a historical read cannot charge today's")
        return float(coefficient) * price * (1.0 - price)
LO, HI = 0.20, 0.30
SPREAD_CAP = 0.06            # skip a rung whose ask - bid exceeds this (doc section 3c)
START_DISAGREE_MIN = 30      # print games whose venue start values disagree by more than this
T_EARLY, T_LATE, SIX_H = dt.timedelta(minutes=60), dt.timedelta(minutes=5), dt.timedelta(hours=6)
SPREAD = "football_team_full_game_spread"
CSV_PATH = "/app/artifacts/reads/longshot_shadow_orders.csv"
CSV_COLUMNS = ["ts_utc", "league", "game_id", "market_slug", "line", "bid", "ask", "no_price",
               "depth_at_bid", "minutes_to_kickoff", "kickoff_source"]

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
# Every distinct game_start_time a game carries is fetched; choose_kickoff picks the earliest.
START_SQL = """
SELECT DISTINCT game_id vg, game_start_time FROM market_snapshots
WHERE game_id = ANY(:gids) AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND game_start_time IS NOT NULL
"""
SNAPS_SQL = """
SELECT game_id vg, event_slug, market_slug, line::float line, best_bid::float bid, best_ask::float ask,
       fee_coefficient::float fee_coefficient, captured_at, game_start_time
FROM market_snapshots
WHERE game_id = ANY(:gids) AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
ORDER BY game_id, market_slug, captured_at
"""
# Live: a game is in scope when its EARLIEST venue start (the clock) is in the next 90 min.
LIVE_GAMES_SQL = """
SELECT game_id FROM market_snapshots
WHERE event_slug LIKE 'cfb-%' AND sports_market_type = :t AND captured_at BETWEEN :lo AND :hi
  AND game_start_time IS NOT NULL
GROUP BY game_id HAVING min(game_start_time) BETWEEN :hi AND :hi + interval '90 minutes'
"""
DEPTH_SQL = """
SELECT s.market_slug, s.captured_at, b.price::float price, b.quantity::float qty
FROM market_snapshots s JOIN book_levels b ON b.snapshot_id = s.id AND b.level_index = 0 AND b.side = 'bid'
WHERE s.market_slug = ANY(:slugs) AND s.captured_at BETWEEN :lo AND :hi
ORDER BY s.market_slug, s.captured_at
"""


# ---------------------------------------------------------------- pure decisions (tested without a DB)
def passes_spread_cap(bid, ask, cap=SPREAD_CAP):
    """True when the rung is tight enough to trade: ask - bid <= cap.

    The difference is rounded to 1e-4 first: 0.51 - 0.45 is 0.06000000000000005 in
    floats and would fail a cap of exactly 0.06 otherwise (round to tick before comparing).
    """
    return round(ask - bid, 4) <= cap


def choose_kickoff(rows):
    """The clock for one game: the EARLIEST non-null game_start_time over its rows.

    Returns (kickoff, disagreement_minutes). kickoff is None when no row carries a
    start; disagreement is latest - earliest in minutes, 0.0 when every value agrees.
    Order of rows is irrelevant; rows without the key, or with None, are ignored.
    """
    starts = sorted({r["game_start_time"] for r in rows if r.get("game_start_time") is not None})
    if not starts:
        return None, 0.0
    return starts[0], (starts[-1] - starts[0]).total_seconds() / 60


def buy_no_pnl_c(bid, y, fee):
    """Cents per $1 contract: buy NO at 1 - bid, settle y (YES = 1), at the coefficient `fee`
    the venue carried on the row the bid came from. Same formula as cfb/run_paper_book.py's
    bet_pnl(side='no') times 100; the test pins the two together at both coefficients. No
    today's-value default: every call in this file is per row, and None is refused."""
    return 100 * ((1 - y) - (1 - bid) - recorded_fee(bid, fee))


def rung_pnl_c(q, y):
    """buy_no_pnl_c on one SNAPS_SQL row: the bid and the coefficient come from the SAME
    row. A row without fee_coefficient is refused (KeyError if the column left the SELECT,
    ValueError if the venue sent NULL), never charged at today's."""
    return buy_no_pnl_c(q["bid"], y, q["fee_coefficient"])


def write_orders_csv(path, rows, columns=CSV_COLUMNS):
    """Append rows to the intended-orders CSV; the header row is written once, when
    the file is new or empty. Returns (rows_written, note). An existing file whose
    first line is not `columns` is left untouched (0 written) and the note says why:
    the alternative is one file carrying two schemas."""
    header = ",".join(columns)
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    if exists:
        with open(path, newline="") as f:
            first = f.readline().rstrip("\r\n")
        if first != header:
            return 0, f"header mismatch: file starts '{first[:160]}', expected '{header}'; NOT written"
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(columns)
        w.writerows(rows)
    return len(rows), ("header + rows written" if not exists else "rows appended")


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


def depth_at(samples, w_lo, t_quote, bid):
    """Latest sample for the rung in [w_lo, t_quote]; '*' if its level price is not the quote's bid."""
    d = [x for x in samples if w_lo <= x["captured_at"] <= t_quote]
    if not d:
        return "n/a", None
    x = d[-1]; flag = "" if abs(x["price"] - bid) < 1e-9 else "*"
    return f"{flag}{x['qty']:.0f}@{x['price']:.2f} {mins(x['captured_at'], t_quote):+.0f}m", x


def depth_at_bid_qty(x, bid):
    """CSV depth_at_bid: the sample's quantity only when its level price IS the quote's bid."""
    return x["qty"] if x is not None and abs(x["price"] - bid) < 1e-9 else ""


HDR = f"    {'rung':<44}{'line':>6}{'bid':>6}{'ask':>6}{'mid':>7}{'NO@':>6}  {'depth@bid(age)':<22}{'T-min':>6}"
def rung_line(s, dep, t_ko):
    return (f"    {s['market_slug']:<44}{s['line']:>+6.1f}{s['bid']:>6.2f}{s['ask']:>6.2f}{mid(s):>7.4f}"
            f"{1 - s['bid']:>6.2f}  {dep:<22}{mins(t_ko, s['captured_at']):>6.1f}")


def summary_line(rows, label=""):
    """The interval line; label '' keeps the registered (no-cap) line byte-identical."""
    if len(rows) < 2:
        print(f"{label}fewer than 2 scored rungs: no interval"); return
    m, h, n, G, ge = clustered([p for p, _ in rows], [v for _, v in rows])
    print(f"{label}mean buy-NO P&L {m:+.2f}c  95% CI [{m - h:+.2f}, {m + h:+.2f}]  n {n}  G {G}  G_eff {ge:.1f}"
          f"   estimator: fills-weighted mean, game-clustered sandwich SE" + ("   UNDERPOWERED (G < 25)" if G < 25 else ""))


def print_start_disagreements(games):
    """Games whose venue game_start_time values disagree by > START_DISAGREE_MIN minutes."""
    bad = [g for g in games if g["disagree_min"] > START_DISAGREE_MIN]
    print(f"venue game_start_time disagrees by > {START_DISAGREE_MIN} min within a game: {len(bad)} of {len(games)}"
          + ("" if not bad else " -- clock = earliest; " + "; ".join(
              f"{g.get('event_slug', g['vg'])} " + "/".join(f"{t:%m-%d %H:%M}Z" for t in g["starts"])
              + f" ({g['disagree_min']:.0f}m)" for g in bad)))


def main():
    from sqlalchemy import create_engine, event, text

    eng = create_engine(os.environ["DATABASE_URL"])
    @event.listens_for(eng, "connect")
    def _no_parallel(dbapi_conn, _rec):  # 64MB /dev/shm: parallel workers die on big scans
        cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close()
        dbapi_conn.commit()

    def depth_for(slugs, lo, hi):
        """Level-0 bid samples for the selected rungs only, keyed by slug."""
        out = defaultdict(list)
        with eng.connect() as c:
            for r in c.execute(text(DEPTH_SQL), {"slugs": sorted(slugs), "lo": lo, "hi": hi}):
                out[r.market_slug].append(dict(r._mapping))
        return out

    def venue_clock(c, gids, lo, hi):
        """Per game: (earliest start, disagreement minutes, every distinct start) from START_SQL."""
        rows = defaultdict(list)
        for r in c.execute(text(START_SQL), {"gids": gids, "t": SPREAD, "lo": lo, "hi": hi}):
            rows[r.vg].append(dict(r._mapping))
        out = {}
        for vg in gids:
            ko, dis = choose_kickoff(rows[vg])
            out[vg] = (ko, dis, sorted({r["game_start_time"] for r in rows[vg]}))
        return out

    with eng.connect() as c:
        now = c.execute(text("SELECT now()")).scalar()
        print(f"longshot-NO shadow  MODE={MODE}  bucket YES mid [{LO},{HI})  db now {now:%Y-%m-%d %H:%M}Z  "
              f"SHADOW: nothing is placed")
        if MODE == "live":
            lo, hi = now - dt.timedelta(hours=3), now
            gids = [r[0] for r in c.execute(text(LIVE_GAMES_SQL), {"t": SPREAD, "lo": lo, "hi": hi})]
            clock = venue_clock(c, gids, lo, hi)
            games = [{"vg": vg, "ko": clock[vg][0], "disagree_min": clock[vg][1], "starts": clock[vg][2]} for vg in gids]
        else:
            d0 = dt.datetime.fromisoformat(DATE).replace(tzinfo=dt.timezone.utc)
            games = [dict(r._mapping) for r in c.execute(text(GAMES_SQL), {"d": DATE})]
            gids = [g["vg"] for g in games]
            clock = venue_clock(c, gids, d0 - dt.timedelta(hours=12), d0 + dt.timedelta(hours=36))
            for g in games:
                g["start"], g["disagree_min"], g["starts"] = clock[g["vg"]]
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
        for g in games:
            g["event_slug"] = next((s["event_slug"] for s in snaps if s["vg"] == g["vg"]), g["vg"])
        print_start_disagreements(games)
        ko_of = {g["vg"]: g for g in games}
        cands = [ss[-1] for _, ss in sorted(by_slug.items()) if LO <= mid(ss[-1]) < HI]
        orders = [q for q in cands if passes_spread_cap(q["bid"], q["ask"])]
        skipped = [q for q in cands if not passes_spread_cap(q["bid"], q["ask"])]
        dep_by = depth_for({q["market_slug"] for q in cands}, lo, hi) if cands else {}
        print(f"\n{len(orders)} intended orders (BUY NO at 1-bid, hold to settlement) for kickoffs in the next 90 min;"
              f" {len(skipped)} rung(s) in the bucket skipped by the spread cap ask-bid > {SPREAD_CAP}")
        print(HDR)
        csv_rows = []
        for q in cands:
            g = ko_of[q["vg"]]; ko = g["ko"]
            dep, x = depth_at(dep_by.get(q["market_slug"], []), lo, q["captured_at"], q["bid"])
            amb = "  AMBIGUOUS venue start " + "/".join(f"{t:%H:%M}Z" for t in g["starts"]) if len(g["starts"]) > 1 else ""
            cap = "" if passes_spread_cap(q["bid"], q["ask"]) else "  SKIP spread>cap"
            print(rung_line(q, dep, ko) + f"  {q['event_slug']}{amb}{cap}")
            if not cap:
                csv_rows.append([now.isoformat(), q["event_slug"].split("-")[0], q["vg"], q["market_slug"], q["line"],
                                 q["bid"], q["ask"], round(1 - q["bid"], 4), depth_at_bid_qty(x, q["bid"]),
                                 round(mins(ko, now), 1), "venue-start" if g["disagree_min"] == 0 else "venue-start-earliest"])
        print("  T-min = minutes from the quote to the EARLIEST venue start of the game (no plays pregame)")
        try:
            n, note = write_orders_csv(CSV_PATH, csv_rows)
            print(f"{CSV_PATH}: {n} rows, {note}")
        except OSError as e:
            print(f"CSV NOT written ({e}) -- run with -v /opt/meridian/artifacts:/app/artifacts")
        raise SystemExit(0)

    # ------------------------------------------------------------ replay: select, then depth, then print
    print_start_disagreements(games)
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
                pnl = None if y is None else rung_pnl_c(q, y)
                picked[g["vg"]].append((q, y, pnl, passes_spread_cap(q["bid"], q["ask"])))
    dep_by = depth_for(win_set, min(g["ko"] for g in games) - T_EARLY, hi) if win_set else {}

    rows, rows_cap = [], []
    for g in games:
        ko, w_lo = g["ko"], g["ko"] - T_EARLY
        gap = f"{mins(ko, g['start']):+.0f}m vs venue start" if g["start"] else "no venue start"
        if len(g["starts"]) > 1:
            gap += " AMBIGUOUS venue start " + "/".join(f"{t:%H:%M}Z" for t in g["starts"])
        fin = f"final away {g['a']} home {g['h']}" if g["h"] is not None else "NOT SETTLED"
        pk = picked.get(g["vg"], [])
        print(f"\n{g['event_slug']}  kickoff {ko:%H:%M:%S}Z [{g['anchor']}, {gap}]  {fin}  rungs in bucket: {len(pk)}")
        if pk:
            print(HDR + f"  {'settle':>7}{'NO P&L c':>10}")
        for q, y, pnl, ok in pk:
            dep, _ = depth_at(dep_by.get(q["market_slug"], []), w_lo, q["captured_at"], q["bid"])
            tail = ("  push/skip" if g["h"] is not None and y is None else "" if pnl is None
                    else f"  {'YES' if y else 'NO':>7}{pnl:>+10.2f}")
            print(rung_line(q, dep, ko) + tail + ("" if ok else "  spread>cap"))
            if pnl is not None:
                rows.append((pnl, g["vg"]))
                if ok:
                    rows_cap.append((pnl, g["vg"]))

    # The coefficient is printed as a tally over the SCORED rungs, not as a constant: it is
    # whatever the venue carried on each row, and a DATE on either side of 2026-09-17 shows
    # one value while a run that straddled it would show two.
    coefs = Counter(q["fee_coefficient"] for pk in picked.values() for q, _, pnl, _ in pk if pnl is not None)
    print(f"\n=== SUMMARY (buy NO at 1-bid on the LAST quote in [T-60,T-5], fee = the row's coefficient*bid*(1-bid); "
          f"coefficients on scored rungs: {', '.join(f'{k:g} x{n}' for k, n in sorted(coefs.items())) or 'none'}) ===")
    print(f"games {len(games)}   games with a bucket rung {len(picked)}   rungs selected {len(win_set)}"
          f"   scored {len(rows)}   (unscored = unsettled or push)")
    n_sel = sum(len(pk) for pk in picked.values()); n_skip = sum(not ok for pk in picked.values() for _, _, _, ok in pk)
    print(f"spread cap ask-bid <= {SPREAD_CAP}: {n_skip} of {n_sel} selected rungs skipped, {len(rows_cap)} scored under the cap"
          f"   (bucket is mid-defined; a wide rung is quoted, not priced; the registered rule has no cap)")
    summary_line(rows)                                   # the registered rule, no cap: line unchanged
    summary_line(rows_cap, "with spread cap: ")          # what a live process would have taken
    print(f"\nselection vs the calibration scan (last quote within 6h of kickoff, same games, same anchor): "
          f"window {len(win_set)}  scan {len(cal_set)}  both {len(win_set & cal_set)}")
    for k, v in sorted(why.items()):
        print(f"  {v:>3}  {k}")
    print("  the scan additionally drops pushes and unsettled games; those are counted above, not here")
    print("  depth legend: qty@price age -- latest level-0 bid sample in the window; '*' level price != quote bid; n/a none")


if __name__ == "__main__":
    main()
