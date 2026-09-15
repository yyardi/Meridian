"""Does a resting quote earn more where the spread is wider?

The question exists because `MAX_SPREAD = 0.15` excluded 32% of the CFB book
before anyone asked, so every adverse-selection number we have is conditioned
on spreads <= 15c.

THE IDENTITY THAT MAKES THIS DANGEROUS, derived from the module rather than
assumed. For a resting bid at half-spread `h` below the mid, with `d` the mid
move over the horizon:

    filled  iff  d <= -h          net_bid = (mid + d) - (mid - h) = d + h
    filled  iff  d >= +h          net_ask = (mid + h) - (mid + d) = h - d

so on either side **net = h - |d|, conditioned on |d| >= h**. Two consequences:

1. NET IS MECHANICALLY <= 0 IN EVERY BAND. "Making loses in every bucket" is an
   identity of this estimator, not a measurement. The fill rule and the P&L
   mark are the same variable.
2. `earned` is `h`, which is the band's own definition. A table of earned-by-
   band is the x-axis plotted against itself.

So the only quantity that can carry information is NET, and the only way to
know whether its gradient means anything is to compare it against what pure
geometry produces. Hence:

THE GEOMETRY-ONLY NULL. Take the pooled distribution of `d` over ALL windows,
independent of spread, and for each band's `h` compute
E[|d| - h | |d| >= h] under that one distribution. Every band then differs
only through `h`. If the observed per-band net matches the null, the gradient
is algebra; if it departs, the departure is the finding. Per
`forced-gradients-on-the-quote-substrate`, the burden of proof on this
substrate is a geometry-only null, not a significance test.

    python cfb/run_wide_spread.py --tsv windows.tsv --cap 0.15 --cap 0.50
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict

BANDS = [(0.01, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 0.15),
         (0.15, 0.25), (0.25, 0.50)]


def load(path: str):
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#") or line.startswith("game_id"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 6:
                continue
            rows.append((p[0], float(p[2]), float(p[3]), p[4] == "1", p[5] == "1"))
    return rows


def clustered_mean(by_cluster: dict[str, list[float]], conf: float = 0.95):
    """Mean of pooled values with a t interval on the CLUSTER means.

    ESTIMATOR, NAMED: equal-weight over clusters for the interval, pooled mean
    for the point estimate — the same pairing `core/quote/adverse_selection.py`
    uses, kept identical so the two are comparable. Per
    `estimator-not-named-in-the-label`, "game-clustered" names the INTERVAL and
    not the estimate, and the two can differ by more than the interval.
    """
    groups = [v for v in by_cluster.values() if v]
    g = len(groups)
    allv = [x for v in groups for x in v]
    if not allv:
        return None
    point = sum(allv) / len(allv)
    if g < 2:
        return point, None, None, g, len(allv)
    means = [sum(v) / len(v) for v in groups]
    m = sum(means) / g
    var = sum((x - m) ** 2 for x in means) / (g - 1)
    se = math.sqrt(var / g)
    t = 1.96 + 2.4 / g            # a small-G widening, monotone in G
    return point, m - t * se, m + t * se, g, len(allv)


def mean_excess(pooled_d: list[float], h: float) -> float | None:
    """e(h) = E[|d| - h | |d| >= h]. THE TAIL IS THE PARAMETER.

    The null's direction is not a property of this substrate, it is a property
    of the move distribution's tail, and e(h) is exactly the quantity that
    decides it:

        e(h) DECREASING in h  -> thin tail  -> net improves as the band widens
        e(h) INCREASING in h  -> heavy tail -> net collapses as it widens

    and net = h - |d| means net-by-band is just -e(h). So reporting e(h) beside
    the null is not a diagnostic next to a result: it IS the result's
    generating parameter, and a monotone net column means opposite things
    under the two regimes.
    """
    tail = [x for x in (abs(v) for v in pooled_d) if x >= h]
    if not tail:
        return None
    return sum(tail) / len(tail) - h


def geometry_null(pooled_d: list[float], h_values: list[float]) -> float | None:
    """E[|d| - h | |d| >= h] averaged over this band's own h values, using the
    POOLED move distribution — so the only thing that varies across bands is h.
    """
    absd = sorted(abs(x) for x in pooled_d)
    if not absd or not h_values:
        return None
    out = []
    for h in h_values:
        tail = [x for x in absd if x >= h]
        if tail:
            out.append(h - sum(tail) / len(tail))
    return sum(out) / len(out) if out else None


def report(rows, cap: float) -> str:
    keep = [r for r in rows if r[1] <= cap + 1e-9]
    pooled_d = [d for _, _, d, _, _ in keep]
    add = [f"CAP MERIDIAN_QUOTE_MAX_SPREAD = {cap:.2f}   "
           f"{len(keep):,} windows of {len(rows):,}"]
    add.append("")
    add.append(f"  {'band':>12s} {'windows':>8s} {'zero-d':>7s} {'fills':>7s} "
               f"{'G':>4s} {'earned':>8s} {'adverse':>8s} {'net/FILL':>9s} "
               f"{'net/GAME':>9s} {'t(game)':>8s} {'null':>8s} {'e(h)':>8s}")
    for lo, hi in BANDS:
        if lo >= cap:
            continue
        band = [r for r in keep if lo <= r[1] < min(hi, cap + 1e-9)]
        if not band:
            continue
        nets: dict[str, list[float]] = defaultdict(list)
        earned, adverse, hs = [], [], []
        for gid, spread, d, bf, af in band:
            h = spread / 2.0
            for filled in (bf, af):
                if filled:
                    nets[gid].append(h - abs(d))
                    earned.append(h)
                    adverse.append(abs(d))
                    hs.append(h)
        cm = clustered_mean(nets)
        nfill = sum(len(v) for v in nets.values())
        nzero = sum(1 for r in band if abs(r[2]) < 1e-12)
        if cm is None or nfill == 0:
            add.append(f"  {f'{lo:.2f}-{hi:.2f}':>12s} {len(band):>8,} "
                       f"{nzero:>7,} {0:>7,}  no fills")
            continue
        point, clo, chi, g, n = cm
        null = geometry_null(pooled_d, hs)
        h_bar = sum(hs) / len(hs)
        e_h = mean_excess(pooled_d, h_bar)
        # PER-GAME estimator, NAMED: equal-weight mean over game means, and a
        # t statistic on those means. The module is fills-weighted, which lets
        # heavily-traded games dominate -- 623 fills/game in the narrow band
        # against 151 in the widest, so the two estimators answer different
        # questions and the flatness of the fills-weighted column is an
        # artefact of that weighting.
        gmeans = [sum(v) / len(v) for v in nets.values() if v]
        per_game = sum(gmeans) / len(gmeans)
        if len(gmeans) > 1:
            gvar = sum((x - per_game) ** 2 for x in gmeans) / (len(gmeans) - 1)
            gse = math.sqrt(gvar / len(gmeans))
            tstat = per_game / gse if gse > 0 else float("nan")
        else:
            tstat = float("nan")
        add.append(
            f"  {f'{lo:.2f}-{hi:.2f}':>12s} {len(band):>8,} {nzero:>7,} "
            f"{nfill:>7,} {g:>4d} {sum(earned)/len(earned)*100:>+7.2f}c "
            f"{sum(adverse)/len(adverse)*100:>+7.2f}c {point*100:>+8.2f}c "
            f"{per_game*100:>+8.2f}c {tstat:>+8.2f} "
            f"{null*100 if null is not None else float('nan'):>+7.2f}c "
            f"{e_h*100 if e_h is not None else float('nan'):>+7.2f}c")
    add.append("")
    add.append("  earned is h, the band's own definition -- the x-axis against "
               "itself.")
    add.append("  NET = h - |mid move|, conditioned on |mid move| >= h, so it "
               "is <= 0 BY IDENTITY.")
    add.append("  net/FILL is fills-weighted (the module's estimator); "
               "net/GAME is equal-weight over")
    add.append("  game means with t on those means. They answer different "
               "questions and can disagree")
    add.append("  in SHAPE: fills-weighting lets heavily-traded games "
               "dominate.")
    add.append("  null is the same quantity from the POOLED move "
               "distribution, so it varies across")
    add.append("  bands only through h. NET at or below null = geometry, no "
               "finding.")
    add.append("  e(h) is the mean excess E[|d|-h | |d|>=h] -- THE TAIL, which "
               "is what sets the null's")
    add.append("  direction. e(h) falling with h = thin tail = net improves "
               "with width FOR FREE.")
    add.append("  e(h) rising = heavy tail = net collapses with width for "
               "free. Read the column pair.")
    add.append("  zero-d counts windows whose mid did not move at all -- "
               "frozen tails from dead")
    add.append("  streams never fill, so they bias the FILL RATE and not the "
               "net.")
    return "\n".join(add)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--cap", type=float, action="append", default=None)
    a = ap.parse_args()
    rows = load(a.tsv)
    print(f"{len(rows):,} windows loaded")
    print("POPULATION CAVEAT, carried from the module: `live_only` selects "
          "genuine live rows PLUS")
    print("frozen tails from dead streams (11,227 of 12,290 markets whose last "
          "row says live were")
    print("last written over 600s ago). Frozen tails have d=0, which drags "
          "every movement")
    print("statistic toward zero -- so adverse selection here is UNDERSTATED "
          "and net OVERSTATED.")
    for cap in (a.cap or [0.15, 0.50]):
        print()
        print(report(rows, cap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
