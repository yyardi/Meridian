"""The feature set the model reads, built only from data observable at the decision instant.

Pure functions over the composite's 1 Hz series and Coinbase candles. Every
feature is named in plain words and carries its unit in the name (``_bp`` =
basis points, ``_s`` = seconds, ``_usd`` = dollars), because the reader is a
language model and a bare number is a guess.

Two baselines ride along so the scorecard can tell a model from a coin:

* ``market_p_up``   -- Kalshi's own mid for YES at the decision instant;
* ``brownian_p_up`` -- a driftless random walk from here to the settlement
  average: z = ln(S/K) / (sigma * sqrt(tau_eff)), P = Phi(z), where tau_eff
  shortens the remaining time by the averaging window (the contract settles
  on the MEAN of the last 60 s, whose variance is that of a walk 40 s shorter).
"""
from __future__ import annotations

import datetime as dt
import math
import statistics


def _lr(a: float, b: float) -> float:
    return math.log(b / a) if a > 0 and b > 0 else 0.0


def ema_series(xs: list[float], n: int) -> list[float]:
    if not xs:
        return []
    k = 2.0 / (n + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder's RSI on the last closes; None without n+1 closes."""
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        d = b - a
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def macd(closes: list[float]) -> tuple[float, float, float] | None:
    if len(closes) < 35:
        return None
    line = [a - b for a, b in zip(ema_series(closes, 12), ema_series(closes, 26))]
    signal = ema_series(line, 9)
    return line[-1], signal[-1], line[-1] - signal[-1]


def bollinger(closes: list[float], n: int = 20, k: float = 2.0) -> tuple[float, float] | None:
    """(%B, bandwidth as a fraction of the middle band)."""
    if len(closes) < n:
        return None
    w = closes[-n:]
    mid = sum(w) / n
    sd = statistics.pstdev(w)
    if sd == 0:
        return 0.5, 0.0
    up, lo = mid + k * sd, mid - k * sd
    return (closes[-1] - lo) / (up - lo), (up - lo) / mid


def atr(bars: list[tuple], n: int = 14) -> float | None:
    """Average true range over bars (t, low, high, open, close, vol)."""
    if len(bars) < n + 1:
        return None
    trs = []
    for prev, b in zip(bars[:-1], bars[1:]):
        trs.append(max(b[2] - b[1], abs(b[2] - prev[4]), abs(b[1] - prev[4])))
    return sum(trs[-n:]) / n


def stoch_k(bars: list[tuple], n: int = 14) -> float | None:
    if len(bars) < n:
        return None
    w = bars[-n:]
    lo, hi = min(b[1] for b in w), max(b[2] for b in w)
    return 50.0 if hi == lo else 100.0 * (w[-1][4] - lo) / (hi - lo)


def realized_vol_bp(closes: list[float]) -> float | None:
    """Standard deviation of per-bar log returns, in basis points."""
    if len(closes) < 3:
        return None
    rs = [_lr(a, b) for a, b in zip(closes[:-1], closes[1:])]
    return 1e4 * statistics.pstdev(rs)


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def brownian_p_up(px: float, strike: float, sigma_1m_bp: float | None, tau_s: float) -> float | None:
    """P(settlement average >= strike) under a driftless walk from here."""
    if not sigma_1m_bp or px <= 0 or strike <= 0:
        return None
    tau_eff = tau_s - 40.0 if tau_s >= 60 else tau_s / 3.0
    if tau_eff <= 0:
        return 1.0 if px >= strike else 0.0
    sigma_s = (sigma_1m_bp / 1e4) / math.sqrt(60.0)
    z = math.log(px / strike) / (sigma_s * math.sqrt(tau_eff))
    return phi(z)


def _px_ago(secs: list[tuple[float, float]], now: float, ago: float) -> float | None:
    """Last composite at or before now - ago."""
    target = now - ago
    best = None
    for t, px in secs:
        if t <= target:
            best = px
        else:
            break
    return best


def _r(round_to: int, x):
    return None if x is None else round(x, round_to)


def build(*, now: float, secs: list[tuple[float, float]], c1m: list, c5m: list, c1h: list,
          market: dict, quotes: dict, funding: dict | None, recent_results: list[str]) -> dict:
    """Every input must already be restricted to data at or before ``now``."""
    c1m = [b for b in c1m if b[0] <= now]
    c5m = [b for b in c5m if b[0] <= now]
    c1h = [b for b in c1h if b[0] <= now]
    secs = [s for s in secs if s[0] <= now]
    px = secs[-1][1] if secs else (c1m[-1][4] if c1m else None)
    strike = market.get("strike")
    open_t, close_t = market["open_ts"], market["close_ts"]
    tau = close_t - now

    closes1 = [b[4] for b in c1m]
    closes5 = [b[4] for b in c5m]
    closes60 = [b[4] for b in c1h]

    def ret_bp(ago_s: float):
        ref = _px_ago(secs, now, ago_s)
        if ref is None and c1m:
            k = int(round(ago_s / 60.0))
            ref = closes1[-1 - k] if 0 < k < len(closes1) else None
        return None if (ref is None or px is None) else 1e4 * _lr(ref, px)

    sig1 = realized_vol_bp(closes1[-61:])
    sig1_4h = realized_vol_bp(closes1[-241:])
    vwap60 = None
    if len(c1m) >= 60:
        v = sum(b[5] for b in c1m[-60:])
        if v > 0:
            vwap60 = sum(((b[1] + b[2] + b[4]) / 3.0) * b[5] for b in c1m[-60:]) / v
    e9, e21, e55 = (ema_series(closes1, n)[-1] if len(closes1) >= n else None for n in (9, 21, 55))
    m = macd(closes1)
    bb = bollinger(closes1)
    yes_bid, yes_ask = market.get("yes_bid"), market.get("yes_ask")
    market_p = (yes_bid + yes_ask) / 2.0 if (yes_bid is not None and yes_ask is not None) else None
    mids = {k: q.mid for k, q in quotes.items() if now - q.t <= 5.0}
    et = dt.datetime.fromtimestamp(now, dt.timezone.utc) - dt.timedelta(hours=4)
    streak = 0
    for r in reversed(recent_results):
        if recent_results and r == recent_results[-1]:
            streak += 1
        else:
            break

    return {
        "window": {
            "ticker": market["ticker"],
            "length_s": round(close_t - open_t),
            "seconds_since_open": round(now - open_t, 1),
            "seconds_to_close": round(tau, 1),
            "strike_usd": strike,
        },
        "price": {
            "btc_usd_now": _r(2, px),
            "distance_to_strike_usd": _r(2, None if (px is None or strike is None) else px - strike),
            "distance_to_strike_bp": _r(2, None if (px is None or not strike) else 1e4 * _lr(strike, px)),
            "distance_in_sigma_to_close": _r(3, None if (px is None or not strike or not sig1 or tau <= 0)
                                             else (1e4 * _lr(strike, px)) / (sig1 * math.sqrt(max(tau, 1) / 60.0))),
            "return_10s_bp": _r(2, ret_bp(10)), "return_30s_bp": _r(2, ret_bp(30)),
            "return_1m_bp": _r(2, ret_bp(60)), "return_3m_bp": _r(2, ret_bp(180)),
            "return_5m_bp": _r(2, ret_bp(300)), "return_15m_bp": _r(2, ret_bp(900)),
            "return_30m_bp": _r(2, ret_bp(1800)), "return_60m_bp": _r(2, ret_bp(3600)),
            "return_4h_bp": _r(2, 1e4 * _lr(closes5[-49], px) if (px and len(closes5) >= 49) else None),
            "return_24h_bp": _r(2, 1e4 * _lr(closes60[-25], px) if (px and len(closes60) >= 25) else None),
            "exchange_mids_usd": {k: round(v, 2) for k, v in sorted(mids.items())},
            "exchange_dispersion_usd": _r(2, (max(mids.values()) - min(mids.values())) if mids else None),
        },
        "volatility": {
            "realized_1m_bp_last_60m": _r(3, sig1),
            "realized_1m_bp_last_4h": _r(3, sig1_4h),
            "vol_ratio_1h_over_4h": _r(3, (sig1 / sig1_4h) if (sig1 and sig1_4h) else None),
            "realized_5m_bp_last_24h": _r(3, realized_vol_bp(closes5[-289:])),
            "atr_1m_usd": _r(2, atr(c1m)),
            "range_last_15m_usd": _r(2, (max(b[2] for b in c1m[-15:]) - min(b[1] for b in c1m[-15:])) if len(c1m) >= 15 else None),
        },
        "technical_1m": {
            "rsi_14": _r(2, rsi(closes1)),
            "ema9_minus_price_bp": _r(2, 1e4 * _lr(px, e9) if (e9 and px) else None),
            "ema21_minus_price_bp": _r(2, 1e4 * _lr(px, e21) if (e21 and px) else None),
            "ema55_minus_price_bp": _r(2, 1e4 * _lr(px, e55) if (e55 and px) else None),
            "ema9_minus_ema21_bp": _r(2, 1e4 * _lr(e21, e9) if (e9 and e21) else None),
            "macd_line_usd": _r(3, m[0] if m else None), "macd_signal_usd": _r(3, m[1] if m else None),
            "macd_hist_usd": _r(3, m[2] if m else None),
            "bollinger_pct_b": _r(3, bb[0] if bb else None), "bollinger_width": _r(5, bb[1] if bb else None),
            "stochastic_k_14": _r(2, stoch_k(c1m)),
            "vwap_60m_minus_price_bp": _r(2, 1e4 * _lr(px, vwap60) if (vwap60 and px) else None),
            "volume_last_5m_over_60m_avg": _r(3, (sum(b[5] for b in c1m[-5:]) / 5.0) / (sum(b[5] for b in c1m[-60:]) / 60.0)
                                             if len(c1m) >= 60 and sum(b[5] for b in c1m[-60:]) > 0 else None),
        },
        "technical_5m": {
            "rsi_14": _r(2, rsi(closes5)),
            "ema9_minus_ema21_bp": _r(2, 1e4 * _lr(ema_series(closes5, 21)[-1], ema_series(closes5, 9)[-1]) if len(closes5) >= 21 else None),
            "bollinger_pct_b": _r(3, (bollinger(closes5) or (None,))[0]),
        },
        "technical_1h": {
            "rsi_14": _r(2, rsi(closes60)),
            "ema9_minus_ema21_bp": _r(2, 1e4 * _lr(ema_series(closes60, 21)[-1], ema_series(closes60, 9)[-1]) if len(closes60) >= 21 else None),
        },
        "market": {
            "yes_bid": yes_bid, "yes_ask": yes_ask, "no_bid": market.get("no_bid"), "no_ask": market.get("no_ask"),
            "yes_bid_size": market.get("yes_bid_size"), "yes_ask_size": market.get("yes_ask_size"),
            "last_price": market.get("last_price"), "volume_usd": market.get("volume"),
            # the same window on the other venue (Kalshi KXBTC15M settles on the same BRTI averages)
            "other_venue_p_up": market.get("reference_p_up"),
            "other_venue_strike_usd": market.get("reference_strike"),
        },
        "context": {
            "hour_et": et.hour, "minute_et": et.minute, "weekday_et": et.strftime("%A"),
            "funding_rate_okx_8h": None if not funding else funding.get("rate"),
            "last_8_window_results": recent_results[-8:],
            "current_result_streak": streak,
        },
        "baselines": {
            "market_p_up": _r(4, market_p),
            "brownian_p_up": _r(4, brownian_p_up(px or 0.0, strike or 0.0, sig1, tau)),
        },
    }
