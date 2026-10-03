"""Kalshi Liquidity Incentive Program, scored on paper: what a resting quote of ours would earn, each
second, from the venue's published rule and its live books. Reads only; places nothing.

The rule (help.kalshi.com article 13823851, read 2026-10-01): a snapshot once a second at a random
moment; the REFERENCE PRICE is found walking down from the best bid to the first level whose
cumulative size reaches one fifth of the market's Target Size; an order at or better than it scores
size x 1.0, an order k ticks worse scores size x discount^k; yes and no sides score separately and a
snapshot score is the share of each; the period reward is paid by share of all participants'
snapshot scores; a snapshot counts only if the market is open and two-sided depth >= Target Size
rests; fills do not matter. Programs (reward, target, discount, dates) are public:
GET /trade-api/v2/incentive_programs?status=active&type=liquidity.

What this does: loads the active programs for the configured series, subscribes to those markets'
books on Kalshi's websocket (orderbook_snapshot then orderbook_delta, seq-tracked; the handshake is
signed with the same key the BRTI relay uses), and once a second, per market and side, computes
the reference, the incumbents' score, and the share a quote of OURS of Q contracts resting AT the
reference would take -- for each configured Q -- plus whether the snapshot would count. Hourly
aggregates (valid seconds, mean share per Q, implied $/day) and a once-a-minute sample go to a
SQLite under /data with 3-day retention. The implied $/day is exact under the rule for the books
as they are; what it cannot know is whether our resting size would be filled, and whether the
incumbents would add size against it. That is what the live step answers, and only the operator
switches it on (docs/math/kalshi-lip-sizing.md).

    python -m core.kalshi.lip_scorer            # the service
    python -m core.kalshi.lip_scorer --once     # programs + one REST read of the books, printed
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import logging
import os
import sqlite3
import sys
import threading
import time

import httpx

log = logging.getLogger("lip")

REST = os.environ.get("KALSHI_API_URL", "https://api.elections.kalshi.com/trade-api/v2")
WS = os.environ.get("KALSHI_WS_URL", "wss://external-api-ws.kalshi.com/trade-api/ws/v2")
DEFAULT_SERIES = ("KXAAAGASDGA,KXAAAGASDFL,KXAAAGASDMD,KXAAAGASDAZ,KXAAAGASDOH,KXAAAGASDMO,KXAAAGASDTX,KXAAAGASDNY,"
                  "KXAAAGASDCA,KXAAAGASDMN,KXAAAGASDCT,KXAAAGASDNV,KXAAAGASDSC,KXAAAGASDWI,KXAAAGASDCO,KXAAAGASDIN,"
                  "KXAAAGASDMA,KXAAAGASDIL,KXAAAGASDNJ,KXAAAGASDTN,KXAAAGASDVA,KXAAAGASDOR,KXAAAGASDNC,KXAAAGASDWA,KXAAAGASDMI")
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS programs(ticker TEXT PRIMARY KEY, series TEXT, per_day_usd REAL, target REAL, discount REAL,
  start_ts REAL, end_ts REAL, loaded_at REAL);
CREATE TABLE IF NOT EXISTS lip_hourly(hour_ts REAL NOT NULL, ticker TEXT NOT NULL, seconds INTEGER, valid INTEGER,
  sum_share TEXT, inc_yes_med REAL, inc_no_med REAL, PRIMARY KEY(hour_ts, ticker));
CREATE TABLE IF NOT EXISTS lip_sample(t REAL NOT NULL, ticker TEXT NOT NULL, yes_best REAL, no_best REAL, ref_yes REAL, ref_no REAL,
  inc_yes REAL, inc_no REAL, depth_yes REAL, depth_no REAL, valid INTEGER, shares TEXT, PRIMARY KEY(t, ticker));
CREATE TABLE IF NOT EXISTS seq_gaps(t REAL, sid INTEGER, expected INTEGER, got INTEGER);
"""


