"""Coin Race incentive farming, LIVE PAPER: the registered live-step policy run against the real
book and the real prints with nothing placed -- what we would have been paid and what we would have
lost, per market-window. The operator's "test it algorithmically before any money" step; its read is
registered in docs/math/coinrace-research.md ("Registered read: the live paper farming arm").

Policy (docs/math/kalshi-incentive-farming.md, "The live step"), KXCRYPTOLEAD15M only. On each
market, each side (YES bid, NO bid) rests SIZE (1,000) one tick in front of that side's best bid,
while that price is <= CAP (10c) and does not cross (our YES bid + the best NO bid < $1, likewise
for NO). With our 1,000 at the top the side's term-sheet reference IS our price, so "price <= 10c" is
"reference <= 10c"; a side above it carries no quote. Re-priced on every book change, so we stay one
tick in front; pulled at T-60 s; no refill after a fill (at most 1,000 filled per side per window).
A side that cannot be one tick in front without crossing rests nothing: joining the best would put
us behind its queue, which the fill rule below does not model.

Each second of a market's program period:
  (a) reward = our term-sheet share at our price with the size still resting
      (lip_scorer.share_qualifying(price=), improve=True's walk), per side, x 1/2 (a snapshot score
      is yes share + no share, max 2) x the period reward per second ($20 / 900 s), only on seconds
      the scorer counts: both sides' incumbent depth >= the Target Size;
  (b) fills from the TRADE channel: a taker selling into a side's bids (taker_side 'no' -> the YES
      bids at yes_price; 'yes' -> the NO bids at no_price) at a price <= our bid fills us FIRST, at
      OUR price, up to the remaining size, because we are alone one tick in front. A print's own book
      delta can arrive before the print and move our quote down first, so a print is tested against
      the highest price our quote held in the last LOOKBACK_S (1 s); fills that needed it carry
      via_lookback = 1.
After the window settles (public REST /markets/{ticker}, status settled/finalized), each fill settles
at value - p (YES) or (1 - value) - p (NO) per contract (a two-coin tie settles 0.5). Makers pay no
fee on this series (fee_type quadratic charges takers).

What paper cannot see: anyone RESPONDING to our quote (we are invisible: nobody steps in front of
us, the takers' flow is unchanged), and fills at our price are INFERRED from prints at or below it.
`book_at_us_*` counts incumbents' bids arriving at or above our price -- placed without seeing us,
so it is not the response; the live step exists to measure that. Socket gaps lose prints: at
settlement each market's full public tape is compared with what the socket delivered
(prints_rest / prints_missed / missed_fillable), so a lost print is a counted number. Program reloads
that change the subscription are deferred to the dead zone after T-60 s (everything pulled) and
before the next window opens, so the routine socket restart cannot lose a print that could fill us.

Ledger: SQLite (`windows`, `fills`, `settlements`, `quotes` sampled once a minute with the number of
re-prices since the last sample); accumulators live in ONE Farm for the life of the process and are
restored from `windows` on restart (the Scorer.adopt defect cannot recur: a reload never makes a
fresh accumulator). Status JSON every minute. Quote samples keep 3 days; the ledger keeps 7, so the
3-day registered read is never pruned under itself.

    python -m core.kalshi.farm_paper                 # the service
    python -m core.kalshi.farm_paper --read          # the registered read on /data/farm_paper.sqlite
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import logging
import math
import os
import queue
import sqlite3
import sys
import threading
import time

import httpx

from core.kalshi.lip_scorer import (
    REST,
    Books,
    BookSocket,
    choose_programs,
    load_programs,
    share_qualifying,
    wait_for_programs,
    write_status,
)

log = logging.getLogger("farm_paper")

SERIES = "KXCRYPTOLEAD15M"
CHANNELS = ("orderbook_delta", "trade")
SIDES = ("yes", "no")
SETTLE_FIRST_S = 45.0          # the venue settled Coin Race ~37 s after close (10-07 05:15Z market)
SETTLE_EVERY_S = 60.0
SETTLE_GIVE_UP_S = 6 * 3600.0
QUIET_MARGIN_S = 20.0          # no socket restart within this many seconds of a window opening

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS windows(ticker TEXT PRIMARY KEY, series TEXT, coin TEXT, start_ts REAL, end_ts REAL, reward_per_s REAL,
  target REAL, discount REAL, first_tick REAL, seconds INTEGER, valid INTEGER, reward_usd REAL, reward_yes REAL, reward_no REAL,
  quoted_yes INTEGER, quoted_no INTEGER, reprices_yes INTEGER, reprices_no INTEGER, book_at_us_yes INTEGER, book_at_us_no INTEGER,
  reasons TEXT, prints_socket INTEGER, fill_qty_yes REAL, fill_qty_no REAL, fill_cost_usd REAL, status TEXT,
  result TEXT, settlement_value REAL, fill_pnl REAL, settled_at REAL, prints_rest INTEGER, prints_missed INTEGER,
  missed_fillable REAL, audit TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS fills(t REAL, ticker TEXT, side TEXT, price_c INTEGER, qty REAL, print_c INTEGER, print_qty REAL,
  trade_id TEXT, ts_ms INTEGER, via_lookback INTEGER, PRIMARY KEY(ticker, side, trade_id));
CREATE TABLE IF NOT EXISTS settlements(ticker TEXT, side TEXT, qty REAL, avg_price REAL, settlement_value REAL, pnl_usd REAL,
  settled_at REAL, PRIMARY KEY(ticker, side));
CREATE TABLE IF NOT EXISTS quotes(t REAL, ticker TEXT, side TEXT, price_c INTEGER, remaining REAL, best_c INTEGER, opp_best_c INTEGER,
  reason TEXT, reprices INTEGER, PRIMARY KEY(t, ticker, side));
CREATE INDEX IF NOT EXISTS fills_t ON fills(t);
CREATE INDEX IF NOT EXISTS windows_end ON windows(end_ts);
"""


