"""The IN-GAME scan. Same grid and same statistics as cfb/run_scan.py, new population.

Everything screened so far was PREGAME closes -- 22,870 of them. This screens the in-game
tape: 17,987,154 live ticks in the last 7 days, ~790x the row count and almost none of it
independent. Prices move continuously, the spread structure differs, and "is there any price
region where crossing pays" has only ever been answered pregame.

## ★ PRE-REGISTERED BEFORE ANY CELL WAS SEEN

**SAMPLING: one tick per market per 10 minutes of wall clock, taking the FIRST tick in each
bucket.** Declared here, not passed as a parameter, because a sampling rate chosen after
seeing the cells is the population error in its purest form. At 18M rows an unsampled scan
makes every cell enormous and every interval meaningless through DEPENDENCE rather than
evidence -- the degeneracy lesson in a new costume, an estimator reporting enormous
confidence built out of repetition.

**CLUSTERING UNIT IS THE GAME, and that is decisive here rather than merely correct.** A
pregame cell held ~1.66 rungs per game; an in-game cell can hold hundreds of ticks from one
game, all driven by one outcome. `G_eff = n^2 / sum(cluster^2)` therefore prints on EVERY
cell, not only in the summary, so a cell with n=2,000 and G_eff=12 is visible as such at a
glance instead of reading as 2,000 observations.

**SPREAD IS A GRID AXIS FROM THE START, not a conditioning discovered at the end.** The
pregame answer was that the entire excess IS the spread (p<0.01 count 0,0,2,5,16 monotone in
the spread cap, and every significant cell losing). Buckets: half-spread <=1c, 1-3c, >3c.

**LIVE IS DERIVED FROM THE CLOCK, NEVER FROM `is_live`.** `core/board.py:market_state()` is
the one definition and it says the flag cannot be trusted in either direction: too early
right after kickoff, and *frozen true forever* when a market drops off the board -- 12,290
markets carry a stale `is_live=true` on their last row and 11,227 have not been written in
600s. A population anchored on the flag collects those end-of-life rows; one anchored on the
clock window does not. Window = [game_start_time, game_start_time + LIVE_H hours].

Settlement is the same venue endpoint, so the frame question does not reopen.

THE HONEST EXPECTATION is that this reproduces the pregame answer, in which case the finding
is that the conclusion holds across a second and much larger population. If it does not, it
gets the same scepticism everything else got.
"""
import datetime as dt, json, math, os, re, sys
from collections import defaultdict

from scipy.stats import t as tdist
from sqlalchemy import create_engine, event, text

from core import settlements
from core.leagues import LEAGUES, venue_patterns
from core.polymarket.client import PolymarketGatewayClient

from core.fees import POLYMARKET_TAKER as FEE_PM  # noqa: E402  0.0695, the venue's feeCoefficient
G_FLOOR = 6
DECILES = [(i / 10, (i + 1) / 10) for i in range(10)]
SPREAD_BUCKETS = ((0.0, 1.0, "<=1c"), (1.0, 3.0, "1-3c"), (3.0, 1e9, ">3c"))
SAMPLE_MIN = 10          # PRE-REGISTERED: one tick per market per 10 minutes, first in bucket
LIVE_H = {"cfb": 4.5, "nfl": 4.5, "wnba": 3.0, "mlb": 4.5, "cricket": 9.0, "tabletennis": 2.0}
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
#: CAST(...), not `::` -- SQLAlchemy will not bind a parameter followed by a
#: colon, so `:since::timestamptz` bound nothing and postgres got the
#: literal. Inherited by copy from cfb/run_scan.py; see the note there.
_FLOOR = "\n    AND {a}captured_at >= CAST(:since AS timestamptz)"
CLOSE_SQL = """
WITH g AS (SELECT game_id, min(game_start_time) ko FROM market_snapshots
  WHERE market_slug LIKE ANY(:pats) AND game_start_time IS NOT NULL GROUP BY 1)
SELECT DISTINCT ON (s.market_slug, floor(extract(epoch from s.captured_at) / (60 * :smin)))
       s.market_slug slug, s.sports_market_type mt, s.game_id gid,
       s.best_bid::float bid, s.best_ask::float ask
FROM market_snapshots s JOIN g ON g.game_id = s.game_id
WHERE s.market_slug LIKE ANY(:pats)
  -- LIVE FROM THE CLOCK, never from is_live (core/board.py: the flag freezes true forever
  -- when a market drops off the board; 11,227 such rows are >600s stale).
  AND s.captured_at >= g.ko AND s.captured_at < g.ko + (:liveh * interval '1 hour')
  AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL AND s.best_ask >= s.best_bid
  AND g.ko < now() - interval '6 hours'
ORDER BY s.market_slug, floor(extract(epoch from s.captured_at) / (60 * :smin)), s.captured_at
"""
CLOSE = CLOSE_SQL


