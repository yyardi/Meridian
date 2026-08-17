"""HTTP clients for Polymarket US.

Two clients live here, and the split is deliberate:

:class:`PolymarketGatewayClient`
    Public data only — no API key, no signing. This is what the recorder uses,
    and it is the entire data layer.

:class:`PolymarketAuthedClient`
    **Read-only** L2-signed requests to the authenticated host. It exposes
    ``get`` and nothing else: there is no post, no put, no delete, so an order
    is not something you are discouraged from placing here — it is not
    expressible. Same principle as the hardcoded order type in
    :mod:`core.executor`.

Design notes
------------
*Synchronous by choice.* A full WNBA slate is ~150 requests; at 10 req/s that
is ~15 seconds per cycle, which is irrelevant for a job that runs every 15
minutes. Async would be faster and strictly more failure modes for a process
whose primary requirement is surviving unattended for months.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from cryptography.hazmat.primitives.asymmetric import ed25519
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import RECORDER, RecorderConfig
from core.polymarket.schemas import BookResponse, EventsResponse
from core.ratelimit import TokenBucket

log = structlog.get_logger(__name__)


class RateLimitedError(Exception):
    """HTTP 429 — a genuine rate limit, worth backing off for."""


class TransientHTTPError(Exception):
    """5xx or network error — retryable."""


class PolymarketGatewayClient:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RECORDER
        self._bucket = TokenBucket(self.config.requests_per_second, self.config.burst_capacity)
        self._client = httpx.Client(
            base_url=self.config.gateway_base_url,
            timeout=httpx.Timeout(self.config.http_timeout_seconds),
            headers={"User-Agent": "meridian-recorder/0.1 (+research)"},
            follow_redirects=True,
        )

    def __enter__(self) -> PolymarketGatewayClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((RateLimitedError, TransientHTTPError)),
            reraise=True,
        )
        def _do() -> dict[str, Any]:
            waited = self._bucket.acquire()
            if waited > 0.5:
                log.debug("rate_limit_wait", seconds=round(waited, 2), path=path)
            try:
                resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise TransientHTTPError(str(exc)) from exc

            if resp.status_code == 429:
                # Docs: stop, wait >= 1s, exponential backoff, max 3 retries.
                raise RateLimitedError(f"429 on {path}")
            if resp.status_code >= 500:
                raise TransientHTTPError(f"{resp.status_code} on {path}")
            resp.raise_for_status()
            return resp.json()

        return _do()

    def get_league_events(self, league: str | None = None, limit: int | None = None) -> tuple[
        EventsResponse, dict[str, Any]
    ]:
        """Fetch the whole league board in one request.

        Returns (parsed, raw_json) so the raw payload can be persisted verbatim —
        reparsing stored JSON later beats re-fetching data that no longer exists.
        """
        league = league or self.config.league_slug
        limit = limit or self.config.event_limit
        raw = self._get(f"/v2/leagues/{league}/events", params={"limit": limit})
        return EventsResponse.model_validate(raw), raw

    def get_book(self, market_slug: str) -> tuple[BookResponse, dict[str, Any]]:
        raw = self._get(f"/v1/markets/{market_slug}/book")
        return BookResponse.model_validate(raw), raw

    def get_settlement(self, market_slug: str) -> dict[str, Any]:
        """Free, unauthenticated resolution label: {"slug": ..., "settlement": 0|1}."""
        return self._get(f"/v1/markets/{market_slug}/settlement")


# --------------------------------------------------------------------------- #
# Request signing — TWO SCHEMES, and the venue uses the second one
# --------------------------------------------------------------------------- #
#
# This is the single most expensive fact in this module, so it is stated first.
#
# **Polymarket International CLOB** (`clob.polymarket.com`), the scheme in
# docs.polymarket.com/developers/CLOB/authentication — five headers,
# HMAC-SHA256, seconds:
#
#     POLY_ADDRESS · POLY_API_KEY · POLY_PASSPHRASE · POLY_TIMESTAMP
#     POLY_SIGNATURE = HMAC-SHA256(timestamp + METHOD + path + body)
#
# **Polymarket US** (`api.polymarket.us`), the CFTC-regulated venue this repo
# actually trades — three headers, **Ed25519**, **milliseconds**:
#
#     X-PM-Access-Key · X-PM-Timestamp
#     X-PM-Signature  = Ed25519_sign(timestamp + METHOD + path)
#
# They share a message layout and nothing else. There is no passphrase, no
# Polygon address, and no HMAC. The L2/HMAC implementation below is retained
# because it is correct for the international CLOB and its trap analysis is
# worth keeping — but it will never authenticate against Polymarket US, and
# `PolymarketAuthedClient` deliberately does not use it.
#
# How this was established, since `docs/math/write-latency.md` records six
# earlier attempts that could not distinguish these cases: the 401 body
# `Missing required API key headers` is returned for every path, every header
# set, and every signature — including a request carrying all five correct
# POLY_* header names. It is therefore not evidence about signing at all. The
# discriminator was the CORS preflight, which `api.polymarket.us` answers with
# a fixed server-declared allowlist naming the headers it actually accepts.

#: Polymarket International CLOB. Present for completeness; not used here.
L2_HEADERS = (
    "POLY_ADDRESS",
    "POLY_API_KEY",
    "POLY_PASSPHRASE",
    "POLY_TIMESTAMP",
    "POLY_SIGNATURE",
)

#: Polymarket US. These are the headers that authenticate.
US_HEADERS = ("X-PM-Access-Key", "X-PM-Timestamp", "X-PM-Signature")

#: The venue rejects a timestamp more than 30s from its own clock. Worth
#: knowing before blaming a signature: clock skew and a bad key look identical
#: from the outside except for the error string.
US_TIMESTAMP_TOLERANCE_SECONDS = 30


def _b64_decode_secret(secret: str) -> bytes:
    """Decode an API secret with the **URL-safe** base64 alphabet.

    This is trap #1, and it fails silently rather than loudly. Python's
    ``b64decode`` ignores characters outside its alphabet instead of raising,
    so a secret containing ``-`` or ``_`` decodes to a *shorter, different* key
    with no error at all::

        b64decode("a-b_cd==").hex()          -> '69b71d'    (3 bytes, wrong)
        urlsafe_b64decode("a-b_cd==").hex()  -> '6be6ff71'  (4 bytes, right)

    URL-safe decoding is the universally correct choice, not merely the safer
    one: it translates ``-_`` to ``+/`` and leaves ``+/`` untouched, so it
    decodes secrets in *either* alphabet identically. There is no case where
    standard decoding is right and this is wrong.

    Decoding is **strict**. ``base64.urlsafe_b64decode`` discards characters
    outside its alphabet rather than raising, so a truncated or corrupted
    secret decodes to plausible-looking nonsense::

        urlsafe_b64decode("not valid base64 !!!! sekrit") -> 15 bytes, no error

    That is the same silent-wrong-key failure as the alphabet trap, arriving by
    a different route, so it is rejected rather than tolerated.
    """
    # Tolerate wrapping and a trailing newline from a copy-paste, then the
    # missing '=' padding that dashboards often strip. Both are formatting;
    # anything else is corruption.
    cleaned = "".join(secret.split())
    translated = cleaned.replace("-", "+").replace("_", "/")
    padded = translated + "=" * (-len(translated) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        # str(exc) describes the *shape* of the failure, never the secret.
        raise ValueError(f"POLYMARKET_SECRET_KEY is not valid base64: {exc}") from None


def build_hmac_signature(
    secret: str,
    timestamp: str,
    method: str,
    request_path: str,
    body: str = "",
) -> str:
    """Sign one request. HMAC-SHA256, URL-safe base64 **with** padding.

    ``body`` is a :class:`str` and is signed **verbatim**, which is trap #2.
    Polymarket's own Python client takes ``body`` as an arbitrary object and
    does ``str(body).replace("'", '"')`` to fake JSON out of a dict repr. That
    is wrong twice: it is not JSON (it mangles apostrophes inside string
    values), and it is a *second* serialisation, so the bytes signed are not
    the bytes sent and the venue returns 401.

    The fix is structural rather than careful: this function will not accept a
    dict, so the caller is forced to serialise once and pass the same string it
    sends. See :meth:`PolymarketAuthedClient.get`, which sends no body at all.

    ``request_path`` is the path only — no query string. The reference client
    signs the endpoint and appends params afterwards, so a signed query string
    would itself be a mismatch.

    ``method`` is signed **verbatim**, not upper-cased. The docs say "uppercase
    HTTP method" and callers here pass ``"GET"``, so the two agree — but the
    reference client applies no casing transform, and its published test vector
    signs the method ``test-sign``. Upper-casing would be a normalisation the
    server does not perform, and reproducing its vector exactly is the only
    evidence we have that this implementation matches the thing that verifies
    it. Pass uppercase; this will not do it for you.
    """
    if not isinstance(body, str):
        raise TypeError(
            "body must be an already-serialised str, not "
            f"{type(body).__name__} — serialise once, sign that string, send "
            "that string (see the docstring)"
        )

    message = f"{timestamp}{method}{request_path}{body}"
    digest = hmac.new(
        _b64_decode_secret(secret), message.encode("utf-8"), hashlib.sha256
    ).digest()
    # urlsafe_b64encode emits padding; the docs specify "urlsafeBase64WithPadding".
    return base64.urlsafe_b64encode(digest).decode("ascii")


# --------------------------------------------------------------------------- #
# Polymarket US — Ed25519. This is the one that works.
# --------------------------------------------------------------------------- #


def build_ed25519_signature(
    secret: str, timestamp: str, method: str, request_path: str
) -> str:
    """Sign one Polymarket US request. Ed25519, standard base64.

    ``secret`` is a standard-base64 64-byte Ed25519 private key: bytes 0..31
    are the seed, bytes 32..63 are the public key. Only the seed is used —
    passing all 64 bytes to ``from_private_bytes`` raises.

    That layout is checkable, and :func:`verify_key_material` checks it, which
    is worth more than it sounds: re-deriving the public key from the seed and
    comparing it to bytes 32..63 confirms the secret is an intact Ed25519 key
    before a single request goes out. A truncated or misparsed key fails that
    comparison locally instead of arriving as an indistinguishable 401.

    There is **no body term.** Polymarket US signs ``timestamp + METHOD + path``
    only. This client is read-only, so the question is academic here, but it is
    a real difference from the CLOB scheme and not an omission.

    Both base64 operations are the *standard* alphabet, per the venue's own
    sample. The URL-safe trap that governs :func:`build_hmac_signature` does
    not apply — but note the two functions are not interchangeable in either
    direction.
    """
    raw = _b64_decode_secret(secret)
    if len(raw) < 32:
        raise ValueError(
            f"Ed25519 secret decodes to {len(raw)} bytes; need at least 32"
        )
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])
    message = f"{timestamp}{method}{request_path}".encode()
    return base64.b64encode(private_key.sign(message)).decode("ascii")


def verify_key_material(secret: str) -> bool:
    """True if the secret is an intact 64-byte Ed25519 key.

    Checks that the public key derived from the seed matches the copy stored in
    bytes 32..63. Catches a truncated or mis-decoded secret locally, before it
    becomes a 401 that looks exactly like every other 401.
    """
    raw = _b64_decode_secret(secret)
    if len(raw) != 64:
        return False
    derived = (
        ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])
        .public_key()
        .public_bytes_raw()
    )
    return hmac.compare_digest(derived, raw[32:64])


@dataclass(frozen=True)
class USCredentials:
    """Polymarket US credentials: a key id and a secret. **Env only, never logged.**

    Two values, not four — there is no passphrase and no signer address in this
    scheme. `.env` already carries both under their existing names.
    """

    key_id: str
    secret: str

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> USCredentials:
        src = os.environ if env is None else env
        values = {
            "key_id": (src.get("POLYMARKET_KEY_ID") or "").strip(),
            "secret": (src.get("POLYMARKET_SECRET_KEY") or "").strip(),
        }
        names = {"key_id": "POLYMARKET_KEY_ID", "secret": "POLYMARKET_SECRET_KEY"}
        missing = [names[k] for k, v in values.items() if not v]
        if missing:
            raise MissingCredentialsError(missing)
        return USCredentials(**values)

    def fingerprint(self) -> dict[str, str]:
        """Safe-to-log identity: lengths and a truncated SHA-256. Enough to
        answer "same key as last time?", not enough to reconstruct anything."""
        return {
            "key_id_len": str(len(self.key_id)),
            "secret_len": str(len(self.secret)),
            "secret_sha256_8": hashlib.sha256(self.secret.encode()).hexdigest()[:8],
        }

    def __repr__(self) -> str:                      # pragma: no cover - trivial
        return "USCredentials(<redacted>)"

    __str__ = __repr__


def us_auth_headers(
    creds: USCredentials,
    method: str,
    request_path: str,
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Build the three Polymarket US headers. ``timestamp_ms`` is injectable
    for deterministic tests; production passes nothing."""
    ts = str(int(time.time() * 1000) if timestamp_ms is None else timestamp_ms)
    return {
        "X-PM-Access-Key": creds.key_id,
        "X-PM-Timestamp": ts,
        "X-PM-Signature": build_ed25519_signature(creds.secret, ts, method, request_path),
    }


