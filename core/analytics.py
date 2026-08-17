"""Pre-compute model-performance analytics for the dashboard.

Writes a JSON blob the UI can render without re-running a backtest on every
page load (a full walk-forward takes ~30s).

    python -m core.analytics

An important framing point, surfaced in the output: the **live prediction log
cannot answer "how is the model doing" yet** — those games have not finished.
Everything quantitative here comes from the historical walk-forward backtest.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from core.backtest.engine import BacktestConfig, run_backtest
from core.backtest.fills import FillModel
from core.storage import Prediction, get_engine, get_sessionmaker

from core.paths import reports_dir

# Regenerable output; lives under the one artifact root (core/paths.py).
OUT = reports_dir() / "analytics.json"

#: The walk-forward backtest issues many small queries per game. Over a remote
#: connection the round-trip latency dominates and a full run takes tens of
#: minutes. Historical data is static, so it is read from the LOCAL standby;
#: only live tables need the remote.
LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


def build(backtest_url: str | None = None) -> dict:
    Session = get_sessionmaker(get_engine(backtest_url or LOCAL_URL))
    with Session() as s:
        results = {
            m: run_backtest(session=s, config=BacktestConfig(
                start_season=2024, end_season=2026, fill_model=m))
            for m in FillModel
        }
        r = results[FillModel.REALISTIC]

        # Live prediction log: distribution only. No outcomes yet.
        live_rows = s.execute(
            select(
                Prediction.sports_market_type,
                func.count(),
                func.avg(Prediction.model_probability),
                func.avg(Prediction.market_mid),
                func.count(Prediction.resolved_outcome),
            ).group_by(Prediction.sports_market_type)
        ).all()

    m = r.metrics
    equity = m.equity_curve

    # Drawdown series alongside equity.
    peak, dd = (equity[0] if equity else 0), []
    for v in equity:
        peak = max(peak, v)
        dd.append(round((v - peak) / peak, 5) if peak else 0.0)

    return {
        "generated_from": "walk-forward backtest 2024-2026, ESPN sportsbook lines",
        "scope_warning": (
            "TOTALS ONLY. Spread and moneyline markets are predicted and "
            "shadow-traded but have never been backtested — there is no "
            "validation behind them."
        ),
        "calibration": [
            {"predicted": round(b.predicted, 2), "realised": b.realised, "n": b.n}
            for b in m.calibration if b.n > 0
        ],
        "equity": [round(v, 3) for v in equity],
        "drawdown": dd,
        "summary": {
            "bets": m.n_bets,
            "filled": m.n_filled,
            "hit_rate": m.hit_rate,
            "roi": m.roi,
            "mean_clv": m.mean_clv,
            "clv_stderr": m.clv_stderr,
            "pct_beating_close": m.pct_beating_close,
            "max_drawdown": m.max_drawdown,
            "sharpe": m.sharpe,
            "edge_corr": m.edge_vs_realised_correlation,
            "total_fees": m.total_fees,
        },
        "fill_models": {
            k.value: {
                "roi": v.metrics.roi,
                "pnl": v.metrics.total_pnl,
                "filled": v.metrics.n_filled,
            } for k, v in results.items()
        },
        # Edge bucket -> realised P&L. Answers "does a bigger edge pay more?"
        "edge_buckets": _edge_buckets(r),
        "scatter": [
            {"edge": round(b.edge, 4), "pnl": round(b.pnl, 4),
             "won": b.won, "season": b.season}
            for b in r.bets if b.filled and b.won is not None
        ][:600],
        "clv_hist": _clv_hist(r),
        "live_predictions": [
            {
                "type": (t or "").replace("basketball_team_full_game_", ""),
                "n": n,
                "avg_model": float(am) if am is not None else None,
                "avg_market": float(mm) if mm is not None else None,
                "resolved": res,
            }
            for t, n, am, mm, res in live_rows
        ],
    }


def _edge_buckets(r) -> list[dict]:
    bets = [b for b in r.bets if b.filled and b.won is not None]
    bets.sort(key=lambda b: abs(b.edge))
    out, k = [], 5
    n = len(bets)
    for i in range(k):
        sub = bets[i * n // k:(i + 1) * n // k]
        if not sub:
            continue
        out.append({
            "quintile": i + 1,
            "n": len(sub),
            "avg_edge": round(sum(abs(b.edge) for b in sub) / len(sub), 4),
            "avg_pnl": round(sum(b.pnl for b in sub) / len(sub), 4),
            "hit_rate": round(sum(1 for b in sub if b.won) / len(sub), 4),
        })
    return out


def _clv_hist(r) -> list[dict]:
    vals = [b.clv_points for b in r.bets if b.clv_points is not None]
    if not vals:
        return []
    buckets: dict[int, int] = {}
    for v in vals:
        b = max(-8, min(8, int(round(v))))
        buckets[b] = buckets.get(b, 0) + 1
    return [{"points": k, "n": v} for k, v in sorted(buckets.items())]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="meridian-analytics")
    ap.add_argument("--database-url", default=None,
                    help="defaults to the local standby (fast); historical data is static")
    args = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = build(args.database_url)
    OUT.write_text(json.dumps(data, indent=1))
    print(f"wrote {OUT}")
    print(f"  bets={data['summary']['bets']} roi={data['summary']['roi']:.4f} "
          f"clv={data['summary']['mean_clv']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
