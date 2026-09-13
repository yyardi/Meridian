"""Longshot-NO decomposition on the full CFB tape (docs/math/longshot-no-candidate.md section 7: Q1, Q2, Q5).

LADDER STUDY, football only. It decomposes spread rungs BY LINE; cricket and table
tennis carry one lineless winner market per event, so there are no rungs.

Runs inside meridian-api (venue client for settlement): docker exec -i -e LEAGUE=cfb meridian-api python - < this.
Prices every rung at the paper book's close (CLOSE_SQL is cfb/run_paper_book.py's plus the line: last quote before
the venue's game_start_time, within 6h), settles from the venue's own endpoint (unsettled skipped and counted), taker
fee 0.06*p*(1-p). Per cell: mean net per $1 contract in cents, 95% game-clustered sandwich interval, n bets, G games,
G_eff = n^2/sum(cluster^2), net per $ staked; G < 25 is UNDERPOWERED. bet_stake / bet_pnl / clustered are the paper
book's, verbatim. Mids are rounded to 4 dp before bucketing (prices tick at 0.01, so mids sit on a 0.005 grid).
  Q1  buy NO at YES-mid [0.20,0.30), split by whether the cheap YES (the AWAY side, always: slug <away>-<home>)
      is the away FAVOURITE failing to cover or the away UNDERDOG covering; favourite = winner mid > 0.5, same close.
  Q5  the NO bet by YES-mid bucket 0-10 .. 40-50 and buy YES for 50-60 .. 90-100, each beside its home-referenced
      twin. TWENTY CELLS PRINT, TEN ARE DISTINCT (each appears once as a main and once as its mirror's twin), and
      each row now carries the UNSETTLED SKIP RATE for both sides -- an unbalanced drop breaks the comparison.
      twin (NO at YES-rung p is the home side at 1-p: the twin of "NO at YES 20-30" is "YES at YES 70-80").
  Q2  the bucket re-defined on NO mid [0.70,0.80): symmetric difference with the YES-mid set. One YES book is
      published (bestBidQuote/bestAskQuote), so NO mid = 1 - YES mid and the sets can differ only at the boundary.
Nothing is placed. DAYS (default 90) bounds the tape; LEAGUE (default cfb) picks the slugs.
"""
import datetime as dt
import os
import sys
from collections import Counter, defaultdict

FEE = 0.06
UTC = dt.timezone.utc
NO_BUCKETS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5)]
YES_BUCKETS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]

CLOSE_SQL = """
WITH g AS (
  SELECT game_id, min(game_start_time) ko FROM market_snapshots
  WHERE market_slug LIKE :pat AND game_start_time IS NOT NULL AND captured_at > :since GROUP BY 1)
SELECT DISTINCT ON (s.market_slug) s.market_slug, s.sports_market_type mtype, s.game_id, g.ko, s.line::float line,
       s.best_bid::float bid, s.best_ask::float ask, s.captured_at
FROM market_snapshots s JOIN g ON g.game_id = s.game_id
WHERE s.market_slug LIKE :pat AND s.captured_at < g.ko AND s.captured_at > g.ko - interval '6 hours'
  AND s.captured_at > :since AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL
  AND g.ko < now() - interval '4 hours'
ORDER BY s.market_slug, s.captured_at DESC
"""


def mid(r): return round((r["bid"] + r["ask"]) / 2, 4)                  # round to tick before comparing
def no_mid(r): return round(((1 - r["ask"]) + (1 - r["bid"])) / 2, 4)
def in_bucket(m, lo, hi): return lo <= m < hi or (hi >= 1.0 and m == 1.0)   # half-open; the top bucket takes 1.0


# ---------------------------------------------------------------- copied verbatim from cfb/run_paper_book.py
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


def cell(bets):
    """bets: (pnl $, stake $, game_id). Mean cents per $1 contract [95% sandwich], n, G, G_eff, net per $ staked."""
    if not bets: return "n=0"
    m, h, n, G, ge = clustered([100 * p for p, _, _ in bets], [g for _, _, g in bets])
    st = sum(s for _, s, _ in bets); pnl = sum(p for p, _, _ in bets)
    return (f"{m:+6.2f} [{m - h:+6.2f}, {m + h:+6.2f}]  n={n:<4} G={G:<3} G_eff={ge:5.1f}  net/$staked={100 * pnl / st:+6.2f}c"
            + ("  UNDERPOWERED" if G < 25 else ""))


def bets_for(rows, side, settle):          # settle(slug) -> 0/1, or None = the venue has not settled it (skipped, counted)
    out, uns = [], 0
    for r in rows:
        y = settle(r["market_slug"])
        if y is None: uns += 1; continue
        out.append((bet_pnl(side, y, r["bid"], r["ask"]), bet_stake(side, r["bid"], r["ask"]), r["game_id"]))
    return out, uns