# ------------------------------------------------------------------ the policy, the fill rule, settlement (pure)
def cents(x) -> int | None:
    """A venue dollar string ('0.0400') as integer cents; prices are compared on the tick grid, never as floats."""
    return None if x is None or x == "" else round(float(x) * 100)


def front_quote(best_c: int | None, opp_best_c: int | None, remaining: float, now: float, end_ts: float,
                cap_c: int = 10, pull_s: float = 60.0) -> tuple[int | None, str]:
    """Our bid on one side, in cents, and why: one tick in front of the side's best bid; none at or
    after T - pull_s, once the size is filled, on an empty side, above the cap, or when one tick in
    front would cross the opposite side's best bid (our bid + theirs must stay under 100c)."""
    if now >= end_ts - pull_s:
        return None, "pulled"
    if remaining <= 0:
        return None, "filled"
    if best_c is None:
        return None, "no_bid"
    p = best_c + 1
    if p > cap_c:
        return None, "above_cap"
    if opp_best_c is not None and p + opp_best_c >= 100:
        return None, "would_cross"
    return p, "front"


def fills_us(print_c: int, quote_c: int) -> bool:
    """A taker selling into our side at or below our bid would have met our bid first."""
    return print_c <= quote_c


def side_hit(taker_side: str | None) -> str | None:
    """The side whose BIDS a print fills: the taker bought NO -> a resting YES bid was hit (at yes_price),
    and vice versa (docs/math/coinrace-research.md, "What a print fills", checked against the book)."""
    return {"no": "yes", "yes": "no"}.get(taker_side or "")


def fill_pnl(side: str, price_c: int, qty: float, value: float) -> float:
    """Settlement P&L in dollars of qty contracts bought at price_c on ``side``; value = the YES settlement (1, 0, 0.5 on a tie)."""
    v = value if side == "yes" else 1.0 - value
    return qty * (v - price_c / 100.0)


def settlement_value(market: dict) -> float | None:
    """The YES settlement of a /markets/{ticker} answer once the venue has settled it, else None."""
    if (market.get("status") or "") not in ("settled", "finalized"):
        return None
    v = market.get("settlement_value_dollars")
    if v not in (None, ""):
        return float(v)
    return {"yes": 1.0, "no": 0.0}.get(market.get("result") or "")


def iso_ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ------------------------------------------------------------------ books that also route prints
class FarmBooks(Books):
    """lip_scorer.Books plus the trade channel: every applied book message re-prices that market's
    quote; every print goes to the Farm's fill rule, in the socket thread, at receipt."""

    def __init__(self) -> None:
        super().__init__()
        self.farm: Farm | None = None
        self.trades = 0

    def handle(self, msg: dict, now: float) -> str | None:
        t = msg.get("type")
        if t == "trade":
            self.trades += 1
            if self.farm is not None:
                self.farm.on_trade(msg.get("msg") or {}, now)
            return None
        out = super().handle(msg, now)
        if out is None and t in ("orderbook_snapshot", "orderbook_delta") and self.farm is not None:
            tk = (msg.get("msg") or {}).get("market_ticker")
            if tk:
                self.farm.on_book(tk, now)
        return out

    def best_c(self, ticker: str, side: str) -> int | None:
        with self._lock:
            b = self.levels.get(ticker, {}).get(side) or {}
            return round(max(b) * 100) if b else None

    def forget(self, ticker: str) -> None:
        with self._lock:
            self.levels.pop(ticker, None)


# ------------------------------------------------------------------ one market-window's state
class MW:
    def __init__(self, ticker: str, p: dict, size: float) -> None:
        self.ticker, self.series = ticker, p.get("series") or ticker.split("-")[0]
        self.coin = ticker.rsplit("-", 1)[-1]
        self.start_ts, self.end_ts = float(p["start_ts"]), float(p["end_ts"])
        self.reward_per_s = float(p["per_day_usd"]) / 86400.0
        self.target, self.discount = float(p["target"]), float(p["discount"])
        self.first_tick: float | None = None
        self.seconds = self.valid = self.prints = 0
        self.reward = 0.0
        self.rs = {"yes": 0.0, "no": 0.0}
        self.quoted = {"yes": 0, "no": 0}
        self.reprices = {"yes": 0, "no": 0}
        self.sampled_reprices = {"yes": 0, "no": 0}
        self.at_us = {"yes": 0, "no": 0}
        self.reasons = {"yes": collections.Counter(), "no": collections.Counter()}
        self.fill_qty = {"yes": 0.0, "no": 0.0}
        self.fill_cost = 0.0
        self.remaining = {"yes": size, "no": size}
        self.quote: dict[str, int | None] = {"yes": None, "no": None}
        self.why = {"yes": "", "no": ""}
        self.best = {"yes": None, "no": None}
        self.hist: dict[str, list[tuple[float, int | None]]] = {"yes": [], "no": []}
        self.status = "live"
        self.audit_partial = False


