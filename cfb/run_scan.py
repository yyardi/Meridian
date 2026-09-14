"""The scan: one grid, every cell reported, and the DISTRIBUTION as the result.

Registered in docs/math/scan-preregistration.md. A SCREEN, never a decision. It may only
nominate families for a pre-registered held-out read.

## READ THIS BEFORE THE TABLE: WHAT PURE NOISE PRODUCES HERE

At m cells with NO edge anywhere, the best cell shows |t| ~ sqrt(2*ln m) and
P(some cell exceeds |t|=3) = 1-(1-0.0027)^m. At m=500 that is |t| ~ 2.9 and **P = 0.74**.
**A three-sigma cell is the MODAL OUTPUT OF NOISE at this m.** The top row of the appendix
table is not a find. Every number below is printed beside what the null gives.

## THE THREE STATISTICS, all from one pass, none chosen after its value was seen

1. **Var(t)** -- dense alternative (many small effects). PRINTED BESIDE ITS G-IMPLIED NULL
   BASELINE, which is NOT 1: a cell's t is ~ t with nu = G-1, and Var(t_nu) = nu/(nu-2), so
   a null scan with G=10..30 cells yields Var(t) ~ 1.07-1.29 by construction. The
   pre-registration's worked example reads Var=1.18 as "ten cells at mu=3, detectable" --
   that sits INSIDE the week-one null band. Var(t) alone is not interpretable on a ragged-G
   scan; the pair is. (Against the permutation null it is valid, because the permutation
   reproduces each cell's realized G. This is an interpretability fix, not a validity one.)
2. **Higher Criticism** over the smallest 10% of p -- sparse mixture. CONTESTED: one
   implementation saturates. Printed with the registered fallback `count(p<0.01)` beside it,
   and no statistic is selected on its value.
3. **max |t|** beside the null's expected max.

## THE SIDE AXIS IS PRESENTATION, NOT EVIDENCE -- so m is not what the cell count says

For one market with YES bid b, ask a, settlement y:
    net_YES = y - a - f(a);  net_NO = (1-y) - (1-b) - f(b) = b - y - f(b)
    net_YES + net_NO = (b - a) - f(a) - f(b)          <- deterministic given prices
So `net_NO = -net_YES + c` and, since the bucket is defined on YES mid, a YES cell and its NO
cell are THE SAME MARKETS. t_NO = -t_YES up to the variation in c. **Only YES is scored; the
NO twin is reported by identity.** Every statistic, Bonferroni and BH run on this
deduplicated set, which hands back 0.17 sigma on the threshold (3.72 vs 3.89 at 500 -> 250).

## WEIGHTED ON SETTLED STOCK, NOT THE ACCRUAL RATE

The binding constraint is settled game-clusters, and the stock is not the rate: table tennis
accrues ~109 cell-G/week but 91-100% of its markets have `game_start_time` in the FUTURE, so
the settled stock is tens, not hundreds. This file prints settled markets and G per family
from its own pass, and the decile detail is only opened where the stock supports it.

G FLOOR = 6, the registered value, for POWER not validity. **Every excluded cell is printed
with its reason** -- silent exclusion is how a family shrinks without anyone deciding to.

NIGHTLY CONTRACT (scripts/nightly_scan.sh runs this at 04:40Z):
  * exits NON-ZERO on any failure, so a silent empty night is impossible;
  * writes CELLS_JSON (the scored cells) and ROWS_JSON (the per-bet INPUTS, not
    outputs -- slug, game, bid, ask, y -- so the permutation null can reshuffle
    settlements within games and recompute, rather than trusting our pnl);
  * needs NO warm settlement cache: it builds the cache as it goes and saves it,
    so the first run on a cold cache is slow but complete, never partial.

RUN prod read-only, one pass (the box carries sweeps), env flags INSIDE docker run:
  scripts/prod_weekend_read.sh V=() with the API image and the checkout mounted.
Nothing is placed. Nothing here decides anything.
"""
import datetime as dt, json, math, os, re, sys
from collections import defaultdict

