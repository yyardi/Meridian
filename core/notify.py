"""One door to the operator's phone, with a scope switch on it.

Why this exists: by 2026-09-18 seven different senders pushed to the same ntfy
topic -- the ladder executor's order tickets, the alerter's health checks
(which flap: DEAD, recovered, DEAD again), the EV guard, the retention job,
the venue alarm, the league-listing watcher and five nightly cron summaries.
The operator was getting five to seven summary pushes a day plus the health
flaps, and asked for TICKETS ONLY. Each sender had its own copy of the POST,
so "tickets only" could not be a setting; it had to be seven edits. Now every
Python sender calls `push(kind, ...)` here and every shell sender asks
`scripts/ntfy_allowed.py` first, and one variable decides what reaches the
phone:

    MERIDIAN_NTFY_SCOPE=tickets            # the default: order tickets only
    MERIDIAN_NTFY_SCOPE=tickets,health     # widen to health flaps too
    MERIDIAN_NTFY_SCOPE=all                # everything, the pre-switch behaviour

A push whose kind is outside the scope is not dropped: it is appended as one
JSON line to the muted log (`MERIDIAN_NTFY_MUTED_LOG`, default
`<repo>/artifacts/reads/ntfy_muted.log`, resolved from this file so the
caller's working directory never decides where the line lands), so widening
the scope later loses nothing and "did the retention job try to page me?" has
an answer on disk. Inside a container `<repo>` is the image (`/app`), which
vanishes on recreate: docker-compose.yml sets `MERIDIAN_NTFY_MUTED_LOG` on
the api and alerter services to the host-mounted
`/opt/meridian/artifacts/reads/ntfy_muted.log` for that reason.

The topic is a secret (anyone who knows it can read the pushes). It is read
from `MERIDIAN_NTFY_TOPIC`, never printed, never logged, never written to the
muted log. `push` never raises: a notification failure must not stop the
sampler, the alerter or the retention job that called it.

Transport is `urllib`, stdlib only, so the executor (which a test pins to
carry no HTTP client library) and the host-side cron scripts can share this
module. Title, priority and tags travel as URL query parameters rather than
headers: HTTP headers are latin-1 in `http.client`, and the first real digest
title carried an em dash -- the header form raised on encoding while the
caller marked the digest sent. Percent-encoded query parameters are UTF-8.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

#: Every kind a sender may name. `push` refuses (mutes) anything else, so a
#: typo in a caller cannot silently become an always-on channel.
KINDS = ("tickets", "schedule", "health", "nightly", "ev", "retention", "listing", "alarm")

#: "schedule" rides with "tickets" by default: it is one message a day
#: naming the slate, which is the thing the dashboard cannot tell the
#: operator because it only knows what is already running.
DEFAULT_SCOPE = "tickets,schedule"
DEFAULT_SERVER = "https://ntfy.sh"
#: Absolute on purpose (see the module docstring): `Path("artifacts/...")`
#: would put the line wherever the sender happened to be started from.
DEFAULT_MUTED_LOG = Path(__file__).resolve().parent.parent / "artifacts" / "reads" / "ntfy_muted.log"

SENT, MUTED, NO_TOPIC, FAILED = "sent", "muted", "no_topic", "failed"


def parse_scope(raw: str | None) -> frozenset[str]:
    """The comma list as a set. Empty/unset means the default; "all" means
    every kind. Unknown names are kept (harmless: nothing pushes under them)
    so a misspelling shows up in `scope()` rather than vanishing."""
    text = (raw if raw is not None else "").strip().strip('"').strip("'")
    if not text:
        text = DEFAULT_SCOPE
    parts = frozenset(p.strip().lower() for p in text.split(",") if p.strip())
    if "all" in parts:
        return frozenset(KINDS)
    return parts


def scope() -> frozenset[str]:
    return parse_scope(os.environ.get("MERIDIAN_NTFY_SCOPE"))


def allowed(kind: str) -> bool:
    """True when a push of this kind reaches the phone under the current scope."""
    return kind in KINDS and kind in scope()


def muted_log_path() -> Path:
    override = (os.environ.get("MERIDIAN_NTFY_MUTED_LOG") or "").strip()
    return Path(override) if override else DEFAULT_MUTED_LOG


def _topic() -> str:
    return (os.environ.get("MERIDIAN_NTFY_TOPIC") or "").strip().strip('"').strip("'")


def _record_muted(kind: str, title: str, body: str) -> None:
    """One JSON line per muted push. Best effort: an unwritable log is not a
    reason to fail the caller (the push was going to be dropped anyway)."""
    line = json.dumps({
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "title": title,
        "body": body[:400],
    }, ensure_ascii=False)
    try:
        path = muted_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 -- see docstring
        return


def push(kind: str, title: str, body: str, *, priority: int | str | None = None,
         tags: str | list[str] | None = None, server: str | None = None,
         timeout: float = 20.0) -> str:
    """Send one notification, or record why it was not sent.

    Returns one of "sent" | "muted" | "no_topic" | "failed". Never raises and
    never prints. `priority` is ntfy's 1..5 or one of its names; `tags` is a
    comma string or a list.
    """
    try:
        if not allowed(kind):
            _record_muted(kind, title, body)
            return MUTED
        topic = _topic()
        if not topic:
            return NO_TOPIC
        base = (server or os.environ.get("MERIDIAN_NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
        params: dict[str, str] = {"title": title}
        if priority is not None:
            params["priority"] = str(priority)
        if tags:
            params["tags"] = tags if isinstance(tags, str) else ",".join(tags)
        url = f"{base}/{topic}?{urlencode(params)}"
        req = Request(url, data=body.encode("utf-8"), method="POST")
        urlopen(req, timeout=timeout).read()
        return SENT
    except Exception:  # noqa: BLE001 -- a notification failure stops nothing
        return FAILED
