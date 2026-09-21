"""Cross-venue pregame football: Polymarket US vs Kalshi on the same games. Read-only; nothing is placed.
(A) SAME-INSTANT DISCREPANCY. Every Polymarket sweep of a matched contract vs the nearest Kalshi snapshot within
    MATCH (5 min): kalshi_mid - poly_mid in cents, in the KALSHI CONTRACT'S YES FRAME ("TEAM wins", "TEAM wins by
    over X", "over X"). Polymarket YES is always the away side (aec: away wins; asc: away margin + line > 0; tsc:
    over), so Kalshi(away, X) == asc line -X and Kalshi(home, X) == NO on asc line +X (book complemented: bid' =
    1 - ask, ask' = 1 - bid). Dutch = YES at one venue's ask + NO at the other's 1 - bid (either way), both fees, < 1.
(B) WHO IS STALE. Pairs with |gap| > 3c at t0; t1 = the next Polymarket sweep 30..90 min later (pregame sweeps
    are ~42 min apart, so an exact +60 does not exist) with Kalshi within MATCH of it. Fraction closed by a venue =
    its own move toward the other / gap at t0 (1 = closed it all); one episode per contract per window; horizon printed.
(C) KALSHI LONGSHOT RUNG. Spread contracts whose YES mid is in [0.20, 0.30) at the LAST Kalshi quote before
    kickoff: buy NO at 1 - yes_bid, net of the Kalshi taker fee. Settled from ESPN finals in the DB
    (espn_cfb_game_state 'post' or Q4 0:00, else espn_cfb_backfill_games: the DB image of the ESPN schedule the
    repo's kalshi_settled analysis settles on). SETTLE_VENUE=1 (inside meridian-api) also reads the matched
    Polymarket rung's settlement endpoint: it settles rungs ESPN's tape missed (the recorder stops before ESPN
    flips to post) and is counted against ESPN wherever both exist. Split by the named team's side: AWAY is the
    Polymarket line's rung (asc line -X at YES mid 0.2-0.3); HOME is the complement of its 0.7-0.8 mirror.
FEES. Kalshi 0.07*p*(1-p) (docs/math/the-rebate.md: NCAAF series quadratic_with_maker_fees, multiplier 1; the
venue's round-up to the cent is not applied; kalshi_snapshots carries no fee field, so this is ONE constant, FK);
Polymarket taker c*p*(1-p) at the coefficient recorded on EACH sweep's own market_snapshots row (the venue raised it
on 2026-09-17; a sweep is charged what it was charged, never today's constant). MATCHING. Kalshi game -> cfb_game_map
game on date +-1, BOTH teams, exact then prefix then containment LAST, over (Kalshi code vs slug token) OR (Kalshi
title vs ESPN display name); orientation from ESPN's home/away names, never ticker order; two games or both
orientations at the winning tier -> refused; the tier is printed. A matched game whose winner mids disagree by
> 35pp at the last pregame pair is flagged and dropped (side-flip fingerprint). Kickoff = ESPN first play, else the
EARLIEST venue game_start_time; pregame instants only. ESTIMATOR: fills-weighted mean, game-clustered sandwich SE
(cluster = game), G < 25 printed UNDERPOWERED and kept.
RUN: docker-run recipe in docs/HANDOFF_2026-09-13.md; env LEAGUE=cfb|nfl, D0/D1 slate dates, SETTLE_VENUE=1 in meridian-api.
"""
import bisect, datetime as dt, os, re, sys
from collections import defaultdict
from sqlalchemy import create_engine, event, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in globals() else os.getcwd())  # run bare: the trainer image mounts cfb/ alone; piped over stdin (nightly_scan.sh) there is no __file__ and cwd is the repo root
from core.fees import KALSHI_TAKER as FK, recorded_fee  # noqa: E402  FK: Kalshi's one constant; recorded_fee: the Polymarket row's own
GAP, LO, HI, FLAG = 3.0, 0.20, 0.30, 35.0
MATCH, B_LO, B_HI, DAY = (dt.timedelta(minutes=m) for m in (5, 30, 90, 1440))
LG, D0, D1 = os.environ.get("LEAGUE", "cfb"), os.environ.get("D0", "2026-09-11"), os.environ.get("D1", "2026-09-13")
SER, DIV = {"cfb": "KXNCAAF%", "nfl": "KXNFL%"}[LG], ("= 'NFL'" if LG == "nfl" else "<> 'NFL'")
PT = {"football_team_full_game_winner": "winner", "football_team_full_game_spread": "spread", "football_team_full_game_total": "total"}
VEN = None
if os.environ.get("SETTLE_VENUE"): from core.polymarket.client import PolymarketGatewayClient; VEN = PolymarketGatewayClient()
Q = dict(
 kg="SELECT game_key gk, first_code fc, second_code sc, title, local_date::date d FROM kalshi_games WHERE league = :lg AND local_date::date BETWEEN :d0 AND :d1",
 gm=f"""SELECT espn_game_id eg, venue_game_id vg, event_slug s, home_espn_name hn, away_espn_name an, espn_date d FROM cfb_game_map
        WHERE division {DIV} AND venue_game_id IS NOT NULL AND espn_date BETWEEN :d0 AND :d1""",
 ko="SELECT game_id eg, min(wall_clock) ko FROM espn_cfb_live_plays WHERE game_id = ANY(:egs) AND wall_clock BETWEEN :lo AND :hi GROUP BY 1",
 fin="""SELECT game_id eg, home_score h, away_score a FROM (SELECT DISTINCT ON (game_id) * FROM espn_cfb_game_state WHERE first_seen_at >= :lo
        ORDER BY game_id, first_seen_at DESC) x WHERE home_score IS NOT NULL AND (state = 'post' OR (period >= 4 AND display_clock = '0:00'))""",
 bf="SELECT game_id eg, home_score h, away_score a FROM espn_cfb_backfill_games WHERE game_id = ANY(:egs) AND home_score IS NOT NULL",
 ks="""SELECT ticker, market_type t, floor_strike::float f, captured_at ts, yes_bid::float b, yes_ask::float a FROM kalshi_snapshots
       WHERE game_key = :gk AND series_ticker LIKE :ser AND captured_at BETWEEN :lo AND :hi AND yes_bid > 0 AND yes_ask < 1 AND yes_ask >= yes_bid ORDER BY captured_at""",
 pm="""SELECT sports_market_type t, line::float line, captured_at ts, best_bid::float b, best_ask::float a, fee_coefficient::float fc,
       game_start_time gst FROM market_snapshots
       WHERE game_id = :vg AND sports_market_type = ANY(:ts) AND captured_at BETWEEN :lo AND :hi AND best_bid > 0 AND best_ask < 1 AND best_ask >= best_bid ORDER BY captured_at""")

