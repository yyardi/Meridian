"""Projection check on the resting-order probe's current design.

The check from `FORCED_GRADIENTS.md` stage four: compute the outcome range the
design can produce, project it onto the branch structure, and inspect the image.
Predetermined / inverted / dead branch / cannot-discriminate.

Design as registered: >=100 games, <=3 orders per game, 10-minute windows,
one-sided Clopper-Pearson, cluster-robust at df = games-1. Bands on the upper
bound of the violation rate: <1% CONFIRMED, 1-8% SUPPORTED, >8% REFUTED.

## VERDICT: it passes the check it was built for, and fails three others

**PASSES.** No branch is predetermined and none is dead: all three verdicts are
reachable under both named methods. This is the failure that killed the n=40
version and it is genuinely gone.

**FAILS 1 — CONFIRMED is a knife-edge.** One-sided Clopper-Pearson needs
**n >= 299** for a zero-violation upper bound below 1%. The design plans 300.
**Headroom is one order.** And `<=3 orders per game` makes 300 a CEILING rather
than a floor, so a single game yielding two orders ends CONFIRMED before any
violation occurs. Not unreachable — reachable only if nothing at all goes wrong,
which is not a property a pre-registered branch should have.
Fix: 111 games (n=332) puts the best case at 0.90%; 124 games (n=373) at 0.80%.

**FAILS 2 — the two named methods disagree on the same data.** At one violation
Clopper-Pearson gives 1.571% (SUPPORTED) and the cluster-robust interval gives
0.995% (CONFIRMED). Registering both means the verdict is selected after the
data exist. One must be named. Clopper-Pearson is the conservative choice and
the one that does not degenerate (below).

**FAILS 3 — the cluster-robust interval collapses on the best case.** With zero
violations every residual is zero, so the sandwich estimator's meat is zero,
stderr is zero and the interval is **[0, 0] — zero width**. It reports the rate
as exactly zero with no uncertainty. A zero-width interval is a broken
computation, not strong evidence, and if cluster-robust is chosen this case
needs an explicit rule.

**AND A PROPERTY TO STATE RATHER THAN FIX.** Under clustering the verdict
depends on how violations DISTRIBUTE, not only how many: 15 violations spread
one-per-game gives 7.374% (SUPPORTED), the same 15 packed into five games gives
9.346% (REFUTED). That is correct behaviour -- concentrated violations carry
less information -- but it means the pre-registered bands cannot be stated as
violation counts alone, and the registration should say so.
"""

from __future__ import annotations

from scipy.stats import beta

from core.quote.adverse_selection import clustered_mean

GAMES, PER_GAME = 100, 3
N = GAMES * PER_GAME


def cp_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided Clopper-Pearson upper bound, as registered."""
    return 1.0 if k == n else float(beta.ppf(1 - alpha, k + 1, n - k))


def band(upper: float) -> str:
    pct = upper * 100
    return "CONFIRMED" if pct < 1 else ("SUPPORTED" if pct <= 8 else "REFUTED")


def clustered_upper(viol_per_game: list[int]) -> float:
    d = {f"g{i}": [1.0] * v + [0.0] * (PER_GAME - v)
         for i, v in enumerate(viol_per_game)}
    r = clustered_mean(d)
    return max(r.hi, 0.0) if r else 0.0


def spread(k: int) -> list[int]:
    """One violation per game until exhausted — maximally spread."""
    v = [0] * GAMES
    i = 0
    while k > 0:
        if v[i % GAMES] < PER_GAME:
            v[i % GAMES] += 1
            k -= 1
        i += 1
    return v


def packed(k: int) -> list[int]:
    """Packed into as few games as possible — maximally concentrated."""
    v, r = [], k
    while r > 0:
        t = min(PER_GAME, r)
        v.append(t)
        r -= t
    return (v + [0] * GAMES)[:GAMES]


def main() -> int:
    print(f"design: {GAMES} games x <={PER_GAME} orders = n {N}\n")
    print(f"  {'viol':>5} {'CP':>9} {'band':>10} | {'clust spread':>12} {'band':>10}"
          f" | {'clust packed':>12} {'band':>10}")
    img_cp, img_cl = set(), set()
    for k in (0, 1, 2, 3, 5, 9, 12, 15, 24, 30, 60):
        u = cp_upper(k, N)
        a, b = clustered_upper(spread(k)), clustered_upper(packed(k))
        img_cp.add(band(u))
        img_cl.update({band(a), band(b)})
        print(f"  {k:>5} {u*100:>8.3f}% {band(u):>10} | {a*100:>11.3f}% {band(a):>10}"
              f" | {b*100:>11.3f}% {band(b):>10}")
    print(f"\n  IMAGE (Clopper-Pearson): {sorted(img_cp)}")
    print(f"  IMAGE (cluster-robust) : {sorted(img_cl)}")
    print("  -> not predetermined, no dead branch. The n=40 failure is gone.")

    print("\n" + "=" * 66)
    print("KNIFE-EDGE: how much attrition does CONFIRMED survive?")
    print("=" * 66)
    nmin = next(n for n in range(2, 4000) if cp_upper(0, n) * 100 < 1)
    for n in (300, 299, 298, 295, 290):
        u = cp_upper(0, n) * 100
        print(f"  n={n:>4} best case {u:.4f}% -> {band(u/100)}")
    print(f"  minimum n for CONFIRMED: {nmin}   headroom at planned 300: "
          f"{300 - nmin} order(s)")
    for tgt in (0.9, 0.8):
        n = next(x for x in range(2, 4000) if cp_upper(0, x) * 100 < tgt)
        print(f"  for a {tgt:.1f}% best case: n={n} ({n/PER_GAME:.0f} games)")

    print("\n" + "=" * 66)
    print("DEGENERACY: the cluster-robust interval on a perfect result")
    print("=" * 66)
    d = {f"g{i}": [0.0] * PER_GAME for i in range(GAMES)}
    r = clustered_mean(d)
    print(f"  zero violations -> mean {r.mean:.6f} stderr {r.stderr:.6f} "
          f"CI [{r.lo:.6f}, {r.hi:.6f}] width {r.hi - r.lo:.6f}")
    print("  A zero-width interval is a broken computation, not certainty.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
