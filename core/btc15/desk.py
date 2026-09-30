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

import datetime as dt
import json
import math
import sqlite3
import threading
import time
from pathlib import Path

from core.btc15.ledger import DEFAULT_LIMIT_U, UNIT, Ledger
from core.btc15.model import cost_usd
from core.btc15.polymarket import HORIZONS

DEFAULT_DIR = "/opt/meridian/artifacts/btc15"

#: Names the tab shows where an arm's ledger name predates the margin sweep. The ledger
#: file, the API's ``arm=`` key and the checkpoint rule keep the original name.
DISPLAY_NAMES = {"kalshi_taker": "kalshi_taker_2c", "kalshi_taker_wide": "kalshi_taker_4c"}

#: The checkpoint counts fills from this instant on (docs/math/btc15-v2-arms.md). Agreed at
#: 2026-09-29 20:02Z (the trades that chose the arms cannot also confirm them), then moved to
#: 2026-09-30 05:08:42Z, when the arms began pricing off the venue's stream and Kalshi's order
#: book: every fill before it was entered on a quote up to ~30 s old.
CHECKPOINT_FROM = "2026-09-30T05:08:42+00:00"


def paths(root: str | Path, horizon: str) -> tuple[Path, Path]:
    """(ledger, status file) for one instance; the names docker-compose.btc15.yml gives them."""
    if horizon not in HORIZONS:
        raise ValueError(f"horizon {horizon!r}: one of {sorted(HORIZONS)}")
    root = Path(root)
    return root / f"polymarket-{horizon}.sqlite", root / f"status-{horizon}.json"


_ARM_NAME = __import__("re").compile(r"^[a-z0-9_]{1,40}$")


def arm_path(root: str | Path, horizon: str, arm: str) -> Path:
    """One strategy arm's ledger file (core/btc15/harness.arm_db_path's naming)."""
    if not _ARM_NAME.match(arm or ""):
        raise ValueError(f"arm {arm!r}")
    p = Path(root) / f"polymarket-{horizon}-arm-{arm}.sqlite"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p


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
    "LEFT JOIN fills f ON f.ticker = w.ticker AND f.mode = ? AND f.epoch = ? "
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