def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n; res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge
def ci(vals, keys, u="c"):
    if len(vals) < 2: return f"n={len(vals)} too few"
    m, hw, n, G, ge = clustered(vals, keys)
    return f"{m:+7.2f}{u} [{m-hw:+7.2f}, {m+hw:+7.2f}]  n={n:<5d} G={G:<3d} G_eff={ge:5.1f}{'  UNDERPOWERED' if G < 25 else ''}"
def pct(xs, q): xs = sorted(xs); return xs[int(round(q * (len(xs) - 1)))]
def fee(p, th): return th * p * (1 - p)                              # Kalshi only: FK is the one coefficient it has
def dutch_cost(kb, ka, pb, pa, pc):
    """The cheaper dutch, fees in: YES at one venue's ask + NO at the other's 1 - bid. Kalshi at FK; Polymarket at
    `pc`, the fee_coefficient recorded on THIS sweep's row -- the venue raised it on 2026-09-17 and a sweep from
    before then is charged what it was charged. None raises (core.fees.recorded_fee), never today's constant."""
    return min(ka + (1 - pb) + fee(ka, FK) + recorded_fee(pb, pc), pa + (1 - kb) + recorded_fee(pa, pc) + fee(kb, FK))
def norm(s): return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", (s or "").lower()).replace("st.", "state"))
def fit(k, e, tier):
    for x, y in zip(k, e):
        if len(x) < 2 or len(y) < 2: continue
        if (tier == 0 and x == y) or (tier == 1 and (x.startswith(y) or y.startswith(x))) or (tier == 2 and (x in y or y in x)): return True
    return False
