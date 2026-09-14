"""Smoke test for the scan's primary statistic. Exits non-zero, runs before the nightly.

WHY THIS FILE EXISTS. A half-applied patch to cfb/run_scan.py once passed `ast.parse`
and then died on prod with `NameError` after the run had started. **A syntax check is
not a smoke test**: parsing gives the feeling of having verified something.

WHAT IT ASSERTS. `poisson_binomial_p` must reduce EXACTLY to scipy.binomtest when every
trial shares one p0 -- that pins the two-sided convention, which is the thing that is
easy to get defensibly wrong. Twice-the-smaller-tail and the small-p method disagree
materially at these n (0.0122 vs 0.0131 at 46/46; 0.0634 vs 0.0459 at 0/12), and the
numbers published in docs/math/scan-preregistration.md were computed with binomtest. The
mixed-p0 case is the one a plain binomial cannot express at all and is why the statistic
exists: a decile spans a 0.1 price band, so break-even varies within every cell.

The function is extracted by AST rather than imported, because run_scan.py opens a
database connection at module scope.
"""
import ast
import pathlib
import sys

from scipy.stats import binomtest

SRC = pathlib.Path(__file__).with_name("run_scan.py")
tree = ast.parse(SRC.read_text())
fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
           and n.name == "poisson_binomial_p"), None)
if fn is None:
    sys.exit("poisson_binomial_p not found in run_scan.py")
ns: dict = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "run_scan", "exec"), ns)
pbp = ns["poisson_binomial_p"]

ok = True
print("poisson_binomial_p must reduce to scipy.binomtest when all p0 are equal:")
for label, trials, ref in (
        ("10 trials p=.500  k=10", [(0.5, 1)] * 10, binomtest(10, 10, 0.5).pvalue),
        ("10 trials p=.500  k=5 ", [(0.5, 1)] * 5 + [(0.5, 0)] * 5, binomtest(5, 10, 0.5).pvalue),
        ("46 trials p=.895  k=46", [(0.895, 1)] * 46, binomtest(46, 46, 0.895).pvalue),
        ("12 trials p=.250  k=0 ", [(0.25, 0)] * 12, binomtest(0, 12, 0.25).pvalue)):
    got, k, n = pbp(trials)
    good = abs(got - ref) < 1e-9
    ok &= good
    print(f"  {label:24} k={k:<3} n={n:<3} p={got:.6g}   binomtest {ref:.6g}   "
          f"{'OK' if good else 'MISMATCH'}")



def brute(trials):
    """Independent reference: enumerate all 2^n outcomes, no DP, no recurrence."""
    from itertools import product
    ps = [q for q, _ in trials]
    k = sum(w for _, w in trials)
    pmf = [0.0] * (len(ps) + 1)
    for combo in product((0, 1), repeat=len(ps)):
        pr = 1.0
        for q, c in zip(ps, combo):
            pr *= q if c else (1 - q)
        pmf[sum(combo)] += pr
    tol = pmf[k] * (1 + 1e-9)
    return min(1.0, sum(v for v in pmf if v <= tol))


print("\nand the DP must match a brute-force enumeration on MIXED p0 -- the case a plain")
print("binomial cannot express, and the reason the statistic exists (a decile spans 0.1):")
for label, trials in (
        ("p=(.80,.85,.90,.95) k=4", [(0.80, 1), (0.85, 1), (0.90, 1), (0.95, 1)]),
        ("p=(.20,.30,.40)     k=3", [(0.20, 1), (0.30, 1), (0.40, 1)]),
        ("p=(.10,.50,.90)     k=1", [(0.10, 1), (0.50, 0), (0.90, 0)]),
        ("p=(.05,.15,.25,.35,.45) k=0",
         [(0.05, 0), (0.15, 0), (0.25, 0), (0.35, 0), (0.45, 0)])):
    got, k, n = pbp(trials)
    ref = brute(trials)
    good = abs(got - ref) < 1e-12
    ok &= good
    print(f"  {label:24} k={k:<3} n={n:<3} p={got:.6g}   brute {ref:.6g}   "
          f"{'OK' if good else 'MISMATCH'}")

print("\n" + ("ALL PASS" if ok else "*** FAILURE -- do not run the scan ***"))
sys.exit(0 if ok else 1)