# --------------------------------------------------------------------------- #
# Polymarket International CLOB — HMAC. Retained, not used against the US venue.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class L2Credentials:
    """Credentials for L2 signing. **From env only, never logged.**

    ``__repr__`` is overridden because a frozen dataclass would otherwise print
    the secret in any traceback that happens to include this object — which is
    exactly the accident `docs/stack/structlog.md` forbids.
    """

    address: str
    api_key: str
    passphrase: str
    secret: str

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> L2Credentials:
        """Load from the environment, raising a message that names only *which*
        variables are missing and never what any of them contain."""
        src = os.environ if env is None else env
        values = {
            "address": (src.get("POLYMARKET_ADDRESS") or "").strip(),
            "api_key": (src.get("POLYMARKET_KEY_ID") or "").strip(),
            "passphrase": (src.get("POLYMARKET_PASSPHRASE") or "").strip(),
            "secret": (src.get("POLYMARKET_SECRET_KEY") or "").strip(),
        }
        missing = [k for k, v in values.items() if not v]
        if missing:
            names = {
                "address": "POLYMARKET_ADDRESS",
                "api_key": "POLYMARKET_KEY_ID",
                "passphrase": "POLYMARKET_PASSPHRASE",
                "secret": "POLYMARKET_SECRET_KEY",
            }
            raise MissingCredentialsError([names[k] for k in missing])
        return L2Credentials(**values)

    def fingerprint(self) -> dict[str, str]:
        """Safe-to-log identity of the credentials: lengths and a truncated
        SHA-256. Enough to tell "did the key change?" from "is it the same key
        failing?", and not enough to reconstruct anything."""
        def fp(value: str) -> str:
            return hashlib.sha256(value.encode()).hexdigest()[:8]

        return {
            "address_len": str(len(self.address)),
            "api_key_len": str(len(self.api_key)),
            "passphrase_len": str(len(self.passphrase)),
            "secret_len": str(len(self.secret)),
            "secret_sha256_8": fp(self.secret),
            "api_key_sha256_8": fp(self.api_key),
        }

    def __repr__(self) -> str:                      # pragma: no cover - trivial
        return "L2Credentials(<redacted>)"

    __str__ = __repr__


