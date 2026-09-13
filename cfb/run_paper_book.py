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

Registered 2026-09-13. LEAGUES env (comma list) limits the run; default all. ONLY=name,name limits strategies.
Settled labels are cached by core/settlements.py (one JSON file under the reads dir) so a daily run
costs a few HTTP calls instead of ~18k; only 0/1 is ever cached, an unsettled market is re-asked.
Cron: scripts/prod_weekend_read.sh (gate mode, Monday) runs it after H4 and
writes stdout to artifacts/reads/paper_book_<UTC>.txt.

The per-bet arithmetic is the pure function bet_pnl (with bet_stake) at module
level, tested without a database in tests/test_longshot_shadow_paper_book.py;
the run is under main() and executes only when the file is the script.
"""
import datetime as dt
import json
import os
import tempfile
from collections import defaultdict

FEE = 0.06
UTC = dt.timezone.utc

def mid(r): return (r["bid"] + r["ask"]) / 2


# --------------------------------------------------------------------------- #
# The JSON the SCOREBOARD page reads. Written beside the txt, by the producer
# that already has every number -- so the page's shape is fixed HERE, not
# recovered downstream by matching a fixed-width table with regexes.
#
# The nine keys below are the whole contract with static/scoreboard.html:
# available, note, file, generated_at, preamble, weekly.rows, all_weeks.rows,
# footer, unparsed. `unparsed` stays and is always empty -- the page renders it
# as "lines the parser did not recognise", and a producer that emits its own
# rows has none by construction.
# --------------------------------------------------------------------------- #

def _ci(m, h): return "%+.2f [%+.2f, %+.2f]" % (m, m - h, m + h)


def verdict_kind(v):
    """The producer's four verdict strings, as a class the page can colour."""
    for word, kind in (("POSITIVE", "positive"), ("NEGATIVE", "negative"),
                       ("UNDERPOWERED", "underpowered"), ("spans", "spans")):
        if v.startswith(word):
            return kind
    return "unknown"


def _wk(name, st, *, week=None, bets=0, games=None, unsettled=None, staked=None,
        pnl=None, net_per_dollar=None, ci=None, underpowered=False, note=None):
    return {"strategy": name, "league": st["league"], "week": week, "bets": bets,
            "games": games, "unsettled": unsettled, "staked": staked, "pnl": pnl,
            "net_per_dollar": net_per_dollar, "ci": ci,
            "underpowered": underpowered, "note": note}


