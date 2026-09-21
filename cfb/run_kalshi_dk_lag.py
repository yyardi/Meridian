"""Does Kalshi's winner market lag the DraftKings line earlier in the week?

THE QUESTION. The operator's friend says he makes money trading Kalshi NFL/CFB
winners with a model. Kalshi's CLOSE is not soft against DraftKings
(run_kalshi_early_vs_close.py), so the only place left is EARLIER in the week:
does Kalshi's pregame mid trail the sportsbook line, so that DK's current
number predicts where Kalshi goes next?

THE RULE (placed nowhere: this reads two tapes and prints tables). At each
h in (72, 48, 24, 12, 6, 2, 1) hours before kickoff, t = ko-h: DraftKings'
power-devigged home win probability p_dk (last change-detected row <= t)
against Kalshi's home-ticker mid (last snapshot <= t, at most STALE old). If
p_dk - mid > fee + half-spread buy YES at yes_ask; if mid - p_dk exceeds it
buy NO at 1 - yes_bid; hold to settlement. Net per $1 contract = payout -
price - 0.07*p*(1-p), p the touch paid. Per league x horizon, game-clustered
95% interval; G < 25 is printed UNDERPOWERED, never read as a result.
ALSO: the DK - Kalshi gap distribution per horizon (median |gap|, p90, share
beyond the cost threshold) and a lag control needing no settlement:
|DK(t) - K(t-1h)| minus |DK(t) - K(t)| > 0 means the hour-earlier Kalshi
price sat further from today's DK number, i.e. Kalshi lags; the mirror
|DK(t-1h) - K(t)| asks the same of DK.

DATA. DraftKings: sportsbook_odds, a row only when the line CHANGES (recorder
from 2026-09-12 16:45Z); the line at t is the last row <= t; a NULL moneyline
there means DK offers none (21 games this week, all 35+ pt spreads). Kalshi:
kalshi_snapshots, yes_bid/yes_ask as probabilities; the ticker ends in the
team code, second_code is home (13/13 NFL games agree with DK's home-moneyline
sign, 2026-09-13). NFL joins on kalshi_games.espn_game_id; CFB has none, so
Kalshi codes are matched to the Polymarket slug tokens in cfb_game_map and,
as a second route, to the ESPN abbreviations in DraftKings' raw payload (plus
a by-eye alias table): exact, then prefix, then containment LAST; two games
or both orientations fitting is refused, the routes must agree, the tier is
printed as provenance, and a >35pp gap at the nearest horizon is flagged as a
mis-pair. Kickoff: ESPN's first play, else kalshi_games.game_start_time.
Settlement: ESPN final (state 'post', or Q4 at 0:00 with a winner -- the
recorder stops BEFORE ESPN flips to post, so a bare "period >= 4" would read
a live Q4 score as a final), else espn_cfb_backfill_games, else Kalshi's own
result; disagreeing sources drop the game.

RUN (read-only; one query at a time; every big table bounded on captured_at):
  H=$(tr -d '[:space:]' < ~/.meridian-server)
  ssh -i ~/.ssh/meridian-aws.pem -o BatchMode=yes -o ConnectTimeout=20 ubuntu@$H \
    'sudo -n docker run --rm -i --network meridian_default \
     -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
     -w /app meridian-trainer python3 -' < cfb/run_kalshi_dk_lag.py
First run 2026-09-13 is a SMOKE TEST of the pipeline: the tape is NFL week 1
(Kalshi from 09-12 20:12Z, DK from 09-12 16:45Z, so h <= 24 at most) and the
09-13 games are unsettled at run time. The registered read is Sat 2026-09-19.
"""
import bisect
import datetime as dt
import os
import sys
from collections import defaultdict