# ------------------------------------------------------------------ the rule
def reference_and_score(levels: list[tuple[float, float]], target: float, discount: float) -> tuple[float | None, float, float]:
    """levels: one side's bids as (price, size), best first. Returns (reference price, incumbents'
    score, cumulative depth). Reference = first level, walking down from the best, whose cumulative
    size reaches target/5; score = size at/better x 1 + size k ticks worse x discount^k (1c ticks)."""
    if not levels:
        return None, 0.0, 0.0
    cum = 0.0; ref = None
    for p, q in levels:
        cum += q
        if ref is None and cum >= target / 5:
            ref = p
    if ref is None:
        ref = levels[-1][0]
    score = 0.0
    for p, q in levels:
        k = round((ref - p) * 100)
        score += q if k <= 0 else q * (discount ** k)
    return ref, score, cum


def our_share(q: float, incumbent_score: float) -> float:
    """A quote of q contracts resting AT the reference: full credit, share of that side's score."""
    return q / (q + incumbent_score) if q > 0 else 0.0


# ------------------------------------------------------------------ programs
def load_programs(series: list[str], http: httpx.Client | None = None, now: float | None = None) -> dict[str, dict]:
    http = http or httpx.Client(timeout=20, headers={"User-Agent": "meridian-lip/1"})
    now = time.time() if now is None else now
    out: dict[str, dict] = {}
    cursor = None
    while True:
        r = http.get(REST + "/incentive_programs", params={"status": "active", "type": "liquidity", "limit": 1000,
                                                             **({"cursor": cursor} if cursor else {})})
        r.raise_for_status()
        d = r.json()
        for p in d.get("incentive_programs") or []:
            t = p["market_ticker"]; s = t.split("-")[0]
            if s not in series:
                continue
            a = dt.datetime.fromisoformat(p["start_date"].replace("Z", "+00:00")).timestamp()
            b = dt.datetime.fromisoformat(p["end_date"].replace("Z", "+00:00")).timestamp()
            if not (a <= now <= b):
                continue
            out[t] = {"series": s, "per_day_usd": p["period_reward"] / 10000 / max(1e-9, (b - a) / 86400),
                      "target": float(p.get("target_size_fp") or 0), "discount": (p.get("discount_factor_bps") or 0) / 10000,
                      "start_ts": a, "end_ts": b}
        cursor = d.get("cursor") or d.get("next_cursor")
        if not cursor or not d.get("incentive_programs"):
            break
    return out


def choose_programs(new: dict[str, dict], old: dict[str, dict], now: float | None = None) -> tuple[dict[str, dict], str]:
    """Which program set the scorer keeps after a reload. The new one when it differs; when it is
    EMPTY: if every old program has ended (the daily gas programs run 12:00Z-03:59Z and the next
    day's are created around 12:00Z, so 04-12Z has none and no one is paid) the set is genuinely
    empty -> ({}, "ended"); if old programs are still inside their period the endpoint answered
    empty -> keep them ("empty"). The caller retries sooner in both cases. Returns (set, why)."""
    now = time.time() if now is None else now
    if not new:
        if old and all(p.get("end_ts", 0) < now for p in old.values()):
            return {}, "ended"
        return old, "empty"
    if set(new) != set(old):
        return new, "changed"
    return old, "same"