# ------------------------------------------------------------------ the farm
class Farm:
    def __init__(self, db_path: str, books: FarmBooks, *, size: float = 1000.0, cap_c: int = 10, pull_s: float = 60.0,
                 lookback_s: float = 1.0, fill_rule=fills_us, keep_days: float = 3.0, ledger_keep_days: float = 7.0) -> None:
        self.books, self.size, self.cap_c, self.pull_s, self.lookback_s = books, float(size), int(cap_c), float(pull_s), float(lookback_s)
        self.fill_rule, self.keep_days, self.ledger_keep_days = fill_rule, keep_days, ledger_keep_days
        self.lock = threading.RLock()
        self.programs: dict[str, dict] = {}
        self.mw: dict[str, MW] = {}
        self.seen: dict[str, set[str]] = collections.defaultdict(set)      # every trade id the socket delivered, per tracked ticker
        self.pending_fills: list[tuple] = []
        self.settle_due: dict[str, list] = {}                              # ticker -> [next_try, end_ts, in_flight]
        self.prints_untracked = 0
        self.resubscribes = 0
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.conn.executescript(SCHEMA)

    # ---- programs
    def set_programs(self, new: dict[str, dict], now: float) -> str:
        """Merge a program reload into the ONE live set: a market whose window is open or that we hold
        state for keeps its program (and its accumulators, which live in self.mw, untouched by reloads);
        upcoming ones follow the venue's list."""
        with self.lock:
            chosen, why = choose_programs(new, self.programs, now)
            keep = {t: p for t, p in self.programs.items() if t in self.mw or p["start_ts"] <= now < p["end_ts"]}
            self.programs = {**keep, **chosen}
            return why

    def subscription(self, now: float) -> list[str]:
        with self.lock:
            return sorted(t for t, p in self.programs.items() if p["end_ts"] > now)

    def quiet(self, now: float) -> bool:
        """True when no market can be quoted now or within QUIET_MARGIN_S: every window is past its
        T - pull_s or opens later than that. A socket restart here cannot lose a print that fills us."""
        with self.lock:
            return not any(p["start_ts"] - QUIET_MARGIN_S <= now < p["end_ts"] - self.pull_s for p in self.programs.values())

    def _state(self, ticker: str) -> MW | None:
        mw = self.mw.get(ticker)
        if mw is None and ticker in self.programs:
            mw = self.mw[ticker] = MW(ticker, self.programs[ticker], self.size)
        return mw

    @staticmethod
    def _in_period(p: dict, now: float) -> bool:
        return p["start_ts"] <= now < p["end_ts"]

    # ---- the quote
    def _reprice(self, mw: MW, now: float) -> None:
        yb, nb = self.books.best_c(mw.ticker, "yes"), self.books.best_c(mw.ticker, "no")
        for side, best, opp in (("yes", yb, nb), ("no", nb, yb)):
            old = mw.quote[side]
            if old is not None and best is not None and best >= old:
                mw.at_us[side] += 1                  # an incumbent bid reached our price (placed without seeing us)
            new, why = front_quote(best, opp, mw.remaining[side], now, mw.end_ts, self.cap_c, self.pull_s)
            mw.why[side], mw.best[side] = why, best
            if new != old:
                mw.quote[side] = new
                mw.hist[side].append((now, new))
                mw.reprices[side] += 1

    def on_book(self, ticker: str, now: float) -> None:
        with self.lock:
            p = self.programs.get(ticker)
            if p is None or not self._in_period(p, now):
                return
            self._reprice(self._state(ticker), now)

    def _lookback_quote(self, mw: MW, side: str, now: float) -> tuple[int | None, int]:
        """The highest price our quote held at any moment in [now - lookback_s, now], and 1 when that is
        above the current quote (the print's own book delta had already moved us)."""
        cur = best = mw.quote[side]
        lo = now - self.lookback_s
        for t, c in reversed(mw.hist[side]):
            if c is not None and (best is None or c > best):
                best = c
            if t <= lo:
                break
        return best, int(best is not None and (cur is None or best > cur))

    def on_trade(self, m: dict, now: float) -> None:
        tk = m.get("market_ticker")
        with self.lock:
            p = self.programs.get(tk)
            if p is None:
                self.prints_untracked += 1
                return
            tid = str(m.get("trade_id") or f"{m.get('ts_ms')}:{m.get('count_fp')}:{m.get('yes_price_dollars')}:{m.get('taker_side')}")
            if tid in self.seen[tk]:
                return
            self.seen[tk].add(tid)
            if not self._in_period(p, now):
                return
            mw = self._state(tk)
            mw.prints += 1
            side = side_hit(m.get("taker_side"))
            if side is None or mw.remaining[side] <= 0:
                return
            pc = cents(m.get("yes_price_dollars") if side == "yes" else m.get("no_price_dollars"))
            cnt = round(float(m.get("count_fp") or m.get("count") or 0), 2)
            ts_ms = m.get("ts_ms")
            tv = ts_ms / 1000.0 if isinstance(ts_ms, (int, float)) else now
            if pc is None or cnt <= 0 or tv >= mw.end_ts - self.pull_s:
                return                                                      # executed after our T-60 cancel
            if now >= mw.end_ts - self.pull_s:
                self._reprice(mw, now)
            qc, via = self._lookback_quote(mw, side, now)
            if qc is None or not self.fill_rule(pc, qc):
                return
            q = round(min(cnt, mw.remaining[side]), 2)
            mw.remaining[side] = round(mw.remaining[side] - q, 2)
            mw.fill_qty[side] = round(mw.fill_qty[side] + q, 2)
            mw.fill_cost += q * qc / 100.0
            self.pending_fills.append((now, tk, side, qc, q, pc, cnt, tid, ts_ms if isinstance(ts_ms, int) else None, via))
            self._reprice(mw, now)                                          # a filled side is pulled

    # ---- the second
    def tick(self, now: float) -> int:
        """One scoring second over every market inside its program period; returns markets valid this second."""
        n = 0
        with self.lock:
            for t, p in list(self.programs.items()):
                if not self._in_period(p, now):
                    continue
                mw = self._state(t)
                if mw.status != "live":
                    continue
                if mw.first_tick is None:
                    mw.first_tick = now
                self._reprice(mw, now)
                yes, no = self.books.side(t, "yes"), self.books.side(t, "no")
                mw.seconds += 1
                for side in SIDES:
                    if mw.quote[side] is not None:
                        mw.quoted[side] += 1
                    else:
                        mw.reasons[side][mw.why[side]] += 1
                valid = bool(yes) and bool(no) and sum(q for _, q in yes) >= mw.target and sum(q for _, q in no) >= mw.target
                if not valid:
                    continue
                mw.valid += 1; n += 1
                for side, lv in (("yes", yes), ("no", no)):
                    c = mw.quote[side]
                    if c is None:
                        continue
                    s = share_qualifying(lv, mw.remaining[side], mw.target, mw.discount, improve=True, price=c / 100.0)[0]
                    r = 0.5 * s * mw.reward_per_s
                    mw.rs[side] += r; mw.reward += r
            ended = [mw for mw in self.mw.values() if mw.status == "live" and now >= mw.end_ts]
            for mw in ended:
                mw.status = "closed"
                mw.quote = {"yes": None, "no": None}
                self.settle_due[mw.ticker] = [mw.end_ts + SETTLE_FIRST_S, mw.end_ts, False]
        for mw in ended:
            self._persist(mw, now)
        return n

    # ---- storage
    def write_fills(self) -> int:
        with self.lock:
            rows, self.pending_fills = self.pending_fills, []
        if rows:
            self.conn.executemany("INSERT OR IGNORE INTO fills VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def _persist(self, mw: MW, now: float) -> None:
        with self.lock:
            row = (mw.ticker, mw.series, mw.coin, mw.start_ts, mw.end_ts, mw.reward_per_s, mw.target, mw.discount, mw.first_tick,
                   mw.seconds, mw.valid, mw.reward, mw.rs["yes"], mw.rs["no"], mw.quoted["yes"], mw.quoted["no"],
                   mw.reprices["yes"], mw.reprices["no"], mw.at_us["yes"], mw.at_us["no"],
                   json.dumps({s: dict(mw.reasons[s]) for s in SIDES}), mw.prints, mw.fill_qty["yes"], mw.fill_qty["no"],
                   mw.fill_cost, mw.status, now)
        self.conn.execute(
            "INSERT INTO windows(ticker, series, coin, start_ts, end_ts, reward_per_s, target, discount, first_tick, seconds, valid,"
            " reward_usd, reward_yes, reward_no, quoted_yes, quoted_no, reprices_yes, reprices_no, book_at_us_yes, book_at_us_no,"
            " reasons, prints_socket, fill_qty_yes, fill_qty_no, fill_cost_usd, status, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(ticker) DO UPDATE SET first_tick=excluded.first_tick, seconds=excluded.seconds, valid=excluded.valid,"
            " reward_usd=excluded.reward_usd, reward_yes=excluded.reward_yes, reward_no=excluded.reward_no,"
            " quoted_yes=excluded.quoted_yes, quoted_no=excluded.quoted_no, reprices_yes=excluded.reprices_yes,"
            " reprices_no=excluded.reprices_no, book_at_us_yes=excluded.book_at_us_yes, book_at_us_no=excluded.book_at_us_no,"
            " reasons=excluded.reasons, prints_socket=excluded.prints_socket, fill_qty_yes=excluded.fill_qty_yes,"
            " fill_qty_no=excluded.fill_qty_no, fill_cost_usd=excluded.fill_cost_usd, status=excluded.status,"
            " updated_at=excluded.updated_at", row)

    def persist(self, now: float) -> None:
        self.write_fills()
        with self.lock:
            mws = [mw for mw in self.mw.values() if mw.status in ("live", "closed")]
        for mw in mws:
            self._persist(mw, now)

    def sample(self, now: float) -> None:
        """Once a minute: each live market-side's quote, and how many times it was re-priced since the last sample."""
        rows = []
        with self.lock:
            for mw in self.mw.values():
                if mw.status != "live" or not (mw.start_ts <= now < mw.end_ts):
                    continue
                for side in SIDES:
                    opp = mw.best["no" if side == "yes" else "yes"]
                    rows.append((round(now, 1), mw.ticker, side, mw.quote[side], mw.remaining[side], mw.best[side], opp, mw.why[side],
                                 mw.reprices[side] - mw.sampled_reprices[side]))
                    mw.sampled_reprices[side] = mw.reprices[side]
        if rows:
            self.conn.executemany("INSERT OR IGNORE INTO quotes VALUES(?,?,?,?,?,?,?,?,?)", rows)

    def restore(self, now: float) -> int:
        """After a restart: the open market-windows' accumulators come back from `windows` and each side's
        remaining size from `fills`, so a restart never rewrites a row from zero; closed ones queue for settlement.
        Their trade-id sets are gone, so their print audit is marked partial."""
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(windows)")]
        n = 0
        for r in self.conn.execute("SELECT * FROM windows WHERE status IN ('live','closed')").fetchall():
            w = dict(zip(cols, r))
            p = {"series": w["series"], "per_day_usd": w["reward_per_s"] * 86400.0, "target": w["target"], "discount": w["discount"],
                 "start_ts": w["start_ts"], "end_ts": w["end_ts"]}
            mw = MW(w["ticker"], p, self.size)
            mw.first_tick, mw.seconds, mw.valid, mw.reward = w["first_tick"], w["seconds"] or 0, w["valid"] or 0, w["reward_usd"] or 0.0
            mw.rs = {"yes": w["reward_yes"] or 0.0, "no": w["reward_no"] or 0.0}
            mw.quoted = {"yes": w["quoted_yes"] or 0, "no": w["quoted_no"] or 0}
            mw.reprices = {"yes": w["reprices_yes"] or 0, "no": w["reprices_no"] or 0}
            mw.sampled_reprices = dict(mw.reprices)
            mw.at_us = {"yes": w["book_at_us_yes"] or 0, "no": w["book_at_us_no"] or 0}
            rs = json.loads(w["reasons"] or "{}")
            mw.reasons = {s: collections.Counter(rs.get(s) or {}) for s in SIDES}
            mw.prints, mw.fill_cost = w["prints_socket"] or 0, w["fill_cost_usd"] or 0.0
            for side, qty in self.conn.execute("SELECT side, SUM(qty) FROM fills WHERE ticker=? GROUP BY side", (w["ticker"],)):
                mw.fill_qty[side] = round(qty, 2); mw.remaining[side] = round(self.size - qty, 2)
            mw.audit_partial = True
            with self.lock:
                self.mw[w["ticker"]] = mw
                if w["end_ts"] > now:
                    self.programs.setdefault(w["ticker"], p)
                else:
                    mw.status = "closed"
                    self.settle_due[w["ticker"]] = [now, w["end_ts"], False]
            n += 1
        return n

    # ---- settlement
    def due_settlements(self, now: float) -> list[str]:
        out = []
        with self.lock:
            for t, d in list(self.settle_due.items()):
                if d[2] or d[0] > now:
                    continue
                if now - d[1] > SETTLE_GIVE_UP_S:
                    self._give_up(t, now)
                    continue
                d[2] = True; out.append(t)
        return out

    def retry_settle(self, ticker: str, now: float) -> None:
        with self.lock:
            d = self.settle_due.get(ticker)
            if d is not None:
                d[0], d[2] = now + SETTLE_EVERY_S, False

    def _give_up(self, ticker: str, now: float) -> None:
        self.settle_due.pop(ticker, None)
        mw = self.mw.pop(ticker, None)
        if mw is not None:
            mw.status = "unsettled"
            self._persist(mw, now)
        log.warning("%s not settled %.0f h after close; recorded as unsettled", ticker, SETTLE_GIVE_UP_S / 3600)

    def _quote_at(self, mw: MW, side: str, t: float) -> int | None:
        c = None
        for ht, hc in mw.hist[side]:
            if ht > t:
                break
            c = hc
        return c

    def settle(self, ticker: str, market: dict, trades: list[dict], now: float) -> float | None:
        """Settle every fill of a closed market-window at the venue's value, and audit the socket's prints
        against the market's full public tape. Returns the window's fill P&L in dollars."""
        value = settlement_value(market)
        if value is None:
            self.retry_settle(ticker, now)
            return None
        self.write_fills()
        with self.lock:
            mw = self.mw.get(ticker)
            seen = set(self.seen.get(ticker) or ())
        if mw is not None:
            self._persist(mw, now)
        pnl = 0.0
        for side in SIDES:
            rows = self.conn.execute("SELECT price_c, qty FROM fills WHERE ticker=? AND side=?", (ticker, side)).fetchall()
            qty = sum(q for _, q in rows)
            sp = sum(fill_pnl(side, c, q, value) for c, q in rows)
            pnl += sp
            if rows:
                self.conn.execute("INSERT OR REPLACE INTO settlements VALUES(?,?,?,?,?,?,?)",
                                  (ticker, side, qty, sum(c * q for c, q in rows) / 100.0 / qty if qty else None, value, sp, now))
        audit = "partial" if mw is None or mw.audit_partial else "full"
        prints_rest = missed = 0; missed_fill = 0.0
        if mw is not None:
            for tr in trades:
                try:
                    tt = iso_ts(tr["created_time"])
                except (KeyError, ValueError, TypeError):
                    continue
                if not (mw.start_ts <= tt < mw.end_ts):
                    continue
                prints_rest += 1
                if str(tr.get("trade_id")) in seen:
                    continue
                missed += 1
                side = side_hit(tr.get("taker_side"))
                pc = cents(tr.get("yes_price_dollars") if side == "yes" else tr.get("no_price_dollars")) if side else None
                qc = self._quote_at(mw, side, tt) if side and tt < mw.end_ts - self.pull_s else None
                if pc is not None and qc is not None and self.fill_rule(pc, qc):
                    missed_fill += float(tr.get("count_fp") or tr.get("count") or 0)
        self.conn.execute("UPDATE windows SET status='settled', result=?, settlement_value=?, fill_pnl=?, settled_at=?, prints_rest=?,"
                          " prints_missed=?, missed_fillable=?, audit=?, updated_at=? WHERE ticker=?",
                          (market.get("result"), value, pnl, now, prints_rest, missed, round(missed_fill, 2), audit, now, ticker))
        with self.lock:
            self.settle_due.pop(ticker, None)
            self.mw.pop(ticker, None)
            self.seen.pop(ticker, None)
            p = self.programs.get(ticker)
            if p is not None and p["end_ts"] <= now:
                self.programs.pop(ticker, None)
        self.books.forget(ticker)
        return pnl

    # ---- retention and status
    def prune(self, now: float) -> None:
        q, led = now - self.keep_days * 86400, now - self.ledger_keep_days * 86400
        self.conn.execute("DELETE FROM quotes WHERE t < ?", (q,))
        self.conn.execute("DELETE FROM fills WHERE t < ?", (led,))
        self.conn.execute("DELETE FROM settlements WHERE settled_at < ?", (led,))
        self.conn.execute("DELETE FROM windows WHERE end_ts < ? AND status NOT IN ('live','closed')", (led,))
        with self.lock:                                                    # trade ids of tracked tickers that never opened a window
            for t in [t for t in self.seen if t not in self.programs and t not in self.mw]:
                self.seen.pop(t, None)

    def _sums(self, since: float) -> dict:
        c = self.conn
        rw = c.execute("SELECT COUNT(*), COALESCE(SUM(reward_usd),0) FROM windows WHERE end_ts > ?", (since,)).fetchone()
        fl = c.execute("SELECT COUNT(*), COALESCE(SUM(qty),0) FROM fills WHERE t >= ?", (since,)).fetchone()
        st = c.execute("SELECT COUNT(*), COALESCE(SUM(fill_pnl),0), COALESCE(SUM(reward_usd + fill_pnl),0) FROM windows"
                       " WHERE status='settled' AND end_ts > ?", (since,)).fetchone()
        return {"market_windows": rw[0], "paper_reward_usd": round(rw[1], 2), "fills": fl[0], "contracts_filled": round(fl[1], 2),
                "settled_market_windows": st[0], "settled_fill_pnl_usd": round(st[1], 2), "settled_net_usd": round(st[2], 2)}

    def status(self, now: float, socket: dict) -> dict:
        with self.lock:
            live = [mw for mw in self.mw.values() if mw.status == "live" and mw.start_ts <= now < mw.end_ts]
            quotes = [{"ticker": mw.ticker, "yes_c": mw.quote["yes"], "no_c": mw.quote["no"], "why_yes": mw.why["yes"], "why_no": mw.why["no"],
                       "remaining_yes": mw.remaining["yes"], "remaining_no": mw.remaining["no"], "reward_usd": round(mw.reward, 4)} for mw in live]
            pending = len(self.settle_due)
            tracked = len(self.programs)
        day = now - now % 86400
        return {"at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"), "series": SERIES,
                "policy": {"size": self.size, "cap_c": self.cap_c, "pull_s": self.pull_s, "lookback_s": self.lookback_s},
                "markets_live": len(live), "markets_tracked": tracked,
                "quotes_resting": {"yes": sum(q["yes_c"] is not None for q in quotes), "no": sum(q["no_c"] is not None for q in quotes)},
                "quotes": quotes, "pending_settlement": pending,
                "today_utc": self._sums(day), "since_start": self._sums(0.0),
                "socket": {**socket, "prints_untracked": self.prints_untracked, "socket_restarts": self.resubscribes},
                "paper": "nothing placed; fills inferred from prints at or below our bid; nobody can respond to an invisible quote"}


