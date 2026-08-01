"""Correlation-aware fractional Kelly sizing with hard guardrails.

Pure functions: inputs -> size. No database, no network, no clock.

Why fractional
--------------
Kelly maximises log wealth **only if the edge estimate is exact**. Ours is
model-derived and, as of the first clean backtest, uncalibrated — realised
outcomes sit near 50% across every predicted-probability bucket
(docs/math/calibration-problem.md).

Kelly is brutally asymmetric to overestimation: betting *twice* the optimal
fraction has **zero** expected growth. So if you think the edge is 10% and it
is really 5%, full Kelly on the wrong number is double Kelly on the right one
— you have wagered the bankroll for nothing. Quarter Kelly keeps ~44% of
theoretical growth for a fraction of the variance, which is the right trade
when the *input* is the uncertain part.

Correlation
-----------
The part most implementations get wrong. Bets on one game are not independent:
moneyline-favourite and Over move together in a blowout, and two same-side
ladder rungs are nearly the same bet. Sizing each at quarter Kelly gives
combined exposure well above quarter Kelly on the underlying risk, so a game
is sized as a **basket**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.backtest.fills import fee_per_contract
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig


class Constraint(str, Enum):
    """Which rule actually determined the size."""

    KELLY = "kelly"
    MIN_EDGE = "min_edge_threshold"
    NEGATIVE_EDGE = "negative_edge"
    MAX_POSITION_PCT = "max_position_size_pct"
    MAX_GAME_PCT = "max_game_exposure_pct"
    MAX_DAILY_PCT = "max_daily_exposure_pct"
    MAX_DOLLARS = "max_position_dollars"
    MIN_BANKROLL = "min_bankroll"
    BELOW_MIN_TRADE_QTY = "below_minimum_trade_qty"


@dataclass(frozen=True)
class PositionSize:
    """A sizing decision, with its reasoning attached."""

    dollars: float
    contracts: float
    kelly_fraction_raw: float          # full Kelly, before the fractional haircut
    kelly_fraction_used: float         # after fractional + all caps
    edge_gross: float
    edge_net: float                    # after fees
    binding_constraint: Constraint
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_tradeable(self) -> bool:
        return self.dollars > 0 and self.contracts > 0


def kelly_fraction(probability: float, price: float) -> float:
    """Full Kelly for a binary contract bought at `price`, paying $1.

        f* = (p - c) / (1 - c)

    Returns 0 for non-positive edge — never a negative (i.e. reversed) bet.
    """
    if not (0.0 < price < 1.0):
        return 0.0
    f = (probability - price) / (1.0 - price)
    return max(0.0, f)


def net_edge(probability: float, price: float, *, is_maker: bool = True) -> float:
    """Edge after fees, in probability terms.

    Sizing on gross edge systematically over-bets. The executor is limit-only,
    so the maker rebate is the default assumption — but a fill that crosses the
    spread becomes a taker, which is worth flagging.
    """
    return (probability - price) - fee_per_contract(price, is_maker=is_maker)


def size_position(
    *,
    probability: float,
    price: float,
    bankroll: float,
    config: WNBATotalsConfig | None = None,
    is_maker: bool = True,
    game_exposure_used: float = 0.0,
    daily_exposure_used: float = 0.0,
    minimum_trade_qty: float = 0.01,
    correlation_haircut: float = 1.0,
) -> PositionSize:
    """Size one position. Kelly is a ceiling; the smallest constraint wins."""
    cfg = config or CONFIG
    notes: list[str] = []

    gross = probability - price
    net = net_edge(probability, price, is_maker=is_maker)
    if not is_maker:
        notes.append("taker fill assumed: crossing the spread costs ~1.5c/contract at p=0.50")

    def _zero(reason: Constraint) -> PositionSize:
        return PositionSize(
            dollars=0.0, contracts=0.0, kelly_fraction_raw=0.0, kelly_fraction_used=0.0,
            edge_gross=gross, edge_net=net, binding_constraint=reason, notes=tuple(notes),
        )

    if bankroll < cfg.min_bankroll:
        notes.append(f"bankroll {bankroll:.2f} below minimum {cfg.min_bankroll:.2f}")
        return _zero(Constraint.MIN_BANKROLL)
    if net <= 0:
        notes.append("no edge after fees")
        return _zero(Constraint.NEGATIVE_EDGE)
    if net < cfg.min_edge_threshold:
        notes.append(
            f"net edge {net:.4f} below threshold {cfg.min_edge_threshold:.4f} "
            "— inside model error"
        )
        return _zero(Constraint.MIN_EDGE)

    # Kelly on the FEE-ADJUSTED probability, so fees shrink the bet.
    adjusted_p = price + net
    raw = kelly_fraction(adjusted_p, price)
    fraction = raw * cfg.kelly_fraction
    binding = Constraint.KELLY

    # Correlation haircut for same-game / same-side exposure.
    if correlation_haircut < 1.0:
        fraction *= correlation_haircut
        notes.append(f"correlation haircut x{correlation_haircut:.2f}")

    # --- guardrails, applied after Kelly ---------------------------- #
    if fraction > cfg.max_position_size_pct:
        fraction = cfg.max_position_size_pct
        binding = Constraint.MAX_POSITION_PCT

    game_room = max(0.0, cfg.max_game_exposure_pct - game_exposure_used)
    if fraction > game_room:
        fraction = game_room
        binding = Constraint.MAX_GAME_PCT

    day_room = max(0.0, cfg.max_daily_exposure_pct - daily_exposure_used)
    if fraction > day_room:
        fraction = day_room
        binding = Constraint.MAX_DAILY_PCT

    dollars = fraction * bankroll
    if dollars > cfg.max_position_dollars:
        dollars = cfg.max_position_dollars
        fraction = dollars / bankroll
        binding = Constraint.MAX_DOLLARS

    contracts = dollars / price if price > 0 else 0.0

    if contracts < minimum_trade_qty:
        notes.append(
            f"size {contracts:.4f} contracts is below the venue minimum "
            f"{minimum_trade_qty} — not tradeable at this bankroll"
        )
        return PositionSize(
            dollars=0.0, contracts=0.0, kelly_fraction_raw=raw, kelly_fraction_used=0.0,
            edge_gross=gross, edge_net=net,
            binding_constraint=Constraint.BELOW_MIN_TRADE_QTY, notes=tuple(notes),
        )

    if bankroll < 100:
        notes.append(
            f"bankroll ${bankroll:.2f}: variance dominates any real edge for a long "
            "time, and Kelly's continuous-fraction assumption is strained by discrete "
            "minimum trade sizes"
        )

    return PositionSize(
        dollars=dollars, contracts=contracts, kelly_fraction_raw=raw,
        kelly_fraction_used=fraction, edge_gross=gross, edge_net=net,
        binding_constraint=binding, notes=tuple(notes),
    )


@dataclass(frozen=True)
class BasketLeg:
    """One candidate position within a game."""

    market_slug: str
    sports_market_type: str
    probability: float
    price: float
    side: str = ""          # e.g. 'over' / 'under', used for ladder correlation


def size_game_basket(
    legs: list[BasketLeg],
    *,
    bankroll: float,
    config: WNBATotalsConfig | None = None,
    daily_exposure_used: float = 0.0,
    minimum_trade_qty: float = 0.01,
) -> dict[str, PositionSize]:
    """Size every leg of one game as a basket, not as independent bets.

    Two correlation effects are applied:

    * **Same-side ladder rungs** (Over 176.5 and Over 179.5) are ~0.95
      correlated — almost literally the same bet.
    * **Different market types** on one game (moneyline vs total) are ~0.5
      correlated.

    Both are conservative fixed assumptions rather than fitted values: ~250
    games/season cannot support a reliable covariance estimate, and a bad
    estimate is more dangerous than an honest constant. The whole game is then
    capped by ``max_game_exposure_pct``.
    """
    cfg = config or CONFIG
    out: dict[str, PositionSize] = {}

    # Best edge first: if the game cap binds, spend it on the strongest leg.
    ordered = sorted(legs, key=lambda leg: leg.probability - leg.price, reverse=True)

    game_used = 0.0
    seen_types: set[str] = set()
    seen_sides: set[tuple[str, str]] = set()

    for leg in ordered:
        haircut = 1.0
        key = (leg.sports_market_type, leg.side)
        if key in seen_sides:
            haircut *= 1.0 - cfg.same_side_ladder_correlation
        elif leg.sports_market_type in seen_types:
            haircut *= 1.0 - cfg.same_game_correlation * 0.5
        elif seen_types:
            haircut *= 1.0 - cfg.same_game_correlation

        size = size_position(
            probability=leg.probability, price=leg.price, bankroll=bankroll,
            config=cfg, game_exposure_used=game_used,
            daily_exposure_used=daily_exposure_used,
            minimum_trade_qty=minimum_trade_qty, correlation_haircut=haircut,
        )
        out[leg.market_slug] = size
        game_used += size.kelly_fraction_used
        seen_types.add(leg.sports_market_type)
        seen_sides.add(key)

    return out