def partition_floors(conn, table="market_snapshots"):
    """Every partition's LOWER bound, asked of the catalogue rather than assumed.

    The scheme is monthly today. A check that hardcoded "the first of a month"
    would keep passing and silently stop pruning if retention ever moved to
    weekly partitions, so the boundaries are read from `relpartbound`.
    """
    rows = conn.execute(text(
        "SELECT pg_get_expr(c.relpartbound, c.oid) b FROM pg_class c "
        "JOIN pg_inherits i ON i.inhrelid = c.oid "
        "WHERE i.inhparent = CAST(:t AS regclass)"),   # not :t::regclass
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


def poisson_binomial_p(trials):
    """Exact two-sided p for k wins among independent Bernoullis with DIFFERENT p0.

    ONE TRIAL PER GAME. A cell holds several rungs of the same game -- 305 of 324 cells
    have n > G, median 1.66 rungs per game, max 14.58 -- and those rungs are functions of
    ONE game outcome. A Poisson-binomial over all n bets treats them as independent and
    understates p by roughly the clustering factor, which is the dependence the sandwich
    existed to handle: swapping t -> Poisson-binomial fixes degeneracy and would silently
    RE-IMPORT clustering. So trials are one per game.

    AND THE PICK IS THE RUNG NEAREST THE DECILE CENTRE, not the first by slug. Slugs sort
    by side then by line as a STRING, so first-by-slug systematically selects one corner
    of the decile -- which would bias the very break-even variation the Poisson-binomial
    was adopted to respect. Nearest-to-centre is deterministic and unbiased with respect
    to price within the band.

    Break-even varies per trial (a single midpoint-derived break-even was wrong by 3.4c
    on one measured cell), so each trial carries its own ask_i + fee(ask_i).

    TWO-SIDED BY THE SMALL-p METHOD: the total probability of every outcome AT MOST AS
    LIKELY as the observed one -- scipy.binomtest's convention, so this reduces EXACTLY
    to it when the p0 are equal (asserted in cfb/test_scan_statistic.py) and the numbers
    in the pre-registration stay on one convention. Twice-the-smaller-tail is the other
    defensible choice and differs materially here: 0.0122 vs 0.0131 on the 46/46 cell,
    0.0634 vs 0.0459 on the 12/0 one. Named rather than assumed.
    """
    ps = [q for q, _ in trials]
    k = sum(w for _, w in trials)
    pmf = [1.0]
    for q in ps:                                    # O(G^2) DP, trivial at these G
        nxt = [0.0] * (len(pmf) + 1)
        for i, v in enumerate(pmf):
            nxt[i] += v * (1 - q)
            nxt[i + 1] += v * q
        pmf = nxt
    tol = pmf[k] * (1 + 1e-9)
    return min(1.0, sum(v for v in pmf if v <= tol)), k, len(ps)


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
#: KNOWN reference run, as `pat=count` pairs, PLUS the floor that run used.
#: `SCAN_EXPECT='since=NONE,%-cfb-%=111,%-nfl-%=222'`   <- fake counts: an
#: example carrying a real run's numbers is the thing someone copies.
#:
#: ★ THE `since=` TERM IS MANDATORY AND IT IS THE WHOLE POINT. Row counts are a
#: fact about one tape window AND one floor, not an invariant. The reference for
#: the 13-query-to-1-query change is the 05:28Z run of 2026-09-14, taken with NO
#: floor -- and cfb, nfl and wnba all have pre-September tape, so a FLOORED run
#: legitimately returns fewer rows for them. Comparing across floors would fire
#: this check on a correct change, which is the worst kind of guard: one that
#: trains people to ignore it. A floor mismatch is therefore a REFUSAL to
#: compare, reported as such, not a count mismatch.
_EXP = dict((k, v) for k, _, v in
            (e.partition("=") for e in (os.environ.get("SCAN_EXPECT") or "").split(",") if e))
EXPECT_SINCE = _EXP.pop("since", None)
EXPECT = {k: int(v) for k, v in _EXP.items()}
if EXPECT and EXPECT_SINCE is None:
    raise SystemExit(
        "SCAN_EXPECT is missing its `since=` term. Row counts depend on the floor, "
        "so a reference without one cannot be compared. Use `since=NONE` for a "
        "reference taken with no floor.")
if EXPECT:
    _ref = None if EXPECT_SINCE.upper() == "NONE" else EXPECT_SINCE
    if _ref != SINCE:
        raise SystemExit(
            f"SCAN_EXPECT was taken with since={EXPECT_SINCE} and this run uses "
            f"since={SINCE or 'NONE'}. Row counts are not comparable across floors "
            "-- a floored run legitimately returns fewer rows wherever a pattern "
            "has tape before the floor. Compare floored against floored.")

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
# ONE QUERY PER LEAGUE, not one for all patterns: the live window LIVE_H differs by sport,
# so a single LIKE ANY pass cannot carry the right bound for each. Six passes, not one, and
# that is the price of not using a wrong window for five of the six.
allrows = []
with eng.connect() as c:
    for _lg in sorted({l for l, _ in PATS}):
        pats_l = [p for l, p in PATS if l == _lg]
        got = [dict(r._mapping) for r in c.execute(text(CLOSE),
               {"pats": pats_l, "smin": SAMPLE_MIN, "liveh": LIVE_H.get(_lg, 4.0)})]
        allrows.extend(got)
        print(f"  ... {_lg} {len(got):,} sampled ticks (1 per market per {SAMPLE_MIN} min,"
              f" window {LIVE_H.get(_lg, 4.0)}h)")

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
            hs_c = (a - m) * 100                       # half-spread in cents
            sb = next(lab for x, yv, lab in SPREAD_BUCKETS if x <= hs_c < yv)
            CELLS[(lg, mt, lo, sb)].append((y - a - fee(a), r["gid"], r["bid"], a, y,
                                            abs(m - (lo + 0.05))))
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
scored, excluded, pb_rows, pb_excluded = [], [], [], []
for key, bets in sorted(CELLS.items()):
    m, se, n, G, ge = clustered([100 * b[0] for b in bets], [b[1] for b in bets])
    # PRIMARY, and it needs no exclusion: a degenerate cell gets a legitimate p here.
    # one trial per GAME, and within a game the rung NEAREST THE DECILE CENTRE (index 5).
    best = {}
    for bb in bets:
        if bb[1] not in best or bb[5] < best[bb[1]][5]: best[bb[1]] = bb
    tr = [(min(max(bb[3] + fee(bb[3]), 1e-9), 1 - 1e-9), 1 if bb[4] == 1 else 0)
          for bb in best.values() if bb[4] in (0, 1)]
    # THE G FLOOR GATES THIS PATH TOO. It used to gate only the sandwich, so a TWO-GAME
    # cell ranked in the top ten at p=8.9e-04 -- and a two-game cell cannot nominate
    # anything, which is what the floor is for. Excluded primary cells print below.
    hs = sorted((bb[3] - (bb[3] + bb[2]) / 2) * 100 for bb in bets)   # half-spread, cents
    med_hs = hs[len(hs) // 2]
    if tr and len(tr) >= G_FLOOR:
        pv, kk, gt = poisson_binomial_p(tr)
        pb_rows.append(dict(key=key, p=pv, k=kk, G=gt, n=n, dropped=n - gt, mean=m,
                            be=sum(q for q, _ in tr) / gt, hs=med_hs))
    elif tr:
        pb_excluded.append((key, len(tr), f"G={len(tr)} < {G_FLOOR} floor: cannot nominate"))
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
print(f"\n{'='*100}\nPRIMARY: POISSON-BINOMIAL, ONE TRIAL PER GAME (no exclusion needed)\n{'='*100}")
bp = sorted(r["p"] for r in pb_rows)
if bp:
    print(f"  cells {len(bp)}   p<0.05: {sum(x < 0.05 for x in bp)} (null {0.05*len(bp):.1f})"
          f"   p<0.01: {sum(x < 0.01 for x in bp)} (null {0.01*len(bp):.1f})   min p {bp[0]:.2e}")
    print(f"  Bonferroni at m={len(bp)} needs p < {0.05/len(bp):.2e};"
          f" cells clearing it: {sum(x < 0.05/len(bp) for x in bp)}")
    print(f"  {'cell':50} {'k/G':>8} {'rate':>7} {'b/e':>7} {'p':>10} {'rungs':>7} {'half-sp':>8}")
    for r in sorted(pb_rows, key=lambda x: x["p"])[:10]:
        lg2, mt2, lo2, sb2 = r["key"]
        print(f"  {lg2 + ' ' + mt2[:26] + ' ' + format(lo2, '.1f') + ' ' + sb2:50} "
              f"{str(r['k'])+'/'+str(r['G']):>8} {r['k']/r['G']:7.1%} {r['be']:7.1%} "
              f"{r['p']:10.2e} {r['dropped']:>7} {r['hs']:7.1f}c")
if pb_excluded:
    print(f"\n  PRIMARY cells excluded by the G floor ({len(pb_excluded)}), printed not dropped:")
    for k2, g2, why in pb_excluded[:12]: print(f"    {str(k2):58} {why}")

# ---- CONDITIONING ON COST. The top cells lose because the ASK is 7-14c above the MID
# on thin market types, which is the venue's spread and not an edge: nobody crosses a
# 14c spread, and selling into it is the making study, already negative with power. So
# the question is whether anything survives once cost is held roughly constant.
print(f"\n{'='*100}\nCONDITIONED ON COST: the same primary, restricted by median half-spread")
print(f"{'='*100}")
print(f"  {'max half-spread':>16} {'cells':>6} {'p<0.05':>7} {'null':>6} {'p<0.01':>7} "
      f"{'null':>6} {'min p':>10}  losing/winning among p<0.05")
for cap in (1.0, 2.0, 3.0, 5.0, 1e9):
    sub = [r for r in pb_rows if r["hs"] <= cap]
    if len(sub) < 5: continue
    ps2 = sorted(r["p"] for r in sub)
    sig = [r for r in sub if r["p"] < 0.05]
    lose = sum(1 for r in sig if r["k"] / r["G"] < r["be"])
    lab = "all" if cap > 100 else f"<= {cap:.0f}c"
    print(f"  {lab:>16} {len(sub):>6} {sum(x < 0.05 for x in ps2):>7} {0.05*len(sub):>6.1f} "
          f"{sum(x < 0.01 for x in ps2):>7} {0.01*len(sub):>6.1f} {ps2[0]:10.2e}  "
          f"{lose}/{len(sig)-lose}")
print("  a cost effect shrinks toward the null as the cap tightens; an EDGE would not.")

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

def _plain(o):
    """numpy/scipy scalars -> python, and NOTHING else silently.

    ★ THE 05:28Z RUN OF 2026-09-14 DIED HERE. `p_lt_01` is
    `sum(p < 0.01 for p in ps)` over scipy p-values, which is a numpy int64,
    and `json.dump` raised `Object of type int64 is not JSON serializable`
    after 225 bytes -- so CELLS_JSON was left as TRUNCATED, UNPARSEABLE JSON
    that still had a plausible size and a fresh mtime. The scan exited 1 as its
    contract promises, but the artifact it left behind was worse than no file.
    Narrow on purpose: anything without `.item()` still raises, so a genuine
    unserialisable object is not swallowed.
    """
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _write_json(path: str, payload) -> None:
    """Write via a temp file and rename, so a crash leaves the OLD file.

    The idiom is lifted from `core/settlements.py`, which has had it for weeks --
    a partial artifact that looks complete is the failure mode both of these
    guard against, and only one of them was doing it.
    """
    import tempfile
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, default=_plain)
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


if os.environ.get("ROWS_JSON"):                 # the permutation null consumes the INPUTS
    _write_json(os.environ["ROWS_JSON"],
                [{"lg": k[0], "mt": k[1], "dec": k[2], "sb": k[3], "game": b[1], "bid": b[2],
                  "ask": b[3], "y": b[4]} for k, bs in CELLS.items() for b in bs])
    print(f"\n  wrote ROWS_JSON {os.environ['ROWS_JSON']}"
          f" ({sum(len(v) for v in CELLS.values()):,} bet inputs)")
if os.environ.get("CELLS_JSON"):
    _write_json(os.environ["CELLS_JSON"], {"run": f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%MZ}", "m_eff": m_eff,
                   "var_t": vt, "var_t_null_baseline": base, "hc": hc, "max_abs_t": mx,
                   "null_expected_max": enull, "p_lt_01": sum(p < 0.01 for p in ps),
                   "p_lt_01_expected": 0.01 * m_eff, "cells_excl_zero": nz,
                   "cells_excl_zero_expected": 0.05 * m_eff, "pair_sd": sd_pair,
                   "excluded": [{"key": list(map(str, k)), "n": n, "G": G, "why": w}
                                for k, n, G, w in excluded],
                   "cells": [{"lg": s2["key"][0], "mt": s2["key"][1], "dec": s2["key"][2], "sb": s2["key"][3],
                              "mean_cents": s2["mean"], "t": s2["t"], "p": s2["p"],
                              "n": s2["n"], "G": s2["G"], "g_eff": s2["ge"]} for s2 in scored]})
    print(f"  wrote CELLS_JSON {os.environ['CELLS_JSON']} ({m_eff} scored cells)")

print(f"\n{'='*100}\nAPPENDIX: every cell, never the best one. Statistics above ran on the")
print(f"deduplicated YES set; the NO twin of each row is -t by identity.\n{'='*100}")
print(f"  {'league':6} {'market type':34} {'dec':>5} {'mean c':>8} {'t':>7} {'p':>8} "
      f"{'n':>6} {'G':>5} {'G_eff':>7}")
for s in sorted(scored, key=lambda x: x["p"]):
    lg, mt, lo, sb = s["key"]
    print(f"  {lg:6} {mt[:28]:28} {lo:5.1f} {sb:>5} {s['mean']:+8.2f} {s['t']:+7.2f} {s['p']:8.5f} "
          f"{s['n']:>6,} {s['G']:>5} {s['ge']:>7.1f}" + ("  UNDERPOWERED" if s["G"] < 25 else ""))