# ------------------------------------------------------------------ REST off the scoring thread
class Http:
    """Every REST call (program list, market result, the market's public trade tape) on one thread, so a
    slow answer never stalls the per-second scoring; results come back on a queue the main loop drains."""

    def __init__(self, series: list[str], horizon_s: float, http: httpx.Client | None = None, load=load_programs,
                 min_gap_s: float = 0.25, sleep=time.sleep) -> None:
        self.series, self.horizon_s, self.load, self.min_gap_s, self._sleep = series, horizon_s, load, min_gap_s, sleep
        self.http = http or httpx.Client(timeout=20, headers={"User-Agent": "meridian-farm-paper/1"})
        self.jobs: queue.Queue = queue.Queue()
        self.results: queue.Queue = queue.Queue()

    def start(self) -> Http:
        threading.Thread(target=self.run, name="farm-http", daemon=True).start()
        return self

    def run(self) -> None:
        while True:
            job = self.jobs.get()
            try:
                self.results.put(self.do(job))
            except Exception as e:                                           # noqa: BLE001 -- reported, retried by the main loop
                self.results.put(("error", job, f"{type(e).__name__}: {str(e)[:160]}"))

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._sleep(self.min_gap_s)
        r = self.http.get(REST + path, params=params)
        r.raise_for_status()
        return r.json()

    def do(self, job: tuple) -> tuple:
        if job[0] == "programs":
            return ("programs", self.load(self.series, http=self.http, horizon_s=self.horizon_s))
        if job[0] == "settle":
            t = job[1]
            m = self._get(f"/markets/{t}").get("market") or {}
            if settlement_value(m) is None:
                return ("not_yet", t, m.get("status"))
            trades, cursor = [], None
            while True:
                d = self._get("/markets/trades", {"ticker": t, "limit": 1000, **({"cursor": cursor} if cursor else {})})
                trades += d.get("trades") or []
                cursor = d.get("cursor") or d.get("next_cursor")
                if not cursor or not d.get("trades"):
                    break
            return ("settled", t, m, trades)
        raise ValueError(f"unknown job {job!r}")


