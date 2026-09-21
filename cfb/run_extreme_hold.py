"""Buy the near-certain side in-game at the ask and HOLD TO SETTLEMENT: one fee, not two.

WHY. c*p*(1-p) collapses at the extremes: a round trip is 2c(1-p) of the ticket, 7% at 50c and
0.7% at 95c at the current coefficient. Everything so far died at mid prices paying two fees and
two half-spreads; holding pays one of each, where both are smallest.

THE NULL IS NOT ZERO: against a calibrated market, taking the ask when the MID is in the band
loses exactly (ask - mid) + fee. Every cell splits exactly and additively, y=0.5 included:
    net = (y - mid) calibration - (ask - mid) crossing - fee(p)
A negative cell with calibration ~0 is a COST result, not a mispricing one.

PRE-REGISTERED BEFORE THE OUTCOME RUN: primary = band x side POOLED over periods, 8 cells;
the 48 period/half cells are EXPLORATORY. ~40 buckets are already looked at on this tape
(brief, open question 1), so nothing is a discovery unless its mirror twin agrees.

YES IS ALWAYS THE AWAY TEAM, so "buy NO" is a HOME near-certain winner and CFB weeks 1-2 carry
a measured whole-ladder home shift (cfb/run_longshot_decomp.py): the NO side should look
better for reasons unrelated to extremity. One-sided is an artifact.

TRAPS, each gated and COUNTED rather than described:
  * change-detected writes make a frozen board look like a held price -> an entry counts only
    if the mid changed within the prior 120 s.
  * a recorder that started mid-game opens at an extreme price -> the tradeable window is
    bounded by ESPN PLAY wall-clock, never by the first tick row, and ends at the last play.
  * SETTLEMENT IS THE VENUE'S OWN (core/settlements.py), never espn_cfb_game_state: only ~41%
    of games reach state='post' (105 post vs 81 stuck at 'in'), so settling from ESPN drops
    half the cohort and selects the survivors on our own recorder's behaviour.
  * A DRAW SETTLES AT 0.5 and is a real settlement (NFL ties); `y in (0,1)` discards those
    rows silently and forever. y is a float and the split stays exact at y=0.5.
  * the play window is a SECOND recorder that can truncate, so the share of games reaching
    period 4 is reported -- truncation under-samples the high bands, which occur late.
  * bands SHARE GAMES (0.90 -> 0.98 enters several), so cells are not independent of each
    other: the clustered interval covers within-cell dependence only, and "three of four
    bands negative" is closer to one observation repeated than to three.
  * the venue RAISED its taker coefficient at 2026-09-17 04:07Z and market_snapshots carries the
    value it charged on every tick, so each entry is charged at ITS tick's fee_coefficient and
    the only fee trap left is a NULL one. The previous trap, "coefficient != today's constant",
    skipped every pre-change game on any window spanning that instant.

RUN prod read-only, env flags INSIDE docker run (sudo drops an env prefix); needs the API image
+ checkout mounted for the venue client -- scripts/prod_weekend_read.sh V=(). Nothing is placed.
G < 25 is UNDERPOWERED, reported and kept.
"""
import datetime as dt, math, os, sys
from bisect import bisect_right
from collections import defaultdict

from sqlalchemy import create_engine, event, text

from core import settlements
from core.polymarket.client import PolymarketGatewayClient

sys.stdout.reconfigure(line_buffering=True)   # a long per-game run must show progress
LG = os.environ.get("LEAGUE", "cfb")
from core.fees import recorded_fee  # noqa: E402  the tick's own coefficient; None raises, never today's
S120, GAP = dt.timedelta(seconds=120), 600.0
NOW = dt.datetime.now(dt.timezone.utc)
BANDS = [(0.900, 0.925), (0.925, 0.950), (0.950, 0.975), (0.975, 0.990)]
BAD = ("timeout", "kickoff", "end period", "end of", "two-minute", "warning")
CACHE = settlements.load()
settle = settlements.settler(PolymarketGatewayClient(), CACHE)
eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(conn, _rec):
    cur = conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); conn.commit()

