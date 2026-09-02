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


#: Quote lifecycle events recorded on the observation stream (PATIENCE needs
#: the full stream, not just fills).
QUOTE_EVENTS = ("rested", "requoted", "withdrawn", "held",
                "filled_bid", "filled_ask", "none")


class QuoteV2Observation(Base):
    """One QUOTE v2 observation of one market on the quoter's OWN clock.

    The forward observation stream (docs/math/quote-v2-observation-schema.md,
    field set signed off by B 2026-09-02). Written by the v2 quoter at <=1s
    cadence with its OWN stamps — never the recorder's (`market_snapshots`),
    whose cross-process timestamps B's congestion detector forbids and whose
    ~200ms cadence over-fires it. **No order exists behind any row** — the
    quoter still rests the FROZEN v1 policy and this table only RECORDS.
    Recording-only is NOT automatically freeze-safe, though: deploying the
    recording binary replaces the pinned freeze commit (7a3a217), so it ships
    only under a research dated amendment (new pinned commit + policy-
    equivalence replay proof, before the first Sept 17 tip or it waits for A1).
    Landing this model/migration is separate — repo code, off-path.
    Shadow-only, credential-free stays load-bearing.

    What consumes each field: guards + the lateness/state arm read the
    quote-time state snapshot (period/score/margin/minutes_left/clock-quality/
    fv); D1's pregame fold reads `game_start_time`; PATIENCE reads the full
    quote stream (`quote_bid`/`quote_ask`/`quote_event`, unfilled requotes
    included); the congestion arm reads B's detector output (`det_in_window`/
    `det_confirm_t0`, pinned by `det_version`). `character` is NOT stored — it
    is recomputed offline from `(observed_at, mid)` by the frozen A1 classifier,
    so no classifier version is frozen into the table; likewise the raw stream
    (`observed_at`, `best_bid/ask`, `sports_market_type`) lets any congestion
    detector version — including the density-gated v2 — be recomputed offline.

    Standing checks the scorer runs on this table (B sign-off): replay-
    reconciliation (recompute the detector from the raw stream, assert it
    matches the recorded `det_*` per game — makes the recorded columns verified
    provenance) and cadence self-measurement (median/p99 inter-obs gap per game
    from raw, so <=1s compliance is measured not assumed).
    """

    __tablename__ = "quote_v2_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    market_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    sports_market_type: Mapped[str] = mapped_column(String(64), nullable=False)

    #: The QUOTER'S OWN receive stamp — the compliant clock. The detector and
    #: markout run on this, never on a recorder timestamp.
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    #: The upstream recorder snapshot's stamp (`market_snapshots.captured_at`)
    #: carried through as RAW PROVENANCE — NOT venue truth (it is the recorder's
    #: capture time, itself downstream of the venue) and NOT a detector clock.
    #: PINNED CONSUMPTION RULE: the detector and EVERY gate read `observed_at`
    #: ONLY; `source_captured_at` is never fed to the detector — the
    #: recording-integrity replay enforces this structurally (re-instrumenting
    #: the detector on this column diverges from the recorded `det_*` and is
    #: caught). It exists for three reads only: (1) the cross-clock VALIDITY
    #: check — a wrong-clock regression is `observed_at == source_captured_at`
    #: everywhere, which integrity alone cannot see; (2) latency decomposition
    #: `observed_at - source_captured_at` (quoter stall vs upstream silence);
    #: (3) the amendment-9 proxy-validation join key (recorder tape ⋈ quoter
    #: stream on this, not fuzzy price-matching). Cheap now, backfill-impossible
    #: later.
    source_captured_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True))
    best_bid: Mapped[Decimal] = mapped_column(Price, nullable=False)
    best_ask: Mapped[Decimal] = mapped_column(Price, nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ---- quote-time state snapshot (guards, lateness, state) -------------- #
    event_period: Mapped[str | None] = mapped_column(String(32))
    event_score: Mapped[str | None] = mapped_column(String(32))
    margin: Mapped[int | None] = mapped_column(Integer)
    total_so_far: Mapped[int | None] = mapped_column(Integer)
    minutes_left: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    #: Clock quality — a guard trigger (v1-only field on PULSE; here it returns
    #: guards to the arm list per the program's named engineering trigger).
    minutes_left_is_estimate: Mapped[bool | None] = mapped_column(Boolean)
    #: The other guard trigger (guard 2 needs a fair value) and a state input.
    fair_value: Mapped[Decimal | None] = mapped_column(Price)
    #: Pregame hours-to-tip (D1's dead-window fold).
    game_start_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # ---- the full quote stream (PATIENCE) -------------------------------- #
    quote_bid: Mapped[Decimal | None] = mapped_column(Price)
    quote_ask: Mapped[Decimal | None] = mapped_column(Price)
    quote_event: Mapped[str] = mapped_column(String(16), nullable=False,
                                             default="none")

    # ---- congestion detector output (B) ---------------------------------- #
    #: The detector code version (commit) that produced the fields below —
    #: B's pin discipline (a congestion number = code version x substrate).
    det_version: Mapped[str | None] = mapped_column(String(40))
    det_in_window: Mapped[bool | None] = mapped_column(Boolean)
    #: The confirmed trigger's t0 AS A VALUE (not a boolean): the true confirm
    #: instant t0+5s falls between observations, so a boolean could never
    #: byte-match offline replay. NULL when no confirm is tied to this obs.
    det_confirm_t0: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "quote_event in ('rested','requoted','withdrawn','held',"
            "'filled_bid','filled_ask','none')", name="ck_qv2_quote_event"),
        Index("ix_qv2_market_slug", "market_slug"),
        Index("ix_qv2_game_id", "game_id"),
        Index("ix_qv2_event_slug", "event_slug"),
        Index("ix_qv2_observed_at", "observed_at"),
    )