from scipy.stats import t as tdist
from sqlalchemy import create_engine, event, text

from core import settlements
from core.leagues import LEAGUES, venue_patterns
from core.polymarket.client import PolymarketGatewayClient

FEE_PM, G_FLOOR = 0.06, 6
DECILES = [(i / 10, (i + 1) / 10) for i in range(10)]
MAXCALLS = int(os.environ.get("MAXCALLS", "40000"))
sys.stdout.reconfigure(line_buffering=True)
CACHE = settlements.load()
settle = settlements.settler(PolymarketGatewayClient(), CACHE)
eng = create_engine(os.environ["DATABASE_URL"])
@event.listens_for(eng, "connect")
def _np(c, _r):
    cur = c.cursor(); cur.execute("SET max_parallel_workers_per_gather = 0"); cur.close(); c.commit()

#: Opt-in lower bound on `captured_at`. **NO DEFAULT, DELIBERATELY.** The scan
#: reads every partition of a 62M-row table TWICE per league pattern -- once for
#: the kickoff CTE, once for the close -- because `market_slug LIKE '%-cfb-%'`
#: has a leading wildcard no btree can serve and `captured_at` is constrained
#: only RELATIVE to `g.ko`, which the planner cannot push down. A floor prunes
#: partitions and is worth a third of the run. But the floor cannot be DERIVED
#: without the aggregate it is avoiding, so it has to come from the caller --
#: and a default would be a silent narrowing of the population, which is the
#: one defect this programme exists to avoid. Absent, nothing is excluded.
SINCE = (os.environ.get("SCAN_SINCE") or "").strip() or None

#: The clause is OMITTED rather than neutralised when there is no floor. A
#: `(:since IS NULL OR captured_at >= :since)` form does in fact prune on
#: postgres 16 -- verified -- but only while the planner substitutes the
#: parameter and builds a CUSTOM plan; after five executions it may switch to a
#: generic plan, and a generic plan cannot fold `$1 IS NULL`, so pruning would
#: disappear silently and the scan would just get slow again. Two literal
#: strings depend on nothing.
_FLOOR = "\n    AND {a}captured_at >= :since::timestamptz"
CLOSE_SQL = """
WITH g AS (SELECT game_id, min(game_start_time) ko FROM market_snapshots
  WHERE market_slug LIKE ANY(:pats) AND game_start_time IS NOT NULL{floor_g} GROUP BY 1)
SELECT DISTINCT ON (s.market_slug) s.market_slug slug, s.sports_market_type mt, s.game_id gid,
       s.best_bid::float bid, s.best_ask::float ask
FROM market_snapshots s JOIN g ON g.game_id = s.game_id
WHERE s.market_slug LIKE ANY(:pats) AND s.captured_at < g.ko AND s.captured_at > g.ko - interval '6 hours'
  AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL AND s.best_ask >= s.best_bid
  AND g.ko < now() - interval '4 hours'          -- STARTED and long finished, never an open board{floor_s}
ORDER BY s.market_slug, s.captured_at DESC"""
CLOSE = CLOSE_SQL.format(floor_g=_FLOOR.format(a="") if SINCE else "",
                         floor_s=_FLOOR.format(a="s.") if SINCE else "")


def partition_floors(conn, table="market_snapshots"):
    """Every partition's LOWER bound, asked of the catalogue rather than assumed.

    The scheme is monthly today. A check that hardcoded "the first of a month"
    would keep passing and silently stop pruning if retention ever moved to
    weekly partitions, so the boundaries are read from `relpartbound`.
    """
    rows = conn.execute(text(
        "SELECT pg_get_expr(c.relpartbound, c.oid) b FROM pg_class c "
        "JOIN pg_inherits i ON i.inhrelid = c.oid WHERE i.inhparent = :t::regclass"),
        {"t": table}).all()
    out = set()
    for (b,) in rows:
        m = re.search(r"FROM \('([^']+)'", b or "")     # DEFAULT has no FROM; skipped
        if m: out.add(m.group(1)[:10])
    return out