# ------------------------------------------------------------------ the registered read
def cluster_mean_ci(clusters: list[list[float]], z: float = 1.96) -> tuple[float, float, float, int, int]:
    """Mean per element over all clusters with a cluster-robust (linearised ratio) 95% interval:
    var = G/(G-1) * sum_g (S_g - mean*m_g)^2 / N^2. Returns (mean, lo, hi, N, G)."""
    cl = [c for c in clusters if c]
    N = sum(len(c) for c in cl); G = len(cl)
    if N == 0:
        return float("nan"), float("nan"), float("nan"), 0, 0
    mean = sum(sum(c) for c in cl) / N
    if G < 2:
        return mean, float("nan"), float("nan"), N, G
    se = math.sqrt(G / (G - 1) * sum((sum(c) - mean * len(c)) ** 2 for c in cl) / N ** 2)
    return mean, mean - z * se, mean + z * se, N, G


def nearest_rank(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(q * len(s)) - 1)] if s else float("nan")


def registered_read(conn: sqlite3.Connection, since: float | None = None, days: float = 3.0, series: str = SERIES) -> dict:
    """The read registered in docs/math/coinrace-research.md before the arm ran. Population: every
    market-window of ``series`` whose period lies in [since, since + days); since defaults to the first
    window the arm ticked within 5 s of its opening. Estimators: per market-window means of net (paper
    reward + settled fill P&L), reward and fill P&L, window-clustered 95% CI (cluster = the 15-minute
    window, five markets); per-window fill loss = -(sum of the five markets' settled fill P&L), p90 by
    nearest rank and max. Decision: net CI excludes zero on the positive side AND p90 loss <= $50."""
    if since is None:
        r = conn.execute("SELECT MIN(start_ts) FROM windows WHERE series=? AND first_tick IS NOT NULL AND first_tick - start_ts <= 5",
                         (series,)).fetchone()
        since = r[0]
    if since is None:
        return {"error": "no window the arm saw open"}
    until = since + days * 86400
    cols = ("ticker", "start_ts", "end_ts", "seconds", "valid", "reward_usd", "fill_pnl", "status", "at_us", "prints_socket",
            "prints_rest", "prints_missed", "missed_fillable", "audit", "quoted_yes", "quoted_no", "settlement_value")
    rows = [dict(zip(cols, r)) for r in conn.execute(
        "SELECT ticker, start_ts, end_ts, seconds, valid, reward_usd, fill_pnl, status, book_at_us_yes + book_at_us_no, prints_socket,"
        " prints_rest, prints_missed, missed_fillable, audit, quoted_yes, quoted_no, settlement_value FROM windows"
        " WHERE series=? AND start_ts >= ? AND end_ts <= ?", (series, since, until))]
    settled = [r for r in rows if r["status"] == "settled"]
    by_w: dict[float, list[dict]] = collections.defaultdict(list)
    for r in settled:
        by_w[r["start_ts"]].append(r)
    net = cluster_mean_ci([[r["reward_usd"] + r["fill_pnl"] for r in g] for g in by_w.values()])
    rew = cluster_mean_ci([[r["reward_usd"] for r in g] for g in by_w.values()])
    fil = cluster_mean_ci([[r["fill_pnl"] for r in g] for g in by_w.values()])
    loss = [-sum(r["fill_pnl"] for r in g) for g in by_w.values()]
    period = sum(r["end_ts"] - r["start_ts"] for r in settled)
    tk = [r["ticker"] for r in settled]
    lb = {"all": 0.0, "via_lookback": 0.0, "pnl_without_lookback": 0.0}
    if tk:
        val = {r["ticker"]: r["settlement_value"] for r in settled}
        for i in range(0, len(tk), 500):
            chunk = tk[i:i + 500]
            for t, side, c, q, via in conn.execute(f"SELECT ticker, side, price_c, qty, via_lookback FROM fills WHERE ticker IN ({','.join('?' * len(chunk))})", chunk):
                lb["all"] += q
                if via:
                    lb["via_lookback"] += q
                else:
                    lb["pnl_without_lookback"] += fill_pnl(side, c, q, val[t])
    out = {"since": since, "until": until, "expected_market_windows": round(days * 96 * 5), "market_windows_present": len(rows),
           "settled": len(settled), "windows": len(by_w), "unsettled_or_open": len(rows) - len(settled),
           "net": net, "reward": rew, "fill_pnl": fil,
           "loss_per_window_p90": nearest_rank(loss, 0.9), "loss_per_window_max": max(loss) if loss else float("nan"),
           "valid_fraction": sum(r["valid"] for r in settled) / period if period else float("nan"),
           "ticked_fraction": sum(r["seconds"] for r in settled) / period if period else float("nan"),
           "quoted_fraction_yes": sum(r["quoted_yes"] for r in settled) / period if period else float("nan"),
           "quoted_fraction_no": sum(r["quoted_no"] for r in settled) / period if period else float("nan"),
           "book_at_or_above_us_events": sum(r["at_us"] for r in settled),
           "prints_rest": sum(r["prints_rest"] or 0 for r in settled), "prints_missed": sum(r["prints_missed"] or 0 for r in settled),
           "missed_fillable_contracts": sum(r["missed_fillable"] or 0 for r in settled),
           "audit_partial": sum(1 for r in settled if r["audit"] != "full"),
           "contracts_filled": lb["all"], "contracts_via_lookback": lb["via_lookback"],
           "fill_pnl_mean_without_lookback_fills": lb["pnl_without_lookback"] / len(settled) if settled else float("nan")}
    # instrument validity, registered with the rule and independent of the outcome: the arm saw >= 90% of the
    # market-windows, and its socket delivered >= 95% of the in-period prints on the public tape
    present_ok = len(settled) >= 0.9 * out["expected_market_windows"]
    tape_ok = out["prints_rest"] == 0 or out["prints_missed"] <= 0.05 * out["prints_rest"]
    out["instrument_valid"] = present_ok and tape_ok
    if not out["instrument_valid"]:
        out["decision"] = ("INVALID INSTRUMENT (" + ", ".join(x for x, ok in (("< 90% of market-windows settled", present_ok),
                                                                               ("socket missed > 5% of the tape's prints", tape_ok)) if not ok)
                           + "): the rule is not applied in either direction; fix and rerun 3 fresh days")
    else:
        out["decision"] = ("PASS: the live step is the operator's call" if net[1] > 0 and out["loss_per_window_p90"] <= 50
                           else "FAIL: farming closes")
    return out