def main():
    from sqlalchemy import create_engine, event, text
    from core.polymarket.client import PolymarketGatewayClient
    sys.stdout.reconfigure(line_buffering=True)
    eng = create_engine(os.environ["DATABASE_URL"])
    @event.listens_for(eng, "connect")
    def _np(c, _r):
        cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); c.commit()
    client, _settle = PolymarketGatewayClient(), {}
    def settle(slug):                         # the venue's own label, cached per run; None = not settled
        if slug not in _settle:
            try: s = client.get_settlement(slug).get("settlement"); _settle[slug] = int(s) if s in (0, 1, "0", "1") else None
            except Exception: _settle[slug] = None
        return _settle[slug]

    lg = os.environ.get("LEAGUE", "cfb")
    since = dt.datetime.now(UTC) - dt.timedelta(days=int(os.environ.get("DAYS", "90")))
    with eng.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(text(CLOSE_SQL), {"pat": f"%-{lg}-%", "since": since})]
    spreads = [r for r in rows if (r["mtype"] or "").endswith("full_game_spread")]
    winners = {r["game_id"]: mid(r) for r in rows if (r["mtype"] or "").endswith("full_game_winner")}
    games = {r["game_id"] for r in spreads}
    fav = {g: "away_fav" if winners[g] > 0.5 else "away_dog" if winners[g] < 0.5 else "pick" for g in games if g in winners}
    cnt = Counter(fav.values())
    print(f"{lg}: {len(rows):,} markets with a pregame close since {since.date()}; {len(spreads):,} spread rungs in {len(games)} games; "
          f"winner close in {len(fav)} games: away favourite {cnt['away_fav']}, away underdog {cnt['away_dog']}, pick {cnt['pick']}, "
          f"no winner close {len(games) - len(fav)}\ncells: mean cents per $1 contract [95% game-clustered sandwich]  n  G  G_eff  net per $ staked")

    prim = [r for r in spreads if in_bucket(mid(r), 0.2, 0.3)]
    paper = sum(0.20 <= (r["bid"] + r["ask"]) / 2 < 0.30 for r in spreads)   # the paper book's unrounded predicate
    bets, uns = bets_for(prim, "no", settle)
    print(f"\nQ1  buy NO at YES-mid [0.20,0.30): {len(prim)} rungs (paper-book unrounded predicate: {paper}), {uns} unsettled skipped")
    for k, lab in (("*", "all"), ("away_fav", "away FAVOURITE (cheap YES = away fav fails to cover)"),
                   ("away_dog", "away UNDERDOG (cheap YES = away dog covers)"), ("pick", "pick (winner mid = 0.5)"), (None, "no winner close")):
        print(f"  {lab:<44}{cell([b for b in bets if k == '*' or fav.get(b[2]) == k])}")

    print(f"\nQ5  bet by YES-mid bucket, beside its home-referenced twin (same price, other team)")
    print("  NOTE: the 10 buckets print 20 cells but compute 10 DISTINCT statistics -- the twin printed beside")
    print("  [0.5,0.6) IS the main of [0.4,0.5), and vice versa. Five comparisons, displayed ten times.")
    print(f"  {'bucket':<11}{'bet':<5}{'cell':<78}{'twin':<17}{'cell':<78}unsettled bet/twin")
    for lo, hi in NO_BUCKETS + YES_BUCKETS:
        (side, tside), tlo, thi = ("no", "yes") if hi <= 0.5 else ("yes", "no"), round(1 - hi, 4), round(1 - lo, 4)
        brows = [r for r in spreads if in_bucket(mid(r), lo, hi)]
        trows = [r for r in spreads if in_bucket(mid(r), tlo, thi)]
        b, buns = bets_for(brows, side, settle)
        t, tuns = bets_for(trows, tside, settle)
        # The unsettled SKIP, printed per cell. Q1 printed it and Q5 did not, so a cell could
        # lose any share of its rungs invisibly. It matters most across a twin pair: the pair is
        # only comparable if both sides lost the same SHARE, and an unbalanced drop is exactly how
        # a twin comparison stops being one. Rates, not counts -- the two sets differ in size.
        br = 100 * buns / len(brows) if brows else 0.0
        tr = 100 * tuns / len(trows) if trows else 0.0
        # No threshold: ANY drop is unexplained selection and the reader judges the size. A
        # tuned cutoff here would decide for them, and the honest cutoff is not knowable.
        flag = ("  <- DROPPED ROWS, ASYMMETRIC" if buns != tuns else "  <- dropped rows") if (buns or tuns) else ""
        print(f"  [{lo:.1f},{hi:.1f})  {side.upper():<5}{cell(b):<78}{f'{tside.upper()} [{tlo:.1f},{thi:.1f})':<17}{cell(t):<78}"
              f"{buns}/{len(brows)} ({br:.0f}%)  {tuns}/{len(trows)} ({tr:.0f}%){flag}")

    A, by_slug = {r["market_slug"] for r in prim}, {r["market_slug"]: r for r in spreads}
    B = {r["market_slug"] for r in spreads if in_bucket(no_mid(r), 0.7, 0.8)}
    Bc = {r["market_slug"] for r in spreads if 0.7 < no_mid(r) <= 0.8}   # the boundary carried over with the flip
    print(f"\nQ2  NO mid [0.70,0.80): {len(B)} rungs vs {len(A)} on YES mid [0.20,0.30); symmetric difference {len(A ^ B)} (only YES-set "
          f"{len(A - B)}, only NO-set {len(B - A)}); NO mid (0.70,0.80]: symmetric difference {len(A ^ Bc)}")
    for s in sorted(A ^ B)[:20]: print(f"    {s}  bid {by_slug[s]['bid']:.2f} ask {by_slug[s]['ask']:.2f} YES-mid {mid(by_slug[s]):.4f} NO-mid {no_mid(by_slug[s]):.4f}")
    bB, _ = bets_for([by_slug[s] for s in B], "no", settle)
    print(f"  {'buy NO on the NO-mid [0.70,0.80) set':<44}{cell(bB)}")
    print("  one YES book is published (bestBidQuote/bestAskQuote); NO mid = 1 - YES mid by construction, so the sets can differ only at the boundary.")


if __name__ == "__main__":
    main()