def tier(k, e): return next((t for t in (0, 1, 2) if fit(k, e, t)), 9)
def match(g, cands):
    """Best (worst-side tier, home_is_second, game) over date+-1 candidates and both orientations; a tie is refused."""
    kA, kB = (g["fc"].lower(), g["nA"]), (g["sc"].lower(), g["nB"]); hits = []
    for m in cands:
        if abs((m["d"] - g["d"]).days) > 1: continue
        tok = m["s"].split("-"); eA, eH = (tok[1], norm(m["an"])), (tok[2], norm(m["hn"]))   # slug: <lg>-<away>-<home>-date
        hits += [(max(tier(kA, eA), tier(kB, eH)), True, m), (max(tier(kA, eH), tier(kB, eA)), False, m)]
    hits = sorted((h for h in hits if h[0] < 9), key=lambda h: h[0])
    if not hits: return None, "unmatched"
    return (None, "refused ambiguous") if len(hits) > 1 and hits[1][0] == hits[0][0] else (hits[0], None)
def near(ts, t):
    i = bisect.bisect_left(ts, t); c = [j for j in (i - 1, i) if 0 <= j < len(ts) and abs(ts[j] - t) <= MATCH]
    return min(c, key=lambda j: abs(ts[j] - t)) if c else None

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(conn, _): cur = conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); conn.commit()

