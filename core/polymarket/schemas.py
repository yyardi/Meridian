"""Pydantic models for the Polymarket US public gateway.

Validation policy, deliberately chosen
--------------------------------------
Fields the recorder genuinely depends on (`slug`, price values) are typed and
validated, so a schema change surfaces as a clear parse error rather than a
silent NULL. Everything else is optional and `extra="allow"`, because the
recorder's dominant failure mode is *dying unattended at 2am* — an unexpected
new field upstream must not take the process down.

Prices arrive as strings ("0.9100"). They are parsed to `Decimal`, never
`float`: the database columns are exact NUMERIC and binary approximation would
defeat the point.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class Quote(BaseModel):
    """A price quote: {"value": "0.9100", "currency": "USD"}."""

    model_config = ConfigDict(extra="allow")

    value: Decimal | None = None
    currency: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _parse(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)


class MarketSide(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    description: str | None = None  # "Over" / "Under" / team name
    price: Decimal | None = None
    long: bool | None = None
    tradable: bool | None = None

    @field_validator("price", mode="before")
    @classmethod
    def _parse(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)


class Market(BaseModel):
    model_config = ConfigDict(extra="allow")

    # The only truly required field: everything keys off the slug.
    slug: str
    id: str | None = None
    question: str | None = None
    sports_market_type: str | None = Field(default=None, alias="sportsMarketType")
    line: Decimal | None = None
    best_bid_quote: Quote | None = Field(default=None, alias="bestBidQuote")
    best_ask_quote: Quote | None = Field(default=None, alias="bestAskQuote")
    order_price_min_tick_size: Decimal | None = Field(
        default=None, alias="orderPriceMinTickSize"
    )
    minimum_trade_qty: Decimal | None = Field(default=None, alias="minimumTradeQty")
    fee_coefficient: Decimal | None = Field(default=None, alias="feeCoefficient")
    game_start_time: str | None = Field(default=None, alias="gameStartTime")
    closed: bool | None = None
    active: bool | None = None
    market_sides: list[MarketSide] = Field(default_factory=list, alias="marketSides")

    @field_validator(
        "line",
        "order_price_min_tick_size",
        "minimum_trade_qty",
        "fee_coefficient",
        mode="before",
    )
    @classmethod
    def _parse(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @property
    def best_bid(self) -> Decimal | None:
        return self.best_bid_quote.value if self.best_bid_quote else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.best_ask_quote.value if self.best_ask_quote else None


class EventState(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: str | None = None
    period: str | None = None
    live: bool | None = None
    ended: bool | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    slug: str | None = None
    title: str | None = None
    start_time: str | None = Field(default=None, alias="startTime")
    # gameId arrives as an int; the DB column is text.
    game_id: str | None = Field(default=None, alias="gameId")
    event_state: EventState | None = Field(default=None, alias="eventState")
    markets: list[Market] = Field(default_factory=list)

    @field_validator("game_id", "id", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> str | None:
        return None if v is None else str(v)

    @property
    def is_live(self) -> bool:
        return bool(self.event_state and self.event_state.live)


class EventsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    events: list[Event] = Field(default_factory=list)


class BookEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    px: Quote
    qty: Decimal | None = None

    @field_validator("qty", mode="before")
    @classmethod
    def _parse(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)


class MarketData(BaseModel):
    model_config = ConfigDict(extra="allow")

    market_slug: str | None = Field(default=None, alias="marketSlug")
    bids: list[BookEntry] = Field(default_factory=list)
    offers: list[BookEntry] = Field(default_factory=list)


class BookResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    market_data: MarketData | None = Field(default=None, alias="marketData")
