"""Run the shadow executor over the latest predictions.

    python -m core.shadow_run

Places nothing. Writes to `shadow_orders` so intentions can later be compared
against what the market actually did.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import defaultdict
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.executor import Executor, ExecutorConfig, OrderSide
from core.kelly_sizing import BasketLeg, size_game_basket
from core.storage import Prediction, ShadowOrder, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc


def run(bankroll: float, dry_run: bool = False) -> int:
    Session = get_sessionmaker(get_engine())
    executor = Executor(ExecutorConfig())   # SHADOW + kill switch on
    written = 0

    with Session() as session:
        latest = session.scalar(select(func.max(Prediction.predicted_at)))
        if latest is None:
            log.warning("no_predictions", hint="run `python -m core.predictions --run`")
            return 0
        preds = session.scalars(
            select(Prediction).where(Prediction.predicted_at == latest)
        ).all()

        games: dict[str, list[tuple[Prediction, BasketLeg]]] = defaultdict(list)
        for p in preds:
            if p.model_probability is None or p.market_ask is None:
                continue
            side = "over" if (p.sports_market_type or "").endswith("total") else ""
            games[p.event_slug or p.market_slug].append((
                p,
                BasketLeg(
                    market_slug=p.market_slug,
                    sports_market_type=p.sports_market_type or "",
                    probability=float(p.model_probability),
                    price=float(p.market_ask),
                    side=side,
                ),
            ))

        for event_slug, entries in games.items():
            sizes = size_game_basket(
                [leg for _, leg in entries], bankroll=bankroll, minimum_trade_qty=0.01
            )
            for pred, leg in entries:
                size = sizes[leg.market_slug]
                decision = executor.decide(
                    market_slug=leg.market_slug,
                    side=OrderSide.BUY,
                    model_probability=leg.probability,
                    size=size,
                    best_bid=float(pred.market_bid) if pred.market_bid is not None else None,
                    best_ask=float(pred.market_ask) if pred.market_ask is not None else None,
                    decided_at=latest,
                )
                executor.execute(decision)   # never places
                if decision.order is None or dry_run:
                    continue

                stmt = pg_insert(ShadowOrder).values(
                    decided_at=latest,
                    idempotency_key=decision.order.idempotency_key,
                    prediction_id=pred.id,
                    market_slug=pred.market_slug,
                    event_slug=pred.event_slug,
                    sports_market_type=pred.sports_market_type,
                    line=pred.line,
                    side=decision.order.side.value,
                    limit_price=decision.order.limit_price,
                    quantity=decision.order.quantity,
                    model_probability=pred.model_probability,
                    market_bid=pred.market_bid,
                    market_ask=pred.market_ask,
                    edge_net=Decimal(str(round(size.edge_net, 6))),
                    would_rest=decision.would_rest,
                    expected_fee=decision.expected_fee,
                    mode=executor.config.mode.value,
                    binding_constraint=size.binding_constraint.value,
                    notes="; ".join(decision.notes) or None,
                ).on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(
                    ShadowOrder.id
                )
                if session.execute(stmt).scalar() is not None:
                    written += 1
        session.commit()

    log.info("shadow_run_complete", predictions=len(preds), shadow_orders=written,
             bankroll=bankroll, placed_real_orders=0)
    return written


def main() -> int:
    p = argparse.ArgumentParser(prog="meridian-shadow")
    p.add_argument("--bankroll", type=float, default=35.68)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    run(args.bankroll, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