class MissingCredentialsError(RuntimeError):
    """Raised when the env does not carry all four credential values.

    Kept distinct from an auth *failure*: not having a passphrase and having a
    rejected passphrase are different findings, and collapsing them is how a
    probe reports "401, signature must be wrong" when nothing was ever signed.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__("missing credentials in env: " + ", ".join(missing))


def l2_headers(
    creds: L2Credentials,
    method: str,
    request_path: str,
    body: str = "",
    timestamp: int | None = None,
) -> dict[str, str]:
    """Build all five headers for one request.

    ``timestamp`` is injectable so tests are deterministic; production passes
    nothing and gets ``time.time()``.
    """
    ts = str(int(time.time()) if timestamp is None else timestamp)
    return {
        "POLY_ADDRESS": creds.address,
        "POLY_API_KEY": creds.api_key,
        "POLY_PASSPHRASE": creds.passphrase,
        "POLY_TIMESTAMP": ts,
        "POLY_SIGNATURE": build_hmac_signature(
            creds.secret, ts, method, request_path, body
        ),
    }


#: Everything except the timestamp. Signatures are masked too: a signature is
#: not the secret, but it is a valid credential for one request and there is no
#: reason to write one to disk. The timestamp is the one field worth reading
#: back, because clock skew is a real failure mode here.
_UNMASKED_HEADERS = {"POLY_TIMESTAMP", "X-PM-Timestamp"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Headers with every credential-bearing value masked, for logs and reports.

    Default-deny: anything not explicitly listed as safe is masked, so a header
    added later is redacted until someone decides otherwise.
    """
    return {
        k: (v if k in _UNMASKED_HEADERS else f"<{len(v)} chars, redacted>")
        for k, v in headers.items()
    }