def check_since(conn, since):
    """Refuse a floor that is not ON a partition boundary.

    A floor inside a partition cannot prune it -- postgres still reads the whole
    thing to filter rows -- so such a value is BOTH narrower and slower than no
    floor at all. Measured 2026-09-14 with the scan's own
    `max_parallel_workers_per_gather = 0`: no floor 7,023,098; `2026-09-01`
    (a boundary) 4,671,180, a 33.5% cut; `2026-08-25` (inside August)
    6,349,000-odd, i.e. MORE than no floor. A parameter whose wrong values are
    both slower and narrower must reject them, not accept them quietly.
    """
    floors = partition_floors(conn)
    if since[:10] not in floors:
        raise SystemExit(
            f"SCAN_SINCE={since} is not a market_snapshots partition boundary.\n"
            f"  A floor inside a partition prunes NOTHING and is slower than no floor,\n"
            f"  while still narrowing the population. Boundaries: {sorted(floors)}")


def fee(p, k=FEE_PM): return k * p * (1 - p)
def mid(bid, ask): return round((bid + ask) / 2, 4)


def clustered(vals, keys):                        # verbatim from cfb/run_paper_book.py
    n = len(vals); m = sum(vals) / n
    res, size = defaultdict(float), defaultdict(int)
    for v, k in zip(vals, keys): res[k] += v - m; size[k] += 1
    G = len(res); ge = n * n / sum(c * c for c in size.values())
    se = (sum(x * x for x in res.values()) ** 0.5) / n * (G / (G - 1)) ** 0.5 if G > 1 else float("inf")
    return m, se, n, G, ge


# Fail fast: a bad floor is caught before the first 62M-row scan, not after it.
if SINCE:
    with eng.connect() as _c: check_since(_c, SINCE)

#: (league, pattern) in the order the per-league loop used to visit them, so the
#: printed coverage lines keep their old order and are diffable against old runs.
PATS = [(lg, pat) for lg in ("cfb", "nfl", "wnba", "mlb", "cricket", "tabletennis")
        if lg in LEAGUES for pat in venue_patterns(lg)]


def like_to_needle(pat: str) -> str:
    """`%-cfb-%` -> `-cfb-`, and REFUSES anything more complicated.

    ★ Attribution must use the SAME pattern strings the query used, never
    `league_of_slug`. Two attribution routes that can disagree would silently
    move rows between cells or drop them -- a population change to a registered
    result, wearing the costume of a faster scan. So this converts the LIKE to
    its exact Python equivalent and refuses any pattern whose equivalent is not
    a plain substring test, rather than quietly mis-handling `_`, a trailing
    anchor, or an escape.
    """
    if not (pat.startswith("%") and pat.endswith("%") and len(pat) > 2):
        raise SystemExit(f"pattern {pat!r} is not of the form %needle% -- "
                         "attribution by substring would not match the SQL")
    body = pat[1:-1]
    if "%" in body or "_" in body:
        raise SystemExit(f"pattern {pat!r} has a wildcard inside it -- "
                         "a substring test is not its equivalent")
    return body


NEEDLES = [(lg, pat, like_to_needle(pat)) for lg, pat in PATS]


def attribute(slug: str) -> tuple[str, str]:
    """The one (league, pattern) this slug belongs to. Exactly one, or the run dies.

    Zero means the query returned something no pattern asked for; two means a
    row would be counted in both leagues and its cell assignment is a coin
    flip. `nfl-cfb-osu-mich-...` is a real slug shape I produced by accident
    while writing a test an hour before this was written, and it matches
    `%-cfb-%` -- the overlap risk is not hypothetical. Fatal rather than a
    warning: a warning in a two-hour batch job is a line nobody reads.
    """
    hit = [(lg, pat) for lg, pat, needle in NEEDLES if needle in slug]
    if len(hit) != 1:
        raise SystemExit(
            f"slug {slug!r} matched {len(hit)} patterns ({[p for _, p in hit]}) -- "
            "attribution is ambiguous and the cell assignment would be arbitrary")
    return hit[0]


