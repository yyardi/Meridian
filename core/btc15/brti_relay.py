"""Kalshi's relay of CF Benchmarks' BRTI -- the number both venues settle on -- over a signed websocket.

Polymarket US "BTC Up or Down" and Kalshi KXBTC15M both settle on the 60-second simple mean of
BRTI before the window's start and before its end (verified against both venues' rule text,
2026-09-30). BRTI itself is licensed and has no free feed; the harness's composite (the median
mid of four of its seven constituents, polled and streamed) proxies it with a -$2.10 mean error
and $3.34 sd against `expiration_value` over 241 windows. Kalshi relays the index to any API
key (docs.kalshi.com/websockets/cfbenchmarks-value, read 2026-09-30):

    wss://external-api-ws.kalshi.com/cfbenchmarks_value
    {"id": 1, "cmd": "subscribe", "params": {"channels": ["cfbenchmarks_value"], "index_ids": ["BRTI"]}}
    -> {"type": "cfbenchmarks_value", "sid": 1, "seq": 42, "msg": {
          "index_id": "BRTI", "received_at": 1710000000123,
          "data": "{\\"type\\":\\"value\\",\\"id\\":\\"BRTI\\",\\"time\\":1710000000123,\\"value\\":\\"68000.12\\"}",
          "avg_60s_data": {"value": "68000.12000000", "window_size": 3, ...},           # trailing 60 s, per tick
          "last_60s_windowed_average_15min": {"value": "68000.23000000", ...}}}          # final minute only

"Ticks are emitted roughly once per second." `avg_60s_data` is the settlement definition
applied to the trailing minute; `last_60s_windowed_average_15min` appears in the final minute
before :00/:15/:30/:45 and is the closing average as it accrues. The relay's own latency
against the settlement is unmeasured; recording it beside `expiration_value` is the first job.

Authentication (docs.kalshi.com quick_start_websockets): headers KALSHI-ACCESS-KEY,
KALSHI-ACCESS-TIMESTAMP (ms) and KALSHI-ACCESS-SIGNATURE = base64 of the key's signature over
``f"{timestamp}GET{path}"`` -- RSA-PSS (SHA-256, MGF1, salt = digest length) or Ed25519 by key
type. The documented path for the trade socket is ``/trade-api/ws/v2``; which path this host
expects for the value feed is not documented, so the URL's own path is signed by default and
``KALSHI_WS_SIGN_PATH`` overrides it. Credentials: ``KALSHI_API_KEY_ID`` and
``KALSHI_PRIVATE_KEY_PATH`` (a PEM file) or ``KALSHI_PRIVATE_KEY`` (PEM text). Prod holds
neither as of 2026-09-30 (the operator's ask); without them the relay is disabled and says so.
Nothing here places an order: the value feed is read-only.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from core.polymarket.ws_min import ConnectionClosed, WSClient

log = logging.getLogger("btc15.brti")

URL = os.environ.get("KALSHI_CF_WS_URL", "wss://external-api-ws.kalshi.com/cfbenchmarks_value")
SUBSCRIBE = {"id": 1, "cmd": "subscribe", "params": {"channels": ["cfbenchmarks_value"], "index_ids": ["BRTI"]}}


# ------------------------------------------------------------------ signing
class MissingKalshiCredentials(Exception):
    pass


def load_private_key(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem, password=None)


def sign(private_key, message: bytes) -> bytes:
    """RSA-PSS (SHA-256, MGF1, salt = digest length) for RSA keys; Ed25519 keys sign directly."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ed25519, padding
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return private_key.sign(message)
    return private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())


def auth_headers(key_id: str, private_key, path: str, ts_ms: int | None = None, method: str = "GET") -> dict[str, str]:
    ts = str(int(time.time() * 1000) if ts_ms is None else ts_ms)
    sig = base64.b64encode(sign(private_key, (ts + method + path.split("?")[0]).encode())).decode()
    return {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts, "KALSHI-ACCESS-SIGNATURE": sig}


def credentials_from_env() -> tuple[str, object]:
    e = os.environ.get
    key_id = e("KALSHI_API_KEY_ID")
    pem = e("KALSHI_PRIVATE_KEY")
    path = e("KALSHI_PRIVATE_KEY_PATH")
    if not key_id or not (pem or path):
        raise MissingKalshiCredentials("KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (or KALSHI_PRIVATE_KEY)")
    if not pem:
        with open(path, "rb") as fh:
            pem_bytes = fh.read()
    else:
        pem_bytes = pem.encode()
    return key_id, load_private_key(pem_bytes)


# ------------------------------------------------------------------ messages
@dataclass(frozen=True)
class BRTITick:
    recv: float                 # our clock at receipt
    source_ts_ms: int | None    # CF's calculation time
    value: float
    avg_60s: float | None       # trailing 60-s mean, per tick
    last_60s_15m: float | None  # the closing average as it accrues, final minute only
    seq: int | None


