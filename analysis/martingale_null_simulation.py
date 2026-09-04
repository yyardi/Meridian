"""What DOES a true martingale score on S? Simulate it, do not argue it.

S = mean over real fills of side x (settlement - mid_at_fill).
My residual in martingale_bar.py is algebraically identical to B's S.

I claimed E[S | fair] = 0. My selftest asserted that by CONSTRUCTING data
with settlement == mid, which forces the answer -- it never simulated a
path under the fill rule. B claims E[S | fair] = +2.18c to +3.18c.

The analytic subtlety that makes this genuinely open:
  E[ SUM_i side_i (Y - m_i) ] = 0 by the tower property, since side_i and
  m_i are F_i-measurable and E[Y | F_i] = m_i under a martingale.
  But S is that sum divided by N, and N is random and path-correlated.
  A ratio of two correlated random quantities need not have expectation
  equal to the ratio of expectations. So the SUM is unbiased and the MEAN
  may not be.

Settle it by simulating a genuine martingale (symmetric random walk with
absorbing barriers at 0 and 1 -- a martingale by construction, terminating
AT its own settlement) and running our actual resting-quote fill rule.
"""
import numpy as np

TICK = 0.01
RNG = np.random.default_rng(20260904)


def one_market(spread_ticks: int, sigma_ticks: float = 2.0,
               max_steps: int = 4000):
    """Symmetric walk with absorbing barriers; quotes at the touch each step.

    Returns list of (side, mid_at_fill) for REAL fills, plus settlement.
    side: +1 our bid filled (long YES), -1 our ask filled (short YES).
    """
    s = spread_ticks * TICK
    mid = RNG.integers(20, 81) * TICK          # start inside the band
    fills = []
    bid_q = ask_q = None                        # our resting quotes
    for _ in range(max_steps):
        bb, ba = mid - s / 2, mid + s / 2
        # 1. fills against the ALREADY-resting quote, real-fill rule:
        #    our bid is hit only if the market's ask came down to it.
        if bid_q is not None and ba <= bid_q + 1e-12:
            fills.append((+1, mid))
        if ask_q is not None and bb >= ask_q - 1e-12:
            fills.append((-1, mid))
        # 2. requote at the touch
        bid_q, ask_q = bb, ba
        # 3. martingale step. A 5s observation interval moves the mid by
        #    SEVERAL ticks; with a one-tick step the mid can never jump a
        #    full spread and a resting quote is never crossed at all (the
        #    first version of this fixture produced exactly zero fills,
        #    which is itself the structural point). Symmetric integer step
        #    keeps it a martingale.
        step = int(np.rint(RNG.normal(0.0, sigma_ticks)))
        mid = mid + step * TICK
        if mid <= 1e-9:
            return fills, 0.0
        if mid >= 1.0 - 1e-9:
            return fills, 1.0
    return fills, float(RNG.random() < mid)     # rare: force a fair terminal


def run(n_markets: int, spread_ticks: int):
    per_market_S, all_terms, n_fills = [], [], 0
    for _ in range(n_markets):
        fills, y = one_market(spread_ticks)
        if not fills:
            continue
        terms = [side * (y - m) for side, m in fills]
        per_market_S.append(np.mean(terms))
        all_terms.extend(terms)
        n_fills += len(terms)
    return np.array(per_market_S), np.array(all_terms), n_fills


print("A TRUE MARTINGALE, our fill rule, binary settlement at the terminal.")
print("If E[S|fair] = 0 my framing holds; if ~+2 to +3c, B's bar is right.\n")
print(f"{'spread':>7s} {'markets':>8s} {'fills':>8s} "
      f"{'S pooled over fills':>22s} {'S mean of per-market':>22s}")
for st in (2, 4, 8):
    pm, terms, nf = run(600, st)
    # pooled: the estimator I used (mean over fills)
    pooled = terms.mean() * 100
    se_p = terms.std(ddof=1) / np.sqrt(len(pm)) * 100      # cluster by market
    # mean of per-market means: the clustered estimator
    mm = pm.mean() * 100
    se_m = pm.std(ddof=1) / np.sqrt(len(pm)) * 100
    print(f"{st:>5d}c {len(pm):>8d} {nf:>8d} "
          f"{f'{pooled:+.3f} +- {1.96*se_p:.3f}':>22s} "
          f"{f'{mm:+.3f} +- {1.96*se_m:.3f}':>22s}")

print("\nAlso the SUM, which the tower property says must be unbiased:")
pm, terms, nf = run(1500, 4)
tot = terms.sum()
print(f"  sum over {nf} fills = {tot:+.3f} contracts-worth "
      f"(mean per fill {terms.mean()*100:+.3f}c)")