#: Opt-in equivalence check for the one-query rewrite: per-pattern counts from a
#: KNOWN reference run, as `pat=count` pairs. Compared exactly.
#: `SCAN_EXPECT='%-cfb-%=111,%-nfl-%=222'`  <- deliberately fake numbers: an
#: example carrying a real run's counts is the thing someone copies.
#:
#: ★ VALID ONLY AGAINST A RUN OVER THE SAME TAPE AND THE SAME FLOOR. The tape
#: grows every minute, so these counts are a fact about one window, not an
#: invariant -- which is exactly why it is opt-in and never hardcoded. The
#: reference for the 13-query-to-1-query change was the 05:28Z run of
#: 2026-09-14 with no floor.
EXPECT = dict(
    (k, int(v)) for k, _, v in
    (e.partition("=") for e in (os.environ.get("SCAN_EXPECT") or "").split(",") if e)
)

CELLS, STOCK, DROP = defaultdict(list), defaultdict(lambda: [0, 0, set()]), defaultdict(int)
calls = 0
for lg in ("cfb", "nfl", "wnba", "mlb", "cricket", "tabletennis"):
    if lg not in LEAGUES: DROP[f"{lg}: not in core.leagues"] += 1

# ★ ONE QUERY FOR ALL THIRTEEN PATTERNS. It used to be one per pattern, and the
# table is read TWICE per query (the kickoff CTE and the close), so that was 26
# full passes over a 57 GB table -- ~1.1 TB of disk reads per run on a box with
# 7 GB of RAM and 128 MB of shared_buffers, where nothing can be cached. Nine of
# the thirteen patterns returned fifteen rows or fewer and each still paid two
# full scans. `LIKE ANY` scans once and tests every row against all of them:
# planner cost 5,630,712 against 13 x 4,671,180 = 60.7M, so 2 passes and ~84 GB.
with eng.connect() as c:
    args = {"pats": [p for _, p in PATS]} | ({"since": SINCE} if SINCE else {})
    allrows = [dict(r._mapping) for r in c.execute(text(CLOSE), args)]

BY_PAT: dict = defaultdict(list)
for r in allrows:
    lg, pat = attribute(r["slug"])
    BY_PAT[pat].append((lg, r))

for lg, pat in PATS:
    rows = BY_PAT.get(pat, [])
    for _lg, r in rows:
        mt = (r["mt"] or "?")
        STOCK[(lg, mt)][0] += 1
        if calls >= MAXCALLS: DROP["settlement calls hit MAXCALLS"] += 1; continue
        y = settle(r["slug"]); calls += 1
        if y is None: STOCK[(lg, mt)][1] += 1; continue
        m = mid(r["bid"], r["ask"])
        for lo, hi in DECILES:
            if not (lo <= m < hi or (hi >= 1.0 and m == 1.0)): continue
            a = r["ask"]
            CELLS[(lg, mt, lo)].append((y - a - fee(a), r["gid"], r["bid"], a, y))
            STOCK[(lg, mt)][2].add(r["gid"])
    # The floor rides on the SAME LINE as the count it produced. A reader
    # cannot see "22,870 closes" without seeing what was excluded to get it.
    # Per-pattern counts survive the rewrite on purpose: they are the only
    # resolution at which the one-query form can be compared to the old one.
    print(f"  ... {pat} {len(rows):,} closes, {calls:,} settlement calls"
          f", since={SINCE or 'ALL (no floor)'}")

if EXPECT:
    # Same tape, same floor, or this means nothing -- see EXPECT.
    off = {p: (len(BY_PAT.get(p, [])), n) for p, n in EXPECT.items()
           if len(BY_PAT.get(p, [])) != n}
    if off:
        raise SystemExit("SCAN_EXPECT mismatch (got, expected): "
                         + ", ".join(f"{p} {g} != {e}" for p, (g, e) in sorted(off.items())))
    print(f"  equivalence: {len(EXPECT)} pattern counts reproduce the reference run exactly")
settlements.save(CACHE)
if not CELLS:
    raise SystemExit("NO DATA: no cell collected -- check the league patterns and the close window")