def summary(root: str | Path, horizon: str, now: float | None = None, arm: str | None = None) -> dict:
    """The tab's header and top panels: the window in play, the selected strategy's call on it,
    its record. ``arm`` None is the model's own ledger (iteration 1's rule); otherwise that arm's.
    The price feed, the lessons and the OpenAI spend always come from the model's ledger."""
    now = time.time() if now is None else now
    db, st = paths(root, horizon)
    status = _status(st, now)
    main_mode = _mode(status)
    main = _ro(db)
    sel = _ro(arm_path(root, horizon, arm)) if arm else main
    mode = "paper" if arm else main_mode
    led = sel
    try:
        a = led.account(mode)
        rec = led.experience(mode, n=0, n_lessons=0)["your_record"]
        cur = led._conn.execute(_ROWS + "WHERE w.open_ts <= ? ORDER BY w.open_ts DESC LIMIT 1",
                                (mode, led.epoch(mode), now)).fetchone()
        cur_row = None if cur is None else _row(cur)
        mcur = main._conn.execute(_ROWS + "WHERE w.open_ts <= ? ORDER BY w.open_ts DESC LIMIT 1",
                                  (main_mode, main.epoch(main_mode), now)).fetchone()
        if arm and mcur is not None and (cur_row is None or cur_row["open_ts"] < mcur["open_ts"]):
            # the arm has not reached the window in play yet: the window, and no call
            cur_row = dict(_row(mcur), decision=None, fill=None)
        spec = _j(led.get("arm_spec")) if arm else None
        last = main._conn.execute("SELECT t, px, n FROM ticks ORDER BY t DESC LIMIT 1").fetchone()
        curve, cum, staked = [], 0, 0
        for r in led._conn.execute(
                "SELECT s.settled_at, s.pnl_u, f.ticker, f.price_u, f.fee_u FROM settlements s JOIN fills f ON f.id = s.fill_id "
                "WHERE f.mode = ? AND f.epoch = ? ORDER BY s.settled_at, f.id", (mode, a["epoch"])):
            cum += r["pnl_u"]
            staked += r["price_u"] + r["fee_u"]
            curve.append({"at": r["settled_at"], "ticker": r["ticker"], "pnl": _usd(r["pnl_u"]), "cum": _usd(cum),
                          "cost": _usd(r["price_u"] + r["fee_u"])})
        counts = {r["status"]: r["n"] for r in led._conn.execute(
            "SELECT status, COUNT(*) n FROM decisions WHERE requested_at >= ? GROUP BY status",
            (led.epoch_from(mode) or "",))}
        # The same selection Ledger.experience hands the model: newest first, twelve.
        lessons = [{"ticker": r["ticker"], "open_ts": r["open_ts"], "close_ts": r["close_ts"], "side": r["side"],
                    "p_up": r["p_up"], "result": r["result"], "lesson": r["lesson"]}
                   for r in main._conn.execute(
                       "SELECT d.ticker, d.side, d.p_up, d.lesson, w.open_ts, w.close_ts, w.result "
                       "FROM decisions d JOIN windows w ON w.ticker = d.ticker WHERE d.lesson IS NOT NULL "
                       "ORDER BY d.requested_at DESC LIMIT 12")]
        spent, spent_total = main.spent(), main.spent_total()
        halted = led.halted(mode)
        ef = led.epoch_from(mode)
        e = edge(led, mode)
    finally:
        led._conn.close()
        if led is not main:
            main._conn.close()
    return {
        "horizon": horizon, "length_s": HORIZONS[horizon], "now": now, "mode": mode, "epoch_from": ef,
        "arm": arm, "arm_label": DISPLAY_NAMES.get(arm, arm) if arm else "v1 favourite (old)", "arm_spec": spec,
        "edge": {k: v for k, v in e.items() if k != "curve"},
        "status": status, "halted": halted,
        "last_tick": None if last is None else {"t": last["t"], "px": last["px"], "exchanges": last["n"]},
        "current": cur_row,
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
            mode: str | None = None, arm: str | None = None) -> list[dict]:
    """Every window the selected strategy saw, newest first: the call, the fill, the settlement."""
    db, st = paths(root, horizon)
    if arm:
        db, mode = arm_path(root, horizon, arm), "paper"
    mode = mode or _mode(_status(st, time.time()))
    led = _ro(db)
    try:
        # this allocation's windows only: from the one in play when the epoch began
        ef = _ts(led.epoch_from(mode))
        floor = -1.0 if ef is None else ef - HORIZONS[horizon]
        rows = led._conn.execute(
            _ROWS + "WHERE w.open_ts < ? AND w.open_ts > ? ORDER BY w.open_ts DESC LIMIT ?",
            (mode, led.epoch(mode), before_ts if before_ts is not None else 1e12, floor,
             max(1, min(int(limit), 500)))).fetchall()
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


# ---------------------------------------------------------------- the edge estimate
def _ts(s: str | None) -> float | None:
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
    except ValueError:
        return None


def _stats(xs: list[float]) -> dict:
    """Mean per contract in cents, its standard error, a 95 % interval and t.

    One contract per window and windows do not overlap, so the trades are treated as
    independent draws; the interval is mean +- 1.96 se with the sample sd (n - 1)."""
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean_c": None, "se_c": None, "lo_c": None, "hi_c": None, "t": None}
    m = sum(xs) / n
    if n < 2:
        return {"n": 1, "mean_c": round(100 * m, 2), "se_c": None, "lo_c": None, "hi_c": None, "t": None}
    se = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) / math.sqrt(n)
    return {"n": n, "mean_c": round(100 * m, 2), "se_c": round(100 * se, 2),
            "lo_c": round(100 * (m - 1.96 * se), 2), "hi_c": round(100 * (m + 1.96 * se), 2),
            "t": round(m / se, 2) if se > 0 else None}


