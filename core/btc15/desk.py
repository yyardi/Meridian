"""Read side of the BTC Up-or-Down harness, for the dashboard's BTC tab.

Everything here opens the harness's SQLite ledger READ-ONLY (``mode=ro``) and
never writes: the api container mounts the ledger directory ``:ro`` and the
harness in its own container stays the only writer. Numbers are the ledger's
own -- the same ``account`` and ``experience`` the harness guards and learns
from -- so the tab cannot disagree with what the bot acts on.

Money in the ledger is integer units of $0.0001; everything returned here is
in dollars.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from core.btc15.ledger import DEFAULT_LIMIT_U, UNIT, Ledger
from core.btc15.model import cost_usd
from core.btc15.polymarket import HORIZONS

DEFAULT_DIR = "/opt/meridian/artifacts/btc15"


def paths(root: str | Path, horizon: str) -> tuple[Path, Path]:
    """(ledger, status file) for one instance; the names docker-compose.btc15.yml gives them."""
    if horizon not in HORIZONS:
        raise ValueError(f"horizon {horizon!r}: one of {sorted(HORIZONS)}")
    root = Path(root)
    return root / f"polymarket-{horizon}.sqlite", root / f"status-{horizon}.json"


def _ro(path: Path) -> Ledger:
    """A Ledger over a read-only connection: its read methods, none of its writes."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    led = Ledger.__new__(Ledger)
    led._conn = conn
    led._lock = threading.RLock()
    return led


def _usd(u: int | None) -> float | None:
    return None if u is None else round(u / UNIT, 4)


def _j(s: str | None) -> dict:
    try:
        return json.loads(s) if s else {}
    except ValueError:
        return {}


def _decision(d: sqlite3.Row | None) -> dict | None:
    if d is None:
        return None
    f = _j(d["features"])
    base, price, market = f.get("baselines") or {}, f.get("price") or {}, f.get("market") or {}
    resp = _j(d["response"])
    usage = _j(d["usage"])
    return {
        "status": d["status"], "error": d["error"], "model": d["model"],
        "requested_at": d["requested_at"], "answered_at": d["answered_at"], "latency_s": d["latency_s"],
        "p_up": d["p_up"], "side": d["side"], "confidence": d["confidence"],
        "rationale": d["rationale"], "key_factors": resp.get("key_factors") or [], "lesson": d["lesson"],
        "market_p_up": base.get("market_p_up"), "random_walk_p_up": base.get("brownian_p_up"),
        "other_venue_p_up": market.get("other_venue_p_up"),
        "btc_at_decision": price.get("btc_usd_now"), "distance_usd": price.get("distance_to_strike_usd"),
        "distance_sigma": price.get("distance_in_sigma_to_close"),
        "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
        "cost_usd": cost_usd(d["model"], usage) if usage else None,
    }


_ROWS = (
    "SELECT w.ticker, w.open_ts, w.close_ts, w.open_time, w.close_time, w.strike, w.result, w.expiration_value, "
    "w.proxy_open, w.proxy_close, d.ticker AS d_ticker, d.requested_at, d.answered_at, d.model, d.features, "
    "d.response, d.p_up, d.side, d.confidence, d.rationale, d.status, d.error, d.latency_s, d.usage, d.lesson, "
    "f.side AS f_side, f.price_u, f.fee_u, f.filled_at, f.epoch, s.payout_u, s.pnl_u, s.settled_at "
    "FROM windows w LEFT JOIN decisions d ON d.ticker = w.ticker "
    "LEFT JOIN fills f ON f.ticker = w.ticker AND f.mode = ? "
    "LEFT JOIN settlements s ON s.fill_id = f.id ")


def _row(r: sqlite3.Row) -> dict:
    fill = None
    if r["price_u"] is not None:
        fill = {"side": r["f_side"], "price": _usd(r["price_u"]), "fee": _usd(r["fee_u"]),
                "cost": _usd(r["price_u"] + r["fee_u"]), "filled_at": r["filled_at"], "epoch": r["epoch"],
                "payout": _usd(r["payout_u"]), "pnl": _usd(r["pnl_u"]), "settled_at": r["settled_at"]}
    return {
        "ticker": r["ticker"], "open_ts": r["open_ts"], "close_ts": r["close_ts"],
        "open_time": r["open_time"], "close_time": r["close_time"],
        "strike": r["strike"], "settle": r["expiration_value"], "result": r["result"],
        "proxy_open": r["proxy_open"], "proxy_close": r["proxy_close"],
        "decision": _decision(r) if r["d_ticker"] else None, "fill": fill,
    }


def _mode(status: dict) -> str:
    m = status.get("mode")
    return m if m in ("paper", "live") else "paper"