F, A, B, C, flagged, second_home, games = defaultdict(int), [], [], [], [], [0, 0], []
with eng.connect() as c:
    q = lambda k, **p: [dict(r._mapping) for r in c.execute(text(Q[k]), p)]
    d0, d1 = dt.date.fromisoformat(D0), dt.date.fromisoformat(D1)
    t_lo, t_hi = (dt.datetime.combine(d, dt.time(), dt.timezone.utc) for d in (d0 - 3 * DAY, d1 + 2 * DAY))
    kg, gm = q("kg", lg=LG, d0=d0, d1=d1), q("gm", d0=d0 - DAY, d1=d1 + DAY); egs = [m["eg"] for m in gm]
    ko = {r["eg"]: r["ko"] for r in q("ko", egs=egs, lo=t_lo, hi=t_hi)}
    fin = {r["eg"]: (r["h"], r["a"]) for r in q("fin", lo=t_lo)}
    for r in q("bf", egs=egs): fin.setdefault(r["eg"], (r["h"], r["a"]))
    for g in kg:
        F["kalshi games"] += 1; parts = (g["title"] or "").split(" vs ")
        g["nA"], g["nB"] = (norm(parts[0]), norm(parts[1])) if len(parts) == 2 else ("", "")
        hit, why = match(g, gm)
        if hit is None: F[why] += 1; continue
        tr, home_second, m = hit; F[f"matched tier {tr}"] += 1; second_home[home_second] += 1
        home, away = (g["sc"], g["fc"]) if home_second else (g["fc"], g["sc"])
        kr = q("ks", gk=g["gk"], ser=SER, lo=t_lo, hi=t_hi)
        if not kr: F["no kalshi tape"] += 1; continue
        pr = q("pm", vg=m["vg"], ts=list(PT), lo=kr[0]["ts"] - MATCH, hi=kr[-1]["ts"] + MATCH)
        kick = ko.get(m["eg"]) or min((r["gst"] for r in pr if r["gst"]), default=None)
        if kick is None: F["no kickoff"] += 1; continue
        F["kickoff from plays" if m["eg"] in ko else "kickoff from venue start"] += 1; F["settled by ESPN"] += m["eg"] in fin
        P, K, meta = defaultdict(list), defaultdict(list), {}
        for r in pr:
            if r["ts"] < kick: P[(PT[r["t"]], None if r["line"] is None else round(r["line"], 1))].append((r["ts"], r["b"], r["a"], r["fc"]))
        for r in kr:
            if r["ts"] < kick: K[r["ticker"]].append((r["ts"], r["b"], r["a"])); meta[r["ticker"]] = (r["t"], r["f"])
        gA, gB, gC, wgap = [], [], [], None
        for tk, ks in K.items():
            t, f = meta[tk]; code = re.sub(r"\d+$", "", tk.rsplit("-", 1)[1])
            side = "over" if t == "total" else "away" if code == away else "home" if code == home else None
            if side is None: F["ticker code not a team"] += 1; continue
            h, a = fin.get(m["eg"], (None, None)); y = None
            if h is not None and not (t == "winner" and h == a):
                y = int(h + a > f) if t == "total" else int(((a - h) if side == "away" else (h - a)) > (f if t == "spread" else 0))
            tl, bl, al = ks[-1]
            if t == "spread" and LO <= (bl + al) / 2 < HI:   # (C): last Kalshi quote before kickoff; venue settlement of the matched rung
                try: s = VEN.get_settlement(f"asc-{m['s']}-{'neg' if side == 'away' else 'pos'}-{int(f)}pt5").get("settlement") if VEN else None; yv = None if s is None else (int(s) if side == "away" else 1 - int(s))
                except Exception: yv = None
                if yv is not None: F["C venue-settled " + ("ESPN missing" if y is None else "agrees ESPN" if y == yv else "DISAGREES ESPN")] += 1; y = yv if y is None else y
                if y is not None: gC.append((100 * ((1 - y) - (1 - bl) - fee(bl, FK)), g["gk"], side, (kick - tl).total_seconds() / 60))
            ps = P.get(("winner", None) if t == "winner" else ("total", round(f, 1)) if t == "total" else ("spread", round(-f if side == "away" else f, 1)))
            if not ps: F["kalshi contracts with no polymarket rung"] += 1; continue
            F["matched contracts"] += 1; kts = [x[0] for x in ks]; seq = []
            for tp, pb, pa, pc in ps:                  # pc: the coefficient recorded on this sweep's row
                if side == "home": pb, pa = 1 - pa, 1 - pb
                j = near(kts, tp)
                if j is None: F["polymarket sweeps with no kalshi within 5 min"] += 1; continue
                _, kb, ka = ks[j]; km, pm_ = (kb + ka) / 2, (pb + pa) / 2; gap = 100 * (km - pm_)
                dutch = round(dutch_cost(kb, ka, pb, pa, pc), 6) < 1
                gA.append((t, side, gap, dutch, g["gk"], abs(kts[j] - tp).total_seconds())); seq.append((tp, pm_, km, gap))
                if t == "winner" and side == "away": wgap = gap
            i = 0
            while i < len(seq):   # (B) episodes, non-overlapping
                t0, p0, k0, g0 = seq[i]; nxt = next((s for s in seq[i + 1:] if B_LO <= s[0] - t0 <= B_HI), None) if abs(g0) > GAP else None
                if nxt is None: i += 1; continue
                t1, p1, k1, _ = nxt; gB.append((t, 100 * (k0 - k1) / g0, 100 * (p1 - p0) / g0, (t1 - t0).total_seconds() / 60, g["gk"]))
                i = next((j for j in range(i + 1, len(seq)) if seq[j][0] > t1), len(seq))
        if wgap is not None and abs(wgap) > FLAG: flagged.append((g["gk"], m["s"], round(wgap, 1))); continue
        F["no winner sanity check (no aec pair)"] += wgap is None; games.append(g["gk"]); A += gA; B += gB; C += gC

print(f"cross-venue {LG} slate {D0}..{D1}  run {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%MZ}  READ-ONLY, nothing placed")
print("funnel: " + "  ".join(f"{k} {v}" for k, v in sorted(F.items())))
print(f"MATCHED GAMES {len(games)}   Kalshi second_code is ESPN home in {second_home[1]}/{sum(second_home)}   "
      f"flagged mis-pairs (|winner gap| > {FLAG:.0f}pp) dropped {len(flagged)}: {flagged}")