@dataclass
class AuthedResponse:
    """One signed-request result, including the timing that motivated the probe.

    ``body_text`` is the **complete** response body. It used to be truncated
    to 2000 characters — harmless while the only consumer was a probe printing
    excerpts, and silently fatal the moment the fill watcher tried to
    ``json.loads`` an activities page that runs tens of KB: every parse failed,
    so no fill was ever reconciled and no pre-authorized exit ever fired.
    Truncation is display's job; every log/persist site already slices.
    """

    method: str
    path: str
    status_code: int
    elapsed_ms: float
    body_text: str
    request_headers: dict[str, str]     # already redacted
    response_headers: dict[str, str]

    @property
    def server_latency_ms(self) -> float | None:
        """Venue-side processing time, from the `x-pm-server-latency` response
        header the venue sets on every response.

        This is worth more than the round-trip. `docs/math/write-latency.md`
        records venue processing as unmeasurable without placing an order —
        true for *writes*, but the venue reports its own read-side processing
        for free, which splits our round-trip into network and venue terms.
        """
        raw = self.response_headers.get("x-pm-server-latency")
        try:
            return float(raw) if raw is not None else None
        except ValueError:
            return None


class PolymarketAuthedClient:
    """Read-only Ed25519-signed client for Polymarket US.

    **GET is the only verb it can express.** No order is placed, modified or
    cancelled by anything here, and there is no code path that could:
    ``httpx.Client.get`` is the single call site in the class. Same principle
    as the hardcoded order type in :mod:`core.executor` — not a rule you are
    asked to follow, a thing you cannot write.
    """

    def __init__(
        self,
        creds: USCredentials,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.creds = creds
        self.base_url = (
            base_url
            or os.environ.get("POLYMARKET_API_URL")
            or "https://api.polymarket.us"
        ).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "meridian-research/0.1 (+read-only)"},
            follow_redirects=False,   # a redirect would re-send a stale signature
        )

    def __enter__(self) -> PolymarketAuthedClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(
        self,
        path: str,
        timestamp_ms: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> AuthedResponse:
        """Signed GET. Returns the response rather than raising on 4xx, because
        the status *is* the measurement here.

        No retry and no rate-limit wait: this measures latency, and a retried
        request reports the wrong number. Each call signs its own fresh
        timestamp — a signature is valid for one request within a 30s window,
        so a cached header set silently expires mid-measurement.

        ``params`` are sent but **not signed** — the venue signs the path only
        (verified live 2026-08-06: ``?limit=100&cursor=...`` on a signature
        over the bare path returns 200 and honours both parameters).
        """
        headers = us_auth_headers(self.creds, "GET", path, timestamp_ms)
        started = time.perf_counter()
        resp = self._client.get(path, params=params, headers=headers)
        elapsed_ms = (time.perf_counter() - started) * 1000

        result = AuthedResponse(
            method="GET",
            path=path,
            status_code=resp.status_code,
            elapsed_ms=elapsed_ms,
            body_text=resp.text,
            request_headers=redact_headers(headers),
            response_headers=dict(resp.headers),
        )
        log.info(
            "authed_read",
            path=path,
            status=resp.status_code,
            elapsed_ms=round(elapsed_ms, 1),
            server_ms=result.server_latency_ms,
            **self.creds.fingerprint(),
        )
        return result


# --------------------------------------------------------------------------- #
# Order submission — the one class in this repo that can move money
# --------------------------------------------------------------------------- #

#: Venue path for order submission.
ORDERS_PATH = "/v1/orders"

#: The venue's regulatory flag for an order a human entered by hand. Polymarket
#: US is CFTC-regulated and this field is not decorative: every order this
#: system sends is, by construction, one a human clicked a button to send, so
#: the truthful value is the constant one. There is no automated counterpart
#: here to select.
MANUAL_ORDER_INDICATOR = "MANUAL_ORDER_INDICATOR_MANUAL"


class OrderSubmissionError(RuntimeError):
    """Submission failed before or during the request. Nothing was accepted."""


class PolymarketOrderClient:
    """Ed25519-signed **order submission**. Deliberately a separate class.

    `PolymarketAuthedClient` above exposes `get` and `close` and nothing else,
    and that is load-bearing — the recorder, the probe and every read path use
    it and cannot place an order even by accident. Widening it with a `post`
    would spend that guarantee for every caller at once. So the ability to
    write lives here, in a class nothing imports except the human-confirm
    endpoint.

    What this class does **not** do, on purpose:

    * No modify. `submit_limit_order` and `cancel_order` are the only verbs —
      cancellation was added 2026-08-07 for the human cancel button (V21),
      and amending an order remains inexpressible.
    * No market orders. The payload's order type is a constant read from
      `core.executor`, not a parameter.
    * No retry. A retried POST is how one click becomes two orders. The
      idempotency key would probably save us; "probably" is the wrong standard
      for order submission, so the caller sees the failure instead. A cancel
      is not retried either: its response IS the V21 measurement, and a human
      can click again.
    """

    def __init__(
        self,
        creds: USCredentials,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.creds = creds
        self.base_url = (
            base_url
            or os.environ.get("POLYMARKET_API_URL")
            or "https://api.polymarket.us"
        ).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "meridian-human-confirm/0.1"},
            follow_redirects=False,   # a redirect would re-send a stale signature
        )

    def __enter__(self) -> PolymarketOrderClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def submit_limit_order(self, payload: dict[str, Any]) -> AuthedResponse:
        """POST one limit order. Returns the response; does not raise on 4xx.

        **Body signing is the one unverified part of this scheme, and it fails
        safe.** The authentication docs give the signed message as
        ``timestamp + METHOD + path`` with no body term, and say nothing about
        POST specifically. If they are wrong, the venue answers 401
        `Invalid API key signature` and **no order is placed** — a wrong guess
        here cannot leak an order, it can only refuse one. Rather than burn a
        human's first click on finding out, this method signs per the docs and,
        on exactly that error, retries once with the serialised body appended.

        The retry is safe for the same reason the guess is: a 401 is a
        definitive not-accepted, and the idempotency key is identical across
        both attempts, so the venue would reject a duplicate even if the first
        had somehow landed.

        The body is serialised **once**, into a string that is both signed and
        sent — the trap that produced 401s in Polymarket's own Python client
        (see `build_hmac_signature`). `httpx` is handed `content=`, not
        `json=`, so it cannot re-serialise behind our back.
        """
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        result = self._post_signed(body, sign_body=False)
        if result.status_code == 401 and "signature" in result.body_text.lower():
            log.warning(
                "order_signature_rejected_retrying_with_body",
                path=ORDERS_PATH,
                note="signing timestamp+METHOD+path was rejected; "
                     "retrying with the body appended to the signed message",
            )
            result = self._post_signed(body, sign_body=True)
        return result

    def cancel_order(self, venue_order_id: str) -> AuthedResponse:
        """DELETE one resting order by its venue id. **Endpoint UNVERIFIED.**

        No cancel has ever been sent by this system, the venue's docs are not
        trusted on paths (C10), and the read side of ``/v1/orders/{id}`` is a
        404 even authenticated (V19) — so ``DELETE /v1/orders/{id}`` is the
        REST-convention guess, built dark and awaiting one live verification
        against a 1-share resting order. Whatever comes back — 2xx ack, 404,
        405, 501 — is returned to the caller verbatim and recorded in
        ``orders.cancel_response``; that body is what findings **V21** gets
        written from.

        Fails safe in every branch: a wrong path cannot cancel the wrong
        thing (the id names one order), cannot place anything (no body, no
        order terms), and is not retried (the response is the measurement; a
        human can click again).

        Signed like every other request: Ed25519 over ``ts + METHOD + path``,
        no body term.
        """
        path = f"{ORDERS_PATH}/{venue_order_id}"
        ts = str(int(time.time() * 1000))
        headers = {
            "X-PM-Access-Key": self.creds.key_id,
            "X-PM-Timestamp": ts,
            "X-PM-Signature": build_ed25519_signature(
                self.creds.secret, ts, "DELETE", path
            ),
        }
        started = time.perf_counter()
        try:
            resp = self._client.delete(path, headers=headers)
        except httpx.HTTPError as exc:
            raise OrderSubmissionError(
                f"transport error cancelling {venue_order_id} — state at the "
                f"venue is UNKNOWN, check the app before assuming either way: {exc}"
            ) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000

        result = AuthedResponse(
            method="DELETE",
            path=path,
            status_code=resp.status_code,
            elapsed_ms=elapsed_ms,
            body_text=resp.text,
            request_headers=redact_headers(headers),
            response_headers=dict(resp.headers),
        )
        log.info(
            "order_cancel_requested",
            venue_order_id=venue_order_id,
            status=resp.status_code,
            elapsed_ms=round(elapsed_ms, 1),
            server_ms=result.server_latency_ms,
            **self.creds.fingerprint(),
        )
        return result

    def _post_signed(self, body: str, *, sign_body: bool) -> AuthedResponse:
        """One signed POST. `body` is sent verbatim as the request content."""
        ts = str(int(time.time() * 1000))
        message_body = body if sign_body else ""
        headers = {
            "X-PM-Access-Key": self.creds.key_id,
            "X-PM-Timestamp": ts,
            "X-PM-Signature": build_ed25519_signature(
                self.creds.secret, ts, "POST", ORDERS_PATH + message_body
            ),
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        try:
            resp = self._client.post(ORDERS_PATH, content=body, headers=headers)
        except httpx.HTTPError as exc:
            # A transport failure is genuinely ambiguous: the order may or may
            # not have reached the venue. Say so rather than implying it did not.
            raise OrderSubmissionError(
                f"transport error submitting order — state at the venue is "
                f"UNKNOWN, reconcile against GET {ORDERS_PATH} before retrying: {exc}"
            ) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000

        result = AuthedResponse(
            method="POST",
            path=ORDERS_PATH,
            status_code=resp.status_code,
            elapsed_ms=elapsed_ms,
            body_text=resp.text,   # complete; consumers truncate for display
            request_headers=redact_headers(headers),
            response_headers=dict(resp.headers),
        )
        log.info(
            "order_submitted",
            status=resp.status_code,
            elapsed_ms=round(elapsed_ms, 1),
            server_ms=result.server_latency_ms,
            signed_with_body=sign_body,
            **self.creds.fingerprint(),
        )
        return result