def _status(path: Path, now: float) -> dict:
    try:
        s = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"age_s": None}
    try:
        from datetime import datetime
        s["age_s"] = round(now - datetime.fromisoformat(s["at"]).timestamp(), 1)
    except (KeyError, ValueError, TypeError):
        s["age_s"] = None
    return s


def summary(root: str | Path, horizon: str, now: float | None = None) -> dict:
    """The tab's header and top panels: the window in play, the bot's call on it, the book."""
    now = time.time() if now is None else now
    db, st = paths(root, horizon)
    status = _status(st, now)
    mode = _mode(status)
    led = _ro(db)
    try:
        a = led.account(mode)
        rec = led.experience(mode, n=0, n_lessons=0)["your_record"]
        cur = led._conn.execute(_ROWS + "WHERE w.open_ts <= ? ORDER BY w.open_ts DESC LIMIT 1",
                                (mode, now)).fetchone()
        last = led._conn.execute("SELECT t, px, n FROM ticks ORDER BY t DESC LIMIT 1").fetchone()
        curve, cum, staked = [], 0, 0
        for r in led._conn.execute(
                "SELECT s.settled_at, s.pnl_u, f.ticker, f.price_u, f.fee_u FROM settlements s JOIN fills f ON f.id = s.fill_id "
                "WHERE f.mode = ? AND f.epoch = ? ORDER BY s.settled_at, f.id", (mode, a["epoch"])):
            cum += r["pnl_u"]
            staked += r["price_u"] + r["fee_u"]
            curve.append({"at": r["settled_at"], "ticker": r["ticker"], "pnl": _usd(r["pnl_u"]), "cum": _usd(cum),
                          "cost": _usd(r["price_u"] + r["fee_u"])})
        counts = {r["status"]: r["n"] for r in led._conn.execute(
            "SELECT status, COUNT(*) n FROM decisions GROUP BY status")}
        # The same selection Ledger.experience hands the model: newest first, twelve.
        lessons = [{"ticker": r["ticker"], "open_ts": r["open_ts"], "close_ts": r["close_ts"], "side": r["side"],
                    "p_up": r["p_up"], "result": r["result"], "lesson": r["lesson"]}
                   for r in led._conn.execute(
                       "SELECT d.ticker, d.side, d.p_up, d.lesson, w.open_ts, w.close_ts, w.result "
                       "FROM decisions d JOIN windows w ON w.ticker = d.ticker WHERE d.lesson IS NOT NULL "
                       "ORDER BY d.requested_at DESC LIMIT 12")]
        spent, spent_total = led.spent(), led.spent_total()
        halted = led.halted(mode)
    finally:
        led._conn.close()
    return {
        "horizon": horizon, "length_s": HORIZONS[horizon], "now": now, "mode": mode,
        "status": status, "halted": halted,
        "last_tick": None if last is None else {"t": last["t"], "px": last["px"], "exchanges": last["n"]},
        "current": None if cur is None else _row(cur),
        "account": {"epoch": a["epoch"], "pnl": _usd(a["realized_u"]), "peak": _usd(a["peak_u"]),
                    "drawdown": _usd(a["drawdown_u"]), "limit": _usd(DEFAULT_LIMIT_U),
                    "open_cost": _usd(a["open_cost_u"]), "open": a["open"], "settled": a["settled"],
                    "wins": a["wins"],
                    # Return on what the settled contracts cost (price + fee): P&L / staked.
                    "staked": _usd(staked),
                    "roi": None if not staked else round(a["realized_u"] / staked, 4)},
        "record": rec, "decision_counts": counts, "pnl_curve": curve, "lessons": lessons,
        "openai": {"today": spent, "total": spent_total,
                   "cap_usd": (status.get("openai_today") or {}).get("cap_usd")},
    }


def history(root: str | Path, horizon: str, limit: int = 100, before_ts: float | None = None,
            mode: str | None = None) -> list[dict]:
    """Every window, newest first: the call, the fill, the settlement, the lesson."""
    db, st = paths(root, horizon)
    mode = mode or _mode(_status(st, time.time()))
    led = _ro(db)
    try:
        rows = led._conn.execute(
            _ROWS + "WHERE w.open_ts < ? ORDER BY w.open_ts DESC LIMIT ?",
            (mode, before_ts if before_ts is not None else 1e12, max(1, min(int(limit), 500)))).fetchall()
    finally:
        led._conn.close()
    return [_row(r) for r in rows]