print(f"\n=== A. kalshi_mid - poly_mid, cents, in the Kalshi contract's YES frame; every Polymarket sweep, nearest Kalshi within 5 min "
      f"(lag median {pct([r[5] for r in A], .5) if A else 0:.0f}s) ===")
print(f"{'type':<7}{'side':<9}{'n':>6}{'G':>4}{'G_eff':>7}{'median':>8}{'q1':>7}{'q3':>7}{'|gap|>3c':>9}{'dutch':>6}  mean [95% game-clustered]")
for t in ("winner", "spread", "total"):
    for side in ("away", "home", "over", "all |gap|"):
        rs = [r for r in A if r[0] == t and (side.startswith("all") or r[1] == side)]
        if not rs: continue
        gs = [abs(r[2]) if side.startswith("all") else r[2] for r in rs]; m, hw, n, G, ge = clustered(gs, [r[4] for r in rs])
        print(f"{t:<7}{side:<9}{n:>6}{G:>4}{ge:>7.1f}{pct(gs, .5):>+8.2f}{pct(gs, .25):>+7.2f}{pct(gs, .75):>+7.2f}{sum(abs(x) > GAP for x in gs) / n:>9.1%}"
              f"{sum(r[3] for r in rs):>6}  {m:+.2f} [{m - hw:+.2f}, {m + hw:+.2f}]{'  UNDERPOWERED' if G < 25 else ''}")
dz = [r for r in A if r[3]]
print(f"  side = the team Kalshi's YES names (home rows compare to the complemented Polymarket rung); 'all |gap|' pools sides on |gap|.\n"
      f"  dutch instants {len(dz)} over {len({r[4] for r in dz})} games; their lag median {pct([r[5] for r in dz], .5) if dz else 0:.0f}s, |gap| median {pct([abs(r[2]) for r in dz], .5) if dz else 0:.2f}c")
print(f"\n=== B. |gap| > {GAP:.0f}c at t0: fraction of the gap closed by each venue at the next Polymarket sweep 30..90 min later (1 = closed it all) ===")
print(f"{'type':<7}{'n':>5}{'G':>4}{'horizon med':>12}{'Kalshi med':>11}{'Poly med':>10}   Kalshi mean [CI]                       |  Polymarket mean [CI]")
for t in ("winner", "spread", "total"):
    rs = [r for r in B if r[0] == t]
    if not rs: print(f"{t:<7}    0  no episodes"); continue
    ks_, ps_, keys = [r[1] for r in rs], [r[2] for r in rs], [r[4] for r in rs]
    print(f"{t:<7}{len(rs):>5}{len(set(keys)):>4}{pct([r[3] for r in rs], .5):>10.0f}m{pct(ks_, .5):>+11.2f}{pct(ps_, .5):>+10.2f}   {ci(ks_, keys, '')}  |  {ci(ps_, keys, '')}")
print(f"\n=== C. Kalshi spread rungs with YES mid in [{LO}, {HI}) at the last quote before kickoff: buy NO at 1 - yes_bid, net of {FK}*p*(1-p), cents per $1 ===")
for side in ("away", "home", "all"):
    rs = [r for r in C if side == "all" or r[2] == side]
    print(f"  {side:<5} {ci([r[0] for r in rs], [r[1] for r in rs]) if rs else 'n=0'}   quote age median {pct([r[3] for r in rs], .5) if rs else 0:.1f} min before kickoff")
print("  Polymarket reference, same rule on asc rungs at the coefficient then in force (STATUS.md 09-13; docs/math/fee-coefficient.md): +5.44c [-1.46, +12.35], 289 bets, 107 games."
      "  AWAY here is that rung (Kalshi 'away wins by over X' == asc line -X); HOME is the complement of its 0.7-0.8 mirror rung.")
print("G < 25 is UNDERPOWERED: a direction, never a result. Nothing here is placed; the tape is the only input.")