# ---- cells, then the distribution -------------------------------------------------------
scored, excluded = [], []
for key, bets in sorted(CELLS.items()):
    m, se, n, G, ge = clustered([100 * b[0] for b in bets], [b[1] for b in bets])
    # DEGENERACY GUARD, before the G floor. A cell in which every bet settled the SAME
    # WAY has no outcome variation, so the sandwich measures the cell's price dispersion
    # rather than its risk, and the interval collapses toward zero width while the mean
    # stays large. Measured 2026-09-14 on 22,870 closes: 16 of 324 cells were degenerate
    # and they were ALL TWELVE of the top twelve by |t| -- max|t| 30.01 and Var(t) 17.282
    # as printed, against 5.87 and 1.308 once removed. A sandwich cannot express this;
    # the honest instrument is a binomial bound on the win count, so these are excluded
    # from every distributional statistic and reported separately.
    # the bet tuple is (pnl, game_id, bid, ask, y) -- the SETTLEMENT is index 4.
    ys = {b[4] for b in bets}
    if len(ys) < 2:
        excluded.append((key, n, G, f"DEGENERATE: all {n} bets settled {next(iter(ys))} -- no outcome variation"))
        continue
    if G < G_FLOOR or se in (0.0, float("inf")) or not math.isfinite(se):
        excluded.append((key, n, G, "G < 6 (power floor)" if G < G_FLOOR else "degenerate se"))
        continue
    t = m / se
    p = 2 * tdist.sf(abs(t), df=G - 1)
    scored.append(dict(key=key, mean=m, se=se, t=t, p=p, n=n, G=G, ge=ge))

print(f"\n{'='*100}\nSCAN  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}Z   "
      f"settlement calls {calls:,}\n{'='*100}")
print("\nSETTLED STOCK PER FAMILY (the weighting basis; the rate is not the stock)")
print(f"  {'league':12} {'market type':40} {'closes':>7} {'unsettled':>10} {'games':>6}")
for (lg, mt), (tot, uns, gs) in sorted(STOCK.items(), key=lambda x: -len(x[1][2])):
    if tot >= 10: print(f"  {lg:12} {mt[:40]:40} {tot:>7,} {uns:>10,} {len(gs):>6}")

m_eff = len(scored)
print(f"\n{'='*100}\nTHE PRIMARY RESULT: THE DISTRIBUTION\n{'='*100}")
print(f"  m_eff = {m_eff} scored cells (YES side only; the NO twin is -t by identity, so the")
print(f"          cell count is NOT the multiplicity -- see the module docstring)")
if m_eff < 2: raise SystemExit("NO DATA: fewer than two scorable cells")
ts = [s["t"] for s in scored]
vt = sum(x * x for x in ts) / len(ts) - (sum(ts) / len(ts)) ** 2
base = sum((s["G"] - 1) / (s["G"] - 3) for s in scored if s["G"] > 3) / max(
    1, sum(1 for s in scored if s["G"] > 3))
print(f"\n  1. Var(t)          {vt:7.3f}   G-IMPLIED NULL BASELINE {base:7.3f}"
      f"   <- compare to THIS, never to 1.000")
print(f"     read against the permutation null, which reproduces each cell's G. The")
print(f"     pre-registration's 'Var=1.18 => ten cells at mu=3' sits inside this baseline.")
ps = sorted(s["p"] for s in scored)
k10 = max(1, int(0.10 * m_eff))
hc = max(math.sqrt(m_eff) * ((i + 1) / m_eff - ps[i]) /
         math.sqrt(max(ps[i] * (1 - ps[i]), 1e-12)) for i in range(k10))
print(f"\n  2. Higher Criticism {hc:7.3f}  over the smallest {k10} p-values   [CONTESTED"
      f" implementation]\n     registered fallback  count(p<0.01) = {sum(p < 0.01 for p in ps)}"
      f"   expected under null {0.01 * m_eff:.1f}")
