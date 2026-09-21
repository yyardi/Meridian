"""Measure the consistency families on an ARCHIVED pregame-close dump.

    python cfb/run_family_scan_archive.py [docs/math/ladder_calibration_2026-09-11.out]

`run_family_scan.py` needs the recorded database. This one needs nothing but a
file that is already in the repository, so the numbers in
docs/math/consistency-families.md can be re-derived by anyone who checks the
tree out -- including on a box with no Postgres, which is where they were taken.

WHAT THE FILE IS. `run_ladder_calibration.py` prints a `### CSV` section of one
row per settled market: `lg,vg,event_slug,type,slug,line,bid,ask,ttk_min,y`,
where the quote is that market's LAST PREGAME quote and `y` is a settlement
DERIVED from ESPN finals under the venue's frames. 4,456 markets, 60 CFB and 2
NFL games.

THREE THINGS IT CANNOT MEASURE, all of which bound the claims it supports:

1. PREGAME ONLY. Every row is a pregame close. The spread ladder's money is in
   play, where its ordering falls from 85.4% to 67-78% (STATUS 0bp); nothing
   here speaks to that phase for any family.
2. NOT ONE INSTANT. Each market carries its own last-pregame quote, so two legs
   of a basket can be hours apart: the within-game spread of `ttk_min` is median
   159 minutes. That is far worse than the recorder sweep the spread work had to
   defend. The runner therefore stratifies EVERY figure by the legs' `ttk_min`
   gap, and a number that moves across those strata is a staleness artifact
   rather than a price.
3. NO SIZE. The dump carries no book quantity, so there is no dollar figure at
   quoted size here and none is printed -- only per-contract edges in cents.
   `scan.MAX_PLAUSIBLE_SIZE` has nothing to cap.

REPORT ONLY. Places nothing and opens no connection.
"""
from __future__ import annotations

import collections
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import families, scan  # noqa: E402

DEFAULT = os.path.join("docs", "math", "ladder_calibration_2026-09-11.out")

#: Leg-gap strata in minutes, None meaning "no restriction". The point of the
#: last one is that it is the only stratum where the two quotes are even
#: plausibly contemporaneous, and a result that survives it is not stale.
GAPS = (None, 5, 1, 0)


