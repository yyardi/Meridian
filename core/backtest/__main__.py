"""Backtest CLI.

    python -m core.backtest                      # default 2024-2026, realistic fills
    python -m core.backtest --all-fill-models    # compare optimistic/realistic/pessimistic
    python -m core.backtest --ab                 # record-modifier A/B
"""

from __future__ import annotations

import argparse
import logging
import sys

import structlog

from core.backtest.engine import BacktestConfig, run_backtest
from core.backtest.fills import FillModel
from core.backtest.report import (
    ABResult,
    format_ab_report,
    format_fill_comparison,
    format_report,
    plot_equity,
    write_csv,
)
from core.storage import get_engine, get_sessionmaker
from strategies.wnba_totals.config import WNBATotalsConfig


def main() -> int:
    p = argparse.ArgumentParser(prog="meridian-backtest")
    p.add_argument("--start", type=int, default=2024)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--min-edge", type=float, default=3.0)
    p.add_argument("--fill", type=str, default="realistic",
                   choices=[m.value for m in FillModel])
    p.add_argument("--all-fill-models", action="store_true")
    p.add_argument("--ab", action="store_true", help="record-modifier A/B")
    p.add_argument("--csv", type=str, default=None)
    p.add_argument("--plot", type=str, default=None)
    p.add_argument("--no-playoffs", action="store_true")
    p.add_argument("--margin", action="store_true",
                   help="backtest spreads and moneylines instead of totals")
    p.add_argument("--assume-maker-rebate", action="store_true",
                   help="sensitivity arm: book the unverified maker rebate (findings C7)")
    args = p.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
    )

    Session = get_sessionmaker(get_engine())

    def cfg(fill: FillModel) -> BacktestConfig:
        return BacktestConfig(
            start_season=args.start, end_season=args.end,
            min_edge_points=args.min_edge, fill_model=fill,
            include_playoffs=not args.no_playoffs,
            assume_maker_rebate=args.assume_maker_rebate,
        )

    with Session() as s:
        if args.margin:
            from core.backtest.margin import (
                MarginBacktestConfig, format_margin_report, run_margin_backtest,
            )
            r = run_margin_backtest(session=s, config=MarginBacktestConfig(
                start_season=args.start, end_season=args.end,
                fill_model=FillModel(args.fill),
                include_playoffs=not args.no_playoffs,
            ))
            print(format_margin_report(r))
            return 0
        if args.all_fill_models:
            results = {m: run_backtest(session=s, config=cfg(m)) for m in FillModel}
            print(format_report(results[FillModel.REALISTIC]))
            print(format_fill_comparison(results))
            main_result = results[FillModel.REALISTIC]
        elif args.ab:
            fill = FillModel(args.fill)
            with_mod = run_backtest(
                session=s, config=cfg(fill),
                model_config=WNBATotalsConfig(record_beta=0.5),
            )
            without = run_backtest(
                session=s, config=cfg(fill),
                model_config=WNBATotalsConfig(record_beta=0.0),
            )
            print(format_report(without))
            print(format_ab_report(ABResult(with_modifier=with_mod, without_modifier=without)))
            main_result = without
        else:
            main_result = run_backtest(session=s, config=cfg(FillModel(args.fill)))
            print(format_report(main_result))

        if args.csv:
            write_csv(main_result, args.csv)
            print(f"\nwrote {args.csv}")
        if args.plot:
            ok = plot_equity(main_result, args.plot)
            print(f"\nwrote {args.plot}" if ok else "\n(matplotlib unavailable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