from sqlalchemy import create_engine, event, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd())  # run bare: the trainer image mounts cfb/ alone; piped over stdin (nightly_scan.sh) there is no __file__ and cwd is the repo root
from core.fees import KALSHI_TAKER as FEE  # noqa: E402  Kalshi's quadratic taker coefficient; no per-row column exists on kalshi_snapshots
HORIZONS = (72, 48, 24, 12, 6, 2, 1)
UTC = dt.timezone.utc
DK_START = dt.datetime(2026, 9, 12, 16, 45, tzinfo=UTC)  # change-detected DK recorder start
STALE = dt.timedelta(minutes=20)                         # Kalshi polls ~60s; older is a gap, not a price
SERIES = {"nfl": "KXNFLGAME", "cfb": "KXNCAAFGAME"}
H1 = dt.timedelta(hours=1)
# ESPN abbreviation -> Kalshi code, each read off the Kalshi title by eye on 2026-09-13; exact-tier only.
ALIAS = {"CLT": "CHAR", "BOIS": "BSU", "MERC": "MHU", "M-OH": "MOH", "STO": "STNH", "CCU": "CCAR", "W&M": "WM",
         "APSU": "PEAY", "UTC": "CHAT", "EKU": "EKY", "BCU": "COOK", "UAPB": "ARPB", "MTSU": "MTU", "OU": "OKLA",
         "TA&M": "TXAM", "NCSU": "NCST", "NU": "NW", "IU": "IND"}

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(conn, _rec):
    cur = conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); conn.commit()

Q = dict(
  games="""SELECT game_key gk, league lg, first_code fc, second_code sc, espn_game_id eg, game_start_time gst,
                  local_date::date d FROM kalshi_games WHERE league IN ('nfl','cfb') AND local_date >= :d0""",
  dk="""SELECT espn_game_id eg, captured_at t, home_moneyline::float hm, away_moneyline::float am, game_date::date d,
               raw->'awayTeamOdds'->'team'->>'abbreviation' aab, raw->'homeTeamOdds'->'team'->>'abbreviation' hab
        FROM sportsbook_odds WHERE provider_name='DraftKings' AND captured_at >= :t0 ORDER BY espn_game_id, captured_at""",
  map="SELECT espn_game_id eg, event_slug s, espn_date d FROM cfb_game_map WHERE division <> 'NFL' AND espn_date >= :d0",
  ko="SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_live_plays WHERE wall_clock >= :t0 GROUP BY 1",
  fin="""SELECT game_id eg, state, period, display_clock ck, home_score h, away_score a FROM (
           SELECT DISTINCT ON (game_id) * FROM espn_cfb_game_state WHERE first_seen_at >= :t0
           ORDER BY game_id, first_seen_at DESC) x WHERE home_score IS NOT NULL AND away_score IS NOT NULL""",
  bf="SELECT game_id eg, home_score h, away_score a FROM espn_cfb_backfill_games WHERE home_score IS NOT NULL AND away_score IS NOT NULL",
  kres="""SELECT DISTINCT game_key gk, series_ticker st, ticker, result FROM kalshi_snapshots
          WHERE captured_at >= :t0 AND market_type='winner' AND result IN ('yes','no')""",
  snap="""SELECT ticker, captured_at t, yes_bid::float b, yes_ask::float a FROM kalshi_snapshots
          WHERE game_key=:gk AND series_ticker=:st AND market_type='winner' AND captured_at BETWEEN :lo AND :hi
            AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL AND yes_bid > 0 AND yes_ask < 1 AND yes_ask >= yes_bid
          ORDER BY captured_at""")

def implied(ml): return -ml / (-ml + 100) if ml < 0 else 100 / (ml + 100)
def power_devig(hm, am):
    ph, pa = implied(hm), implied(am); lo, hi = 1.0, 20.0
    for _ in range(60):
        k = (lo + hi) / 2
        if ph ** k + pa ** k > 1: lo = k
        else: hi = k
    k = (lo + hi) / 2
    return ph ** k / (ph ** k + pa ** k)

def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n; res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge

def pct(xs, q): xs = sorted(xs); return xs[int(q * (len(xs) - 1))]
def fmt_ci(vals, keys, unit="c"):
    m, hw, n, G, ge = clustered(vals, keys)
    return f"{m:+7.2f}{unit} [{m-hw:+6.2f}, {m+hw:+6.2f}]  G={G:<3d} G_eff={ge:5.1f}{'  UNDERPOWERED' if G < 25 else ''}"

def _fit(c, t, tier):
    c, t = c.lower(), t.lower()
    if len(c) < 2 or len(t) < 2: return False
    return c == t if tier == 0 else (t.startswith(c) or c.startswith(t)) if tier == 1 else (c in t or t in c)
def match(g, cands):
    """cands: [(key, away_tok, home_tok, date)]. Exact, then prefix, then containment LAST; the first tier
    with a fit decides; two games or both orientations there -> refused. Returns ((key, home_code), why)."""
    for tier in (0, 1, 2):
        hits = set()
        for key, at, ht, d in cands:
            if d is None or abs((d - g["d"]).days) > 1: continue
            if _fit(g["fc"], at, tier) and _fit(g["sc"], ht, tier): hits.add((key, g["sc"]))
            if _fit(g["fc"], ht, tier) and _fit(g["sc"], at, tier): hits.add((key, g["fc"]))
        if len(hits) == 1: return hits.pop(), ("exact", "prefix", "contain")[tier]
        if hits: return None, "ambiguous"
    return None, "none"

def last_at(ts, t):
    i = bisect.bisect_right(ts, t); return i - 1 if i else None

