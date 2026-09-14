"""What the BEST cell looks like when there is no edge at all.

A 400-600 cell scan will produce a best cell whatever the truth is. Reading
that cell against zero asks the wrong question — the right one is whether it
beats what the same scan produces on data with the edge removed and everything
else intact. This builds that comparison.

METHOD. Take the scan's own pregame closes. Keep every price and every rule
EXACTLY as they are — selection reads prices only, never settlements, so the
chosen cells are identical in every replicate and are computed once. Permute
the SETTLEMENTS, destroying the pairing of price to outcome while preserving
the marginal win rate and the price distribution. Re-score. Repeat.

★ PERMUTE WHOLE GAMES, NOT ROWS. Outcomes are clustered by game: the two sides
of one game, and several rungs of one ladder, move together. Shuffling
settlements freely across rows destroys that dependence and yields a null that
is TOO NARROW — which makes everything look significant, the opposite of what
a null is for. Blocks are permuted within (league, market type, block size):
same size so a block can only land where it fits, which keeps the marginal win
rate exact rather than approximately right.

A stratum holding one game cannot be permuted — there is nowhere for its block
to go. Those rows are COUNTED and reported as `frozen`, because rows that never
move contribute no null variance and would quietly narrow the distribution.

★ AND THE CONTROL ON THE CONTROL. A null that flags nothing is as useless as
one that flags everything, and the output looks the same either way. So
`plant_edge()` injects a known edge into one price bucket and the harness
asserts the Monte Carlo SEES it. Neither number means anything without the
other: quantiles say what noise looks like, the planted edge says the
instrument can tell signal from it.

Seeded throughout. A threshold nobody can reproduce is not a threshold.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import json
import pathlib
import random
import statistics
import sys
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load(name: str):
    """cfb/ is not a package; the scan's arithmetic is loaded by path so this
    file cannot drift into a second definition of it."""
    spec = importlib.util.spec_from_file_location(name, REPO / "cfb" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pb = _load("run_paper_book")
bet_pnl, bet_stake, clustered = _pb.bet_pnl, _pb.bet_stake, _pb.clustered

from strategies.ladder import select  # noqa: E402


# --------------------------------------------------------------- permutation
def permute_settlements(rows, rng) -> tuple[list[int], int]:
    """Return permuted settlements, and how many rows could not be moved.

    Strata are (league, market type, rows-in-this-game). Whole game blocks are
    exchanged inside a stratum, so every outcome a game produced travels with
    the rest of that game's outcomes and the marginal win rate is unchanged.
    """
    out = [r["y"] for r in rows]
    blocks: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    for i, r in enumerate(rows):
        blocks[(r["league"], r["mtype"])][r["game_id"]].append(i)

    frozen = 0
    for games in blocks.values():
        by_size: dict[int, list] = defaultdict(list)
        for idxs in games.values():
            by_size[len(idxs)].append(idxs)
        for size, bs in by_size.items():
            if len(bs) < 2:                      # nowhere to send it
                frozen += size * len(bs)
                continue
            order = list(range(len(bs)))
            rng.shuffle(order)
            for dest, src in zip(bs, [bs[j] for j in order]):
                for k in range(size):
                    out[dest[k]] = rows[src[k]]["y"]
    return out, frozen


# ------------------------------------------------------------------- scoring
#: The scan's power floor (cfb/run_scan.py:69). Matched, not chosen: a cell the
#: scan never reports must not sit in the reference distribution.
G_FLOOR = 6


def score_cells(rows, ys, chosen=None, dropped: dict | None = None) -> dict:
    """Per-cell clustered mean, t and net per $1, with the SCAN'S OWN EXCLUSIONS.

    `chosen` is passed in because selection reads PRICES ONLY — identical in
    every replicate, and recomputing it would be both slow and a lie about what
    the permutation changes.

    ★ A CELL WHOSE BETS ALL SETTLE THE SAME WAY IS NOT A MEASUREMENT. With no
    outcome variation the sandwich has no risk to measure, so it measures the
    cell's PRICE DISPERSION instead: the interval collapses while the mean stays
    large. Reproduced here on 40 bets all settling YES, prices over 40 ticks:

        all-same outcome      mean +49.714c  half 1.4513   t = 67.14
        same prices, varying  mean +14.714c  half 14.8349  t =  1.94

    35x on |t| from identical prices. On the real scan 16 of 324 cells were
    degenerate and were ALL TWELVE of the top twelve by |t|; removing them took
    max|t| 30.01 -> 5.87 and Var(t) 17.282 -> 1.308.

    ★ THE GUARD RUNS INSIDE EVERY REPLICATE, not once on the observed data.
    Permuting settlements can CREATE a degenerate cell that was not degenerate
    on the real tape and DESTROY one that was, so a null filtered on the
    observed degeneracy set would reproduce the artifact in the reference and
    then agree with the observed value for the wrong reason. Effective m
    therefore varies by replicate, and that is reported rather than asserted
    away.

    ★ AND THE G FLOOR AND se CHECK ARE THE SCAN'S, verbatim from
    cfb/run_scan.py:146. A reference distribution filtered differently from the
    instrument it calibrates is a reference for a different statistic.
    """
    if chosen is None:
        chosen = select(rows)
    idx = {r["market_slug"]: i for i, r in enumerate(rows)}
    thin = degenerate = floored = 0
    out = {}
    for name, bets in chosen.items():
        vals, keys, pnl, staked, outcomes = [], [], 0.0, 0.0, set()
        for b in bets:
            i = idx[b.market_slug]
            r, y = rows[i], ys[i]
            outcomes.add(y)
            pv = bet_pnl(b.side, y, r["bid"], r["ask"])
            vals.append(100 * pv)
            keys.append(r["game_id"])
            pnl += pv
            staked += bet_stake(b.side, r["bid"], r["ask"])
        if len(vals) < 2 or staked <= 0:
            thin += 1
            continue
        if len(outcomes) < 2:
            degenerate += 1
            continue
        m, h, n, G, ge = clustered(vals, keys)
        se = h / 1.96 if h not in (0.0, float("inf")) else float("inf")
        if G < G_FLOOR or se in (0.0, float("inf")) or not math.isfinite(se):
            floored += 1
            continue
        out[name] = {
            "mean_c": m, "half": h, "n": n, "games": G, "g_eff": ge,
            "t": m / se,
            "net_per_1": pnl / staked,
            "excludes_zero": abs(m) > h,
        }
    if dropped is not None:
        dropped.update(thin=thin, degenerate=degenerate, floored=floored)
    return out


def _p_two_sided(t: float, df: int | None = None) -> float:
    """Two-sided p on t(df), MATCHING the scan (`tdist.sf(|t|, df=G-1)`).

    ★ NOT normal, and the difference is large where it matters most. At G=6 the
    scan's df is 5, and t(5).sf(3) = 0.01505 against the normal 0.00135 — an
    11x gap in the p-value at a t the scan sees routinely. HC reads the
    SMALLEST p-values, so computing them on the normal would hand it p's an
    order of magnitude too small at the low-G end and inflate it against a
    scan that never saw those numbers.

    df=None falls back to the normal, for the independent-cell calibration
    where there is no G.
    """
    if df is None or df < 1:
        return max(1e-15, math.erfc(abs(t) / math.sqrt(2.0)))
    from scipy.stats import t as tdist
    return max(1e-15, float(2.0 * tdist.sf(abs(t), df=df)))


def higher_criticism(ts, alpha0: float = 0.25, dfs=None) -> float:
    """Donoho-Jin HC, stabilised by CLAMPING THE DENOMINATOR at 1/m.

        HC* = max_i  sqrt(m) (i/m - p_(i)) / sqrt(p~(1 - p~)),  p~ = max(p_(i), 1/m)

    Sensitive to MANY SMALL EFFECTS AT ONCE, which max|t| is blind to by
    construction: ten cells at a true t of 3 lift the pool while not one of
    them clears the threshold multiplicity demands of a single cell.

    ★ TWO WAYS TO GET THE STABILISATION WRONG, AND I SHIPPED BOTH BEFORE THIS.
    Unclamped, one tiny p-value drives the denominator to zero: p99 2,864 and
    max 10,626 on synthetic NULL data, a division by almost nothing wearing
    the clothes of a heavy tail. Then HC+ — SKIPPING every i with
    p_(i) < 1/m — made it identically 0.00 across 400 null replicates and the
    observed value alike, which is not a conservative statistic, it is a dead
    one, and it reports exactly as much as the exploding version did.

    Clamping only the denominator keeps the numerator's signal — HC still
    grows with the COUNT of small p-values, which is the whole point — while
    bounding the ratio at roughly i. Below 1/m a p-value is an extrapolation
    of the normal tail rather than anything this sample resolved, so it is
    not allowed to set the scale.
    """
    m = len(ts)
    if m == 0:
        return 0.0
    if dfs is None:
        dfs = [None] * m
    ps = sorted(_p_two_sided(t, d) for t, d in zip(ts, dfs))
    floor = 1.0 / m
    best = 0.0
    # max(2, ...): int() truncation leaves a SINGLE term below m=8,
    # which is how a working statistic looked dead.
    for i, pi in enumerate(ps[:max(2, int(alpha0 * m))], start=1):
        pt = max(pi, floor)
        denom = math.sqrt(pt * (1.0 - pt))
        if denom > 0.0:
            best = max(best, math.sqrt(m) * (i / m - pi) / denom)
    return best


def var_t(ts) -> float:
    """Variance of the cell t-statistics. One under a pure independent null;
    inflated by many modest true effects. The pool sees what the parts cannot."""
    m = len(ts)
    if m < 2:
        return 0.0
    mu = sum(ts) / m
    return sum((t - mu) ** 2 for t in ts) / (m - 1)


def summarise(cells: dict) -> dict:
    """Every statistic the scan will produce, so each has its own null.

    max|t| answers "is the best cell real". It is the WEAKEST of the three
    against a diffuse alternative, and reporting it alone would hide exactly
    the case the scan exists to find.
    """
    if not cells:
        return {"max_abs_t": 0.0, "n_excluding_zero": 0, "best_net_per_1": 0.0,
                "var_t": 0.0, "hc": 0.0}
    ts = [c["t"] for c in cells.values()]
    dfs = [max(1, c["games"] - 1) for c in cells.values()]
    return {
        "max_abs_t": max(abs(t) for t in ts),
        "n_excluding_zero": sum(1 for c in cells.values() if c["excludes_zero"]),
        "best_net_per_1": max(c["net_per_1"] for c in cells.values()),
        "var_t": var_t(ts),
        "hc": higher_criticism(ts, dfs=dfs),
    }


# ---------------------------------------------------------------- the null
def null_distribution(rows, *, reps: int = 1000, seed: int = 20260914) -> dict:
    """Permutation null. Seeded: the same rows and seed give the same numbers.

    ★ REPORTS THE CELLS ACTUALLY SCORED, NOT THE CELLS SELECTED. `score_cells`
    drops any cell with fewer than two bets, so `len(select(rows))` overstates
    m whenever a league is thin. I reported 29 while computing on 7 and
    concluded from it that Higher Criticism was dead — at m=7,
    `int(0.25 * m) == 1`, so HC examined a SINGLE term and of course barely
    moved. The statistic was fine; the m was a fiction. Effective m is now
    measured per replicate and asserted constant, because it is the parameter
    every one of these statistics is read against.
    """
    chosen = select(rows)
    rng = random.Random(seed)
    draws = {k: [] for k in ("max_abs_t", "n_excluding_zero",
                             "best_net_per_1", "var_t", "hc", "min_p")}
    # Fixed across replicates -- see cell_price_table. One setup, not reps setups.
    btable = cell_price_table(rows, chosen, cluster=True)
    per_cell: dict[str, list[float]] = defaultdict(list)
    frozen_rows = 0
    eff_m: list[int] = []
    degen: list[int] = []
    mixed: list[int] = []
    for _ in range(reps):
        ys, frozen = permute_settlements(rows, rng)
        frozen_rows = frozen
        drop: dict = {}
        cells = score_cells(rows, ys, chosen, dropped=drop)
        eff_m.append(len(cells))
        degen.append(drop.get("degenerate", 0))
        for name, c in cells.items():
            per_cell[name].append(abs(c["t"]))
        s = summarise(cells)
        bc = binomial_cells(rows, ys, chosen, cluster=True, rng=rng, table=btable)
        s["min_p"] = min_p(bc)
        mixed.append(sum(c["mixed_games"] for c in bc.values()))
        for k in draws:
            draws[k].append(s[k])
    return {
        "reps": reps, "seed": seed,
        "cells_selected": len(chosen),
        # m VARIES BY REPLICATE once degeneracy is judged inside the replicate,
        # because a permutation can create it and destroy it. Reported, not
        # asserted away — and the degenerate count per replicate is itself a
        # measure of how thin the tape is.
        "cells_scored": (statistics.median(eff_m) if eff_m else 0),
        "cells_scored_min": (min(eff_m) if eff_m else 0),
        "cells_scored_max": (max(eff_m) if eff_m else 0),
        "cells_scored_varied": len(set(eff_m)) > 1,
        "degenerate_per_rep": (_q(degen) if degen else None),
        "reps_with_degenerate": sum(1 for d in degen if d > 0),
        "rows": len(rows), "frozen_rows": frozen_rows,
        # The binomial branch's own diagnostic: how much within-game agreement
        # the permutation destroyed. Observed is near zero by construction.
        "binomial_cells": len(btable),
        "mixed_games_per_rep": (_q(mixed) if mixed else None),
        "per_cell_abs_t": {k: sorted(v) for k, v in per_cell.items()},
        "quantiles": {k: _q(v) for k, v in draws.items()},
        "draws": draws,
    }


def empirical_hc(cells: dict, null: dict, alpha0: float = 0.25) -> float:
    """HC on EMPIRICAL p-values — each cell's |t| ranked against its OWN
    permutation draws.

    The principled form inside a permutation framework, and it removes the
    whole family of failures at once: p >= 1/(reps+1) by construction, so
    there is nothing to explode, nothing to skip below a floor, and no
    denominator to clamp — which is what gave the clamped version a ceiling at
    alpha0*m that the permutation could sit on. Calibrated by the same
    machinery that produces the null, rather than by normal theory that the
    cluster-robust t does not obey at finite G.
    """
    import bisect

    reps = null["reps"]
    ps = []
    for name, c in cells.items():
        draws = null["per_cell_abs_t"].get(name)
        if not draws:
            continue
        at_least = len(draws) - bisect.bisect_left(draws, abs(c["t"]))
        ps.append((1 + at_least) / (reps + 1))
    m = len(ps)
    if m == 0:
        return 0.0
    ps.sort()
    best = 0.0
    for i, pi in enumerate(ps[:max(2, int(alpha0 * m))], start=1):
        denom = math.sqrt(max(1e-12, pi * (1.0 - pi)))
        best = max(best, math.sqrt(m) * (i / m - pi) / denom)
    return best


def _q(xs) -> dict:
    s = sorted(xs)
    def at(p):
        return s[min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))]
    return {"p50": at(0.50), "p90": at(0.90), "p95": at(0.95),
            "p99": at(0.99), "max": s[-1]}


# ------------------------------------------------- the control on the control
def plant_edge(rows, *, lo: float, hi: float, cents: float, seed: int = 7):
    """Return settlements carrying a known edge in one price bucket.

    Without this the harness cannot tell a null that flags nothing from one
    that works — both print quantiles and look equally healthy. `cents` is the
    YES-side edge in cents per contract: outcomes in the bucket are re-drawn so
    the realised YES win rate exceeds the ask by cents/100.
    """
    rng = random.Random(seed)
    ys = [r["y"] for r in rows]
    for i, r in enumerate(rows):
        mid = (r["bid"] + r["ask"]) / 2
        if lo <= mid < hi:
            # CAPPED AWAY FROM THE BOUNDARY. An uncapped edge drives the
            # bucket's win rate to 1, the cell loses all outcome variation, the
            # degeneracy guard correctly removes it — and the control then
            # reports "not detected" because the cell carrying the signal
            # stopped existing. Measured: a 40c plant on a 1-row-per-game
            # fixture made the target cell degenerate and max|t| fell to 0.38.
            ys[i] = 1 if rng.random() < min(0.97, r["ask"] + cents / 100.0) else 0
    return ys


def recovery_rate(rows, null, *, lo: float, hi: float, cents: float,
                  trials: int = 60, stat: str = "max_abs_t",
                  seed: int = 4242) -> float:
    """Fraction of planted replicates whose statistic clears the null's p95.

    ONE planted trial is a coin flip, not a control. Recovery is a RATE, and
    the rate is what the two-sided band is stated against.
    """
    thr = null["quantiles"][stat]["p95"]
    hits = lost = 0
    for k in range(trials):
        ys = plant_edge(rows, lo=lo, hi=hi, cents=cents, seed=seed + k)
        drop: dict = {}
        cells = score_cells(rows, ys, dropped=drop)
        # A planted trial whose target cell went DEGENERATE is not a miss — the
        # cell stopped existing. Counted separately so a control cannot report
        # "undetectable" for a reason that is really "removed by the guard".
        if drop.get("degenerate", 0) > null_degenerate_floor(null):
            lost += 1
            continue
        if summarise(cells)[stat] > thr:
            hits += 1
    usable = trials - lost
    if usable == 0:
        return float("nan")
    return hits / usable


def null_degenerate_floor(null) -> int:
    """How many degenerate cells the NULL itself produces, at its median. A
    planted trial only counts as 'cell removed' if it exceeds what permutation
    alone does."""
    d = null.get("degenerate_per_rep")
    return int(d["p50"]) if d else 0


def min_detectable_edge(rows, null, *, lo: float, hi: float,
                        candidates=(2, 5, 10, 15, 20, 30, 50, 75),
                        trials: int = 40, stat: str = "max_abs_t"):
    """Smallest planted edge RECOVERED AT LEAST HALF THE TIME.

    Defined on the rate, not on a single trial: an edge that clears once in
    twenty is not detectable, and a single-trial definition would call it so
    one time in twenty. Returns None when no candidate reaches 50%, which is a
    verdict on the sample rather than a missing value.
    """
    for cents in candidates:
        if recovery_rate(rows, null, lo=lo, hi=hi, cents=cents,
                         trials=trials, stat=stat) >= 0.50:
            return cents
    return None


#: The two-sided pass bands. A control that ALWAYS recovers is as useless as
#: one that never does, and only the upper bound catches a leak — an edge
#: planted at the detection floor must be missed about half the time, because
#: that is what being at the floor means.
BAND_AT_MDE = (0.35, 0.65)
BAND_AT_2MDE = (0.85, 1.00)


def control_verdict(at_mde: float, at_2mde: float) -> tuple[bool, str]:
    """Both bands, both directions."""
    lo1, hi1 = BAND_AT_MDE
    lo2, hi2 = BAND_AT_2MDE
    if at_mde > hi1:
        return False, (f"LEAKING: {at_mde:.0%} recovery at the detection floor, "
                       f"band {lo1:.0%}-{hi1:.0%}. An edge planted AT the floor "
                       "must be missed about half the time; recovering it "
                       "almost always means the harness sees the planting "
                       "rather than the edge.")
    if at_mde < lo1:
        return False, (f"UNDERPOWERED: {at_mde:.0%} at the floor, band "
                       f"{lo1:.0%}-{hi1:.0%} — the floor is misplaced.")
    if at_2mde < lo2:
        return False, (f"BLUNT: {at_2mde:.0%} at twice the floor, band "
                       f"{lo2:.0%}-{hi2:.0%} — doubling the edge should be "
                       "nearly always visible.")
    return True, (f"PASS: {at_mde:.0%} at the floor (band {lo1:.0%}-{hi1:.0%}), "
                  f"{at_2mde:.0%} at twice it (band {lo2:.0%}-{hi2:.0%}).")


def calibration_independent(m: int, *, trials: int = 2000, seed: int = 99) -> dict:
    """Textbook numbers for m INDEPENDENT cells, in BOTH conventions.

    ★ THE REGISTERED PAIR MIXES THEM, and the two cannot describe one
    statistic. Derived exactly at m=500:

        median max|t|, two-sided          3.198
        median max t,  one-sided          2.992
        asymptotic MEAN of max t          2.907   <- the registered 2.9
        P(max|t| > 3), two-sided          0.741   <- the registered 0.74
        P(max t  > 3), one-sided          0.491

    So 2.9 is the one-sided MEAN and 0.74 is the two-sided exceedance. Each is
    right on its own terms. This harness is two-sided throughout — `max|t|`
    and `excludes_zero` both are — so the consistent pair to read against is
    3.198 and 0.741, and a comparison of the permutation p50 against 2.9 would
    understate the clustering gap by the convention difference rather than
    measure it.

    Both are returned so the comparison cannot be made against the wrong one
    by accident.
    """
    rng = random.Random(seed)
    best_two, best_one, over3_two, over3_one = [], [], 0, 0
    for _ in range(trials):
        ts = [rng.gauss(0.0, 1.0) for _ in range(m)]
        b2, b1 = max(abs(t) for t in ts), max(ts)
        best_two.append(b2)
        best_one.append(b1)
        over3_two += (b2 > 3.0)
        over3_one += (b1 > 3.0)
    best_two.sort()
    best_one.sort()
    return {
        "m": m, "trials": trials,
        "median_best_abs_t": best_two[len(best_two) // 2],
        "median_best_signed_t": best_one[len(best_one) // 2],
        "p_any_abs_exceeds_3": over3_two / trials,
        "p_any_signed_exceeds_3": over3_one / trials,
    }



def report(rows, *, reps: int, seed: int, lo: float, hi: float,
           trials: int = 60) -> str:
    """Every statistic's null AND the two-sided control, together.

    One function on purpose. Quantiles alone describe a null that may be
    incapable of seeing anything; a control alone says an instrument works
    without saying what to compare against. A caller cannot take one and leave
    the other.
    """
    null = null_distribution(rows, reps=reps, seed=seed)
    q = null["quantiles"]
    observed = summarise(score_cells(rows, [r["y"] for r in rows]))
    ind = calibration_independent(max(2, null["cells_scored"]))

    L = [
        f"rows {null['rows']:,}  reps {reps}  seed {seed}",
        f"cells: {null['cells_scored']} SCORED of {null['cells_selected']} "
        f"selected — m is the scored count, and every statistic below is read "
        f"against it",
        f"frozen rows (unpermutable, no null variance): {null['frozen_rows']:,}",
        "",
        "NULL — the scan with the edge removed and everything else intact",
        f"{'statistic':<18}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}"
        f"{'observed':>11}   verdict",
    ]
    for key, label, fmt in (("max_abs_t", "max |t|", "{:.2f}"),
                            ("var_t", "Var(t)", "{:.3f}"),
                            ("hc", "Higher Criticism", "{:.2f}"),
                            ("n_excluding_zero", "cells excl. 0", "{:.0f}"),
                            ("best_net_per_1", "best net/$1", "{:+.4f}")):
        d, o = q[key], observed[key]
        L.append(
            f"{label:<18}" + "".join(fmt.format(d[p]).rjust(9)
                                     for p in ("p50", "p95", "p99", "max"))
            + fmt.format(o).rjust(11)
            + ("   CLEARS p95" if o > d["p95"] else "   inside the null"))
    L += [
        "",
        "max|t| is the WEAKEST of the three against many modest effects: ten",
        "cells at a true t of 3 lift Var(t) and HC while no single one clears",
        "the threshold multiplicity demands. Read all three or none.",
        "",
        f"INDEPENDENT-CELL CALIBRATION (m={ind['m']}, textbook, no clustering)",
        f"  two-sided: median max|t| {ind['median_best_abs_t']:.2f}   "
        f"P(any > 3) {ind['p_any_abs_exceeds_3']:.2f}",
        f"  one-sided: median max t  {ind['median_best_signed_t']:.2f}   "
        f"P(any > 3) {ind['p_any_signed_exceeds_3']:.2f}",
        "  (the registered 2.9 is the ONE-SIDED mean and 0.74 the TWO-SIDED",
        "   exceedance; this harness is two-sided, so read against the first)",
        f"  permutation p50 {q['max_abs_t']['p50']:.2f} — the gap is REAL and",
        "  its cause is NOT isolated here. Two things move together: cells",
        "  share games (correlated t's, fewer effective tries) AND the",
        "  cluster-robust t is not standard normal at finite G, where it has",
        "  heavier tails. On synthetic data the permutation p50 came out",
        "  ABOVE the independent median, which is the tail effect winning,",
        "  not the correlation. Do not read this gap as either one alone.",
        "",
        f"CONTROL ON THE CONTROL — planted in [{lo:.2f}, {hi:.2f}), "
        f"{trials} trials per point",
    ]
    floor = min_detectable_edge(rows, null, lo=lo, hi=hi, trials=trials)
    if floor is None:
        L += ["  ★ NOTHING was recovered at 50% up to the largest candidate.",
              "    These quantiles describe an instrument not shown to see",
              "    anything. NO cell from this scan should be read."]
        return "\n".join(L)
    at1 = recovery_rate(rows, null, lo=lo, hi=hi, cents=floor, trials=trials)
    at2 = recovery_rate(rows, null, lo=lo, hi=hi, cents=2 * floor, trials=trials)
    ok, why = control_verdict(at1, at2)
    L += [f"  detection floor {floor}c per contract",
          f"  recovery at {floor}c: {at1:.0%}    at {2 * floor}c: {at2:.0%}",
          f"  {why}",
          f"  => a claim below {floor}c is not supported by this sample: not",
          "     false, just under what the instrument could have seen."]
    if not ok:
        L.append("  ★ THE CONTROL FAILED ITS BAND. The quantiles above are not "
                 "usable until it passes.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--bucket", default="0.60,0.80")
    ap.add_argument("--rows-json", help="pre-extracted rows, to avoid a DB hit")
    a = ap.parse_args(argv)
    lo, hi = (float(x) for x in a.bucket.split(","))
    if not a.rows_json:                              # pragma: no cover
        raise SystemExit(
            "no --rows-json given. This reads the same closes the scan reads; "
            "extract them alongside a scan run rather than paying for a second "
            "full pass over the tape.")
    rows = json.loads(pathlib.Path(a.rows_json).read_text())
    print(report(rows, reps=a.reps, seed=a.seed, lo=lo, hi=hi, trials=a.trials))
    return 0


if __name__ == "__main__":                            # pragma: no cover
    raise SystemExit(main())


# ------------------------------------------------------- the binomial branch
def poisson_binomial_pmf(ps) -> list[float]:
    """Exact pmf of a sum of independent Bernoullis with DIFFERENT p.

    A decile cell spans a 0.1 PRICE BAND, so every bet in it has its own
    break-even and the null is Poisson-binomial rather than binomial.
    Collapsing to one p mis-states the tail in whichever direction the
    within-cell price distribution leans — the same class of approximation as
    the sandwich it replaces, milder but not free. Exact by convolution; n here
    is at most a few hundred, so there is no reason to approximate.
    """
    pmf = [1.0]
    for p in ps:
        nxt = [0.0] * (len(pmf) + 1)
        for k, w in enumerate(pmf):
            nxt[k] += w * (1.0 - p)
            nxt[k + 1] += w * p
        pmf = nxt
    return pmf


def poisson_binomial_p(k: int, ps) -> float:
    """Two-sided p for observing k wins, by the method of small probabilities:
    sum every outcome no more likely than the one observed."""
    pmf = poisson_binomial_pmf(ps)
    if not (0 <= k < len(pmf)):
        return 1.0
    obs = pmf[k]
    return min(1.0, sum(w for w in pmf if w <= obs * (1 + 1e-12)))


def break_even(ask: float, fee_rate: float = 0.06) -> float:
    """Win probability a YES-at-ask bet needs to break even: you pay the ask
    plus the fee, so EV = p - ask - fee = 0."""
    return ask + fee_rate * ask * (1.0 - ask)


def cell_price_table(rows, chosen, *, cluster: bool = True) -> dict:
    """Precompute, ONCE, everything about a cell that a permutation cannot change.

    ★ THE PERMUTATION SHUFFLES `y`, NOT PRICES. So each cell's break-even vector
    is fixed across every replicate, and therefore so is its Poisson-binomial
    pmf — only the win count `k` moves. Caching the pmf per cell turns the null
    from O(reps * cells * G^2) into one O(cells * G^2) setup plus an O(rows)
    lookup per replicate, which is the difference between minutes and hours.

    Returns per cell: the game grouping, the price vector, and `pval[k]` — the
    two-sided exact p for every achievable k, so a replicate is a table read.
    """
    idx = {r["market_slug"]: i for i, r in enumerate(rows)}
    table = {}
    for name, bets in chosen.items():
        by_game: dict[str, list[int]] = defaultdict(list)
        prices: dict[str, list[float]] = defaultdict(list)
        for b in bets:
            i = idx[b.market_slug]
            g = rows[i]["game_id"]
            by_game[g].append(i)
            prices[g].append(break_even(rows[i]["ask"]))
        n = sum(len(v) for v in by_game.values())
        if n < 2:
            continue
        gids = list(by_game)
        if cluster:
            ps = [sum(prices[g]) / len(prices[g]) for g in gids]
        else:
            ps = [q for g in gids for q in prices[g]]
        pmf = poisson_binomial_pmf(ps)
        pval = [min(1.0, sum(w for w in pmf if w <= pmf[k] * (1 + 1e-12)))
                for k in range(len(pmf))]
        table[name] = {
            "gids": gids,
            "members": [by_game[g] for g in gids],
            "bets": n, "games": len(gids),
            "n_over_g": n / len(gids),
            "mean_break_even": sum(ps) / len(ps),
            "unit_n": len(ps),
            "pval": pval,
        }
    return table


def binomial_cells(rows, ys, chosen, *, cluster: bool = True, rng=None,
                   table: dict | None = None) -> dict:
    """Per-cell exact test on the WIN COUNT, which the sandwich cannot express.

    Quant B's measurement of the overstatement, same cells, sandwich against
    binomial: p 3.9e-12 vs 6.3e-02, 7.9e-33 vs 6.1e-02, 1.2e-25 vs 4.7e-02.
    Five to thirty orders of magnitude, and Var(t) was built out of that gap.

    ★ BUT A BINOMIAL ASSUMES INDEPENDENT BETS, AND BETS IN ONE GAME ARE NOT.
    That is precisely why the sandwich clusters. Replacing one with the other
    trades a homogeneity failure for a clustering failure: with n bets over G
    games the independent test overstates evidence by roughly sqrt(n/G), which
    at n=68 over G=15 is a factor of ~2.1 in z. So `cluster=True` reduces each
    game to ONE observation and the n/G ratio is reported either way.

    ★ MIXED GAMES ARE KEPT BY MAJORITY, NOT DROPPED, AND THE REASON IS THE NULL.
    Dropping a game whose bets disagree looks cleaner, but a permutation BREAKS
    within-game agreement by construction: the observed tape has few mixed games
    (that agreement is what produced the degenerate cells), the permuted tape has
    many. Dropping them would shrink G in the null and not in the observed, so
    the null would be built from smaller-G cells that cannot reach as far into
    the tail — anti-conservative, in the direction of my own hypothesis. Majority
    vote holds G fixed at a property of the price/game structure, which is what
    makes observed and null comparable at all. Exact ties carry no direction, so
    they are broken by the same rng that drew the permutation (a fixed `>= 0.5`
    would count every tie as a win and lift the null's k on both tails).
    """
    if table is None:
        table = cell_price_table(rows, chosen, cluster=cluster)
    out = {}
    for name, t in table.items():
        k, mixed = 0, 0
        if cluster:
            for members in t["members"]:
                vals = [float(ys[i]) for i in members]
                s = sum(vals)
                if len(set(vals)) > 1:
                    mixed += 1
                half = len(vals) / 2.0
                if s > half:
                    won = True
                elif s < half:
                    won = False
                else:
                    won = (rng.random() < 0.5) if rng is not None else True
                k += int(won)
        else:
            k = int(sum(float(ys[i]) for m in t["members"] for i in m))
        out[name] = {
            "k": k, "unit_n": t["unit_n"], "bets": t["bets"],
            "games": t["games"], "n_over_g": t["n_over_g"],
            "mixed_games": mixed,
            "mean_break_even": t["mean_break_even"],
            "p": t["pval"][k] if 0 <= k < len(t["pval"]) else 1.0,
        }
    return out


def min_p(bcells: dict) -> float:
    """The across-cell statistic. A per-cell binomial is exact and needs no
    permutation — and the permutation would ABSORB it, since shuffling existing
    settlements holds the marginal win count fixed, which is the quantity that
    hypothesis is about. What needs a reference is the MINIMUM over correlated
    cells, and that is what the permutation supplies, conditional on the
    observed marginal."""
    return min((c["p"] for c in bcells.values()), default=1.0)