def ticks(root: str | Path, horizon: str, since_ts: float, points: int = 1200) -> dict:
    """The composite BTC price since ``since_ts``, at most ``points`` samples (last price per bucket),
    and the windows that overlap it, for the chart's strike lines and decision marks."""
    db, _ = paths(root, horizon)
    led = _ro(db)
    try:
        span = max(1.0, time.time() - since_ts)
        step = max(1, int(span // max(points, 1)))
        # SQLite returns the bare column from the row holding MAX(t): the last price in the bucket.
        px = [[round(r[0], 3), r[1]] for r in led._conn.execute(
            "SELECT MAX(t), px FROM ticks WHERE t >= ? GROUP BY CAST(t / ? AS INTEGER) ORDER BY 1",
            (since_ts, step))]
        wins = [{"ticker": r["ticker"], "open_ts": r["open_ts"], "close_ts": r["close_ts"], "strike": r["strike"],
                 "result": r["result"], "settle": r["expiration_value"], "side": r["side"], "p_up": r["p_up"],
                 "status": r["status"], "answered_at": r["answered_at"]}
                for r in led._conn.execute(
                    "SELECT w.ticker, w.open_ts, w.close_ts, w.strike, w.result, w.expiration_value, "
                    "d.side, d.p_up, d.status, d.answered_at FROM windows w LEFT JOIN decisions d "
                    "ON d.ticker = w.ticker WHERE w.close_ts > ? ORDER BY w.open_ts", (since_ts,))]
    finally:
        led._conn.close()
    return {"step_s": step, "px": px, "windows": wins}


# ---------------------------------------------------------------- the strategy arms
def _book(led: Ledger, mode: str = "paper") -> dict:
    a = led.account(mode)
    r = led._conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(f.price_u + f.fee_u), 0) staked, "
        "COALESCE(SUM(CASE WHEN s.pnl_u > 0 THEN 1 ELSE 0 END), 0) wins "
        "FROM fills f JOIN settlements s ON s.fill_id = f.id WHERE f.mode = ? AND f.epoch = ?",
        (mode, a["epoch"])).fetchone()
    staked = r["staked"]
    return {"pnl": _usd(a["realized_u"]), "staked": _usd(staked), "settled": r["n"], "wins": r["wins"],
            "roi": None if not staked else round(a["realized_u"] / staked, 4), "open": a["open"],
            "drawdown": _usd(a["drawdown_u"]), "halted": led.halted(mode) is not None}


def arms(root: str | Path, horizon: str, now: float | None = None) -> list[dict]:
    """Every arm beside the model's own ledger: its rule, its record, and what it is doing now."""
    now = time.time() if now is None else now
    db, st = paths(root, horizon)
    out = []
    main = _ro(db)
    try:
        out.append({"name": "favourite", "rule": "v1: buys the model's favoured side at the ask, whatever the price",
                    **_book(main, _mode(_status(st, now)))})
    finally:
        main._conn.close()
    for f in sorted(Path(root).glob(f"polymarket-{horizon}-arm-*.sqlite")):
        led = _ro(f)
        try:
            spec = _j(led.get("arm_spec"))
            counts = {r["status"]: r["n"] for r in led._conn.execute("SELECT status, COUNT(*) n FROM decisions GROUP BY status")}
            cur = led._conn.execute(
                "SELECT d.ticker, d.status, d.side, d.p_up, d.rationale, w.close_ts FROM decisions d "
                "JOIN windows w ON w.ticker = d.ticker ORDER BY w.open_ts DESC LIMIT 1").fetchone()
            row = {"name": spec.get("name") or f.stem.split("-arm-")[-1], "spec": spec, **_book(led),
                   "declined": counts.get("no_edge", 0) + counts.get("expired", 0), "counts": counts,
                   "now": None if cur is None or cur["close_ts"] < now else
                   {"status": cur["status"], "side": cur["side"], "p": cur["p_up"], "note": cur["rationale"]}}
        finally:
            led._conn.close()
        out.append(row)
    return out


# ---------------------------------------------------------------- the live book
_BOOK: dict[str, tuple[float, dict | None]] = {}
_BOOK_TTL_S = 4.0


def live_book(horizon: str, venue=None, now: float | None = None) -> dict | None:
    """The venue's book for the window in play, cached a few seconds so a page
    left open polls the venue at most once per TTL, whatever its refresh rate."""
    now = time.time() if now is None else now
    hit = _BOOK.get(horizon)
    if hit and now - hit[0] < _BOOK_TTL_S:
        return hit[1]
    if venue is None:
        from core.btc15.polymarket import PolymarketBTC
        venue = PolymarketBTC(horizon=horizon)
    try:
        m = venue.current(now)
    except Exception:                                            # noqa: BLE001 -- a venue hiccup is "no book"
        m = None
    out = None if m is None else {k: m.get(k) for k in (
        "ticker", "yes_bid", "yes_ask", "no_bid", "no_ask", "yes_bid_size", "yes_ask_size",
        "last_price", "strike", "open_ts", "close_ts", "book_state")}
    _BOOK[horizon] = (now, out)
    return out
