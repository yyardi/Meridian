"""edge.py — PRIMARY validation: is the disagreement PROFITABLE, net of cost?

WHY NOT RankIC. corr(ours-mkt, OUTCOME) is badly attenuated: a model that is
EXACTLY right against a noisy-but-unbiased market scores only +0.0715, barely
over the 0.05 'good' threshold, so a genuinely useful but imperfect model gets
killed. The residual form corr(ours-mkt, OUTCOME-mkt) scores +0.3127 on the
same data and is correct -- but the equity IC thresholds (0.05/0.10/0.15) are
calibrated to forecast-vs-forward-return and DO NOT transfer: they would flag
a perfect model as overfitting. Importing a benchmark across constructions is
the same error as importing a constant across populations.

So the primary is the DECISION: act on disagreement, score against the realised
outcome, charge the measured cost, cluster by game. No borrowed benchmark.

MARKET FRESHNESS IS MANDATORY. A frozen venue feed (2026-09-05: 4.5h at 0.0%
of markets moving) gives a mid that CANNOT move. Our model's probability still
moves with game state, so every play generates a 'disagreement' against a stale
price and the measured edge is enormous and entirely artefactual -- and it
reads as caution rather than as a bug. Stale rows are EXCLUDED AND COUNTED,
never silently dropped.
"""
from __future__ import annotations
import random, statistics as st


def edge_pnl(rows, threshold=0.02, cost=0.0, require_fresh=True):
    """rows: (game_id, our_prob, market_prob, outcome, market_fresh)
    Returns (trades, stats). market_fresh may be omitted -> treated as UNKNOWN
    and excluded when require_fresh (absence is not freshness)."""
    trades, n_stale, n_unknown, n_flat = [], 0, 0, 0
    for r in rows:
        g, ours, mkt, o = r[0], r[1], r[2], r[3]
        fresh = r[4] if len(r) > 4 else None
        if require_fresh:
            if fresh is None: n_unknown += 1; continue
            if not fresh:     n_stale += 1;   continue
        d = ours - mkt
        if d > threshold:      trades.append((g, o - mkt - cost))
        elif d < -threshold:   trades.append((g, mkt - o - cost))
        else:                  n_flat += 1
    return trades, {"excluded_stale": n_stale, "excluded_unknown_freshness": n_unknown,
                    "no_disagreement": n_flat, "considered": len(rows)}


def block_bootstrap_mean(trades, n_boot=2000, seed=20260905):
    """Resample WHOLE GAMES -- plays within a game share one label."""
    if not trades:
        return (None, None, None, 0, 0)
    rng = random.Random(seed)
    by = {}
    for g, p in trades:
        by.setdefault(g, []).append(p)
    games = list(by)
    means = []
    for _ in range(n_boot):
        draw = [rng.choice(games) for _ in games]
        means.append(st.mean([p for g in draw for p in by[g]]))
    means.sort()
    return (st.mean(p for _, p in trades),
            means[int(.025 * n_boot)], means[int(.975 * n_boot)],
            len(games), len(trades))


def report(rows, threshold=0.02, cost=0.0, min_games=25, n_boot=2000):
    trades, stats = edge_pnl(rows, threshold, cost)
    pt, lo, hi, ng, nt = block_bootstrap_mean(trades, n_boot=n_boot)
    lines = [f"considered={stats['considered']}  excluded_stale={stats['excluded_stale']}"
             f"  excluded_unknown_freshness={stats['excluded_unknown_freshness']}"
             f"  no_disagreement={stats['no_disagreement']}",
             f"GAMES={ng}  TRADES={nt}  threshold={threshold}  cost={cost}"]
    if nt == 0:
        lines.append("VERDICT: NO TRADES -- the model never disagrees with a fresh market. No edge to have.")
    elif ng < min_games:
        lines.append(f"VERDICT: UNDERPOWERED -- {ng} games < {min_games}. REFUSING to report an edge.")
    elif lo <= 0 <= hi:
        lines.append(f"VERDICT: NO EDGE -- {pt:+.4f}/trade 95%CI [{lo:+.4f},{hi:+.4f}]. DO NOT GO LIVE.")
    elif hi < 0:
        lines.append(f"VERDICT: NEGATIVE EDGE -- {pt:+.4f}/trade CI entirely below zero.")
    else:
        lines.append(f"VERDICT: EDGE -- {pt:+.4f}/trade 95%CI [{lo:+.4f},{hi:+.4f}].")
    return "\n".join(lines)


def _selftest():
    rng = random.Random(11)
    A = []
    for g in range(60):
        truth = rng.random(); o = 1 if rng.random() < truth else 0   # ONE outcome per game
        for _ in range(40):
            m = min(max(truth + rng.gauss(0, .15), .01), .99)
            A.append((g, truth, m, o, True))                          # we are exactly right
    t, s = edge_pnl(A); pt, lo, hi, ng, nt = block_bootstrap_mean(t, n_boot=400)
    print(f"  (A) perfect model, fresh, no cost : {pt:+.4f} [{lo:+.4f},{hi:+.4f}] games={ng} trades={nt}")
    assert lo > 0, "a perfect model must show edge"
    t2, _ = edge_pnl(A, cost=0.03); pt2, lo2, *_ = block_bootstrap_mean(t2, n_boot=400)
    assert pt2 < pt, "cost must reduce measured edge"
    B = [(g, m, m, o, True) for g, _, m, o, _ in A]
    tb, _ = edge_pnl(B); assert len(tb) == 0, "a model that never disagrees must never trade"
    # * FROZEN MARKET: stale rows must be excluded and COUNTED, not silently dropped.
    F = [(g, ours, mkt, o, False) for g, ours, mkt, o, _ in A]
    tf, sf = edge_pnl(F)
    assert len(tf) == 0 and sf["excluded_stale"] == len(A), "stale rows leaked into trades"
    # * absence of a freshness flag is NOT freshness
    U = [(g, ours, mkt, o) for g, ours, mkt, o, _ in A]
    tu, su = edge_pnl(U)
    assert len(tu) == 0 and su["excluded_unknown_freshness"] == len(A), "unknown freshness treated as fresh"
    few = [(g, p) for g, p in t if g < 10]
    assert "UNDERPOWERED" in report([r for r in A if r[0] < 10], n_boot=100)
    print(f"  (B) frozen market : trades={len(tf)} excluded_stale={sf['excluded_stale']} -> correctly refused")
    print("selftest OK -- edge detected, cost binds, no-disagreement=0 trades, frozen excluded+counted, power guard fires")


if __name__ == "__main__":
    _selftest()