def format_read(r: dict) -> str:
    if "error" in r:
        return r["error"]
    f = lambda t: f"${t[0]:+.2f} [{t[1]:+.2f}, {t[2]:+.2f}]"
    iso = lambda s: dt.datetime.fromtimestamp(s, dt.timezone.utc).isoformat(timespec="minutes")
    return "\n".join([
        f"Coin Race live paper farming, {iso(r['since'])} -> {iso(r['until'])}; nothing placed, before anyone responds",
        "PAPER: fills are inferred from prints at or below our bid; nobody can step in front of or respond to an invisible quote",
        (f"market-windows: {r['settled']} settled of {r['market_windows_present']} present ({r['expected_market_windows']} expected); "
         f"windows {r['windows']}; unsettled/open {r['unsettled_or_open']}"),
        f"per market-window, window-clustered 95% CI: net {f(r['net'])}; paper reward {f(r['reward'])}; settled fill P&L {f(r['fill_pnl'])}",
        f"fill loss per window (5 markets): p90 ${r['loss_per_window_p90']:.2f} (nearest rank), max ${r['loss_per_window_max']:.2f}",
        f"seconds: valid {r['valid_fraction']:.3f}, ticked {r['ticked_fraction']:.3f}, quoted YES {r['quoted_fraction_yes']:.3f}, NO {r['quoted_fraction_no']:.3f} (of program seconds)",
        (f"contracts filled {r['contracts_filled']:.0f}, of which via the 1-s lookback {r['contracts_via_lookback']:.0f}; "
         f"fill P&L per market-window without them ${r['fill_pnl_mean_without_lookback_fills']:+.2f}"),
        f"prints: public tape {r['prints_rest']}, socket missed {r['prints_missed']} ({r['missed_fillable_contracts']:.0f} contracts would have hit our quote, upper bound); audit partial on {r['audit_partial']} market-windows",
        f"stepped in front of: not measurable on paper (we are invisible); incumbent bids reaching our price: {r['book_at_or_above_us_events']} events",
        f"instrument valid (>= 90% of market-windows settled, socket >= 95% of the tape's prints): {r['instrument_valid']}",
        f"decision (net CI > 0 and p90 loss <= $50): {r['decision']}",
    ])


