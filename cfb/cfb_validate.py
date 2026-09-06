"""cfb_validate.py -- SECONDARY validation. Proves the model is not broken.
It does NOT prove edge; edge.py does that. A perfectly calibrated model that
never disagrees with the market has zero edge -- calibration and edge are
different questions and only edge decides go-live.

STRATIFY, NEVER POOL. Late-game plays are easy and inflate aggregate Brier.
Cross-division games are ~1/3 of our volume and ARE the blowout tail, where
public models document weak calibration -- pooled numbers hide exactly that.
"""
from __future__ import annotations
import statistics as st

SPREAD_BUCKETS = [(0, 7), (7, 14), (14, 24), (24, 999)]


def calibration(rows, buckets=10):
    """rows: (pred, outcome) -> [(lo, n, mean_pred, realised, gap)]"""
    out = []
    for b in range(buckets):
        lo, hi = b / buckets, (b + 1) / buckets
        sel = [r for r in rows if (lo <= r[0] < hi) or (b == buckets - 1 and r[0] == 1.0)]
        if sel:
            mp = st.mean(x[0] for x in sel); rz = st.mean(x[1] for x in sel)
            out.append((round(lo, 2), len(sel), round(mp, 4), round(rz, 4), round(rz - mp, 4)))
    return out


def brier(rows):
    return st.mean((p - o) ** 2 for p, o in rows) if rows else None


def weighted_calibration_error(rows, buckets=10):
    cal = calibration(rows, buckets); n = sum(c[1] for c in cal)
    return sum(c[1] * abs(c[4]) for c in cal) / n if n else None


def stratified(rows, key_fn, label):
    """rows: (pred, outcome, phase, abs_spread, division). Reports each stratum
    separately WITH its n -- a stratum too small to speak must say so."""
    groups = {}
    for r in rows:
        groups.setdefault(key_fn(r), []).append((r[0], r[1]))
    lines = [f"--- {label} ---"]
    for k in sorted(groups, key=str):
        g = groups[k]
        wce = weighted_calibration_error(g)
        lines.append(f"  {str(k):18s} n={len(g):6d}  Brier={brier(g):.4f}"
                     f"  wCalErr={wce:.4f}" + ("   [THIN -- not a verdict]" if len(g) < 200 else ""))
    return "\n".join(lines)


def spread_bucket(abs_spread):
    if abs_spread is None: return "unknown"
    for lo, hi in SPREAD_BUCKETS:
        if lo <= abs_spread < hi: return f"|spread| {lo}-{hi}"
    return "unknown"


def full_report(rows, bench_close=None, bench_espn=None):
    """rows: (pred, outcome, phase, abs_spread, division)"""
    flat = [(r[0], r[1]) for r in rows]
    out = [f"POOLED (do not quote alone): n={len(flat)} Brier={brier(flat):.4f} "
           f"wCalErr={weighted_calibration_error(flat):.4f}",
           stratified(rows, lambda r: r[2], "BY PHASE"),
           stratified(rows, lambda r: spread_bucket(r[3]), "BY |SPREAD| (the blowout tail)"),
           stratified(rows, lambda r: r[4], "BY DIVISION (FBS / CROSS / FCS)")]
    if bench_close: out.append(f"  benchmark closing-line-implied Brier={brier(bench_close):.4f}  [is it broken?]")
    if bench_espn:  out.append(f"  benchmark ESPN per-play WP    Brier={brier(bench_espn):.4f}  [beats a public model?]")
    out.append("  NOTE: neither benchmark is the go-live bar. See edge.py.")
    return "\n".join(out)


def _selftest():
    import random
    rng = random.Random(5)
    rows = []
    for _ in range(4000):
        p = rng.random(); o = 1 if rng.random() < p else 0
        rows.append((p, o, rng.choice(["regulation", "clutch", "overtime"]),
                     rng.choice([3.5, 10.0, 20.0, 40.0]), rng.choice(["FBS", "CROSS"])))
    flat = [(r[0], r[1]) for r in rows]
    assert weighted_calibration_error(flat) < 0.05, "a well-calibrated generator should look calibrated"
    bad = [(0.9, 0) for _ in range(500)] + [(0.9, 1) for _ in range(100)]
    assert weighted_calibration_error(bad) > 0.5, "miscalibration must be detected"
    txt = full_report(rows)
    assert "BY |SPREAD|" in txt and "BY DIVISION" in txt and "do not quote alone" in txt
    thin = [(0.5, 1, "overtime", 3.5, "FCS")] * 50
    assert "THIN" in stratified(thin, lambda r: r[4], "x"), "thin strata must refuse to be a verdict"
    print("selftest OK -- calibration detected, miscalibration detected, strata present, thin strata flagged")


if __name__ == "__main__":
    _selftest()