with eng.connect() as c:
    q = lambda k, **p: [dict(r._mapping) for r in c.execute(text(Q[k]), p)]
    t0 = DK_START - dt.timedelta(hours=2); d0 = DK_START.date() - dt.timedelta(days=1)
    games = q("games", d0=d0); dk = q("dk", t0=DK_START); maps = q("map", d0=d0)
    ko = {r["eg"]: r["ko"] for r in q("ko", t0=t0)}
    fin, n_q4live = defaultdict(set), 0
    for r in q("bf"):
        if r["h"] != r["a"]: fin[r["eg"]].add(r["h"] > r["a"])
    for r in q("fin", t0=t0):
        if r["h"] == r["a"]: continue
        if r["state"] == "post" or (r["period"] == 4 and r["ck"] == "0:00"): fin[r["eg"]].add(r["h"] > r["a"])
        elif r["period"] and r["period"] >= 4: n_q4live += 1
    kres = defaultdict(dict)
    for r in q("kres", t0=t0): kres[(r["st"], r["gk"])][r["ticker"].rsplit("-", 1)[1]] = r["result"]
    dkrows, dkmeta = defaultdict(list), {}
    for r in dk:
        dkrows[r["eg"]].append((r["t"], r["hm"], r["am"]))
        if r["aab"] and r["hab"] and r["d"]: dkmeta.setdefault(r["eg"], (r["aab"], r["hab"], r["d"]))
    nfl_eg = {g["eg"] for g in games if g["lg"] == "nfl" and g["eg"]}
    cands_map = [(m["eg"], t[1], t[2], m["d"]) for m in maps for t in [m["s"].split("-")] if len(t) == 6]
    cands_abbr = [(eg, ALIAS.get(a, a), ALIAS.get(h, h), d) for eg, (a, h, d) in dkmeta.items() if eg not in nfl_eg]
    print(f"kalshi_dk_lag  run {dt.datetime.now(UTC):%Y-%m-%d %H:%MZ}   DK tape {min(r['t'] for r in dk):%m-%d %H:%MZ}"
          f"..{max(r['t'] for r in dk):%m-%d %H:%MZ} on {len(dkrows)} games   registered read Sat 2026-09-19")
    print("SMOKE TEST until a full week is on tape: NFL week 1 only, h <= 24, 09-13 games unsettled at run time.")
    print(f"ESPN finals: {len(fin)} games; {n_q4live} games whose LAST state row is a live Q4/OT score are NOT settled here")
    rows, funnel, flagged = [], defaultdict(lambda: defaultdict(int)), []
    for g in games:
        lg, F = g["lg"], funnel[g["lg"]]; F["kalshi games"] += 1
        if lg == "nfl":
            eg, home = g["eg"], g["sc"]
            if not eg: F["no espn id"] += 1; continue
        else:
            m1, w1 = match(g, cands_map); m2, w2 = match(g, cands_abbr)
            if "ambiguous" in (w1, w2): F["refused ambiguous"] += 1; continue
            if m1 and m2 and m1 != m2: F["refused routes disagree"] += 1; continue
            if not (m1 or m2): F["unmatched"] += 1; continue
            F[f"matched {'both' if m1 and m2 else 'map' if m1 else 'dk-abbr'}:"
              f"{'/'.join(w for m, w in ((m1, w1), (m2, w2)) if m)}"] += 1   # tier is provenance: print it
            eg, home = m1 or m2
        if eg not in dkrows: F["no DK rows"] += 1; continue
        kick = ko.get(eg) or g["gst"]
        if kick is None: F["no kickoff"] += 1; continue
        lo = max(kick - dt.timedelta(hours=HORIZONS[0] + 2), DK_START - H1)
        snaps = q("snap", gk=g["gk"], st=SERIES[lg], lo=lo, hi=kick)
        hs = [s for s in snaps if s["ticker"].endswith("-" + home)]
        if not hs:   # only the away ticker: NO on away is YES on home, no_bid = 1 - yes_ask (verified 08-05)
            hs = [dict(t=s["t"], b=1 - s["a"], a=1 - s["b"]) for s in snaps if not s["ticker"].endswith("-" + home)]
        if not hs: F["no Kalshi tape"] += 1; continue
        F["with both feeds"] += 1
        outs = set(fin.get(eg, set())); kr = kres.get((SERIES[lg], g["gk"]), {}); away = g["fc"] if home == g["sc"] else g["sc"]
        if home in kr: outs.add(kr[home] == "yes")
        elif away in kr: outs.add(kr[away] == "no")
        if len(outs) > 1: F["settlement sources disagree"] += 1; continue
        y = int(outs.pop()) if outs else None
        F["settled"] += y is not None
        kts, dts = [s["t"] for s in hs], [r[0] for r in dkrows[eg]]
        def K(t):
            i = last_at(kts, t)
            return None if i is None or t - kts[i] > STALE else (hs[i]["b"], hs[i]["a"], (t - kts[i]).total_seconds() / 60)
        def D(t):
            i = last_at(dts, t)
            return None if i is None or dkrows[eg][i][1] is None or dkrows[eg][i][2] is None else \
                (power_devig(dkrows[eg][i][1], dkrows[eg][i][2]), (t - dts[i]).total_seconds() / 3600)
        grows = []
        for h in HORIZONS:
            t = kick - dt.timedelta(hours=h); k, d = K(t), D(t)
            if not k or not d: continue
            kl, dl = K(t - H1), D(t - H1)
            grows.append(dict(lg=lg, gk=g["gk"], h=h, p=d[0], b=k[0], a=k[1], y=y, dk_age=d[1], k_age=k[2],
                              kl=(kl[0] + kl[1]) / 2 if kl else None, pl=dl[0] if dl else None, kick=kick))
        if grows and abs(grows[-1]["p"] - (grows[-1]["b"] + grows[-1]["a"]) / 2) > 0.35:
            flagged.append((lg, g["gk"], eg, home, grows[-1]["h"], grows[-1]["p"], grows[-1]["b"])); F["flagged mis-pair"] += 1
            continue
        rows += grows