# ------------------------------------------------------------------ main
def settings() -> dict:
    e = os.environ.get
    return {"series": [s for s in (e("MERIDIAN_FARM_PAPER_SERIES") or SERIES).split(",") if s],
            "db": e("MERIDIAN_FARM_PAPER_DB") or "/data/farm_paper.sqlite",
            "status": e("MERIDIAN_FARM_PAPER_STATUS") or "/data/farm_paper_status.json",
            "size": float(e("MERIDIAN_FARM_PAPER_SIZE") or 1000),
            "cap_c": round(float(e("MERIDIAN_FARM_PAPER_CAP") or 0.10) * 100),
            "pull_s": float(e("MERIDIAN_FARM_PAPER_PULL_S") or 60),
            "lookback_s": float(e("MERIDIAN_FARM_PAPER_LOOKBACK_S") or 1.0),
            "horizon_s": float(e("MERIDIAN_FARM_PAPER_HORIZON_S") or 3600),
            "reload_s": float(e("MERIDIAN_FARM_PAPER_RELOAD_S") or 900)}


def run(cfg: dict) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    progs = wait_for_programs({"series": cfg["series"], "horizon_s": cfg["horizon_s"], "status": cfg["status"]})
    books = FarmBooks()
    farm = Farm(cfg["db"], books, size=cfg["size"], cap_c=cfg["cap_c"], pull_s=cfg["pull_s"], lookback_s=cfg["lookback_s"])
    books.farm = farm
    now = time.time()
    restored = farm.restore(now)
    farm.set_programs(progs, now)
    sock = BookSocket(farm.subscription(now), books, channels=CHANNELS).start()
    http = Http(cfg["series"], cfg["horizon_s"]).start()
    log.info("farm paper: %d programs, %d restored market-windows, policy %s", len(progs), restored,
             {k: cfg[k] for k in ("size", "cap_c", "pull_s", "lookback_s")})
    next_reload, next_minute, next_prune = now + cfg["reload_s"], 0.0, now + 3600
    resub_since: float | None = None
    while True:
        t0 = time.time()
        try:
            farm.tick(t0)
            farm.write_fills()
            while True:
                try:
                    res = http.results.get_nowait()
                except queue.Empty:
                    break
                if res[0] == "programs":
                    why = farm.set_programs(res[1], t0)
                    if why in ("empty", "ended"):
                        next_reload = t0 + 300
                elif res[0] == "settled":
                    pnl = farm.settle(res[1], res[2], res[3], t0)
                    log.info("settled %s at %s: fill P&L %s", res[1], res[2].get("result"), None if pnl is None else round(pnl, 2))
                elif res[0] == "not_yet":
                    farm.retry_settle(res[1], t0)
                else:
                    log.warning("REST %s failed: %s", res[1], res[2])
                    if res[1][0] == "settle":
                        farm.retry_settle(res[1][1], t0)
                    else:
                        next_reload = t0 + 300
            for tk in farm.due_settlements(t0):
                http.jobs.put(("settle", tk))
            if resub_since is None and farm.subscription(t0) != sock.tickers:
                resub_since = t0
            if resub_since is not None and (farm.quiet(t0) or t0 - resub_since > 2 * cfg["reload_s"]):
                tickers = farm.subscription(t0)
                log.info("subscription %d -> %d markets; socket restart in the quiet zone=%s", len(sock.tickers), len(tickers), farm.quiet(t0))
                sock.request_stop()
                sock = BookSocket(tickers, books, channels=CHANNELS).start()
                farm.resubscribes += 1; resub_since = None
            if t0 >= next_reload:
                http.jobs.put(("programs",)); next_reload = t0 + cfg["reload_s"]
            if t0 >= next_minute:
                next_minute = t0 + 60
                farm.persist(t0); farm.sample(t0)
                st = farm.status(t0, {**sock.counters(t0), "trades": books.trades})
                write_status(cfg["status"], st)
                log.info("status %s", json.dumps({k: st[k] for k in ("markets_live", "quotes_resting", "pending_settlement", "today_utc")}))
            if t0 >= next_prune:
                farm.prune(t0); next_prune = t0 + 3600
        except Exception:
            log.exception("tick")
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--read", action="store_true", help="print the registered read from the ledger")
    ap.add_argument("--db", default=None)
    ap.add_argument("--since", default=None, help="ISO start of the read (default: the first window the arm saw open)")
    ap.add_argument("--days", type=float, default=3.0)
    a = ap.parse_args(argv)
    cfg = settings()
    if a.read:
        path = a.db or cfg["db"]
        if not os.path.exists(path):
            print(f"no ledger at {path}")
            return 1
        conn = sqlite3.connect(path)                     # reads only; a WAL ledger opened mode=ro needs its -shm file
        print(format_read(registered_read(conn, iso_ts(a.since) if a.since else None, a.days)))
        return 0
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
