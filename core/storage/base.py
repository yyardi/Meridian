"""Database engine, session factory, and declarative base.

`DATABASE_URL` comes from the environment — never hardcoded. Stock Postgres
only, so this connects identically to local Docker, Supabase Pro, AWS RDS, or
a small Hetzner box.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


#: Supabase's two pooler ports, and why the distinction matters here.
#:
#: 5432 is **session mode**: one client holds one real Postgres connection for
#: its whole life, and the project is capped at 15 clients *in total*. With four
#: containers plus the dashboard plus an ad-hoc query, that ceiling is reached
#: and the losers get EMAXCONNSESSION — which is exactly what stopped the
#: live-odds recorder from starting.
#:
#: 6543 is **transaction mode**: a connection is borrowed only for the duration
#: of a statement, so hundreds of clients share a small server-side pool.
#: Measured: 12 concurrent connections opened without complaint.
#:
#: The catch is that transaction mode cannot hold session state — no prepared
#: statements (psycopg caches them by default, hence `prepare_threshold=None`)
#: and no advisory locks, which Alembic uses. So **migrations must keep using
#: session mode**. They do, because Alembic reads `get_database_url()` directly
#: while everything else goes through `get_engine()`.
SESSION_POOLER_PORT = ":5432/"
TRANSACTION_POOLER_PORT = ":6543/"

#: Only Supabase runs a second pooler on 6543. Every other Postgres — including
#: the local container the live recorder writes to — listens on 5432 and nothing
#: else, so rewriting its port points the writer at a closed door. Matching on
#: the port alone silently killed the 200ms recorder for 23 hours: it logged
#: `Connection refused` on every tick and no other component noticed.
SUPABASE_POOLER_HOSTS = ("pooler.supabase.com", "supabase.co")


def get_database_url() -> str:
    """Read DATABASE_URL from the environment, falling back to local Docker.

    Deliberately *not* rewritten to the transaction pooler: Alembic calls this,
    and migrations need session mode for advisory locks.
    """
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _use_transaction_pooler() -> bool:
    return os.environ.get("MERIDIAN_TX_POOLER", "").strip().lower() in {"1", "true", "yes"}


def app_database_url(url: str | None = None) -> str:
    """The URL long-lived app processes should use.

    Rewrites Supabase's session port to the transaction port when
    `MERIDIAN_TX_POOLER` is set. Opt-in rather than automatic because it
    silently changes connection semantics, and anything holding session state
    would break in ways that look like flaky networking.
    """
    url = url or get_database_url()
    if not _use_transaction_pooler():
        return url
    if SESSION_POOLER_PORT not in url:
        return url
    if not any(host in url for host in SUPABASE_POOLER_HOSTS):
        # A local or self-hosted Postgres. It has no 6543 listener.
        return url
    return url.replace(SESSION_POOLER_PORT, TRANSACTION_POOLER_PORT)


class Base(DeclarativeBase):
    """Declarative base for all Meridian ORM models."""


#: Connections this process may hold. SQLAlchemy defaults to pool_size=5 with
#: max_overflow=10, i.e. **15 per engine** — and Supabase's session-mode pooler
#: allows 15 *in total, across every client*. Three containers on the defaults
#: can therefore exhaust the whole allowance on their own, which is exactly what
#: happened once the live recorder moved to a 1s loop with a background depth
#: thread: the long-lived processes kept their connections and everything else
#: (the scheduler, ad-hoc queries) started failing with EMAXCONNSESSION.
#:
#: Two connections is enough for the busiest process here — the live recorder's
#: price loop plus its depth thread — and the single overflow covers a brief
#: handover rather than a third concurrent worker.
DEFAULT_POOL_SIZE = 2
DEFAULT_MAX_OVERFLOW = 1


#: Engines are shared per (url, options), not created per caller.
#:
#: Every job class does `get_sessionmaker(get_engine())` in its constructor, and
#: the scheduler constructs `PredictionLogger()`, `ESPNOddsFetcher()` and
#: `ResolutionJob()` fresh on every cycle. Without this cache that is a new
#: engine — and a new connection pool — several times an hour, forever. Nothing
#: disposes them; they survive until CPython happens to collect the owning
#: object, so the process's real connection count depends on GC timing.
#:
#: That is how the session-mode pooler was exhausted in the first place, and it
#: is worth removing rather than relying on a pool cap to contain it. Sharing is
#: safe because a SQLAlchemy Engine is thread-safe by design and is meant to be
#: process-wide; it is the Session that must not be shared.
_ENGINES: dict[tuple, object] = {}


def get_engine(url: str | None = None, **kwargs):
    """Return the shared engine for this URL and options, creating it once.

    `pool_pre_ping` matters for the recorder: it runs for days at a time and
    managed Postgres providers drop idle connections without warning.

    The pool is deliberately small; see `DEFAULT_POOL_SIZE`. Callers that
    genuinely need more can pass their own `pool_size`/`max_overflow`.

    Routes through `app_database_url`, so setting `MERIDIAN_TX_POOLER` moves
    every app process onto Supabase's transaction pooler while Alembic — which
    reads `get_database_url()` directly — stays on session mode where its
    advisory locks work.
    """
    resolved = app_database_url(url)
    kwargs.setdefault("pool_size", DEFAULT_POOL_SIZE)
    kwargs.setdefault("max_overflow", DEFAULT_MAX_OVERFLOW)
    cache_key = (resolved, tuple(sorted((k, repr(v)) for k, v in kwargs.items())))
    cached = _ENGINES.get(cache_key)
    if cached is not None:
        return cached
    # Hand a connection back rather than queueing forever: a recorder that
    # blocks on the pool stops recording silently, which is worse than an
    # error it can log and retry past.
    kwargs.setdefault("pool_timeout", 10)
    if TRANSACTION_POOLER_PORT in resolved:
        # Transaction mode borrows a server connection per statement, so it
        # cannot carry a prepared-statement cache across them. psycopg prepares
        # after 5 executions by default and would fail once rotated onto a
        # different backend.
        connect_args = dict(kwargs.pop("connect_args", {}))
        connect_args.setdefault("prepare_threshold", None)
        kwargs["connect_args"] = connect_args
    engine = create_engine(resolved, pool_pre_ping=True, future=True, **kwargs)
    _ENGINES[cache_key] = engine
    return engine


def get_sessionmaker(engine=None):
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False, future=True)