def dump_json(preamble, weekly_rows, all_rows, footer, path=None):
    """Write the page's document. No path (no PB_JSON set) means the txt only."""
    path = path or os.environ.get("PB_JSON")
    if not path:
        return None
    doc = {"available": True, "generated_at": dt.datetime.now(UTC).isoformat(),
           "file": os.path.basename(path), "preamble": preamble, "footer": footer,
           "unparsed": [], "weekly": {"rows": weekly_rows},
           "all_weeks": {"rows": all_rows}}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    os.replace(tmp, path)          # the page never sees a half-written book
    return path
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
    # --- registered 2026-09-13 18:30Z by the manager: the WNBA under/over asymmetry tried on football, and
    #     MLB first-five markets (thinner, retail). CFB/NFL totals already have two Saturdays of tape: the
    #     first read of those is a back-read, labelled so; pre-registered from 09-19 on.
    "cfb_total_under_all":    dict(league="cfb",  types=("full_game_total",), side="no",  rule=lambda r: True),
    "cfb_total_over_all":     dict(league="cfb",  types=("full_game_total",), side="yes", rule=lambda r: True),
    "nfl_total_under_all":    dict(league="nfl",  types=("full_game_total",), side="no",  rule=lambda r: True),
    "nfl_total_over_all":     dict(league="nfl",  types=("full_game_total",), side="yes", rule=lambda r: True),
    "mlb_f5_total_under_all": dict(league="mlb",  types=("first_five_total",), side="no",  rule=lambda r: True),
    "mlb_f5_total_over_all":  dict(league="mlb",  types=("first_five_total",), side="yes", rule=lambda r: True),
    "mlb_f5_spread_no_20_30": dict(league="mlb",  types=("first_five_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
}

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


# ---------------------------------------------------------------- the per-bet arithmetic (pure, tested)
def bet_stake(side, bid, ask):
    """Dollars at risk on one $1 contract: YES costs the ask; NO costs 1 - bid."""
    return ask if side == "yes" else 1 - bid


def bet_pnl(side, y, bid, ask, fee=FEE):
    """Net P&L in dollars on one $1 contract, settled y (1 = YES resolved), taker fee charged.

    side 'yes': buy YES at the ask p:      y - p - fee*p*(1-p)
    side 'no' : buy NO at 1 - bid, p = bid: (1-y) - (1-p) - fee*p*(1-p)
    The fee is the venue's 0.06*p*(1-p) on the YES price p either way (p(1-p) is
    symmetric in p and 1-p, so pricing the fee on the NO price gives the same number).
    """
    if side == "yes":
        p = ask
        return y - p - fee * p * (1 - p)
    p = bid
    return (1 - y) - (1 - p) - fee * p * (1 - p)


def clustered(vals, keys):
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, 1.96 * se, n, G, ge


def main():
    from sqlalchemy import create_engine, event, text
    # settlement: the venue's own endpoint, cached in a small table-free dict per run;
    # rows the venue has not settled are skipped and counted.
    from core.polymarket.client import PolymarketGatewayClient

    eng = create_engine(os.environ["DATABASE_URL"])
    @event.listens_for(eng, "connect")
    def _np(c, _r):
        cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); c.commit()

    client = PolymarketGatewayClient()
    try:
        from core import settlements
    except ImportError:                    # api image predates core/settlements.py (rebuild pending): same numbers, nothing persisted
        import types
        def _memo(client, cache):
            def settlement(slug):
                if slug not in cache:
                    try: s = client.get_settlement(slug).get("settlement"); cache[slug] = int(s) if s in (0, 1, "0", "1") else None
                    except Exception: cache[slug] = None
                return cache[slug]
            return settlement
        settlements = types.SimpleNamespace(PATH="none (uncached)", load=dict, save=lambda c: None, settler=_memo)
    _settle = settlements.load(); _hits = len(_settle)
    settlement = settlements.settler(client, _settle)

    preamble, weekly_rows, all_rows = [], [], []
    leagues = [x for x in os.environ.get("LEAGUES", "cfb,nfl,wnba,mlb").split(",") if x]
    since = dt.datetime.now(UTC) - dt.timedelta(days=int(os.environ.get("DAYS", "60")))
    rows_by_league = {}
    with eng.connect() as c:
        for lg in leagues:
            rows_by_league[lg] = [dict(r._mapping) for r in c.execute(text(CLOSE_SQL), {"pat": f"%-{lg}-%", "since": since})]
            preamble.append(f"{lg}: {len(rows_by_league[lg]):,} markets with a pregame close, "
                            f"{len({r['game_id'] for r in rows_by_league[lg]})} games")
            print(preamble[-1])

    print(f"\n{'strategy':<26}{'week':<12}{'bets':>6}{'games':>6}{'unsettled':>10}{'staked $':>10}{'P&L $':>9}{'net/$1':>9}{'95% CI on mean bet (c)':>26}")
    grand = defaultdict(list)
    only = [x for x in os.environ.get("ONLY", "").split(",") if x]   # ONLY=a,b limits a run to those strategies
    for name, st in STRATEGIES.items():
        if only and name not in only: continue
        rows = [r for r in rows_by_league.get(st["league"], []) if any(r["mtype"].endswith(t) for t in st["types"]) and st["rule"](r)]
        if not rows:
            weekly_rows.append(_wk(name, st, note="no markets on tape"))
            print(f"{name:<26}{'-':<12}{0:>6}   no markets on tape"); continue
        weeks = defaultdict(list); unsettled = defaultdict(int)
        for r in rows:
            y = settlement(r["market_slug"]); wk = r["ko"].date() - dt.timedelta(days=r["ko"].weekday())
            if y is None: unsettled[wk] += 1; continue
            weeks[wk].append((bet_pnl(st["side"], y, r["bid"], r["ask"]), bet_stake(st["side"], r["bid"], r["ask"]), r["game_id"]))
        for wk in sorted(set(weeks) | set(unsettled)):
            w = weeks.get(wk, [])
            if not w:
                weekly_rows.append(_wk(name, st, week=str(wk), bets=0, games=0,
                                       unsettled=unsettled[wk], note="unsettled only"))
                print(f"{name:<26}{str(wk):<12}{0:>6}{0:>6}{unsettled[wk]:>10}"); continue
            m, h, n, G, ge = clustered([100 * p for p, _, _ in w], [g for _, _, g in w])
            staked = sum(s for _, s, _ in w); pnl = sum(p for p, _, _ in w)
            weekly_rows.append(_wk(name, st, week=str(wk), bets=n, games=G, unsettled=unsettled[wk],
                                   staked=round(staked), pnl=pnl,
                                   net_per_dollar=pnl / staked if staked else 0,
                                   ci=_ci(m, h), underpowered=G < 25))
            print(f"{name:<26}{str(wk):<12}{n:>6}{G:>6}{unsettled[wk]:>10}{staked:>10.0f}{pnl:>+9.2f}{pnl/staked if staked else 0:>+9.3f}"
                  f"{'%+.2f [%+.2f, %+.2f]' % (m, m-h, m+h):>26}{'  G<25' if G < 25 else ''}")
            grand[name].extend(w)
    print(f"\n{'strategy, ALL WEEKS':<26}{'bets':>6}{'games':>6}{'staked $':>10}{'P&L $':>9}{'net/$1':>9}{'95% CI on mean bet (c)':>26}   verdict")
    for name, w in grand.items():
        m, h, n, G, ge = clustered([100 * p for p, _, _ in w], [g for _, _, g in w])
        staked = sum(s for _, s, _ in w); pnl = sum(p for p, _, _ in w)
        v = "UNDERPOWERED (G<25)" if G < 25 else ("POSITIVE, excludes 0" if m - h > 0 else ("NEGATIVE, excludes 0" if m + h < 0 else "spans 0"))
        all_rows.append({"strategy": name, "league": STRATEGIES[name]["league"], "bets": n,
                         "games": G, "staked": round(staked), "pnl": pnl,
                         "net_per_dollar": pnl / staked if staked else 0, "ci": _ci(m, h),
                         "verdict": v, "verdict_kind": verdict_kind(v)})
        print(f"{name:<26}{n:>6}{G:>6}{staked:>10.0f}{pnl:>+9.2f}{pnl/staked if staked else 0:>+9.3f}{'%+.2f [%+.2f, %+.2f]' % (m, m-h, m+h):>26}   {v}")
    settlements.save(_settle)
    print(f"\nsettlement cache {settlements.PATH}: {_hits:,} reused, {len(_settle) - _hits:,} fetched, {len(_settle):,} stored")
    footer = ["P&L is per $1-contract bets, taker fee charged, venue-settled. A positive line becomes a candidate",
              "at G >= 25 AND excludes 0 AND its home/away twin does not contradict it; nothing here is sized or armed."]
    for line in footer:
        print(line)
    dump_json(preamble, weekly_rows, all_rows, footer)


if __name__ == "__main__":
    main()
