"""Storage for the PULSE live run: one row per in-game shadow decision.

The model lives here, beside its only writer, following the precedent
`core/quote/storage.py` set — one strategy's raw material next to the engine
that produces it. Fold into `core/storage/models.py` later if anyone cares;
the table is identical either way.

What a row is
-------------
One DECISION of the live loop (`core/pulse/live.py`): an entry the loop chose
to rest, an exit it chose to rest against an open position, or a throttled
hold mark while a position rode. **No order exists behind any row and none
can** — the engine has no import path to the executor or the order client,
pinned by the same AST-level test the quote engine carries.

The tape join
-------------
Rows carry the game tape's own join keys — ``event_slug``, ``market_slug``,
``decided_at`` — plus the same as-of context columns the deep-dive page
renders (score, period, margin, clock estimate), captured AT DECISION TIME
from the observation that triggered the decision, so no as-of lateral join is
needed to render them. ``phase`` marks the seam the tape view labels:
``in_play`` rows are what "decided in-play" counts. The tape's context chip
branches on a boolean ``is_live`` — serialisers map ``phase == 'in_play'`` to
it rather than expecting the view to parse a string.

Prices and frames
-----------------
Every stored price is the YES frame, like every price in this repo (V14).
``side`` is the POSITION's direction: ``yes`` is long YES at ``limit_price``;
``no`` is long NO, costing ``1 − limit_price``. An exit is stored in the same
YES frame — a ``yes`` position exits by resting an ask, a ``no`` position by
resting a bid — so entry and exit prices subtract directly.

Lifecycle columns, updated in place by the engine
-------------------------------------------------
``filled_at``/``mid_at_fill`` when the simulated fill rule triggers (the
study's endpoint rule, optimism and all); ``withdrawn_at`` when the engine
stands the resting order down (edge gone, game over, superseded exit);
``settlement``/``settled_at`` from the public settlement endpoint for filled
entries, explicit 0/1 only — the scoring basis for positions that never
exited (money at price, C11).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.base import Base

Price = Numeric(6, 4)
Qty = Numeric(18, 4)
Points = Numeric(8, 2)

#: Phase marker — the tape seam's vocabulary. The engine only acts in play;
#: the pregame value exists so a decision made against a not-yet-live snapshot
#: is labelled honestly rather than impossibly.
PREGAME = "pregame"
IN_PLAY = "in_play"

ENTER = "enter"
EXIT = "exit"
HOLD = "hold"

#: Position direction, YES frame. `no` costs `1 − limit_price` (V14).
YES = "yes"
NO = "no"

#: Which live estimate drove the decision.
STRAT_WINNER = "winner"
STRAT_TOTAL = "total"
STRAT_SPREAD = "spread"


class PulseDecision(Base):
    """One live shadow decision. **No order exists.**"""

    __tablename__ = "pulse_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    decided_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    game_id: Mapped[str | None] = mapped_column(String(64))
    sports_market_type: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Points)

    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(8), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(3), nullable=False)

    #: The resting price, YES frame always.
    limit_price: Mapped[Decimal] = mapped_column(Price, nullable=False)
    contracts: Mapped[Decimal] = mapped_column(Qty, nullable=False, default=0)
    #: New money committed by THIS decision: entry cost for enters, 0 for
    #: exits and holds (their money entered at the entry row).
    stake_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    #: The real account balance the size was computed against
    #: (core/bankroll.py — stored readings only, the engine never fetches).
    bankroll_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    binding_constraint: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(String(200))
    #: For exit/hold rows: the id of the entry decision they belong to.
    entry_id: Mapped[int | None] = mapped_column(BigInteger)

    # ---- context at decision time (the tape renders these) --------------- #
    score: Mapped[str | None] = mapped_column(String(32))
    #: First team's frame — the frame the YES side is quoted in (V19).
    margin: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[str | None] = mapped_column(String(32))
    minutes_left: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    minutes_left_is_estimate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False)
    total_so_far: Mapped[int | None] = mapped_column(Integer)
    projected_total: Mapped[Decimal | None] = mapped_column(Points)
    total_sigma: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    market_bid: Mapped[Decimal | None] = mapped_column(Price)
    market_ask: Mapped[Decimal | None] = mapped_column(Price)
    #: Model probability for YES at decision time.
    fair_value: Mapped[Decimal | None] = mapped_column(Price)
    #: Net edge at the limit, in the POSITION's own cost frame, after fees.
    edge_net: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))

    # ---- simulated lifecycle, updated in place --------------------------- #
    filled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    mid_at_fill: Mapped[Decimal | None] = mapped_column(Price)
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    #: 0 | 1 once the market settles (public endpoint, explicit answers only).
    settlement: Mapped[int | None] = mapped_column(SmallInteger)
    settled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("phase in ('pregame','in_play')", name="ck_pd_phase"),
        CheckConstraint("action in ('enter','exit','hold')", name="ck_pd_action"),
        CheckConstraint("side in ('yes','no')", name="ck_pd_side"),
        CheckConstraint("strategy in ('winner','total','spread')", name="ck_pd_strategy"),
        CheckConstraint("settlement is null or settlement in (0,1)",
                        name="ck_pd_settlement"),
        Index("ix_pd_event_slug", "event_slug"),
        Index("ix_pd_market_slug", "market_slug"),
        Index("ix_pd_decided_at", "decided_at"),
        Index("ix_pd_entry_id", "entry_id"),
        Index("ix_pd_settlement", "settlement"),
    )