# ------------------------------------------------------------------ books
class Books:
    """Per-market yes/no bid levels from orderbook_snapshot + orderbook_delta, seq-tracked per sid."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.levels: dict[str, dict[str, dict[float, float]]] = {}
        self.seq: dict[int, int] = {}
        self.gaps: list[tuple[float, int, int, int]] = []
        self.snapshots = self.deltas = 0

    def handle(self, msg: dict, now: float) -> str | None:
        """Returns 'gap' when a sequence number was skipped (the caller resubscribes)."""
        t = msg.get("type")
        if t not in ("orderbook_snapshot", "orderbook_delta"):
            return None
        sid, seq = msg.get("sid"), msg.get("seq")
        m = msg.get("msg") or {}
        tk = m.get("market_ticker")
        if not tk:
            return None
        with self._lock:
            if isinstance(sid, int) and isinstance(seq, int):
                last = self.seq.get(sid)
                if last is not None and seq != last + 1 and t == "orderbook_delta":
                    self.gaps.append((now, sid, last + 1, seq))
                    self.seq[sid] = seq
                    return "gap"
                self.seq[sid] = seq
            if t == "orderbook_snapshot":
                self.snapshots += 1
                self.levels[tk] = {"yes": {float(p): float(q) for p, q in (m.get("yes_dollars_fp") or m.get("yes_dollars") or [])},
                                   "no": {float(p): float(q) for p, q in (m.get("no_dollars_fp") or m.get("no_dollars") or [])}}
            else:
                self.deltas += 1
                side = m.get("side")
                book = self.levels.setdefault(tk, {"yes": {}, "no": {}}).get(side)
                if book is None:
                    return None
                p = float(m.get("price_dollars")); d = float(m.get("delta_fp") or m.get("delta") or 0)
                q = book.get(p, 0.0) + d
                if q <= 1e-9:
                    book.pop(p, None)
                else:
                    book[p] = q
        return None

    def side(self, ticker: str, side: str) -> list[tuple[float, float]]:
        with self._lock:
            b = self.levels.get(ticker, {}).get(side, {})
            return sorted(((p, q) for p, q in b.items() if q > 0), reverse=True)

    def known(self) -> list[str]:
        with self._lock:
            return list(self.levels)


# ------------------------------------------------------------------ scoring and storage
class Scorer:
    def __init__(self, db_path: str, programs: dict[str, dict], sizes: list[float], books: Books, clock=time.time,
                 keep_days: float = 3.0) -> None:
        self.db_path, self.programs, self.sizes, self.books, self._clock, self.keep_days = db_path, programs, sizes, books, clock, keep_days
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.conn.executescript(SCHEMA)
        for t, p in programs.items():
            self.conn.execute("INSERT OR REPLACE INTO programs VALUES(?,?,?,?,?,?,?,?)",
                              (t, p["series"], p["per_day_usd"], p["target"], p["discount"], p["start_ts"], p["end_ts"], clock()))
        self.acc: dict[str, dict] = {}            # ticker -> {"hour", "seconds", "valid", "sum": {Q: share}, "inc_yes": [], "inc_no": []}
        self.last_sample = 0.0
        self.ticks = 0

    def score_market(self, ticker: str) -> dict | None:
        p = self.programs.get(ticker)
        if p is None:
            return None
        yes = self.books.side(ticker, "yes"); no = self.books.side(ticker, "no")
        if not yes or not no:
            return {"valid": 0, "ticker": ticker}
        ry, sy, dy = reference_and_score(yes, p["target"], p["discount"])
        rn, sn, dn = reference_and_score(no, p["target"], p["discount"])
        valid = int(dy >= p["target"] and dn >= p["target"])
        shares = {str(int(q)): 0.5 * (our_share(q, sy) + our_share(q, sn)) for q in self.sizes}
        return {"ticker": ticker, "valid": valid, "yes_best": yes[0][0], "no_best": no[0][0], "ref_yes": ry, "ref_no": rn,
                "inc_yes": sy, "inc_no": sn, "depth_yes": dy, "depth_no": dn, "shares": shares}

    def tick(self, now: float | None = None) -> int:
        """One scoring second over every program market with a book; returns markets scored."""
        now = self._clock() if now is None else now
        hour = now - now % 3600
        n = 0
        sample = now - self.last_sample >= 60
        for t in self.programs:
            r = self.score_market(t)
            if r is None:
                continue
            a = self.acc.get(t)
            if a is None or a["hour"] != hour:
                if a is not None:
                    self._flush(t, a)
                a = self.acc[t] = {"hour": hour, "seconds": 0, "valid": 0, "sum": {str(int(q)): 0.0 for q in self.sizes}, "inc_yes": [], "inc_no": []}
            a["seconds"] += 1
            if r["valid"]:
                a["valid"] += 1
                for k, v in r["shares"].items():
                    a["sum"][k] += v
                a["inc_yes"].append(r["inc_yes"]); a["inc_no"].append(r["inc_no"])
                n += 1
            if sample and r.get("shares") is not None:
                self.conn.execute("INSERT OR IGNORE INTO lip_sample VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (round(now, 1), t, r["yes_best"], r["no_best"], r["ref_yes"], r["ref_no"], r["inc_yes"], r["inc_no"],
                                   r["depth_yes"], r["depth_no"], r["valid"], json.dumps(r["shares"])))
        if sample:
            self.last_sample = now
        self.ticks += 1
        if self.ticks % 3600 == 0:
            self.prune(now)
        return n

    def _flush(self, t: str, a: dict) -> None:
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
        self.conn.execute("INSERT OR REPLACE INTO lip_hourly VALUES(?,?,?,?,?,?,?)",
                          (a["hour"], t, a["seconds"], a["valid"], json.dumps(a["sum"]), med(a["inc_yes"]), med(a["inc_no"])))

    def flush_all(self) -> None:
        for t, a in list(self.acc.items()):
            self._flush(t, a)

    def prune(self, now: float) -> None:
        floor = now - self.keep_days * 86400
        self.conn.execute("DELETE FROM lip_sample WHERE t < ?", (floor,))
        self.conn.execute("DELETE FROM lip_hourly WHERE hour_ts < ?", (floor,))

    def implied_per_day(self) -> dict:
        """From the current hour's accumulators: per series and total, implied $/day at each Q =
        sum over markets of (mean share while valid x valid fraction x per_day)."""
        by: dict[str, dict] = collections.defaultdict(lambda: {str(int(q)): 0.0 for q in self.sizes})
        for t, a in self.acc.items():
            if not a["seconds"]:
                continue
            p = self.programs[t]
            for k, s in a["sum"].items():
                by[p["series"]][k] += (s / a["seconds"]) * p["per_day_usd"]
        total = {str(int(q)): sum(v[str(int(q))] for v in by.values()) for q in self.sizes}
        return {"by_series": dict(by), "total": total}


# ------------------------------------------------------------------ the socket
SUB_BATCH = int(os.environ.get("MERIDIAN_LIP_SUB_BATCH") or 100)


def subscribe_msgs(tickers: list[str], channels: tuple[str, ...] = ("orderbook_delta",)) -> list[dict]:
    return [{"id": i + 1, "cmd": "subscribe", "params": {"channels": list(channels), "market_tickers": tickers[j:j + SUB_BATCH]}}
            for i, j in enumerate(range(0, len(tickers), SUB_BATCH))]


class BookSocket:
    """Kalshi's one websocket, signed like the BRTI relay, subscribed to orderbook_delta for the
    program markets; a seq gap triggers a fresh socket (and so fresh snapshots)."""

    def __init__(self, tickers: list[str], books: Books, *, open_socket=None, clock=time.time, sleep=time.sleep,
                 max_backoff: float = 30.0, channels: tuple[str, ...] = ("orderbook_delta",)) -> None:
        self.tickers, self.books, self.channels = tickers, books, channels
        self._open_socket = open_socket or self._default_socket
        self._clock, self._sleep, self.max_backoff = clock, sleep, max_backoff
        self.stop = threading.Event()
        self.msgs = self.reconnects = self.resubscribes = 0
        self.last_msg_at: float | None = None
        self.last_error = ""
        self._ws = None

    def _default_socket(self):
        from core.btc15.brti_relay import auth_headers, credentials_from_env
        from core.polymarket.ws_min import WSClient
        key_id, pk = credentials_from_env()
        ws = WSClient(WS, auth_headers(key_id, pk, "/trade-api/ws/v2"), timeout=30.0)
        ws.connect()
        return ws

    def start(self) -> "BookSocket":
        threading.Thread(target=self.run, name="lip-books", daemon=True).start()
        return self

    def run(self) -> None:
        from core.polymarket.ws_min import ConnectionClosed
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except Exception as e:                                           # noqa: BLE001, PERF203
                # ConnectionClosed/OSError are the expected ones; a malformed message raising
                # KeyError/TypeError out of handle() must not end this daemon thread silently
                # and leave the scorer ticking on frozen books.
                self.last_error = f"{type(e).__name__}: {str(e)[:120]}"; self.reconnects += 1
                if not isinstance(e, (ConnectionClosed, OSError, ValueError)):
                    log.exception("book socket")
                if self.stop.is_set():
                    return
                self._sleep(backoff); backoff = min(backoff * 2, self.max_backoff)

    def _session(self) -> None:
        ws = self._open_socket(); self._ws = ws
        try:
            for m in subscribe_msgs(self.tickers, self.channels):
                ws.send_json(m)
            while not self.stop.is_set():
                msg = ws.recv_json()
                self.msgs += 1; self.last_msg_at = self._clock()
                if isinstance(msg, dict) and self.books.handle(msg, self.last_msg_at) == "gap":
                    # A skipped seq means the book is wrong from here. A second subscribe on a
                    # channel this socket already holds is answered by the venue with an error,
                    # not a snapshot, so the recovery is a fresh socket: return, and run() opens
                    # one (backoff 1 s) whose subscribes bring new snapshots for every batch.
                    self.resubscribes += 1
                    return
        finally:
            self._ws = None
            try:
                ws.close()
            except Exception:                                            # noqa: BLE001 -- closing a dead socket
                pass

    def request_stop(self) -> None:
        self.stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except OSError:
                pass

    def counters(self, now: float | None = None) -> dict:
        now = self._clock() if now is None else now
        return {"messages": self.msgs, "reconnects": self.reconnects, "resubscribes": self.resubscribes,
                "last_msg_age_s": None if self.last_msg_at is None else round(now - self.last_msg_at, 1),
                "snapshots": self.books.snapshots, "deltas": self.books.deltas, "seq_gaps": len(self.books.gaps),
                "books": len(self.books.known()), "last_error": self.last_error}


# ------------------------------------------------------------------ main
def settings() -> dict:
    e = os.environ.get
    return {"series": [s for s in (e("MERIDIAN_LIP_SERIES") or DEFAULT_SERIES).split(",") if s],
            "sizes": [float(x) for x in (e("MERIDIAN_LIP_SIZES") or "200,500").split(",")],
            "db": e("MERIDIAN_LIP_DB") or "/data/lip_scorer.sqlite",
            "status": e("MERIDIAN_LIP_STATUS") or "/data/lip_status.json",
            "reload_s": float(e("MERIDIAN_LIP_RELOAD_S") or 3600)}


def once(cfg: dict) -> int:
    """Programs + one REST read of every market's book, scored and printed by series."""
    http = httpx.Client(timeout=20, headers={"User-Agent": "meridian-lip/1"})
    progs = load_programs(cfg["series"], http)
    print(f"{len(progs)} program markets in {len({p['series'] for p in progs.values()})} series")
    by = collections.defaultdict(lambda: {"n": 0, "valid": 0, "usd": {str(int(q)): 0.0 for q in cfg['sizes']}, "pool": 0.0})
    for t, p in progs.items():
        try:
            ob = http.get(REST + f"/markets/{t}/orderbook", params={"depth": 10}).json().get("orderbook_fp") or {}
        except Exception:                                                # noqa: BLE001
            continue
        time.sleep(0.12)
        yes = sorted([(float(a), float(b)) for a, b in (ob.get("yes_dollars") or []) if float(b) > 0], reverse=True)
        no = sorted([(float(a), float(b)) for a, b in (ob.get("no_dollars") or []) if float(b) > 0], reverse=True)
        g = by[p["series"]]; g["n"] += 1; g["pool"] += p["per_day_usd"]
        if not yes or not no:
            continue
        ry, sy, dy = reference_and_score(yes, p["target"], p["discount"]); rn, sn, dn = reference_and_score(no, p["target"], p["discount"])
        if dy >= p["target"] and dn >= p["target"]:
            g["valid"] += 1
        for q in cfg["sizes"]:
            g["usd"][str(int(q))] += 0.5 * (our_share(q, sy) + our_share(q, sn)) * p["per_day_usd"]
    print("series          markets  valid-now  pool $/day   " + "   ".join(f"$/day@{int(q)}" for q in cfg["sizes"]))
    tot = collections.Counter()
    for s, g in sorted(by.items(), key=lambda kv: -kv[1]["pool"]):
        print(f"{s:15s} {g['n']:7d}  {g['valid']:9d}   ${g['pool']:8.0f}   " + "   ".join(f"${g['usd'][str(int(q))]:8.0f}" for q in cfg["sizes"]))
        for q in cfg["sizes"]:
            tot[str(int(q))] += g["usd"][str(int(q))]
    print("total: " + ", ".join(f"${v:,.0f}/day at {k}/side" for k, v in tot.items()))
    return 0


