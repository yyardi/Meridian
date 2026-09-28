"""Price-aware probabilities for the Bitcoin Up-or-Down windows, one definition for backtest and live.

The first iteration asked a model for p_up once per window and bought the side it
favoured at whatever the ask was. The model's probabilities sat within a few cents
of the market's, so 98 % of its fills cost more than its own probability said they
were worth (2026-09-28: 63 fills, -$8.74, mean -3.1c of expected value by the
model's own number). This module is the price-aware half: probabilities that can be
compared with the ask, computed from the same inputs by the backtest
(analysis on Kalshi's KXBTC15M history) and by the live harness, so a threshold
fitted on one is applied to the identical expression on the other.

Inputs, all point-in-time at the decision second t:
    s        the Bitcoin price at t
    strike   the window's price to beat
    tau      seconds to the close
    closes   1-minute closes ending at or before t, oldest first (>= 61 for sigma,
             >= 241 for the volatility ratio)
    mid      the venue's yes mid at t
    frac     fraction of the window elapsed, 0..1

walk_p:  a driftless random walk to the settlement average. The contract settles on
         the 60-second average before the close, which carries a third of that
         minute's variance, so the effective horizon is tau - 40 s (tau / 3 inside
         the last minute).
quant_p: a logistic model on [logit(mid), z, r1, r5, r15, vol ratio, frac] whose
         coefficients are fitted on Kalshi's settled history and stored beside this
         file with their provenance (quant_coef.json). No coefficients -> None, and
         the arms that need it record "no_model".
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

COEF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant_coef.json")


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def tau_eff(tau: float) -> float:
    return tau - 40.0 if tau >= 60 else tau / 3.0


def sigma_1m(closes: list[float], n: int = 60) -> float | None:
    """Std of the last n 1-minute log returns (needs n + 1 closes)."""
    if len(closes) < n + 1:
        return None
    xs = closes[-(n + 1):]
    r = [math.log(xs[i + 1] / xs[i]) for i in range(n)]
    m = sum(r) / n
    v = sum((x - m) ** 2 for x in r) / n
    return math.sqrt(v) if v > 0 else None


@dataclass(frozen=True)
class QuantInputs:
    z: float
    r1: float
    r5: float
    r15: float
    vr: float
    sigma_1m: float


def inputs(s: float, strike: float, tau: float, closes: list[float]) -> QuantInputs | None:
    sig = sigma_1m(closes)
    if sig is None or s <= 0 or strike <= 0 or tau <= 0:
        return None
    z = math.log(s / strike) / ((sig / math.sqrt(60)) * math.sqrt(tau_eff(tau)))

    def ret(n: int) -> float:
        if len(closes) < n + 1:
            return 0.0
        return math.log(s / closes[-(n + 1)]) / (sig * math.sqrt(n))
    vr = 1.0
    if len(closes) >= 241:
        four = closes[-241::4]
        r4 = [math.log(four[i + 1] / four[i]) for i in range(len(four) - 1)]
        m = sum(r4) / len(r4)
        v4 = math.sqrt(sum((x - m) ** 2 for x in r4) / len(r4)) / 2.0
        vr = sig / v4 if v4 > 0 else 1.0
    return QuantInputs(z=z, r1=ret(1), r5=ret(5), r15=ret(15), vr=vr, sigma_1m=sig)


def walk_p(q: QuantInputs) -> float:
    return _phi(q.z)


def vector(q: QuantInputs, mid: float, frac: float) -> list[float]:
    return [logit(mid), q.z, q.r1, q.r5, q.r15, q.vr, frac]


_COEF: dict | None = None


def coefficients(path: str = COEF_PATH) -> dict | None:
    global _COEF
    if _COEF is None and os.path.exists(path):
        with open(path) as fh:
            _COEF = json.load(fh)
    return _COEF


def quant_p(q: QuantInputs, mid: float, frac: float, coef: dict | None = None) -> float | None:
    c = coef if coef is not None else coefficients()
    if not c:
        return None
    x = vector(q, mid, frac)
    t = c["intercept"] + sum(w * v for w, v in zip(c["coef"], x))
    return 1.0 / (1.0 + math.exp(-t))


def fee(p: float, coefficient: float) -> float:
    """The venue's taker fee per contract, rounded up to the cent (the ledger's reading)."""
    return math.ceil(coefficient * p * (1 - p) * 100 - 1e-9) / 100


def edge(p_up: float, yes_ask: float | None, yes_bid: float | None, coefficient: float) -> tuple[str | None, float, float | None]:
    """The better side to BUY at its ask and its expected value per contract under p_up, net
    of the taker fee: YES at the yes ask, NO at 1 - yes bid. (side, ev, price) or (None, best ev, None)."""
    best = (None, -1.0, None)
    if yes_ask is not None and 0 < yes_ask < 1:
        ev = p_up - yes_ask - fee(yes_ask, coefficient)
        best = ("YES", ev, yes_ask)
    if yes_bid is not None and 0 < yes_bid < 1:
        no = 1 - yes_bid
        ev = (1 - p_up) - no - fee(no, coefficient)
        if ev > best[1]:
            best = ("NO", ev, no)
    return best