Q_GAMES = """WITH fin AS (SELECT DISTINCT ON (game_id) game_id, state, home_score hs, away_score aws
  FROM espn_cfb_game_state WHERE league = :lg ORDER BY game_id, first_seen_at DESC)
SELECT p.game_id eg, m.venue_game_id vg, m.home_espn_team_id mh, m.away_espn_team_id ma,
       min(p.home) ph, min(p.away) pa, max(p.wall_clock) t1, f.state, f.hs, f.aws
FROM espn_cfb_live_plays p JOIN cfb_game_map m ON m.espn_game_id = p.game_id
LEFT JOIN fin f ON f.game_id = p.game_id
WHERE p.league = :lg AND m.venue_game_id IS NOT NULL AND p.wall_clock IS NOT NULL
GROUP BY 1,2,3,4,8,9,10 ORDER BY min(p.wall_clock)"""
Q_PLAYS = """SELECT wall_clock wc, period, is_overtime ot, coalesce(play_type,'') pt
FROM espn_cfb_live_plays WHERE game_id = :eg AND league = :lg AND wall_clock IS NOT NULL
ORDER BY wall_clock, id"""
Q_TICKS = """SELECT captured_at t, best_bid::float b, best_ask::float a, fee_coefficient::float fc,
  market_slug slug FROM market_snapshots WHERE game_id = :vg AND sports_market_type = :mt
  AND captured_at BETWEEN :lo AND :hi AND best_bid > 0 AND best_ask < 1 AND best_ask >= best_bid
ORDER BY captured_at"""
MT = "football_team_full_game_winner"

def fee_trap(rows):
    """The one fee trap left: a tick with NO recorded coefficient, skipped and counted.

    rows are Q_TICKS tuples, r[3] = fee_coefficient. A tick whose coefficient differs from
    today's is the venue's history, not a trap -- the previous check here was `!= constant`
    and on a window spanning 2026-09-17 04:07Z it fired on every pre-change tick."""
    return "TRAP fee_coefficient NULL on some tick" if any(r[3] is None for r in rows) else None

def entry(win, paid, pm, coef):
    """The fee-bearing terms of one entry, charged at the coefficient recorded on ITS tick.

    net = win - paid - fee(paid); nm = the same at the untradeable mid pm; fe = -fee(paid).
    p(1-p) is symmetric, so a NO entry at 1-bid pays what YES would at the bid. `coef` is the
    tick's fee_coefficient and travels out as `fc`; None raises (core.fees.recorded_fee) --
    fee_trap ran first, so a None here is a caller defect, never a fallback to today's."""
    f = recorded_fee(paid, coef)
    return dict(net=win - paid - f, nm=win - pm - recorded_fee(pm, coef), fe=-f, fc=coef)

def clustered(vals, keys):                     # verbatim from cfb/run_paper_book.py
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge

