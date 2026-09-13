"""THE PAPER BOOK: every registered shadow strategy, one P&L line per week.

Runs inside the meridian-api container (it needs the venue client for
settlement): docker exec -i meridian-api python - < cfb/run_paper_book.py
Reads market_snapshots, prices each strategy at the last quote before the
venue's game_start_time (within 6h), settles from the venue's OWN settlement
endpoint (authoritative; unsettled markets are skipped and counted), and
prints per strategy x week: bets, games, staked, P&L, net per $1, and a
game-clustered 95% interval on the per-bet mean. Nothing is placed.

A strategy is a rule over the ladder, registered here by name BEFORE its
weeks accrue. Adding one is a new entry in STRATEGIES; changing one is a new
name. The point is one table the operator can read on Monday that says which
paper lines are positive, on how many games, with what interval -- and the
same table next Monday. Fees: taker 0.06*p*(1-p) on Polymarket US.

Registered 2026-09-13. LEAGUES env (comma list) limits the run; default all.
"""
import datetime as dt
import os
import sys
from collections import defaultdict

from sqlalchemy import create_engine, event, text

FEE = 0.06
UTC = dt.timezone.utc

def mid(r): return (r["bid"] + r["ask"]) / 2
# side: 'yes' = buy YES at ask; 'no' = buy NO at 1-bid. rule(r) -> bool on the priced row.
STRATEGIES = {
    # --- the two the operator asked to keep alive, exactly as they were found
    "cfb_spread_no_20_30":    dict(league="cfb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    "wnba_spread_yes_80_100": dict(league="wnba", types=("full_game_spread",), side="yes",
                                   rule=lambda r: mid(r) >= 0.80),
    "wnba_total_under_all":   dict(league="wnba", types=("full_game_total",), side="no",
                                   rule=lambda r: True),
    # --- the decomposition's cleaner versions (home-referenced twins), beside them
    "cfb_spread_home_all":    dict(league="cfb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),   # NO on every away rung = home side, every rung
    "wnba_spread_no_00_20":   dict(league="wnba", types=("full_game_spread",), side="no",
                                   rule=lambda r: mid(r) <= 0.20),            # the home-favourite twin of yes_80_100
    # --- NFL, same rules as CFB, no prior
    "nfl_spread_no_20_30":    dict(league="nfl",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    "nfl_spread_home_all":    dict(league="nfl",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),
    # --- MLB, registered before any tape exists (recorder overlay staged 2026-09-13)
    "mlb_total_under_all":    dict(league="mlb",  types=("full_game_total",), side="no",
                                   rule=lambda r: True),
    "mlb_total_over_all":     dict(league="mlb",  types=("full_game_total",), side="yes",
                                   rule=lambda r: True),
    "mlb_winner_fav_yes":     dict(league="mlb",  types=("full_game_winner",), side="yes",
                                   rule=lambda r: mid(r) >= 0.60),
    "mlb_winner_dog_yes":     dict(league="mlb",  types=("full_game_winner",), side="yes",
                                   rule=lambda r: mid(r) <= 0.40),
    "mlb_spread_no_20_30":    dict(league="mlb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
}

eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(c, _r):
    cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); c.commit()

CLOSE_SQL = """
WITH g AS (
  SELECT game_id, min(game_start_time) ko FROM market_snapshots
  WHERE market_slug LIKE :pat AND game_start_time IS NOT NULL AND captured_at > :since GROUP BY 1)
SELECT DISTINCT ON (s.market_slug) s.market_slug, s.sports_market_type mtype, s.game_id, g.ko,
       s.best_bid::float bid, s.best_ask::float ask, s.captured_at
FROM market_snapshots s JOIN g ON g.game_id = s.game_id
WHERE s.market_slug LIKE :pat AND s.captured_at < g.ko AND s.captured_at > g.ko - interval '6 hours'
  AND s.captured_at > :since AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL
  AND g.ko < now() - interval '4 hours'
ORDER BY s.market_slug, s.captured_at DESC
"""

def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge

# settlement: the venue's own endpoint, cached in a small table-free dict per run;
# rows the venue has not settled are skipped and counted.
from core.polymarket.client import PolymarketGatewayClient  # noqa: E402
client = PolymarketGatewayClient()
_settle = {}
def settlement(slug):
    if slug not in _settle:
        try:
            r = client.get_settlement(slug); s = r.get("settlement")
            _settle[slug] = int(s) if s in (0, 1, "0", "1") else None
        except Exception:
            _settle[slug] = None
    return _settle[slug]

leagues = [x for x in os.environ.get("LEAGUES", "cfb,nfl,wnba,mlb").split(",") if x]
since = dt.datetime.now(UTC) - dt.timedelta(days=int(os.environ.get("DAYS", "60")))
rows_by_league = {}
with eng.connect() as c:
    for lg in leagues:
        rows_by_league[lg] = [dict(r._mapping) for r in c.execute(text(CLOSE_SQL), {"pat": f"%-{lg}-%", "since": since})]
        print(f"{lg}: {len(rows_by_league[lg]):,} markets with a pregame close, {len({r['game_id'] for r in rows_by_league[lg]})} games")

print(f"\n{'strategy':<26}{'week':<12}{'bets':>6}{'games':>6}{'unsettled':>10}{'staked $':>10}{'P&L $':>9}{'net/$1':>9}{'95% CI on mean bet (c)':>26}")
grand = defaultdict(list)
for name, st in STRATEGIES.items():
    rows = [r for r in rows_by_league.get(st["league"], []) if any(r["mtype"].endswith(t) for t in st["types"]) and st["rule"](r)]
    if not rows:
        print(f"{name:<26}{'-':<12}{0:>6}   no markets on tape"); continue
    weeks = defaultdict(list); unsettled = defaultdict(int)
    for r in rows:
        y = settlement(r["market_slug"]); wk = r["ko"].date() - dt.timedelta(days=r["ko"].weekday())
        if y is None: unsettled[wk] += 1; continue
        if st["side"] == "yes":
            p = r["ask"]; stake = p; pnl = y - p - FEE * p * (1 - p)
        else:
            p = r["bid"]; stake = 1 - p; pnl = (1 - y) - (1 - p) - FEE * p * (1 - p)
        weeks[wk].append((pnl, stake, r["game_id"]))
    for wk in sorted(set(weeks) | set(unsettled)):
        w = weeks.get(wk, [])
        if not w:
            print(f"{name:<26}{str(wk):<12}{0:>6}{0:>6}{unsettled[wk]:>10}"); continue
        m, h, n, G, ge = clustered([100 * p for p, _, _ in w], [g for _, _, g in w])
        staked = sum(s for _, s, _ in w); pnl = sum(p for p, _, _ in w)
        print(f"{name:<26}{str(wk):<12}{n:>6}{G:>6}{unsettled[wk]:>10}{staked:>10.0f}{pnl:>+9.2f}{pnl/staked if staked else 0:>+9.3f}"
              f"{'%+.2f [%+.2f, %+.2f]' % (m, m-h, m+h):>26}{'  G<25' if G < 25 else ''}")
        grand[name].extend(w)
print(f"\n{'strategy, ALL WEEKS':<26}{'bets':>6}{'games':>6}{'staked $':>10}{'P&L $':>9}{'net/$1':>9}{'95% CI on mean bet (c)':>26}   verdict")
for name, w in grand.items():
    m, h, n, G, ge = clustered([100 * p for p, _, _ in w], [g for _, _, g in w])
    staked = sum(s for _, s, _ in w); pnl = sum(p for p, _, _ in w)
    v = "UNDERPOWERED (G<25)" if G < 25 else ("POSITIVE, excludes 0" if m - h > 0 else ("NEGATIVE, excludes 0" if m + h < 0 else "spans 0"))
    print(f"{name:<26}{n:>6}{G:>6}{staked:>10.0f}{pnl:>+9.2f}{pnl/staked if staked else 0:>+9.3f}{'%+.2f [%+.2f, %+.2f]' % (m, m-h, m+h):>26}   {v}")
print("\nP&L is per $1-contract bets, taker fee charged, venue-settled. A positive line becomes a candidate")
print("at G >= 25 AND excludes 0 AND its home/away twin does not contradict it; nothing here is sized or armed.")
