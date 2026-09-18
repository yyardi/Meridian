"""A minimal RFC 6455 WebSocket client for the Polymarket US markets stream.

Why this exists rather than `websockets`: the production api image carries
httpx/anyio/cryptography and no WebSocket library, and the first use of the
stream is a one-night, read-only measurement (does the REST book lag the
stream?). Eighty lines of stdlib beats a dependency change on a slate night.

The venue (docs.polymarket.us, read 2026-09-18):

    wss://api.polymarket.us/v1/ws/markets      X-PM-Access-Key / X-PM-Timestamp /
                                               X-PM-Signature over  ts + "GET" + path
    subscribe -> {"subscribe": {"requestId", "subscriptionType", "marketSlugs"}}
    MARKET_DATA messages carry a full book + stats + transactTime per market;
    TRADE messages carry price / quantity / tradeTime / maker+taker intents.

Text frames only; the client masks (as RFC 6455 requires of clients), answers
pings with pongs, reassembles continuation frames, and raises
:class:`ConnectionClosed` on a close frame or a dead socket. Nothing here can
place an order: the private stream is a different path and is never opened.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
from typing import Callable
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class ConnectionClosed(Exception):
    pass


def accept_key(client_key: str) -> str:
    """The Sec-WebSocket-Accept a compliant server must return (RFC 6455 §4.2.2)."""
    return base64.b64encode(hashlib.sha1((client_key + GUID).encode()).digest()).decode()


def encode_frame(opcode: int, payload: bytes, mask: bool = True) -> bytes:
    """One unfragmented frame. Clients MUST mask; the mask is random per frame."""
    head = bytes([0x80 | (opcode & 0x0F)])
    n = len(payload)
    mbit = 0x80 if mask else 0
    if n < 126:
        head += bytes([mbit | n])
    elif n < 65536:
        head += bytes([mbit | 126]) + struct.pack("!H", n)
    else:
        head += bytes([mbit | 127]) + struct.pack("!Q", n)
    if not mask:
        return head + payload
    key = os.urandom(4)
    return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def read_frame(read_exact: Callable[[int], bytes]) -> tuple[bool, int, bytes]:
    """(fin, opcode, payload) from a byte source. Unmasks if the server masked."""
    b0, b1 = read_exact(2)
    fin, opcode = bool(b0 & 0x80), b0 & 0x0F
    masked, n = bool(b1 & 0x80), b1 & 0x7F
    if n == 126:
        (n,) = struct.unpack("!H", read_exact(2))
    elif n == 127:
        (n,) = struct.unpack("!Q", read_exact(8))
    key = read_exact(4) if masked else b""
    data = read_exact(n) if n else b""
    if masked:
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return fin, opcode, data


class WSClient:
    """Blocking client. `recv_json()` yields the next text message as a dict,
    transparently answering pings; everything else raises."""

    def __init__(self, url: str, headers: dict[str, str], timeout: float = 60.0) -> None:
        self.url, self.headers, self.timeout = url, dict(headers), timeout
        self._sock: ssl.SSLSocket | None = None
        self._buf = b""

    # -- lifecycle ----------------------------------------------------------
    def connect(self) -> None:
        u = urlsplit(self.url)
        host, port = u.hostname, u.port or (443 if u.scheme == "wss" else 80)
        path = u.path or "/"
        raw = socket.create_connection((host, port), timeout=self.timeout)
        self._sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        lines += [f"{k}: {v}" for k, v in self.headers.items()]
        self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionClosed("handshake: socket closed")
            head += chunk
        head, _, rest = head.partition(b"\r\n\r\n")
        self._buf = rest
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status:
            raise ConnectionClosed(f"handshake refused: {status[:80]}")
        hdrs = {k.strip().lower(): v.strip() for k, _, v in
                (ln.decode(errors="replace").partition(":") for ln in head.split(b"\r\n")[1:])}
        if hdrs.get("sec-websocket-accept") != accept_key(key):
            raise ConnectionClosed("handshake: bad Sec-WebSocket-Accept")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.sendall(encode_frame(OP_CLOSE, struct.pack("!H", 1000)))
            except OSError:
                pass
            try:
                self._sock.close()
            finally:
                self._sock = None

    # -- io -----------------------------------------------------------------
    def _read_exact(self, n: int) -> bytes:
        assert self._sock is not None
        while len(self._buf) < n:
            chunk = self._sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise ConnectionClosed("socket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send_text(self, text: str) -> None:
        assert self._sock is not None
        self._sock.sendall(encode_frame(OP_TEXT, text.encode()))

    def send_json(self, obj: dict) -> None:
        self.send_text(json.dumps(obj, separators=(",", ":")))

    def recv_text(self) -> str:
        parts: list[bytes] = []
        while True:
            fin, op, data = read_frame(self._read_exact)
            if op == OP_PING:
                self._sock.sendall(encode_frame(OP_PONG, data))          # type: ignore[union-attr]
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                raise ConnectionClosed("server closed")
            if op in (OP_TEXT, OP_BIN, OP_CONT):
                parts.append(data)
                if fin:
                    msg, parts = b"".join(parts), []
                    return msg.decode("utf-8", errors="replace")

    def recv_json(self) -> dict:
        return json.loads(self.recv_text())