for lg in ("nfl", "cfb"):
    print(f"\n=== {lg} ===  " + "  ".join(f"{k} {v}" for k, v in sorted(funnel[lg].items())))
    R = [r for r in rows if r["lg"] == lg]
    if len({r["gk"] for r in R}) <= 40:
        for gk in sorted({r["gk"] for r in R}):
            r = [x for x in R if x["gk"] == gk][-1]; mid = (r["b"] + r["a"]) / 2
            print(f"   {gk:<16} ko {r['kick']:%m-%d %H:%M}Z  T-{r['h']:<2}  DK {r['p']:.3f}  K {r['b']:.2f}/{r['a']:.2f}"
                  f"  gap {100*(r['p']-mid):+5.1f}c  settled {'-' if r['y'] is None else r['y']}")
    print(f"  {'T-h':>4}{'games':>6}  {'DKage_h':>7}{'Kage_m':>7}{'hsprd':>6}  {'|gap| med':>9}{'p90':>6}{'>thr':>6}  "
          f"{'LAG |DK-K(-1h)| minus |DK-K| (Kalshi lags if >0)':<50}  {'MIRROR |DK(-1h)-K| minus |DK-K| (DK lags if >0)'}")
    for h in HORIZONS:
        rs = [r for r in R if r["h"] == h]
        if not rs: print(f"  {h:>4}{0:>6}  no rows"); continue
        gaps = [r["p"] - (r["b"] + r["a"]) / 2 for r in rs]
        over = sum(abs(gp) > (r["a"] - r["b"]) / 2 + FEE * (r["a"] if gp > 0 else r["b"]) * (1 - (r["a"] if gp > 0 else r["b"]))
                   for gp, r in zip(gaps, rs)) / len(rs)
        lag = [(abs(r["p"] - r["kl"]) - abs(gp)) * 100 for gp, r in zip(gaps, rs) if r["kl"] is not None]
        mir = [(abs(r["pl"] - (r["b"] + r["a"]) / 2) - abs(gp)) * 100 for gp, r in zip(gaps, rs) if r["pl"] is not None]
        lk = [r["gk"] for r in rs if r["kl"] is not None]; mk = [r["gk"] for r in rs if r["pl"] is not None]
        print(f"  {h:>4}{len(rs):>6}  {pct([r['dk_age'] for r in rs], .5):>7.1f}{pct([r['k_age'] for r in rs], .5):>7.1f}"
              f"{100*pct([(r['a']-r['b'])/2 for r in rs], .5):>5.1f}c  {100*pct([abs(x) for x in gaps], .5):>8.1f}c"
              f"{100*pct([abs(x) for x in gaps], .9):>5.1f}c{100*over:>5.0f}%  "
              f"{fmt_ci(lag, lk) if len(lag) > 1 else 'no K(-1h)':<50}  {fmt_ci(mir, mk) if len(mir) > 1 else 'no DK(-1h)'}")
    print("  --- P&L of the rule on settled games, net c per $1 contract (fee 0.07*p*(1-p) at the touch) ---")
    for h in HORIZONS + ("all",):
        rs = [r for r in R if r["y"] is not None and (h == "all" or r["h"] == h)]
        pnl, keys, side = [], [], defaultdict(int)
        for r in rs:
            gp = r["p"] - (r["b"] + r["a"]) / 2
            if gp > (r["a"] - r["b"]) / 2 + FEE * r["a"] * (1 - r["a"]):
                pnl.append(100 * (r["y"] - r["a"] - FEE * r["a"] * (1 - r["a"]))); keys.append(r["gk"]); side["YES"] += 1
            elif -gp > (r["a"] - r["b"]) / 2 + FEE * r["b"] * (1 - r["b"]):
                pnl.append(100 * ((1 - r["y"]) - (1 - r["b"]) - FEE * r["b"] * (1 - r["b"]))); keys.append(r["gk"]); side["NO"] += 1
        tag = f"{str(h):>4}  settled {len(rs):>4}  trades {len(pnl):>4} (YES {side['YES']}, NO {side['NO']})"
        print(f"  {tag}  {fmt_ci(pnl, keys) if len(pnl) >= 2 else 'too few trades'}")
if flagged:
    print("\nFLAGGED as suspected mis-pairs (>35pp DK-Kalshi gap at the nearest horizon), excluded:")
    for f in flagged: print("   ", f)
print("\nG < 25 is UNDERPOWERED: a direction, never a result. Nothing here is placed; the tape is the only input.")