def load(path: str) -> dict[tuple[str, str], dict[str, dict[float, tuple]]]:
    """(league, game) -> family -> line -> (bid, ask, ttk_min, settlement).

    Team totals are split into one family per team, keyed off the `-tt-<team>-`
    token that `run_ladder_calibration.py:settle` reads to settle them, so a
    rung this misassigns is one that file would also settle wrong.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    body = text.split("### CSV", 1)[1].splitlines()[1:]
    out: dict[tuple[str, str], dict[str, dict[float, tuple]]] = (
        collections.defaultdict(lambda: collections.defaultdict(dict)))
    for row in csv.DictReader(body, fieldnames=(
            "lg", "vg", "event_slug", "type", "slug", "line", "bid", "ask",
            "ttk_min", "y")):
        if not row["type"] or row["lg"] not in ("cfb", "nfl", "mlb"):
            continue
        key = row["type"]
        if key == "team_tot":
            toks = row["slug"].split("-")
            if "tt" not in toks:
                continue
            key = f"team_tot|{toks[toks.index('tt') + 1]}"
        line = 0.0 if row["line"] == "" else float(row["line"])
        out[(row["lg"], row["event_slug"])][key][line] = (
            float(row["bid"]), float(row["ask"]), int(row["ttk_min"]),
            int(row["y"]))
    return out


def _claim(line: float, quote: tuple) -> families.Claim:
    """Size is 1.0 because the dump has none: every figure is per contract."""
    return families.Claim(f"{line:+.1f}", quote[0], quote[1], 1.0, 1.0)


def two_leg(board, family: str, higher_is_subset: bool, relation: str):
    """Every ordered pair of one family's rungs, as (lg, game, basket-or-None,
    edge, gap, ordered).

    `higher_is_subset` IS THE WHOLE SIGN OF THE SCAN and is passed rather than
    inferred: a larger totals line is harder to clear (the higher rung is the
    subset), a larger spread line is easier to cover (the lower rung is).
    """
    out = []
    for (lg, game), fams in board.items():
        rungs = fams.get(family, {})
        claims = {ln: _claim(ln, q) for ln, q in rungs.items()}
        pairs = (families.totals_ladder_pairs(claims) if higher_is_subset
                 else families.spread_ladder_pairs(claims))
        for sub, sup in pairs:
            b = families.dominance(game, claims[sub], claims[sup], relation)
            edge = (claims[sub].bid - claims[sup].ask
                    - scan.fee(claims[sub].bid) - scan.fee(claims[sup].ask))
            gap = abs(rungs[sub][2] - rungs[sup][2])
            mid = lambda c: (c.bid + c.ask) / 2.0  # noqa: E731
            out.append((lg, game, b, edge, gap,
                        mid(claims[sup]) >= mid(claims[sub])))
    return out


def three_leg(board):
    """Frechet splits of the game total into the two team totals.

    BOTH directions are priced and `allow_upper` is not a question here: the two
    team totals EXHAUST the game total (overtime points enter all three), so
    there is no unquoted residual and T3 applies. The `--allow-upper-frechet`
    caution in the database runner is about SEGMENT splits, where overtime may
    sit outside the quoted parts.
    """
    up, low = [], []
    for (lg, game), fams in board.items():
        teams = sorted(k for k in fams if k.startswith("team_tot|"))
        tot = fams.get("total", {})
        if len(teams) != 2 or not tot:
            continue
        a_r, b_r = fams[teams[0]], fams[teams[1]]
        for big_n, q_t in tot.items():
            whole = _claim(big_n, q_t)
            for a, q_a in a_r.items():
                for b, q_b in b_r.items():
                    parts = (_claim(a, q_a), _claim(b, q_b))
                    gap = (max(q_t[2], q_a[2], q_b[2])
                           - min(q_t[2], q_a[2], q_b[2]))
                    if a + b <= big_n:
                        edge = whole.bid - scan.fee(whole.bid) - sum(
                            p.ask + scan.fee(p.ask) for p in parts)
                        # NON-VACUOUS only if the two parts cost under $1: above
                        # that, P <= 1 satisfies the bound on its own and the
                        # basket is arithmetic, not a price observation.
                        binds = sum(p.ask for p in parts) < 1.0
                        up.append((lg, game,
                                   families.frechet_upper(game, whole, parts),
                                   edge, gap, binds))
                    if a + b >= big_n:
                        edge = (sum(p.bid - scan.fee(p.bid) for p in parts)
                                - 1.0 - whole.ask - scan.fee(whole.ask))
                        binds = sum(p.bid for p in parts) - 1.0 > 0.0
                        low.append((lg, game,
                                    families.frechet_lower(game, whole, parts),
                                    edge, gap, binds))
    return up, low


def report(name: str, recs, last_column: str) -> None:
    print(f"\n=== {name} ===")
    print(f"  {'gap':>6} {'lg':>4} {'pairs':>8} {'games':>6} {'viol':>6} "
          f"{'rate':>8} {'max edge':>9} {'median':>9}  {last_column}")
    for cap in GAPS:
        sel = [x for x in recs if cap is None or x[4] <= cap]
        for lg in ("cfb", "nfl"):
            s = [x for x in sel if x[0] == lg]
            if not s:
                continue
            edges = sorted(x[3] for x in s)
            viol = [x for x in s if x[2] is not None]
            # The scanner's own verdict and the arithmetic must agree; if they
            # do not, one of the two is wrong and the run says so rather than
            # printing the prettier number.
            hand = sum(1 for x in s if 0.0 < x[3] <= scan.MAX_PLAUSIBLE_EDGE)
            flag = "" if hand == len(viol) else f"  !! scanner {len(viol)} vs hand {hand}"
            tag = "any" if cap is None else f"<={cap}m"
            print(f"  {tag:>6} {lg:>4} {len(s):>8,} {len({x[1] for x in s}):>6} "
                  f"{len(viol):>6,} {len(viol) / len(s):>7.3%} "
                  f"{edges[-1] * 100:>+8.2f}c {statistics.median(edges) * 100:>+8.2f}c"
                  f"  {sum(x[5] for x in s) / len(s):>7.2%}{flag}")


def main(argv) -> int:
    path = argv[1] if len(argv) > 1 else DEFAULT
    board = load(path)
    print(f"archive family scan  {path}")
    print(f"  {len(board)} games, "
          f"{sum(len(v) for f in board.values() for v in f.values()):,} rungs")
    gaps = [max(q[2] for f in fams.values() for q in f.values())
            - min(q[2] for f in fams.values() for q in f.values())
            for fams in board.values()]
    print(f"  within-game leg gap, minutes: median {statistics.median(gaps):.0f} "
          f"max {max(gaps)} -- THESE LEGS ARE NOT SIMULTANEOUS")

    report("(a) TOTALS ladder  P(Over N) non-increasing",
           two_leg(board, "total", True, "totals_ladder"), "ordered")
    report("CONTROL: SPREAD ladder  (must be able to fail, and does)",
           two_leg(board, "spread", False, "spread_ladder"), "ordered")
    up, low = three_leg(board)
    report("(d) FRECHET UPPER  team totals vs game total", up, "non-vacuous")
    report("(d) FRECHET LOWER  team totals vs game total", low, "non-vacuous")
    print("\n  'ordered' is the pair-weighted POOLED rate and carries no "
          "interval: pairs share legs.")
    print("  'non-vacuous' is the share of splits where the bound is not "
          "implied by 0 <= P <= 1 alone.")
    print("  NO SIZE IN THIS FILE: edges are per contract, never dollars.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
