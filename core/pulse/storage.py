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
``in_play`` rows are what "decided in-play" counts.

The wiring contract for whoever joins this table into ``/api/game``
(agreed with the tape view's author, 2026-08-18):

* the context chip branches on a boolean ``is_live`` — map
  ``phase == 'in_play'`` to it in the serialiser; the chip stays dumb;
* there is no ``note`` column — the chip tolerates a null note; synthesize
  one from ``reason`` or omit it;
* ``GameDetail.n_live_decisions`` MUST count these rows (phase !=
  'pregame', per event) or the deep-dive banner will call a PULSE game
  pregame-only while rendering its in-play rounds on the same screen.

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
    #: Which estimate set priced this decision ('v1' | 'v2'). Recorded per
    #: row — not per engine mode — so two model generations never blend in a
    #: performance query (the era-separation lesson). A v2-mode engine whose
    #: form refused prices with v1 values and its rows say 'v1'.
    estimates_version: Mapped[str] = mapped_column(
        String(4), nullable=False, default="v1", server_default="v1")

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
    #: SHADOW SIZING SEMANTICS (operator decision, 2026-08-21): in shadow
    #: mode, exposure caps never shrink or block a decision — `contracts`/
    #: `stake_usd` carry the model's FULL desired (fractional-Kelly) size,
    #: and when a cap WOULD have bound in live mode these two carry the
    #: live-faithful capped size (0 when the cap would have blocked
    #: entirely, as the 2026-08-20 daily cap did for two whole games).
    #: NULL = no cap would have bound. The live-faithful subset is these
    #: columns, filterable; caps are evaluated against the shadow book's
    #: exposure (an approximation once sizes diverge — see
    #: docs/math/pulse-live.md's dated note).
    capped_stake_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    capped_contracts: Mapped[Decimal | None] = mapped_column(Qty)
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


class PulseAbstention(Base):
    """One recorded refusal to price: a state the guards would not touch.

    The `binding_constraint` principle applied to pricing (operator ticket,
    2026-09-01): a blocked size is data, and so is a refused state. Rows are
    written by the engine, throttled per (market, guard) like hold rows, so
    a persistent bad state marks itself once a minute instead of at feed
    cadence. `fair_value_raw` carries what the model WOULD have asserted
    when the confidence guard refused (the evidence); the state guard
    refuses before pricing, so there it is NULL. See `core/pulse/guards.py`
    for the checks and their measured tape footprints.
    """

    __tablename__ = "pulse_abstentions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 'implausible_state' | 'unrepresentable_confidence' (guards.py).
    guard: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The guard's own detail string, e.g. 'score_too_high_for_elapsed:...'.
    reason: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- the refused state, as observed ---------------------------------- #
    period: Mapped[str | None] = mapped_column(String(32))
    minutes_left: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    total_so_far: Mapped[int | None] = mapped_column(Integer)
    margin: Mapped[int | None] = mapped_column(Integer)
    line: Mapped[Decimal | None] = mapped_column(Points)
    fair_value_raw: Mapped[Decimal | None] = mapped_column(Price)
    estimates_version: Mapped[str] = mapped_column(String(4), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "guard in ('implausible_state','unrepresentable_confidence')",
            name="ck_pa_guard"),
        Index("ix_pa_event_slug", "event_slug"),
        Index("ix_pa_decided_at", "decided_at"),
    )