def edge(led: Ledger, mode: str = "paper") -> dict:
    """What each settled contract of this allocation earned, as an estimate of the edge.

    ``all``      realised P&L per contract (payout - price - fee), every settled contract;
    ``since``    the same, counting only fills at or after CHECKPOINT_FROM;
    ``entry_c``  the edge the rule itself claimed when it bought: p(side) - price - fee, with
                 p the probability it traded on (Kalshi's mid for the Kalshi takers, the
                 model's own p_up for the agent). Realised converging to it is the check;
    ``curve``    after each settlement, in order: [settled_ts, n, mean_c, lo_c, hi_c, entry_c].
    """
    a = led.account(mode)
    rows = led._conn.execute(
        "SELECT f.side, f.qty, f.price_u, f.fee_u, f.filled_at, s.pnl_u, s.settled_at, d.p_up "
        "FROM fills f JOIN settlements s ON s.fill_id = f.id LEFT JOIN decisions d ON d.ticker = f.ticker "
        "WHERE f.mode = ? AND f.epoch = ? ORDER BY s.settled_at, f.id", (mode, a["epoch"])).fetchall()
    cut = _ts(CHECKPOINT_FROM)
    pnl, since, entry, curve = [], [], [], []
    s1 = s2 = 0.0
    for r in rows:
        q = max(1, r["qty"] or 1)
        x = r["pnl_u"] / UNIT / q
        pnl.append(x)
        filled = _ts(r["filled_at"])
        if filled is not None and filled >= cut:
            since.append(x)
        if r["p_up"] is not None:
            p_side = r["p_up"] if r["side"] == "YES" else 1 - r["p_up"]
            entry.append(p_side - (r["price_u"] + r["fee_u"]) / UNIT)
        n = len(pnl)
        s1 += x
        s2 += x * x
        m = s1 / n
        se = math.sqrt(max(0.0, (s2 - n * m * m) / (n - 1)) / n) if n > 1 else None
        curve.append([_ts(r["settled_at"]), n, round(100 * m, 2),
                      None if se is None else round(100 * (m - 1.96 * se), 2),
                      None if se is None else round(100 * (m + 1.96 * se), 2),
                      round(100 * sum(entry) / len(entry), 2) if entry else None])
    return {"all": _stats(pnl), "since": _stats(since), "since_from": CHECKPOINT_FROM,
            "entry_c": round(100 * sum(entry) / len(entry), 2) if entry else None, "entry_n": len(entry),
            "curve": curve}


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


def arms(root: str | Path, horizon: str, now: float | None = None, include_v1: bool = False) -> list[dict]:
    """Every running arm: its rule, its record, and what it is doing now. Retired arms'
    ledgers live under <root>/retired/ and are not listed; iteration 1's rule (the model's
    own ledger) is listed only on request -- it is halted and its data feeds the agent."""
    now = time.time() if now is None else now
    db, st = paths(root, horizon)
    out = []
    if include_v1:
        main = _ro(db)
        try:
            mode = _mode(_status(st, now))
            e = edge(main, mode)
            out.append({"name": "favourite", "label": "v1 favourite (old)",
                        "rule": "v1: buys the model's favoured side at the ask, whatever the price",
                        **_book(main, mode), "edge": {k: v for k, v in e.items() if k != "curve"},
                        "edge_curve": e["curve"]})
        finally:
            main._conn.close()
    for f in sorted(Path(root).glob(f"polymarket-{horizon}-arm-*.sqlite")):
        led = _ro(f)
        try:
            spec = _j(led.get("arm_spec"))
            counts = {r["status"]: r["n"] for r in led._conn.execute(
                "SELECT status, COUNT(*) n FROM decisions WHERE requested_at >= ? GROUP BY status",
                (led.epoch_from("paper") or "",))}
            cur = led._conn.execute(
                "SELECT d.ticker, d.status, d.side, d.p_up, d.rationale, w.close_ts FROM decisions d "
                "JOIN windows w ON w.ticker = d.ticker ORDER BY w.open_ts DESC LIMIT 1").fetchone()
            name = spec.get("name") or f.stem.split("-arm-")[-1]
            e = edge(led)
            row = {"name": name, "label": DISPLAY_NAMES.get(name, name), "spec": spec, **_book(led),
                   "edge": {k: v for k, v in e.items() if k != "curve"}, "edge_curve": e["curve"],
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
