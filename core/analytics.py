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

from sqlalchemy import func, select
from sqlalchemy import text as sql_text

from core.backtest.engine import BacktestConfig, run_backtest
from core.backtest.fills import FillModel
from core.paths import analytics_path
from core.storage import Prediction, get_engine, get_sessionmaker

#: The walk-forward backtest issues many small queries per game. Over a remote
#: connection the round-trip latency dominates and a full run takes tens of
#: minutes. Historical data is static, so it is read from the LOCAL standby;
#: only live tables need the remote.
LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


# --------------------------------------------------------------------------- #
# Per-market-type split — the operator's "totals-only is useless"
# --------------------------------------------------------------------------- #
#
# TWO SAMPLES, NEVER BLENDED IN ONE NUMBER. This is the trap the split creates,
# and the reason every block below carries its own count:
#
#   * `n_preds` / `n_resolved` / `n_games` / the Brier scores come from the LIVE
#     prediction log, which covers all three market types.
#   * `money` and `clv` come from the WALK-FORWARD BACKTEST on ESPN sportsbook
#     lines, which only ever ran on TOTALS, and only pregame.
#
# So a `total / pregame` row shows ~50k predictions beside a few hundred
# backtested bets. Those are different samples, so their sizes sit inside their
# own blocks (`money.n_bets`, `clv.n`) where no reader can mistake one for the
# other. `backtested` says which rows have any validation at all, and the
# caption says it in words.

_TYPE_LABELS = {
    "basketball_team_full_game_total": "total",
    "basketball_team_full_game_winner": "winner",
    "basketball_team_full_game_spread": "spread",
}

#: Phase is `predicted_at` against the game's start time.
_PHASE_SQL = """
    with starts as (
        select market_slug, min(game_start_time) as gst
        from market_snapshots
        where game_start_time is not null
        group by market_slug
    )
"""

CAPTION = (
    "Split by market type. Only totals have ever been backtested — spread and "
    "moneyline numbers are prediction records with no validation behind them, "
    "marked accordingly. Win rates are shown with their stake-weighted entry "
    "cost, which is the breakeven they must beat: a 30% win rate on 25c "
    "entries is profit, not failure. Prediction counts and money columns come "
    "from different samples, and each carries its own n. Brier is mean squared "
    "error against the 0/1 outcome, so LOWER IS BETTER: a model Brier above "
    "the market's on the same row means the market priced it more accurately "
    "than the model did."
)


def _brier(pairs: list[tuple[float, int]]) -> float | None:
    """Mean squared error of a probability against a 0/1 outcome."""
    if not pairs:
        return None
    return round(sum((p - o) ** 2 for p, o in pairs) / len(pairs), 5)


def _prediction_rows(session) -> dict[tuple[str, str], dict]:
    """Live-log counts and Brier scores, keyed by (type, phase).

    In-play rows are expected to be nearly empty — the model is pregame-only —
    and are emitted anyway. "The model has never predicted inside a game" is a
    fact worth seeing, not an absence to hide.
    """
    counts = session.execute(sql_text(_PHASE_SQL + """
        select p.sports_market_type,
               case when s.gst is not null and p.predicted_at >= s.gst
                    then 'ingame' else 'pregame' end as phase,
               count(*), count(p.resolved_outcome), count(distinct p.game_id)
        from predictions p
        left join starts s on s.market_slug = p.market_slug
        group by 1, 2
    """)).all()

    resolved = session.execute(sql_text(_PHASE_SQL + """
        select p.sports_market_type,
               case when s.gst is not null and p.predicted_at >= s.gst
                    then 'ingame' else 'pregame' end as phase,
               p.model_probability, p.market_mid, p.resolved_outcome
        from predictions p
        left join starts s on s.market_slug = p.market_slug
        where p.resolved_outcome is not null
    """)).all()

    model_pairs: dict[tuple[str, str], list] = {}
    market_pairs: dict[tuple[str, str], list] = {}
    for mtype, phase, prob, mid, outcome in resolved:
        key = (_TYPE_LABELS.get(mtype or "", "other"), phase)
        if prob is not None:
            model_pairs.setdefault(key, []).append((float(prob), outcome))
        if mid is not None:
            market_pairs.setdefault(key, []).append((float(mid), outcome))

    out: dict[tuple[str, str], dict] = {}
    for mtype, phase, n_preds, n_resolved, n_games in counts:
        key = (_TYPE_LABELS.get(mtype or "", "other"), phase)
        agg = out.setdefault(key, {"n_preds": 0, "n_resolved": 0, "n_games": 0})
        agg["n_preds"] += n_preds
        agg["n_resolved"] += n_resolved
        agg["n_games"] = max(agg["n_games"], n_games)
        agg["brier_model"] = _brier(model_pairs.get(key, []))
        agg["brier_market"] = _brier(market_pairs.get(key, []))
    return out


