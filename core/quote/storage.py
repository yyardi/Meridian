"""Storage for the QUOTE shadow run: one row per simulated fill.

The model lives here, beside its only consumer, rather than in
`core/storage/models.py` — that file was carrying another session's
uncommitted work when this shipped, and editing it would have swept that work
into an unrelated commit (the C12-numbering lesson). Move it there when the
file is clean, if anyone cares; the table is identical either way.

The row is the raw material of the registered measurement
(docs/math/quote-shadow.md): everything needed to score a fill at settlement
(money at price, C11) and to mark it against the static study's numbers
(net capture at the next observation), tagged with the regime and the game so
the clustering (C4) is a query, not a reconstruction.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base

Price = Numeric(6, 4)

PREGAME = "pregame"
INGAME = "ingame"

BID = "bid"
ASK = "ask"


class ShadowQuoteFill(Base):
    """One simulated fill of one resting shadow quote. **No order exists.**

    A filled `bid` is a unit LONG YES position at `quote_price`; a filled
    `ask` is a unit SHORT YES — the NO side, costing `1 − quote_price`
    (V14's frame, applied at scoring time, never stored twice).
    """

    __tablename__ = "shadow_quote_fills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 'pregame' | 'ingame', from the snapshot's is_live at QUOTE BIRTH — a
    #: quote born pregame and filled at tip belongs to the pregame regime,
    #: because pregame is when the decision to rest it was made.
    regime: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)   # 'bid' | 'ask'

    #: The resting price — always the YES frame, like every stored price.
    quote_price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    mid_at_quote: Mapped[Decimal] = mapped_column(Price, nullable=False)
    spread_at_quote: Mapped[Decimal] = mapped_column(Price, nullable=False)
    #: The observation that filled us, for the static-study-comparable mark:
    #: net capture = (mid_at_quote − quote_price) ± (mid_at_fill − mid_at_quote).
    mid_at_fill: Mapped[Decimal] = mapped_column(Price, nullable=False)

    quoted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: 0 | 1 once the market settles (public settlement endpoint, explicit
    #: answers only). NULL = not yet settled — distinct from "asked and
    #: failed", which changes nothing (the fill-watcher lesson).
    settlement: Mapped[int | None] = mapped_column(SmallInteger)
    settled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("regime in ('pregame','ingame')", name="ck_sqf_regime"),
        CheckConstraint("side in ('bid','ask')", name="ck_sqf_side"),
        CheckConstraint("settlement is null or settlement in (0,1)",
                        name="ck_sqf_settlement"),
        Index("ix_sqf_market_slug", "market_slug"),
        Index("ix_sqf_game_id", "game_id"),
        Index("ix_sqf_settlement", "settlement"),
        Index("ix_sqf_filled_at", "filled_at"),
    )