def med(xs): xs = sorted(xs); return xs[len(xs) // 2] if xs else float("nan")

def cp_lo(k, n, a=0.05):
    """Exact one-sided Clopper-Pearson LOWER bound on k/n. P(X>=k|p) rises in p, so bisect.

    THE HONEST INSTRUMENT WHERE EVERY GAME WON. With k = n the P&L has no outcome
    variance left, so the game-clustered sandwich collapses onto the band's own price
    dispersion and reports an interval tighter than anything else on the board -- 7/7
    read +1.68 [+1.41, +1.96] while being consistent with a true rate of 65%."""
    if k <= 0: return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        m = (lo + hi) / 2
        if sum(math.comb(n, i) * m ** i * (1 - m) ** (n - i) for i in range(k, n + 1)) > a: hi = m
        else: lo = m
    return lo

def cell(bets, fld="net"):
    """bets: dicts with net/nm/calib/cross/fe ($ per $1 contract), win, game, secs, dips."""
    if not bets: return "n=0"
    m, h, n, G, ge = clustered([100 * b[fld] for b in bets], [b["game"] for b in bets])
    ca, cr, fe = (100 * sum(b[k] for b in bets) / n for k in ("calib", "cross", "fe"))
    wr = sum(b["win"] for b in bets) / n
    be = sum(b["p"] + recorded_fee(b["p"], b["fc"]) for b in bets) / n   # break-even at the tick's own fee
    k = round(sum(b["win"] for b in bets))
    return (f"{m:+6.2f} [{m - h:+6.2f},{m + h:+6.2f}] n={n:<4} G={G:<3} Ge={ge:5.1f} "
            f"| calib{ca:+6.2f} cross{cr:+6.2f} fee{fe:+6.2f} | win {wr:5.1%} CPlo {cp_lo(k, n):5.1%} "
            f"need {be:5.1%} "
            f"| {med([b['secs'] for b in bets]) / 60:4.0f}m {med([b['dips'] for b in bets]):3.0f}dip"
            + ("  UNDERPOWERED" if G < 25 else ""))

C, cells, SEEN = defaultdict(int), defaultdict(list), set()   # SEEN: coefficients charged on scored ticks
with eng.connect() as c:
    games = [dict(r._mapping) for r in c.execute(text(Q_GAMES), {"lg": LG})]
    for g in games:
        C["games in plays+map"] += 1
        if g["ph"] != g["mh"] or g["pa"] != g["ma"]: C["TRAP orientation: plays vs map ids"] += 1; continue
        plays = [dict(r._mapping) for r in c.execute(text(Q_PLAYS), {"eg": g["eg"], "lg": LG})]
        if not plays: continue
        f0 = plays[0]["wc"]
        P = [p for p in plays if p["period"] and 1 <= p["period"] <= 4 and not p["ot"]
             and not any(b in p["pt"].lower() for b in BAD)
             and p["wc"] < f0 + dt.timedelta(hours=5)]
        if len(P) < 40: C["skipped: < 40 usable plays"] += 1; continue
        rows = c.execute(text(Q_TICKS), {"vg": g["vg"], "mt": MT, "lo": P[0]["wc"],
                                         "hi": P[-1]["wc"]}).fetchall()
        if len(rows) < 50: C["skipped: no in-game winner tape"] += 1; continue
        trap = fee_trap(rows)
        if trap: C[trap] += 1; continue
        SEEN.update(r[3] for r in rows)
        y = settle(rows[0][4])                      # the venue's own label, not our recorder's
        if y is None: C["skipped: venue has not settled"] += 1; continue
        C[f"venue settlement y={y}"] += 1
        C["window reaches period 4"] += (P[-1]["period"] == 4)
        if g["state"] == "post" and g["hs"] is not None and g["hs"] != g["aws"]:
            C["ESPN final available for cross-check"] += 1
            if (g["aws"] > g["hs"]) != (y == 1): C["TRAP venue settlement disagrees with ESPN score"] += 1
        C["games scored"] += 1
        if C["games scored"] % 20 == 0: print(f"  ... {C['games scored']} games scored")
        T = [r[0] for r in rows]; B = [r[1] for r in rows]; A = [r[2] for r in rows]
        FC = [r[3] for r in rows]                                  # the coefficient charged on each tick
        M = [round((a + b) / 2, 4) for a, b in zip(A, B)]          # round to tick before bucketing
        chg = [T[0]]
        for i in range(1, len(T)): chg.append(T[i] if M[i] != M[i - 1] else chg[-1])
        pw = [p["wc"] for p in P]
        if y != 0.5 and (M[-1] > 0.5) != (y == 1):
            C["TRAP last in-game mid disagrees with venue settlement"] += 1
        fired = set()
        for i in range(len(T)):
            for lo, hi in BANDS:
                for side in ("YES", "NO"):
                    key = (lo, hi, side)
                    if key in fired: continue
                    m = M[i]
                    hit = (lo <= m < hi) if side == "YES" else (1 - hi < m <= 1 - lo)
                    if not hit: continue
                    fired.add(key)
                    if T[i] - chg[i] > S120: C["TRAP frozen board: no mid change in 120 s"] += 1; continue
                    yes = side == "YES"
                    paid, pm = (A[i], m) if yes else (1 - B[i], 1 - m)   # touch, then untradeable mid
                    win = y if yes else 1 - y                            # y is 0, 0.5 or 1
                    out = (lambda j: M[j] < lo) if yes else (lambda j: M[j] > 1 - lo)
                    k = bisect_right(pw, T[i])
                    b = dict(win=win, p=paid, **entry(win, paid, pm, FC[i]),   # fee at THIS tick's coefficient
                             gap=(T[i] - T[i - 1]).total_seconds() if i else 0.0,
                             chg_age=(T[i] - chg[i]).total_seconds(),
                             calib=(y - m) if yes else (m - y),
                             cross=-(A[i] - m) if yes else -(m - B[i]), game=g["eg"],
                             secs=(T[-1] - T[i]).total_seconds(),
                             dips=sum(1 for j in range(i + 1, len(T)) if out(j) and not out(j - 1)))
                    per = P[k - 1]["period"] if k else 1
                    for kk in (key, (lo, hi, side, per), (lo, hi, side, "H1" if per <= 2 else "H2")):
                        cells[kk].append(b)
                    C[f"entries {side}"] += 1

settlements.save(CACHE)
print(f"LEAGUE={LG}  {NOW:%Y-%m-%d %H:%M}Z  fee c*p*(1-p) charged PER TICK at the coefficient the venue"
      f" recorded on it; coefficients on scored ticks: {sorted(SEEN)}")
for k in sorted(C): print(f"  {k}: {C[k]}")
if not cells: raise SystemExit("NO DATA: no entry taken")
print("\ncents per $1 contract [95% game-clustered sandwich] n G G_eff | EXACT SPLIT calib (y-mid),"
      "\ncross (ask-mid), fee | win rate vs break-even needed | median minutes held, median dips")
for fld, lab in (("net", "PRIMARY (pre-registered), entry at the ASK, band x side pooled over periods"),
                 ("nm", "SAME 8 CELLS, entry at the MID (NOT tradeable): separates 'calibrated at the "
                        "extremes'\n  from 'calibrated and we pay to cross'. Positive calib eaten by cross "
                        "=> a RESTING MAKER\n  entry, which is this study's exit and the momentum scalp's "
                        "was not.")):
    print(f"\n{lab}")
    for lo, hi in BANDS:
        print(f"  [{lo:.3f},{hi:.3f})  YES/away  {cell(cells[(lo, hi, 'YES')], fld)}")
        print(f"  mirror ({1 - hi:.3f},{1 - lo:.3f}]  NO/home   {cell(cells[(lo, hi, 'NO')], fld)}")
allb = [b for (lo, hi, side) in [(l, h, s2) for l, h in BANDS for s2 in ("YES", "NO")]
        for b in cells[(lo, hi, side)]]
gaps = sorted(b["gap"] for b in allb)
print(f"\nGAP AT ENTRY, seconds since the PREVIOUS write (n={len(gaps)}): median {med(gaps):.1f}"
      f"  p90 {gaps[int(0.9 * len(gaps))]:.1f}  max {max(gaps):.1f}  over {GAP:.0f}s: "
      f"{sum(g > GAP for g in gaps)}")
ca = sorted(b["chg_age"] for b in allb)
print(f"  age of the last MID CHANGE at entry: median {med(ca):.1f}  max {max(ca):.1f}  -- the"
      f" registered 120 s gate tests THIS and\n  it cannot fail on a change-detected tape:"
      f" nearly every written row IS a change, so chg==T. A frozen board is a GAP.")
print("\nPAIRED FRESHNESS CUT: registered (left) vs gap-to-previous-write <= "
      f"{GAP:.0f}s (right). Reported, NOT substituted.")
for lo, hi in BANDS:
    for side in ("YES", "NO"):
        b = cells[(lo, hi, side)]; f = [x for x in b if x["gap"] <= GAP]
        print(f"  [{lo:.3f},{hi:.3f}) {side:<3} {cell(b)}")
        if len(f) != len(b): print(f"  {'':>17}fresh  {cell(f)}")
        else: print(f"  {'':>17}fresh  IDENTICAL: 0 of {len(b)} entries dropped")
print("\nEXPLORATORY: by period and half (not pre-registered; 48 cells)")
for lo, hi in BANDS:
    for side in ("YES", "NO"):
        for per in (1, 2, 3, 4, "H1", "H2"):
            if cells[(lo, hi, side, per)]:
                print(f"  [{lo:.3f},{hi:.3f}) {side:<3} {str(per):<3} {cell(cells[(lo, hi, side, per)])}")