mx = max(abs(s["t"]) for s in scored)
enull = math.sqrt(2 * math.log(m_eff)) if m_eff > 1 else float("nan")
print(f"\n  3. max|t|          {mx:7.3f}   null expected max {enull:7.3f}"
      f"   P(null max>3) = {1 - (1 - 0.0027) ** m_eff:5.2f}")
nz = sum(1 for s in scored if abs(s["t"]) > 1.96)
sd_pair = math.sqrt(2) * math.sqrt(m_eff * 0.05 * 0.95)
print(f"\n  cells with |t|>1.96: {nz}   null expectation {0.05 * m_eff:.1f}"
      f"   +/-1.96sd band {max(0, 0.05 * m_eff - 1.96 * sd_pair):.1f}..{0.05 * m_eff + 1.96 * sd_pair:.1f}")
print(f"     (band widened by sqrt(2) for the YES/NO pairing: sd {sd_pair:.1f} not"
      f" {math.sqrt(m_eff * 0.05 * 0.95):.1f})")
print(f"\n  Bonferroni |t| at m_eff={m_eff}: {abs(tdist.ppf(0.025 / m_eff, df=30)):.2f} (df=30 ref)"
      f"   nominations require the HELD-OUT read, never this table")

print(f"\n{'='*100}\nEXCLUDED CELLS, every one with its reason (silent exclusion shrinks a family)\n{'='*100}")
for key, n, G, why in excluded: print(f"  {str(key):58} n={n:<5} G={G:<4} {why}")
print(f"  excluded {len(excluded)} of {len(CELLS)} cells")
for k in sorted(DROP): print(f"  NOTE {k}: {DROP[k]}")

if os.environ.get("ROWS_JSON"):                 # the permutation null consumes the INPUTS
    with open(os.environ["ROWS_JSON"], "w") as fh:
        json.dump([{"lg": k[0], "mt": k[1], "dec": k[2], "game": b[1], "bid": b[2],
                    "ask": b[3], "y": b[4]} for k, bs in CELLS.items() for b in bs], fh)
    print(f"\n  wrote ROWS_JSON {os.environ['ROWS_JSON']}"
          f" ({sum(len(v) for v in CELLS.values()):,} bet inputs)")
if os.environ.get("CELLS_JSON"):
    with open(os.environ["CELLS_JSON"], "w") as fh:
        json.dump({"run": f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%MZ}", "m_eff": m_eff,
                   "var_t": vt, "var_t_null_baseline": base, "hc": hc, "max_abs_t": mx,
                   "null_expected_max": enull, "p_lt_01": sum(p < 0.01 for p in ps),
                   "p_lt_01_expected": 0.01 * m_eff, "cells_excl_zero": nz,
                   "cells_excl_zero_expected": 0.05 * m_eff, "pair_sd": sd_pair,
                   "excluded": [{"key": list(map(str, k)), "n": n, "G": G, "why": w}
                                for k, n, G, w in excluded],
                   "cells": [{"lg": s2["key"][0], "mt": s2["key"][1], "dec": s2["key"][2],
                              "mean_cents": s2["mean"], "t": s2["t"], "p": s2["p"],
                              "n": s2["n"], "G": s2["G"], "g_eff": s2["ge"]} for s2 in scored]}, fh)
    print(f"  wrote CELLS_JSON {os.environ['CELLS_JSON']} ({m_eff} scored cells)")

print(f"\n{'='*100}\nAPPENDIX: every cell, never the best one. Statistics above ran on the")
print(f"deduplicated YES set; the NO twin of each row is -t by identity.\n{'='*100}")
print(f"  {'league':6} {'market type':34} {'dec':>5} {'mean c':>8} {'t':>7} {'p':>8} "
      f"{'n':>6} {'G':>5} {'G_eff':>7}")
for s in sorted(scored, key=lambda x: x["p"]):
    lg, mt, lo = s["key"]
    print(f"  {lg:6} {mt[:34]:34} {lo:5.1f} {s['mean']:+8.2f} {s['t']:+7.2f} {s['p']:8.5f} "
          f"{s['n']:>6,} {s['G']:>5} {s['ge']:>7.1f}" + ("  UNDERPOWERED" if s["G"] < 25 else ""))