def _num(x) -> float | None:
    if isinstance(x, dict):
        x = x.get("value")
    if x in (None, ""):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_tick(msg, recv: float) -> BRTITick | None:
    """One relay message -> a tick, or None for anything that is not a BRTI value (acks, errors)."""
    if not isinstance(msg, dict) or msg.get("type") != "cfbenchmarks_value":
        return None
    m = msg.get("msg") or {}
    if m.get("index_id") != "BRTI":
        return None
    data = m.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    data = data if isinstance(data, dict) else {}
    value = _num(data.get("value"))
    if value is None:
        return None
    ts = data.get("time")
    return BRTITick(recv=recv, source_ts_ms=int(ts) if isinstance(ts, (int, float)) else None, value=value,
                    avg_60s=_num(m.get("avg_60s_data")), last_60s_15m=_num(m.get("last_60s_windowed_average_15min")),
                    seq=msg.get("seq") if isinstance(msg.get("seq"), int) else None)


# ------------------------------------------------------------------ the socket
class BRTIRelay:
    """The relay on its own thread. ``latest`` is the last tick; ``on_tick(tick)`` is called for each."""

    def __init__(self, key_id: str | None = None, private_key=None, *, url: str = URL, sign_path: str | None = None,
                 on_tick=None, open_socket=None, clock=time.time, sleep=time.sleep, max_backoff: float = 30.0,
                 timeout: float = 30.0) -> None:
        self.key_id, self.private_key, self.url = key_id, private_key, url
        self.sign_path = sign_path or os.environ.get("KALSHI_WS_SIGN_PATH") or (urlsplit(url).path or "/")
        self.on_tick = on_tick
        self._open_socket = open_socket or (lambda: self._default_socket(timeout))
        self._clock, self._sleep, self.max_backoff = clock, sleep, max_backoff
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._ws = None
        self.latest: BRTITick | None = None
        self.msgs = self.ticks = self.reconnects = 0
        self.last_error = ""
        self._thread: threading.Thread | None = None

    @classmethod
    def from_env(cls, **kw) -> "BRTIRelay":
        key_id, pk = credentials_from_env()
        return cls(key_id, pk, **kw)

    def _default_socket(self, timeout: float):
        ws = WSClient(self.url, auth_headers(self.key_id, self.private_key, self.sign_path), timeout=timeout)
        ws.connect()
        return ws

    def start(self) -> "BRTIRelay":
        self._thread = threading.Thread(target=self.run, name="btc-brti", daemon=True)
        self._thread.start()
        return self

    def request_stop(self) -> None:
        self.stop.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except OSError:
                pass

    def live(self, now: float | None = None, within: float = 5.0) -> bool:
        t = self.latest
        if t is None:
            return False
        now = self._clock() if now is None else now
        return now - t.recv <= within

    def run(self) -> None:
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except (ConnectionClosed, OSError, ValueError, json.JSONDecodeError) as e:    # noqa: PERF203
                with self._lock:
                    self.last_error = f"{type(e).__name__}: {str(e)[:120]}"
                    self.reconnects += 1
                if self.stop.is_set():
                    return
                self._sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)

    def _session(self) -> None:
        ws = self._open_socket()
        with self._lock:
            self._ws = ws
        try:
            ws.send_json(SUBSCRIBE)
            while not self.stop.is_set():
                self.handle(ws.recv_json())
        finally:
            with self._lock:
                self._ws = None
            try:
                ws.close()
            except OSError:
                pass

    def handle(self, msg) -> None:
        now = self._clock()
        with self._lock:
            self.msgs += 1
        if isinstance(msg, dict) and msg.get("type") == "error":
            with self._lock:
                self.last_error = json.dumps(msg.get("msg"), default=str)[:120]
            return
        t = parse_tick(msg, now)
        if t is None:
            return
        with self._lock:
            self.latest = t
            self.ticks += 1
        if self.on_tick is not None:
            try:
                self.on_tick(t)
            except Exception:                                    # noqa: BLE001 -- a consumer error never drops the socket
                log.exception("brti tick handler")

    def counters(self, now: float | None = None) -> dict:
        now = self._clock() if now is None else now
        with self._lock:
            t = self.latest
            return {"messages": self.msgs, "ticks": self.ticks, "reconnects": self.reconnects, "live": self.live(now),
                    "last_tick_age_s": None if t is None else round(now - t.recv, 2),
                    "value": None if t is None else t.value, "avg_60s": None if t is None else t.avg_60s,
                    "last_60s_15m": None if t is None else t.last_60s_15m, "last_error": self.last_error}
