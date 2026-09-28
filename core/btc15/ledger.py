"""The ledger: every buy and every settlement, in integer units, and the $10 drawdown guard.

Money never touches a float. A unit is $0.0001 (Kalshi quotes to the deci-cent
near the extremes), so $1.00 = 10,000 units; prices, fees, payouts and P&L are
Python ints computed from the venue's dollar strings through Decimal.

What the database itself refuses (CHECK / UNIQUE, not code paths):

* a fill of more than ONE contract;
* a price outside (0, $1);
* two fills for the same window in the same mode;
* two settlements for the same fill.

The drawdown guard (``can_trade``) is recomputed from the ledger rows on every
call -- there is no running counter to drift. Equity is realized P&L of the
current epoch (settled fills only); its high-water mark starts at zero; an
open fill counts as a total loss until Kalshi settles it. A trade is allowed
only if, with every open fill AND this one losing in full, equity stays
within ``limit`` of its peak. When the next trade alone would breach the limit
(no open fills to wait on), the guard LATCHES: trading in that mode and epoch
stops until an operator starts a new epoch. Predictions continue regardless;
they are data.

Kalshi's quadratic taker fee, as the venue charges it: ceil to the cent of
0.07 x multiplier x contracts x P x (1 - P) dollars.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from decimal import ROUND_CEILING, Decimal

from core.fees import KALSHI_TAKER

UNIT = 10_000                      # units per dollar
DEFAULT_LIMIT_U = 10 * UNIT        # the operator's $10 maximum drawdown
MODES = ("paper", "live")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS ticks(
  t REAL PRIMARY KEY, px REAL NOT NULL, n INTEGER NOT NULL, disp REAL);
CREATE TABLE IF NOT EXISTS windows(
  ticker TEXT PRIMARY KEY, open_time TEXT, close_time TEXT, open_ts REAL, close_ts REAL,
  strike REAL, result TEXT, expiration_value REAL, proxy_open REAL, proxy_close REAL, finalized_at TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  ticker TEXT PRIMARY KEY, requested_at TEXT NOT NULL, answered_at TEXT, model TEXT,
  features TEXT, response TEXT, p_up REAL, side TEXT, confidence TEXT, rationale TEXT,
  status TEXT NOT NULL, error TEXT, latency_s REAL, usage TEXT, lesson TEXT);
CREATE TABLE IF NOT EXISTS fills(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL CHECK(mode IN ('paper','live')),
  epoch INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('YES','NO')),
  qty INTEGER NOT NULL CHECK(qty = 1),
  price_u INTEGER NOT NULL CHECK(price_u > 0 AND price_u < 10000),
  fee_u INTEGER NOT NULL CHECK(fee_u >= 0),
  filled_at TEXT NOT NULL, venue_order_id TEXT, book TEXT,
  UNIQUE(mode, ticker));
CREATE TABLE IF NOT EXISTS settlements(
  fill_id INTEGER PRIMARY KEY REFERENCES fills(id),
  result TEXT NOT NULL, payout_u INTEGER NOT NULL, pnl_u INTEGER NOT NULL, settled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def fee_units(price_u: int, qty: int = 1, multiplier: Decimal = Decimal(1)) -> int:
    """Kalshi quadratic taker fee in units, rounded UP to the cent as the venue does."""
    p = Decimal(price_u) / UNIT
    dollars = Decimal(str(KALSHI_TAKER)) * multiplier * qty * p * (1 - p)
    cents = (dollars * 100).to_integral_value(rounding=ROUND_CEILING)
    return int(cents) * 100


def payout_units(side: str, result: str, price_u: int, qty: int = 1) -> int:
    """$1 per contract on the winning side, nothing on the losing side; a void
    returns the price (the fee is kept as lost -- the conservative reading)."""
    if result not in ("yes", "no"):
        return price_u * qty
    won = (side == "YES" and result == "yes") or (side == "NO" and result == "no")
    return UNIT * qty if won else 0


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ state
    def get(self, key: str, default: str | None = None) -> str | None:
        r = self._conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (key, value))

    def epoch(self, mode: str) -> int:
        return int(self.get(f"epoch_{mode}", "1"))

    def new_epoch(self, mode: str) -> int:
        """Operator action: a fresh $10 allocation. Never called by the harness."""
        e = self.epoch(mode) + 1
        self.put(f"epoch_{mode}", str(e))
        return e

    def halted(self, mode: str) -> dict | None:
        v = self.get(f"halted_{mode}_{self.epoch(mode)}")
        return json.loads(v) if v else None

    # ------------------------------------------------------------------ data
    def add_ticks(self, rows: list[tuple[float, float, int, float]]) -> None:
        if rows:
            with self._lock:
                self._conn.executemany("INSERT OR IGNORE INTO ticks(t,px,n,disp) VALUES(?,?,?,?)", rows)

    def upsert_window(self, m: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO windows(ticker,open_time,close_time,open_ts,close_ts,strike) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET strike=COALESCE(excluded.strike, windows.strike)",
                (m["ticker"], m["open_time"], m["close_time"], m["open_ts"], m["close_ts"], m.get("strike")))

    def set_proxy_open(self, ticker: str, px: float | None) -> None:
        with self._lock:
            self._conn.execute("UPDATE windows SET proxy_open=? WHERE ticker=? AND proxy_open IS NULL", (px, ticker))

    def unfinalized_windows(self, now_ts: float) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM windows WHERE result IS NULL AND close_ts <= ? ORDER BY close_ts", (now_ts,)).fetchall()

    def finalize_window(self, ticker: str, result: str, expiration_value: float | None, proxy_close: float | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE windows SET result=?, expiration_value=?, proxy_close=?, finalized_at=? WHERE ticker=? AND result IS NULL",
                (result, expiration_value, proxy_close, _now_iso(), ticker))

    def recent_results(self, n: int = 12) -> list[str]:
        rows = self._conn.execute(
            "SELECT result FROM windows WHERE result IN ('yes','no') ORDER BY close_ts DESC LIMIT ?", (n,)).fetchall()
        return [r["result"] for r in reversed(rows)]

    # ------------------------------------------------------------------ decisions
    def start_decision(self, ticker: str, model: str | None, features: dict) -> bool:
        """True if this window had no decision yet. A restart never re-decides a window."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO decisions(ticker,requested_at,model,features,status) VALUES(?,?,?,?,'requested')",
                (ticker, _now_iso(), model, json.dumps(features)))
            return cur.rowcount == 1

    def finish_decision(self, ticker: str, **fields) -> None:
        allowed = {"answered_at", "response", "p_up", "side", "confidence", "rationale", "status",
                   "error", "latency_s", "usage", "lesson"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"unknown decision fields {bad}")
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._conn.execute(f"UPDATE decisions SET {cols} WHERE ticker=?", (*fields.values(), ticker))

    def decision(self, ticker: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM decisions WHERE ticker=?", (ticker,)).fetchone()

    # ------------------------------------------------------------------ money
    def account(self, mode: str, epoch: int | None = None) -> dict:
        """Recomputed from rows every time. Units throughout."""
        epoch = self.epoch(mode) if epoch is None else epoch
        rows = self._conn.execute(
            "SELECT f.id, f.price_u, f.fee_u, f.qty, s.pnl_u, s.settled_at FROM fills f "
            "LEFT JOIN settlements s ON s.fill_id = f.id WHERE f.mode=? AND f.epoch=? "
            "ORDER BY (s.settled_at IS NULL), s.settled_at, f.id", (mode, epoch)).fetchall()
        realized = peak = open_cost = 0
        n_open = n_settled = wins = 0
        for r in rows:
            if r["pnl_u"] is None:
                open_cost += r["price_u"] * r["qty"] + r["fee_u"]
                n_open += 1
            else:
                realized += r["pnl_u"]
                peak = max(peak, realized)
                n_settled += 1
                wins += r["pnl_u"] > 0
        return {"mode": mode, "epoch": epoch, "realized_u": realized, "peak_u": peak,
                "drawdown_u": peak - realized, "open_cost_u": open_cost, "open": n_open,
                "settled": n_settled, "wins": wins}

    def can_trade(self, mode: str, next_cost_u: int, limit_u: int = DEFAULT_LIMIT_U) -> tuple[bool, str]:
        with self._lock:
            if self.halted(mode):
                return False, "halted"
            a = self.account(mode)
            if a["peak_u"] - (a["realized_u"] - next_cost_u) > limit_u:
                self.put(f"halted_{mode}_{a['epoch']}", json.dumps(
                    {"at": _now_iso(), "realized_u": a["realized_u"], "peak_u": a["peak_u"],
                     "next_cost_u": next_cost_u, "limit_u": limit_u}))
                return False, "latched: the next trade alone could breach the drawdown limit"
            worst = a["realized_u"] - a["open_cost_u"] - next_cost_u
            if a["peak_u"] - worst > limit_u:
                return False, "waiting: open fills plus this one could breach the drawdown limit"
            return True, "ok"

    def record_fill(self, mode: str, ticker: str, side: str, price_u: int, fee_u: int,
                    limit_u: int = DEFAULT_LIMIT_U, venue_order_id: str | None = None,
                    book: dict | None = None) -> tuple[int | None, str]:
        """Guard and insert under one lock: a fill exists only if the guard passed."""
        with self._lock:
            ok, why = self.can_trade(mode, price_u + fee_u, limit_u)
            if not ok:
                return None, why
            try:
                cur = self._conn.execute(
                    "INSERT INTO fills(mode,epoch,ticker,side,qty,price_u,fee_u,filled_at,venue_order_id,book) "
                    "VALUES(?,?,?,?,1,?,?,?,?,?)",
                    (mode, self.epoch(mode), ticker, side, price_u, fee_u, _now_iso(), venue_order_id,
                     json.dumps(book) if book else None))
            except sqlite3.IntegrityError as e:
                return None, f"refused by the ledger: {e}"
            return cur.lastrowid, "filled"

    def unsettled_fills(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT f.* FROM fills f LEFT JOIN settlements s ON s.fill_id=f.id WHERE s.fill_id IS NULL").fetchall()

    def settle(self, fill_id: int, result: str) -> bool:
        """Idempotent: a fill settles once. Returns True if this call settled it."""
        with self._lock:
            f = self._conn.execute("SELECT * FROM fills WHERE id=?", (fill_id,)).fetchone()
            if f is None:
                raise KeyError(fill_id)
            payout = payout_units(f["side"], result, f["price_u"], f["qty"])
            pnl = payout - f["price_u"] * f["qty"] - f["fee_u"]
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO settlements(fill_id,result,payout_u,pnl_u,settled_at) VALUES(?,?,?,?,?)",
                (fill_id, result, payout, pnl, _now_iso()))
            return cur.rowcount == 1

    # ------------------------------------------------------------------ memory for the model
    def experience(self, mode: str, n: int = 20, n_lessons: int = 12) -> dict:
        rows = self._conn.execute(
            "SELECT d.ticker, d.p_up, d.side, d.confidence, d.features, w.result, w.close_time, "
            "f.price_u, s.pnl_u FROM decisions d JOIN windows w ON w.ticker=d.ticker "
            "LEFT JOIN fills f ON f.ticker=d.ticker AND f.mode=? LEFT JOIN settlements s ON s.fill_id=f.id "
            "WHERE d.p_up IS NOT NULL AND w.result IN ('yes','no') ORDER BY w.close_ts DESC", (mode,)).fetchall()
        n_all = len(rows)
        bm = bk = bb = 0.0
        nb = hits = 0
        recent = []
        for i, r in enumerate(rows):
            y = 1.0 if r["result"] == "yes" else 0.0
            p = r["p_up"]
            hits += (p >= 0.5) == (y == 1.0)
            bm += (p - y) ** 2
            base = (json.loads(r["features"] or "{}").get("baselines") or {})
            mk, br = base.get("market_p_up"), base.get("brownian_p_up")
            if mk is not None and br is not None:
                bk += (mk - y) ** 2
                bb += (br - y) ** 2
                nb += 1
            if i < n:
                recent.append({"closed": r["close_time"], "your_p_up": round(p, 3), "side": r["side"],
                               "confidence": r["confidence"], "market_p_up_then": mk, "result": r["result"],
                               "correct": (p >= 0.5) == (y == 1.0),
                               "entry_price": None if r["price_u"] is None else r["price_u"] / UNIT,
                               "pnl_usd": None if r["pnl_u"] is None else r["pnl_u"] / UNIT})
        lessons = self._conn.execute(
            "SELECT ticker, lesson FROM decisions WHERE lesson IS NOT NULL ORDER BY requested_at DESC LIMIT ?",
            (n_lessons,)).fetchall()
        a = self.account(mode)
        return {
            "your_record": {
                "windows_scored": n_all,
                "hit_rate": None if not n_all else round(hits / n_all, 4),
                "brier_you": None if not n_all else round(bm / n_all, 4),
                "brier_market_mid": None if not nb else round(bk / nb, 4),
                "brier_random_walk": None if not nb else round(bb / nb, 4),
                "pnl_usd_this_allocation": a["realized_u"] / UNIT,
                "drawdown_usd": a["drawdown_u"] / UNIT,
            },
            "recent_calls_newest_first": recent,
            "your_lessons_newest_first": [{"window": r["ticker"], "lesson": r["lesson"]} for r in lessons],
        }
