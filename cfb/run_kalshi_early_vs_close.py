"""Kalshi, pregame: how much do prices move from early week to the close, and
what would a trader whose model EQUALS the close have earned?

This is the CEILING of "trade Kalshi with a good sports model". A model can do
no better than know the closing price in advance; trading the early price
toward the eventual close, settled at the venue's own result, net of Kalshi's
taker fee (0.07 * p * (1-p) per contract), is the most that strategy can pay.
It is LOOK-AHEAD by construction and says nothing about whether any model can
anticipate the close -- that is the next question, and only if this one is
worth asking. The tradeable version needs a real-time reference (a sportsbook
line path) that is not on this tape.

For every Kalshi CFB/NFL market settled on the tape: mid at T-72h, T-24h, T-6h,
T-1h before kickoff (last snapshot at or before), the close (last snapshot
before kickoff), the venue's result. Per league x market type x horizon:
  * how far the early mid sits from the close (median / p90 |close - early|)
  * early half-spread (a 10c early book kills the idea before the model does)
  * CEILING P&L: buy the side the close favours, at the early touch, when
    |close - early| >= 1c; net of fee; game-clustered
  * CONTROLS: buy YES always / buy NO always at the same early touch, so a
    one-sided bias is not mistaken for foresight.
"""
import datetime as dt
import os
from collections import defaultdict

from sqlalchemy import create_engine, event, text

FEE = 0.07
HORIZONS = (6, 3, 1)   # the recorder polls only from tip-6h (pregame_window_hours); earlier does not exist on tape

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(dbapi_conn, _rec):
    cur = dbapi_conn.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); dbapi_conn.commit()

# Kalshi has no start time (venue fact). `venue_occurrence_time` is set on 253
# CFB games and was measured on WNBA to be tip + 3h; that offset is a HYPOTHESIS
# here and is checked below against ESPN's first play on every game the
# Polymarket slug tokens can be matched to (same date, code is a prefix of the
# slug token or vice versa). NFL rows carry neither field: NFL is out for now.
# Kalshi has no start time (venue fact). `venue_occurrence_time` is Kalshi's
# occurrence_datetime, measured tip+3h on WNBA; here the anchor is ESPN's first
# play instead, reached by matching Kalshi team codes to the Polymarket event
# slug in cfb_game_map on the same date. The recorder polls a game only from
# pregame_window_hours (6h) before tip, so every ticker has ~6h of pregame
# tape and nothing earlier: T-72h / T-24h cannot be asked of this tape.
# Settlement from the mapped ESPN final (Kalshi's `result` field is sparse:
# 915 'yes' rows vs 32 'no' -- the losing side vanishes unseen).
GAMES_SQL = """
SELECT g.game_key, g.league, g.first_code, g.second_code, g.local_date::date d
FROM kalshi_games g WHERE g.league = 'cfb'
"""
MAP_SQL = """
WITH fin AS (
  SELECT game_id eg, home_score h, away_score a FROM espn_cfb_backfill_games
  WHERE home_score IS NOT NULL AND away_score IS NOT NULL
  UNION ALL
  SELECT eg, h, a FROM (
    SELECT DISTINCT ON (game_id) game_id eg, home_score h, away_score a
    FROM espn_cfb_game_state WHERE league='cfb' AND home_score IS NOT NULL AND period >= 4
      AND game_id NOT IN (SELECT game_id FROM espn_cfb_backfill_games WHERE home_score IS NOT NULL)
    ORDER BY game_id, first_seen_at DESC) x)
SELECT m.event_slug, m.espn_date::date d, f.h, f.a,
       COALESCE((SELECT min(b.wall_clock) FROM espn_cfb_backfill_plays b WHERE b.game_id = m.espn_game_id),
                (SELECT min(p.wall_clock) FROM espn_cfb_live_plays p WHERE p.game_id = m.espn_game_id)) AS ko
FROM cfb_game_map m JOIN fin f ON f.eg = m.espn_game_id WHERE m.division <> 'NFL'
"""
SNAP_SQL = """
SELECT ticker, captured_at, yes_bid::float b, yes_ask::float a
FROM kalshi_snapshots
WHERE game_key = :gk AND captured_at BETWEEN :lo AND :ko
  AND yes_bid IS NOT NULL AND yes_ask IS NOT NULL AND yes_bid > 0 AND yes_ask < 1
ORDER BY ticker, captured_at
"""

def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge

def _tok_match(code, tok):
    """Exact, then prefix, then containment -- containment LAST and only with
    both teams required on the same date, so 'WASH' cannot pair with
    'washst' unless the other code also fits (containment-matching lesson)."""
    c, t = code.lower(), tok.lower()
    if len(c) < 2 or len(t) < 2: return False
    return c == t or t.startswith(c) or c.startswith(t) or c in t or t in c

