"""Smoke test the statistic before it touches prod -- the step I skipped last run."""
src = open("/private/tmp/claude-501/-Users-yayardia-Documents-Quant-Meridian/38848fd4-29aa-4ee9-88d0-6eee80878c28/scratchpad/mer-scan/cfb/run_scan.py").read()
head = src.split("CELLS, STOCK, DROP")[0]
head = "\n".join(l for l in head.split("\n") if not l.startswith(("from core", "from sqlalchemy", "eng =", "CACHE =", "settle =")))
head = head.replace("@event.listens_for(eng, \"connect\")", "if False:").replace("def _np(c, _r):", "  def _np(c, _r):")
ns = {}
exec(compile(head, "rs", "exec"), ns)
pbp = ns["poisson_binomial_p"]
from scipy.stats import binomtest
print("SMOKE TEST: poisson_binomial_p must reduce to the exact binomial when all p0 are equal")
ok = True
for lab, tr, ref in (
        ("10 trials p=.5  k=10", [(0.5, 1)] * 10, binomtest(10, 10, 0.5).pvalue),
        ("10 trials p=.5  k=5 ", [(0.5, 1)] * 5 + [(0.5, 0)] * 5, binomtest(5, 10, 0.5).pvalue),
        ("46 trials p=.895 k=46", [(0.895, 1)] * 46, binomtest(46, 46, 0.895).pvalue),
        ("12 trials p=.25 k=0 ", [(0.25, 0)] * 12, binomtest(0, 12, 0.25).pvalue)):
    got, k, n = pbp(tr)
    good = abs(got - ref) < 1e-9
    ok &= good
    print(f"  {lab:22} k={k:<3} n={n:<3} p={got:.6g}  scipy {ref:.6g}  {'OK' if good else 'MISMATCH'}")
tr = [(0.80, 1), (0.85, 1), (0.90, 1), (0.95, 1)]
got, k, n = pbp(tr)
hand = min(1.0, 2 * (0.80 * 0.85 * 0.90 * 0.95))
good = abs(got - hand) < 1e-12
ok &= good
print(f"  {'mixed p0, k=4/4':22} k={k:<3} n={n:<3} p={got:.6g}  hand {hand:.6g}  {'OK' if good else 'MISMATCH'}")
print("\n  " + ("ALL PASS -- the mixed-p0 case is the one a plain binomial cannot do"
                if ok else "*** FAILURE: do not run this on prod ***"))
raise SystemExit(0 if ok else 1)
