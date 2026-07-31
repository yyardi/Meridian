"""Backtest reporting.

The report's job is to be *honest*, not flattering. It states sample size,
closing-line coverage, and which fill model produced which number, and it says
plainly when a result means nothing.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from core.backtest.engine import BacktestResult
from core.backtest.fills import ASSUMPTIONS, FillModel
from core.backtest.metrics import sample_size_verdict


def _fmt(value: float | None, spec: str = ".4f", dash: str = "n/a") -> str:
    return dash if value is None else format(value, spec)


def format_report(result: BacktestResult, *, title: str = "BACKTEST") -> str:
    m = result.metrics
    cfg = result.config
    out: list[str] = []
    add = out.append

    add(title)
    add("=" * 78)
    add(f"model            : {result.model_version}  config_hash={result.config_hash[:12]}")
    add(f"seasons          : {cfg.start_season}-{cfg.end_season}")
    add(f"fill model       : {cfg.fill_model.value} — {ASSUMPTIONS[cfg.fill_model].description}")
    add(f"min edge         : {cfg.min_edge_points} points")
    add("")

    add("SAMPLE")
    add("-" * 78)
    add(f"  games considered           : {result.games_considered}")
    add(f"  skipped, no odds           : {result.games_no_odds}")
    add(f"  skipped, thin features     : {result.games_insufficient_features}")
    add(f"  bets triggered             : {m.n_bets}")
    add(f"  bets filled                : {m.n_filled}")
    add("")

    # --- honesty flags ------------------------------------------------ #
    add("DATA PROVENANCE")
    add("-" * 78)
    add("  Market prices are ESPN SPORTSBOOK lines, not Polymarket US.")
    add("  Polymarket launched ~2026-03, so no multi-year venue history exists.")
    add("  This measures whether the model beats a sportsbook closing line;")
    add("  venue-specific edge requires the recorder running forward.")
    add("")
    if m.n_bets:
        pct = m.n_with_closing_line / m.n_bets * 100
        add(f"  bets with a TRUE closing line : {m.n_with_closing_line}/{m.n_bets} ({pct:.1f}%)")
        if pct < 100:
            add("  Remaining bets have consensus lines only (2020-2023 has no")
            add("  open/close split), so CLV is not computable for them.")
    add("")

    add("CLOSING LINE VALUE  (primary metric)")
    add("-" * 78)
    if m.clv_points:
        stderr = m.clv_stderr
        mean = m.mean_clv
        add(f"  mean CLV            : {_fmt(mean, '+.3f')} points")
        add(f"  standard error      : {_fmt(stderr, '.3f')}")
        if mean is not None and stderr:
            lo, hi = mean - 1.96 * stderr, mean + 1.96 * stderr
            add(f"  95% CI              : [{lo:+.3f}, {hi:+.3f}]")
            if lo <= 0 <= hi:
                add("  -> CI includes zero: NO measurable closing-line edge.")
            elif lo > 0:
                add("  -> CI is entirely positive: the model beats the close.")
            else:
                add("  -> CI is entirely negative: the model LOSES to the close.")
        add(f"  % of bets beating close : {_fmt(m.pct_beating_close, '.1%')}")
    else:
        add("  no bets had a true closing line — CLV not computable")
    add("")

    add("RETURNS  (secondary — noise-dominated at small n)")
    add("-" * 78)
    add(f"  hit rate            : {_fmt(m.hit_rate, '.3f')}  ({m.n_wins}/{m.n_resolved})")
    add(f"  ROI                 : {_fmt(m.roi, '+.2%')}")
    add(f"  total P&L           : {m.total_pnl:+.2f} units")
    add(f"  total fees          : {m.total_fees:+.2f} units")
    add(f"  max drawdown        : {m.max_drawdown:.1%}")
    add(f"  Sharpe (per bet)    : {_fmt(m.sharpe, '.3f')}")
    add(f"  edge vs realised r  : {_fmt(m.edge_vs_realised_correlation, '+.3f')}")
    add("")

    if m.calibration and any(b.n for b in m.calibration):
        add("CALIBRATION")
        add("-" * 78)
        add(f"  {'predicted':>10}{'realised':>10}{'n':>7}")
        for b in m.calibration:
            if b.n == 0:
                continue
            add(f"  {b.predicted:>10.2f}{_fmt(b.realised, '.2f'):>10}{b.n:>7}")
        add("")

    playoff_bets = [b for b in result.bets if b.is_playoff]
    if playoff_bets:
        add("PLAYOFF COHORT (reported separately)")
        add("-" * 78)
        add(f"  bets: {len(playoff_bets)}")
        add("  Postseason samples are ~15-24 games/season. No playoff-specific")
        add("  conclusion is statistically supportable at this size.")
        add("")

    add("VERDICT")
    add("-" * 78)
    for line in sample_size_verdict(m.n_bets).split(". "):
        if line.strip():
            add(f"  {line.strip().rstrip('.')}.")
    add("")
    return "\n".join(out)


@dataclass
class ABResult:
    with_modifier: BacktestResult
    without_modifier: BacktestResult


def format_ab_report(ab: ABResult) -> str:
    """Record-modifier A/B: measured, never assumed."""
    a, b = ab.with_modifier, ab.without_modifier
    out: list[str] = []
    add = out.append

    add("RECORD-MODIFIER A/B")
    add("=" * 78)
    add(f"  {'':<22}{'beta fitted':>16}{'beta = 0':>16}{'delta':>12}")
    add("-" * 78)

    def row(label: str, x: float | None, y: float | None, spec: str = ".4f") -> None:
        if x is None or y is None:
            add(f"  {label:<22}{_fmt(x, spec):>16}{_fmt(y, spec):>16}{'n/a':>12}")
        else:
            add(f"  {label:<22}{x:>16{spec}}{y:>16{spec}}{x - y:>+12{spec}}")

    row("mean CLV (points)", a.metrics.mean_clv, b.metrics.mean_clv, "+.3f")
    row("ROI", a.metrics.roi, b.metrics.roi, "+.4f")
    row("hit rate", a.metrics.hit_rate, b.metrics.hit_rate, ".4f")
    add(f"  {'bets':<22}{a.metrics.n_bets:>16}{b.metrics.n_bets:>16}")
    add("")

    same = (
        a.metrics.n_bets == b.metrics.n_bets
        and abs((a.metrics.total_pnl or 0) - (b.metrics.total_pnl or 0)) < 1e-9
    )
    if same:
        add("  The two arms are IDENTICAL.")
        add("  Expected: the record modifier applies to spread/moneyline only, and")
        add("  this backtest covers TOTALS. Clutch execution has no mechanism for")
        add("  moving a game's combined score, so totals are untouched by design.")
    else:
        add("  The arms differ — inspect which markets moved and why.")
    add("")
    add("  Reminder: on 2023-2025 data the record residual's spread across teams")
    add("  (4.9 win-% pts) is SMALLER than pure binomial noise for a 40-game")
    add("  season (7.9 win-% pts). A near-zero effect is the expected, valid")
    add("  result — not a bug, and not something to tune away.")
    return "\n".join(out)


def format_fill_comparison(results: dict[FillModel, BacktestResult]) -> str:
    """All three fill models side by side.

    If an edge only survives OPTIMISTIC, there is no edge.
    """
    out: list[str] = []
    add = out.append
    add("FILL MODEL COMPARISON")
    add("=" * 78)
    add(f"  {'model':<14}{'bets':>7}{'filled':>8}{'ROI':>10}{'P&L':>10}{'fees':>10}{'meanCLV':>10}")
    add("-" * 78)
    for model in (FillModel.OPTIMISTIC, FillModel.REALISTIC, FillModel.PESSIMISTIC):
        r = results.get(model)
        if r is None:
            continue
        m = r.metrics
        add(
            f"  {model.value:<14}{m.n_bets:>7}{m.n_filled:>8}"
            f"{_fmt(m.roi, '+.2%'):>10}{m.total_pnl:>+10.2f}"
            f"{m.total_fees:>+10.2f}{_fmt(m.mean_clv, '+.3f'):>10}"
        )
    add("")
    add("  If a result is only positive under OPTIMISTIC, it is not an edge —")
    add("  that model assumes every resting order fills at the quoted price.")
    return "\n".join(out)


def write_csv(result: BacktestResult, path: str) -> None:
    """Export bets for notebook analysis."""
    import csv

    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "game_date", "espn_game_id", "season", "season_type", "side",
            "entry_line", "closing_line", "projected_total", "model_probability",
            "entry_price", "edge", "contracts", "filled", "fee",
            "actual_total", "won", "pnl", "clv_points", "is_playoff",
        ])
        for b in result.bets:
            w.writerow([
                b.game_date.isoformat(), b.espn_game_id, b.season, b.season_type, b.side,
                b.entry_line, b.closing_line, round(b.projected_total, 2),
                round(b.model_probability, 4), round(b.entry_price, 4), round(b.edge, 4),
                round(b.contracts, 4), b.filled, round(b.fee, 4),
                b.actual_total, b.won, round(b.pnl, 4), b.clv_points, b.is_playoff,
            ])


def plot_equity(result: BacktestResult, path: str) -> bool:
    """Equity curve + drawdown. Returns False if matplotlib is unavailable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    eq = result.metrics.equity_curve
    if len(eq) < 2:
        return False

    peaks, dd, peak = [], [], eq[0]
    for v in eq:
        peak = max(peak, v)
        peaks.append(peak)
        dd.append((v - peak) / peak if peak else 0.0)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(eq, linewidth=1.3, color="#1d3557")
    ax1.plot(peaks, linewidth=0.8, color="#adb5bd", linestyle="--", label="peak")
    ax1.set_ylabel("bankroll (units)")
    ax1.set_title(
        f"Meridian backtest — {result.config.start_season}-{result.config.end_season}, "
        f"{result.config.fill_model.value} fills, n={result.metrics.n_filled}"
    )
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    ax2.fill_between(range(len(dd)), dd, 0, color="#6a040f", alpha=0.65)
    ax2.set_ylabel("drawdown")
    ax2.set_xlabel("bet number")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True