with eng.connect() as c:
    kg = [dict(g._mapping) for g in c.execute(text(GAMES_SQL))]
    maps = [dict(r._mapping) for r in c.execute(text(MAP_SQL))]
    matched = {}; ambiguous = 0
    for g in kg:
        for m in maps:
            toks = m["event_slug"].split("-")     # cfb-<away>-<home>-YYYY-MM-DD
            if len(toks) < 6 or m["d"] is None or m["ko"] is None or abs((m["d"] - g["d"]).days) > 1: continue
            a_, h_ = toks[1], toks[2]
            fwd = _tok_match(g["first_code"], a_) and _tok_match(g["second_code"], h_)
            rev = _tok_match(g["first_code"], h_) and _tok_match(g["second_code"], a_)
            if fwd and rev:
                ambiguous += 1; break          # both orientations fit: refuse, never guess a side
            if fwd:
                matched[g["game_key"]] = (m, g["first_code"], g["second_code"]); break
            if rev:
                matched[g["game_key"]] = (m, g["second_code"], g["first_code"]); break
    print(f"kalshi cfb games {len(kg)}  matched to a settled ESPN game with a first play {len(matched)}  "
          f"(refused as side-ambiguous {ambiguous})")
    rows, hist = [], []
    for gk, (m, away_code, home_code) in sorted(matched.items()):
        ko = m["ko"]
        if m["h"] == m["a"]: continue
        away_won = m["a"] > m["h"]
        snaps = defaultdict(list)
        for r in c.execute(text(SNAP_SQL), {"gk": gk, "lo": ko - dt.timedelta(hours=200), "ko": ko}):
            snaps[r._mapping["ticker"]].append((r._mapping["captured_at"], float(r._mapping["b"]), float(r._mapping["a"])))
        for tk, ss in snaps.items():
            if not tk.startswith("KXNCAAFGAME-"): continue
            code = tk.rsplit("-", 1)[1]
            if code == away_code: y = int(away_won)
            elif code == home_code: y = int(not away_won)
            else: continue
            hist.append((ko - ss[0][0]).total_seconds() / 3600)
            close = ss[-1]
            for h in HORIZONS:
                t = ko - dt.timedelta(hours=h)
                early = None
                for s_ in ss:
                    if s_[0] <= t: early = s_
                    else: break
                if early is None: continue
                rows.append(dict(gk=gk, lg="cfb", mt="winner", h=h, y=y, eb=early[1], ea=early[2],
                                 cb=close[1], ca=close[2], age_h=(t - early[0]).total_seconds() / 3600))
    if hist:
        hist.sort()
        print(f"pregame Kalshi tape per winner ticker, hours before ESPN's first play: "
              f"median {hist[len(hist)//2]:.1f}  p10 {hist[int(len(hist)*0.1)]:.1f}  max {hist[-1]:.1f}")

print(f"(ticker, horizon) rows {len(rows):,}")
for lg in ("cfb",):
    for mt in ("winner",):
        print(f"\n=== {lg} {mt} ===")
        print(f"  {'T-h':>4}{'n':>7}{'G':>5}{'G_eff':>7}  {'early half-sprd':>15}  {'|close-early| med/p90':>22}  "
              f"{'moved>=1c':>10}  {'CEILING net c':>14}{'95% CI':>18}  {'buyYES always':>14}{'buyNO always':>13}")
        for h in HORIZONS:
            rs = [r for r in rows if r["lg"] == lg and r["mt"] == mt and r["h"] == h]
            if len(rs) < 20:
                print(f"  {h:>4}{len(rs):>7}   too few"); continue
            keys = [r["gk"] for r in rs]
            em = [(r["eb"] + r["ea"]) / 2 for r in rs]; cm = [(r["cb"] + r["ca"]) / 2 for r in rs]
            mv = sorted(abs(a - b) for a, b in zip(cm, em))
            hs = 100 * sum((r["ea"] - r["eb"]) / 2 for r in rs) / len(rs)
            sig = [(r, cmid - emid) for r, emid, cmid in zip(rs, em, cm) if abs(cmid - emid) >= 0.01]
            if len(sig) >= 20:
                pnl, pk = [], []
                for r, d in sig:
                    if d > 0:   # close higher: buy YES at the early ask
                        p = r["ea"]; pnl.append(100 * (r["y"] - p - FEE * p * (1 - p)))
                    else:       # close lower: buy NO at 1 - early bid
                        p = r["eb"]; pnl.append(100 * ((1 - r["y"]) - (1 - p) - FEE * p * (1 - p)))
                    pk.append(r["gk"])
                cm_, ch_, cn, cG, cge = clustered(pnl, pk)
                ceil = f"{cm_:>+14.2f}{'[%+.2f, %+.2f]' % (cm_-ch_, cm_+ch_):>18}"
            else:
                cn = len(sig); cG = 0; cge = 0.0; ceil = f"{'too few moved':>32}"
            by, *_ = clustered([100 * (r["y"] - r["ea"] - FEE * r["ea"] * (1 - r["ea"])) for r in rs], keys)
            bn, *_ = clustered([100 * ((1 - r["y"]) - (1 - r["eb"]) - FEE * r["eb"] * (1 - r["eb"])) for r in rs], keys)
            print(f"  {h:>4}{len(rs):>7}{len(set(keys)):>5}{clustered([0.0]*len(rs) or [0], keys)[4] if False else len(set(keys)):>7}  "
                  f"{hs:>14.2f}c  {100*mv[len(mv)//2]:>9.1f}/{100*mv[int(len(mv)*0.9)]:<10.1f}  "
                  f"{len(sig):>10}  {ceil}  {by:>+13.2f}c{bn:>+12.2c}" if False else
                  f"  {h:>4}{len(rs):>7}{len(set(keys)):>5}{'':>7}  {hs:>14.2f}c  {100*mv[len(mv)//2]:>9.1f}/{100*mv[int(len(mv)*0.9)]:<10.1f}  "
                  f"{len(sig):>10}  {ceil}  {by:>+13.2f}c {bn:>+11.2f}c")
print("\nCEILING = trade the early touch toward the eventual close, when they differ by >=1c, net of 0.07*p*(1-p).")
print("It is look-ahead; a real model captures some fraction of it, and only if a real-time reference moves first.")
print("The controls (buy YES always / buy NO always at the same early touch) show what a one-sided bias alone earns.")