def idle_status(now: float, series: list[str]) -> dict:
    """The status written while no program is live (04-12Z for the gas series): markets 0 and the reason,
    so a reader sees a fresh 'idle' instead of a stale file from the last scored second."""
    return {"at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"), "markets": 0,
            "scored_this_second": 0, "idle": "no live liquidity programs for %s (the daily gas programs run 12:00Z-03:59Z); checking every 5 min" % ",".join(series[:3]),
            "socket": {}, "implied_per_day": {"by_series": {}, "total": {}}}


def write_status(path: str, st: dict) -> None:
    with open(path, "w") as fh:
        json.dump(st, fh, indent=1)


def wait_for_programs(cfg: dict, load=None, sleep=time.sleep, clock=time.time, status=None) -> dict[str, dict]:
    """The live program set, waiting while there is none (04-12Z for the gas series) and
    surviving a failed fetch. Overnight 2026-10-02 three fetches failed (a 429 at 06:08Z, two
    more at 10:49Z/11:14Z) and each one ended the process -- docker restarted it, nothing was
    paid in those hours, but the hourly reload during paid hours is guarded and this was not.
    A failure logs one warning and waits 10 min; an empty answer waits 5 min; both write the
    idle status so a reader sees idle, not dead."""
    load = load or load_programs
    while True:
        try:
            progs = load(cfg["series"])
        except Exception as e:                                           # noqa: BLE001
            log.warning("program list fetch failed (%s: %s); retrying in 10 min", type(e).__name__, str(e)[:120])
            (status or write_status)(cfg["status"], idle_status(clock(), cfg["series"]))
            sleep(600)
            continue
        if progs:
            return progs
        log.warning("no live liquidity programs for %s right now (the daily gas programs run 12:00Z-03:59Z); retrying in 5 min", cfg["series"][:3])
        (status or write_status)(cfg["status"], idle_status(clock(), cfg["series"]))
        sleep(300)