def _backtest_money(result) -> tuple[dict | None, dict | None]:
    """(money, clv) for the one slice the backtest actually covers.

    The walk-forward backtest is totals-only and pregame-only, so this belongs
    to the `total / pregame` row and nowhere else. Returning None for the rest
    is the honest answer, not a gap to fill with the overall figure.
    """
    m = result.metrics
    filled = [b for b in result.bets if b.filled]
    contracts = sum(b.contracts for b in filled)
    if not filled or not m.total_staked:
        return None, None
    money = {
        "staked": round(m.total_staked, 2),
        "returned": round(m.total_staked + m.total_pnl, 2),
        "roi": None if m.roi is None else round(m.roi, 5),
        "n_bets": m.n_filled,
        "win_rate": None if m.hit_rate is None else round(m.hit_rate, 4),
        # Stake-weighted cost per contract — the breakeven the win rate must
        # beat (C11). A win rate shown without it is a category error.
        "entry_cost": round(m.total_staked / contracts, 4) if contracts else None,
        "fees": round(m.total_fees, 2),
    }
    clv = None
    if m.clv_points:
        clv = {
            "mean": None if m.mean_clv is None else round(m.mean_clv, 4),
            "stderr": None if m.clv_stderr is None else round(m.clv_stderr, 4),
            "n": m.n_with_closing_line,
        }
    return money, clv


def by_market_type(session, result) -> dict:
    """The `by_market_type` block, in the shape agreed with the renderer."""
    preds = _prediction_rows(session)
    money, clv = _backtest_money(result)

    rows = []
    for mtype in ("total", "winner", "spread"):
        for phase in ("pregame", "ingame"):
            agg = preds.get((mtype, phase), {})
            backtested = mtype == "total" and phase == "pregame"
            if backtested:
                note = ("money and CLV are the walk-forward backtest on ESPN "
                        "lines — a different, smaller sample than the "
                        "prediction counts beside them")
            elif mtype == "total":
                note = "backtest is pregame-only; no validation for in-play"
            elif phase == "ingame":
                note = "never backtested, and the model is pregame-only"
            else:
                note = "never backtested — prediction record only"
            rows.append({
                "type": mtype,
                "phase": phase,
                "n_preds": agg.get("n_preds", 0),
                "n_resolved": agg.get("n_resolved", 0),
                "n_games": agg.get("n_games", 0),
                "brier_model": agg.get("brier_model"),
                "brier_market": agg.get("brier_market"),
                "clv": clv if backtested else None,
                "money": money if backtested else None,
                "backtested": backtested,
                "note": note,
            })
    return {"rows": rows, "caption": CAPTION}


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

        # Inside the session deliberately: `s` is closed below.
        market_type_split = by_market_type(s, r)

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
        "by_market_type": market_type_split,
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
    # Resolved here, not at import: MERIDIAN_DATA_DIR is read per call so the
    # host job and the api container land on the same file (core/paths.py).
    out = analytics_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build(args.database_url)
    out.write_text(json.dumps(data, indent=1))
    print(f"wrote {out}")
    print(f"  bets={data['summary']['bets']} roi={data['summary']['roi']:.4f} "
          f"clv={data['summary']['mean_clv']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
