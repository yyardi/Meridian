"""Scan the NON-spread market families for the same arithmetic contradiction.

    python cfb/run_family_scan.py [--since 2026-09-13] [--league cfb|nfl|mlb]
                                  [--phase inplay|pregame|both] [--census]

`cfb/run_ladder_scan.py` asks whether one spread ladder contradicts itself.
This asks the four questions the spread ladder cannot: the totals ladder (the
same monotonicity with the sign reversed), the winner market against the 0-line
spread, a segment total against the whole it sits inside, and the Frechet bounds
between a total and the two parts that sum to it. The derivations, the
EXACT-vs-EXPECTED split and what each one is worth are in
docs/math/consistency-families.md.

REPORT ONLY. Places nothing, imports no venue client, and takes no decision.

TWO CAVEATS THAT ARE WORSE HERE THAN ON THE SPREAD LADDER, both printed on
every run so a reader cannot take a number without them:

1. SIMULTANEITY. Legs are keyed on (game_id, captured_at), which is ONE SWEEP,
   not one instant: the recorder stamps a cycle with the time the cycle started
   and the measured fetch spread inside a stamp is median 5s, p90 14s, max 110s
   (STATUS 0bs). Within one ladder those rungs are at least adjacent in the
   sweep. ACROSS families they need not be, and nothing in the recorder orders
   them, so a cross-family "violation" in play can be two prices that never
   coexisted. Only a genuinely simultaneous fetch settles it, which is what
   STATUS 0bu did for spreads and what nobody has done for these.

2. --census IS NOT OPTIONAL BEFORE BELIEVING A NUMBER. The line and the team of
   a totals rung are parsed out of the slug, and an inverted parse is the defect
   that produced an 88c phantom arbitrage on the spread board. The census prints
   the parse, the rung counts and the mean YES mid per rung; a totals family
   whose mean mid does not FALL across rising lines has a broken parse and its
   dollar figure is meaningless.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import families, scan  # noqa: E402

#: (winner, spread, game total, team total) per league, venue-probed
#: 2026-09-02 for football (analysis/archive/nfl_day_one_survey.py) and read
#: off the MLB tape in cfb/run_ladder_calibration.py.
#:
#: `..._team_full_game_total` IS THE GAME TOTAL and `..._team_points_full_game_total`
#: is the one-team total. The venue's naming says the opposite of what it means
#: and both settlement routines in this repo agree on the meaning, so the name
#: is never read as evidence: the mapping is pinned here and tested.
SPORT = {
    "cfb": ("football_team_full_game_winner", "football_team_full_game_spread",
            "football_team_full_game_total", "football_team_points_full_game_total"),
    "nfl": ("football_team_full_game_winner", "football_team_full_game_spread",
            "football_team_full_game_total", "football_team_points_full_game_total"),
    "mlb": ("baseball_team_full_game_winner", "baseball_team_full_game_spread",
            "baseball_team_full_game_total", None),
}

#: Segment totals that sit INSIDE the full-game total, per league. The pairs are
#: (part, part, whole) decompositions with no unquoted residual EXCEPT overtime,
#: which is why the runner reports the two Frechet directions separately: the
#: lower bound survives overtime and the upper bound does not.
SEGMENTS = {
    "cfb": [("football_game_first_half_total", "football_game_second_half_total",
             "football_team_full_game_total")],
    "nfl": [("football_game_first_half_total", "football_game_second_half_total",
             "football_team_full_game_total"),
            ("football_game_first_quarter_total", "football_game_second_quarter_total",
             "football_game_first_half_total"),
            ("football_game_third_quarter_total", "football_game_fourth_quarter_total",
             "football_game_second_half_total")],
    "mlb": [],
}

SQL = """
SELECT ms.game_id, ms.sports_market_type, ms.market_slug, ms.line,
       ms.best_bid, ms.best_ask, ms.captured_at,
       (SELECT max(quantity) FROM book_levels b
         WHERE b.snapshot_id = ms.id AND b.level_index = 0 AND b.side = 'bid'),
       (SELECT max(quantity) FROM book_levels b
         WHERE b.snapshot_id = ms.id AND b.level_index = 0 AND b.side = 'offer')