def run(cfg: dict) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    progs = wait_for_programs(cfg)
    log.info("lip scorer: %d program markets, series %s, sizes %s", len(progs), sorted({p['series'] for p in progs.values()}), cfg["sizes"])
    books = Books()
    scorer = Scorer(cfg["db"], progs, cfg["sizes"], books)
    sock = BookSocket(sorted(progs), books).start()
    # The implied figure in the status is a 24-h RATE (share x period reward / period days). The gas
    # programs pay $100 a market over a 16-h period, so the money per calendar day is share x $100 a
    # market, i.e. the rate x 16/24; the 48-h read integrates over live hours (docs/math/kalshi-lip-sizing.md).
    next_reload = time.time() + cfg["reload_s"]; next_status = 0.0
    while True:
        t0 = time.time()
        try:
            n = scorer.tick(t0)
            if t0 >= next_status:
                next_status = t0 + 60
                st = {"at": dt.datetime.fromtimestamp(t0, dt.timezone.utc).isoformat(timespec="seconds"), "markets": len(progs),
                      "scored_this_second": n, "socket": sock.counters(t0), "implied_per_day": scorer.implied_per_day()}
                write_status(cfg["status"], st)
                log.info("status %s", json.dumps({k: v for k, v in st.items() if k != "implied_per_day"}) + " implied " + json.dumps(st["implied_per_day"]["total"]))
            if t0 >= next_reload:
                next_reload = t0 + cfg["reload_s"]
                try:
                    chosen, why = choose_programs(load_programs(cfg["series"]), progs, t0)
                    if why == "empty":
                        log.warning("program reload returned none while %d programs are still live; keeping them, retrying in 5 min", len(progs))
                        next_reload = t0 + 300
                    elif why == "ended":
                        # the daily programs ended (gas: 03:59Z) and the next day's are not listed yet (~12:00Z):
                        # nothing is paid in between, so nothing is scored; look every five minutes for the new ones
                        if progs:
                            log.info("all %d programs ended; idle until the next ones are listed (checking every 5 min)", len(progs))
                            scorer.flush_all(); sock.request_stop()
                            progs = {}; scorer = Scorer(cfg["db"], progs, cfg["sizes"], books)
                        next_reload = t0 + 300
                    elif why == "changed":
                        log.info("programs changed: %d -> %d; restarting the socket", len(progs), len(chosen))
                        scorer.flush_all()
                        progs = chosen; scorer = Scorer(cfg["db"], progs, cfg["sizes"], books)
                        sock.request_stop(); sock = BookSocket(sorted(progs), books).start()
                except Exception:                                        # noqa: BLE001
                    log.exception("program reload")
                    next_reload = t0 + 300
        except Exception:                                                # noqa: BLE001 -- a bad second never takes the service down
            log.exception("tick")
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    cfg = settings()
    return once(cfg) if a.once else run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
