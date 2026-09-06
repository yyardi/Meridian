"""The venue-tape pre-flight, executable rather than prose.

Registered in `analysis/slate_0912_preregistration.md`. Written before the run
so the three conditions are code, not a description someone re-implements on
the night. A prose condition gets paraphrased; this one does not.

    .venv/bin/python analysis/tape_preflight.py <captured_at.csv> \
        [--start 16:00] [--end 24:00] [--label "CFB 09-12"]

Input: any CSV with a `captured_at` column of venue snapshot timestamps for the
markets under test. The conditions are computed on DISTINCT stamps, because the
question is whether the tape ticked, not how many rows each tick carried.

## THE THREE CONDITIONS — all must hold

    1. CADENCE     median inter-stamp gap  <  10 s
    2. CONTINUITY  maximum inter-stamp gap <= 60 s
    3. COVERAGE    minutes holding >=1 stamp >= 95% of window minutes

**Why three.** The first version of this was cadence alone, and it PASSED
2026-09-05 — the day CFB venue recording died mid-slate with ~110 minutes of no
tape. An outage of any length contributes exactly ONE gap; among 6,099 slate
gaps only three exceeded 60 s, and a median is the 3,050th value. **A median
measures the spacing of stamps that exist and is blind to stamps that are
absent**, which is the thing being tested. No threshold on it fixes that.

Continuity catches one long hole. Coverage catches many short ones. They fail
on different shapes, so both are kept.

## Known-good and known-bad, for calibration

    09-05 slate (died 22:08Z)   median 3.16 s   max 2,487 s   coverage 77.5%
    09-06 (dead all day)        median 2,076 s
    healthy peak                median ~3.7 s   (967 stamps in one hour)

**The separation on continuity is ~600x, so this is not a delicate test.**
Figures above are Debugger's; I could not reproduce them locally — my only
substrate with `captured_at` is the book/trade join at 810 stamps against their
13,175 — and they are recorded as theirs.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

CADENCE_MAX_S = 10.0      # median gap must be under this
CONTINUITY_MAX_S = 60.0   # no single gap may exceed this
COVERAGE_MIN = 0.95       # fraction of window minutes holding a stamp


def evaluate(stamps: pd.Series, window_start=None, window_end=None) -> dict:
    s = pd.Series(sorted(pd.to_datetime(stamps, utc=True).dropna().unique()))
    if window_start is not None:
        s = s[s >= window_start]
    if window_end is not None:
        s = s[s < window_end]
    if len(s) < 3:
        return {"ok": False, "reason": f"only {len(s)} distinct stamps in window"}
    gaps = s.diff().dt.total_seconds().dropna()
    # COVERAGE IS ONLY MEANINGFUL AGAINST AN EXPLICIT WINDOW. With a
    # data-defined span a recorder that ran 6 minutes of an 8-hour slate scores
    # ~100% over its OWN span and the condition is vacuous — it cannot see a
    # truncated start or end, which is the failure it exists to catch.
    explicit = window_start is not None and window_end is not None
    lo = window_start or s.min()
    hi = window_end or s.max()
    # minute BUCKETS spanned, not elapsed//60: the latter gave 7/5 = 140%.
    window_min = int((hi.floor("min") - lo.floor("min")).total_seconds() // 60) + 1
    covered = s.dt.floor("min").nunique()
    coverage = min(covered / window_min, 1.0)
    r = {
        "stamps": len(s), "median_gap_s": float(gaps.median()),
        "max_gap_s": float(gaps.max()), "coverage": float(coverage),
        "window_minutes": window_min, "covered_minutes": int(covered),
    }
    r["cadence_ok"] = r["median_gap_s"] < CADENCE_MAX_S
    r["continuity_ok"] = r["max_gap_s"] <= CONTINUITY_MAX_S
    r["explicit_window"] = explicit
    # Not a pass when the window was not stated: report it as untested.
    r["coverage_ok"] = explicit and r["coverage"] >= COVERAGE_MIN
    r["ok"] = r["cadence_ok"] and r["continuity_ok"] and r["coverage_ok"]
    return r


def report(r: dict, label: str) -> bool:
    print(f"=== VENUE TAPE PRE-FLIGHT — {label} ===")
    if "reason" in r:
        print(f"  NOT MEASURABLE: {r['reason']}")
        return False
    print(f"  distinct stamps {r['stamps']:,}   window {r['window_minutes']} min\n")
    for name, val, ok, bar in (
        ("CADENCE    median gap", f"{r['median_gap_s']:8.2f}s", r["cadence_ok"],
         f"< {CADENCE_MAX_S:.0f}s"),
        ("CONTINUITY max gap   ", f"{r['max_gap_s']:8.2f}s", r["continuity_ok"],
         f"<= {CONTINUITY_MAX_S:.0f}s"),
        ("COVERAGE   minutes   ", f"{r['coverage']*100:7.1f}%", r["coverage_ok"],
         f">= {COVERAGE_MIN*100:.0f}%"),
    ):
        verdict = "PASS" if ok else "FAIL"
        if name.startswith("COVERAGE") and not r["explicit_window"]:
            verdict = "UNTESTED — pass --start/--end"
        print(f"  {name} {val}   need {bar:>7}   {verdict}")
    print(f"\n  VERDICT: {'PASS — the slate measures the question' if r['ok'] else 'FAIL — the slate does NOT measure the question'}")
    if not r["ok"]:
        print("  Per the registration, a failing pre-flight means the day is")
        print("  reported as NOT MEASURED, not as a FAIL of the model.")
    return r["ok"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--column", default="captured_at")
    p.add_argument("--start", default=None, help="ISO datetime, window start")
    p.add_argument("--end", default=None, help="ISO datetime, window end")
    p.add_argument("--label", default="unlabelled")
    a = p.parse_args()
    df = pd.read_csv(a.csv)
    if a.column not in df.columns:
        print(f"no column {a.column!r}; have {list(df.columns)[:12]}")
        return 2
    ws = pd.Timestamp(a.start, tz="UTC") if a.start else None
    we = pd.Timestamp(a.end, tz="UTC") if a.end else None
    return 0 if report(evaluate(df[a.column], ws, we), a.label) else 1


if __name__ == "__main__":
    raise SystemExit(main())