FROM market_snapshots ms
WHERE ms.captured_at >= CAST(:since AS timestamptz)
  AND ms.market_slug LIKE :pat
  AND ms.sports_market_type = ANY(:types)
  AND ms.best_bid IS NOT NULL AND ms.best_ask > ms.best_bid
  AND ms.game_start_time IS NOT NULL AND {phase}
"""
# max(quantity) rather than a bare scalar subquery: book_levels holds duplicate
# level_index = 0 rows -- worst seen 27 on NFL, 12 on CFB (STATUS 0bk).

PHASE = {"inplay": "ms.captured_at > ms.game_start_time",
         "pregame": "ms.game_start_time > ms.captured_at",
         "both": "TRUE"}


def line_of(slug: str, recorded) -> float | None:
    """The rung's line, preferring the recorded column and falling back to the
    slug's trailing `...-24pt5`.

    Two sources on purpose. `market_snapshots.line` is what the venue sent;
    the slug is what the venue named. They should agree, and the census prints
    how often they do -- a silent disagreement between a payload field and the
    string beside it is the shape of defect that put a whole spread scan on the
    wrong side of zero.

    THE `neg-`/`pos-` GROUP IS NOT DECORATION. Spread slugs carry the sign as a
    token (`asc-cfb-akron-wake-2026-09-03-neg-10pt5`) and BOTH signs are listed
    for the same magnitude in the same game. A bare `-(\\d+)pt(\\d)$` matches the
    tail of either and returns +10.5 for both, so the two opposite rungs collide
    on one dict key and whichever the cursor yields last silently wins -- a rung
    priced as its own mirror image. Totals slugs (`...-total-29pt5`) carry no
    sign token, which is why the group is optional rather than required.
    `cfb/run_ladder_scan.py:line_of` has always read the token; this fallback
    did not, and it is the fallback that runs whenever the recorded column is
    NULL.
    """
    if recorded is not None:
        return float(recorded)
    m = re.search(r"-(neg-|pos-)?(\d+)pt(\d)$", slug)
    if m is None:
        return None
    mag = float(m.group(2)) + float(m.group(3)) / 10.0
    return -mag if m.group(1) == "neg-" else mag


def team_of(slug: str) -> str | None:
    """Which team a `...-tt-<team>-...` team-total rung belongs to.

    The same token `cfb/run_ladder_calibration.py:settle` reads to settle these
    markets, so a rung this function mis-assigns is a rung that file would also
    settle wrong -- the two agree by construction rather than by luck.
    """
    toks = slug.split("-")
    if "tt" not in toks:
        return None
    i = toks.index("tt")
    return toks[i + 1] if i + 1 < len(toks) else None


def claims_by_line(rungs: dict[float, tuple]) -> dict[float, families.Claim]:
    return {ln: families.Claim(f"{ln:+.1f}", *q) for ln, q in rungs.items()}


def scan_totals_ladder(game, rungs) -> list[families.Basket]:
    """Candidate (a): P(Over N) is non-increasing in N.

    `families.totals_ladder_pairs`, NOT `scan.scan_ladder` -- the spread
    scanner's ordering is the mirror of this one and reusing it here would
    report the correct board as broken.
    """
    c = claims_by_line(rungs)
    out = []
    for sub, sup in families.totals_ladder_pairs(c):
        v = families.dominance(game, c[sub], c[sup], "totals_ladder")
        if v is not None:
            out.append(v)
    return out


def scan_winner_against_zero(game, winner, spread_rungs) -> list[families.Basket]:
    """Candidate (b): the winner market IS the spread at line 0, so the identity
    is violated in EITHER direction and both are scanned."""
    zero = spread_rungs.get(0.0)
    if winner is None or zero is None:
        return []
    w = families.Claim("winner", *winner)
    z = families.Claim("spread+0.0", *zero)
    out = [families.dominance(game, w, z, "winner_is_line_zero"),
           families.dominance(game, z, w, "winner_is_line_zero")]
    return [v for v in out if v is not None]


def scan_segment_in_whole(game, part_rungs, whole_rungs, tag) -> list[families.Basket]:
    """Candidate (c), the containment form: P(part > n) <= P(whole > n)."""
    part, whole = claims_by_line(part_rungs), claims_by_line(whole_rungs)
    out = []
    for n, big_n in families.containment_pairs(part, whole):
        v = families.dominance(game, part[n], whole[big_n], f"segment_in_whole:{tag}")
        if v is not None:
            out.append(v)
    return out


def scan_frechet(game, whole_rungs, a_rungs, b_rungs, tag,
                 *, allow_upper: bool) -> list[families.Basket]:
    """Candidates (c) and (d), the bound form. `allow_upper` is the overtime
    switch: the upper bound needs the parts to exhaust the whole, the lower one
    does not, and a caller that cannot show the decomposition is complete must
    pass False rather than take the bigger number."""
    whole, a, b = (claims_by_line(whole_rungs), claims_by_line(a_rungs),
                   claims_by_line(b_rungs))
    out = []
    for big_n, (na, nb), which in families.frechet_splits(whole, [a, b]):
        parts = (a[na], b[nb])
        if which == "frechet_upper":
            v = (families.frechet_upper(game, whole[big_n], parts,
                                        relation=f"frechet_upper:{tag}")
                 if allow_upper else None)
        else:
            v = families.frechet_lower(game, whole[big_n], parts,
                                       relation=f"frechet_lower:{tag}")
        if v is not None:
            out.append(v)
    return out


def census(by_type: dict[str, dict[float, list[float]]]) -> None:
    """Print the parse before any dollar figure. Mean YES mid per rung must FALL
    across rising totals lines; if it rises, the parse or the YES frame is
    inverted and every number below it is noise."""
    print("  census -- mean YES mid by line (totals must FALL, spreads must RISE)")
    for mt in sorted(by_type):
        cells = by_type[mt]
        shown = sorted(cells)[:9]
        body = "  ".join(f"{ln:+.1f}:{sum(cells[ln]) / len(cells[ln]):.3f}"
                         f"(n={len(cells[ln])})" for ln in shown)
        print(f"    {mt:<46} {body}")


def coverage_census(by_type: dict[str, dict[float, list[float]]],
                    league: str) -> dict[str, int]:
    """Print each relation's DENOMINATOR -- how many baskets the listed lines
    can form before any price is looked at.

    Without this a relation with no coverage and a relation that is clean are
    the same printed zero. Two of the five candidates have a denominator of 0 on
    this venue's all-half-point grid; see `families.coverage`.
    """
    winner_t, spread_t, total_t, _ = SPORT[league]
    cov = families.coverage({k: list(v) for k, v in by_type.items()},
                            totals=total_t, spread=spread_t, winner=winner_t,
                            segments=SEGMENTS[league])
    print("  coverage -- formable baskets per relation (the denominator)")
    for rel in sorted(cov):
        note = "  <-- NO COVERAGE, a zero here is not a clean board" \
            if cov[rel] == 0 else ""
        print(f"    {rel:<46} {cov[rel]:>9,}{note}")
    return cov


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-13")
    ap.add_argument("--league", default="cfb", choices=sorted(SPORT))
    ap.add_argument("--phase", default="inplay", choices=sorted(PHASE))
    ap.add_argument("--census", action="store_true",
                    help="print the parse census and exit without pricing")
    ap.add_argument("--allow-upper-frechet", action="store_true",
                    help="price the Frechet UPPER bound too. Off by default: it "
                         "is exact only if the quoted parts exhaust the whole, "
                         "and whether the venue's second-half total carries "
                         "overtime is unverified.")
    a = ap.parse_args()

    from sqlalchemy import create_engine, text

    winner_t, spread_t, total_t, team_total_t = SPORT[a.league]
    types = [t for t in SPORT[a.league] if t]
    for parts in SEGMENTS[a.league]:
        types += [t for t in parts if t not in types]

    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        rows = c.execute(text(SQL.format(phase=PHASE[a.phase])),
                         {"since": a.since, "pat": f"%-{a.league}-%",
                          "types": types}).all()

    # (game, sweep) -> market type -> line -> quote. Keyed on captured_at so the
    # legs of any basket come from ONE sweep; see caveat 1 in the docstring.
    board: dict[tuple, dict[str, dict[float, tuple]]] = defaultdict(
        lambda: defaultdict(dict))
    mids: dict[str, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for gid, mt, slug, line, bid, ask, ts, qb, qo in rows:
        if qb is None or qo is None:
            continue
        ln = line_of(slug, line)
        if ln is None and mt != winner_t:
            continue
        key = mt
        if mt == team_total_t:
            team = team_of(slug)
            if team is None:
                continue
            key = f"{mt}|{team}"
        quote = (float(bid), float(ask), float(qb), float(qo))
        board[(gid, ts)][key][0.0 if ln is None else ln] = quote
        mids[key][0.0 if ln is None else ln].append((float(bid) + float(ask)) / 2.0)

    print(f"family scan  league={a.league}  phase={a.phase}  since={a.since}")
    print(f"  {len(board):,} sweeps, {len(rows):,} rungs, {len(mids)} families")
    census(mids)
    cov = coverage_census(mids, a.league)
    if a.census:
        return 0

    found: list[families.Basket] = []
    for (gid, _ts), fam in board.items():
        found += scan_totals_ladder(gid, fam.get(total_t, {}))
        winner = fam.get(winner_t, {}).get(0.0)
        found += scan_winner_against_zero(gid, winner, fam.get(spread_t, {}))
        teams = sorted(k for k in fam if k.startswith(f"{team_total_t}|")) \
            if team_total_t else []
        if len(teams) == 2 and fam.get(total_t):
            found += scan_frechet(gid, fam[total_t], fam[teams[0]], fam[teams[1]],
                                  "team_totals", allow_upper=True)
        for pa, pb, whole in SEGMENTS[a.league]:
            if fam.get(pa) and fam.get(pb) and fam.get(whole):
                found += scan_segment_in_whole(gid, fam[pa], fam[whole], pa)
                found += scan_frechet(gid, fam[whole], fam[pa], fam[pb], whole,
                                      allow_upper=a.allow_upper_frechet)

    by_relation: dict[str, list[families.Basket]] = defaultdict(list)
    for v in found:
        by_relation[v.relation.split(":")[0]].append(v)

    print(f"  {len(found):,} contradictions across {len(by_relation)} relations")
    # A relation with no formable baskets is listed even when it found nothing,
    # with its coverage beside it, so a bare 0 can never be read as a clean
    # board. `formable` is per sweep AND assumes every pooled line is listed in
    # that sweep, so it is an UPPER BOUND on the denominator, not the
    # denominator: the true one needs the per-sweep line set and is not computed
    # here. It is printed as a coverage figure and must not be divided into.
    for rel in sorted(set(by_relation) | {k.split(":")[0] for k in cov}):
        vs = by_relation.get(rel, [])
        best = scan.best_per_game(vs)
        formable = sum(n for k, n in cov.items() if k.split(":")[0] == rel)
        print(f"    {rel:<24} {len(vs):>6,} violations  "
              f"(<={formable:,} formable/sweep)   "
              f"best/game summed ${sum(best.values()):,.2f} "
              f"over {len(best)} games")
    # ONE best per game across ALL relations, never the sum of the per-relation
    # lines above. A single mispriced total rung contradicts its own ladder AND
    # every Frechet split it appears in; those baskets share a leg and compete
    # for the same depth, which is the defect that overstated CFB 2.5x in 0bi
    # one level down.
    joint = scan.best_per_game(found)
    print(f"  JOINT best single basket per game, summed: ${sum(joint.values()):,.2f} "
          f"over {len(joint)} games")
    print("  SIZE IS QUOTED, NOT FILLED, and a three-leg basket needs three "
          "fills. Cross-family legs are not known to be simultaneous.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
