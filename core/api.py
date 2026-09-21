"""Read-only JSON API behind the Meridian dashboard.

Serves the picks landing page, recorder health, prediction/edge data and
shadow orders.

**Read-only by construction.** There is no write endpoint and no order path —
the dashboard is a window, not a control panel. Placing orders stays in
`core/executor.py`, in shadow mode, behind a kill switch.

Reads are unauthenticated; how far they are exposed is decided at the compose
layer (loopback vs all interfaces — currently all, for tailnet dashboard access
while the operator is away). The order path is gated by MERIDIAN_ORDER_TOKEN
regardless of binding and fails closed without it.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import threading
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from core import heartbeat
from core.board import FINISHED, IN_PLAY, latest_snapshot_per_market, market_state
from core.game_detail import build_game_detail, list_games
from core.executor import (
    ARB_TIF,
    VENUE_MAX_PRICE,
    VENUE_MIN_PRICE,
    ExecutionMode,
    ExecutorConfig,
    OrderSide,
    OutcomeSide,
    build_order,
    round_to_tick,
)
from core.ladder import desk as _ladder_desk
from core.ladder import gamelog as _ladder_gamelog
from core.ladder import gamelog_page as _ladder_gamelog_page
from core.ladder import instructions as _ladder_instructions
from core.ladder import pnl as _ladder_pnl
from core.ladder import pnl_page as _ladder_pnl_page
from core.ladder import tape as _ladder_tape
from core.ladder.intent import MID_LADDER, is_mid, is_spread_pair, ticket_for
from core.ladder.live import book_age_s, line_of, sample, slugs_for
from core.ladder.scan import (MAX_PLAUSIBLE_EDGE, MAX_PLAUSIBLE_SIZE, clears_floor,
                              best_per_game, fee, scan_ladder)
from core.ladder.ui import ui_wording
from core.polymarket.client import (
    MissingCredentialsError,
    OrderSubmissionError,
    PolymarketGatewayClient,
    PolymarketOrderClient,
    USCredentials,
)
from core.leagues import (
    LEAGUES,
    UnknownLeagueError,
    default_league,
    get_league,
    league_of_slug,
)
from core.ratelimit import TokenBucket
from core.storage import (
    MarketSnapshot,
    PendingExit,
    PlacedOrder,
    Prediction,
    ShadowOrder,
    get_engine,
    get_sessionmaker,
)
from core.team_mapping import human_market as _human_market
from core.team_mapping import parse_market_slug

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

app = FastAPI(title="Meridian", docs_url=None, redoc_url=None)

#: The same policy the executor enforces. Read from one place so the page and
#: the order path can never disagree about what is tradable.
_EXECUTOR_POLICY = ExecutorConfig()

#: Below this the shadow sizer wanted the position but not a tradable amount.
MIN_TICKET_QTY = 0.1

#: The venue's own minimum. Matches `core.executor.DEFAULT_MIN_TRADE_QTY`.
VENUE_MIN_QTY = Decimal("0.01")

#: Hard ceiling on a single order, in dollars of stake. Fat-finger protection,
#: not a risk model: there is no cancel button, so a size typed with one extra
#: zero is unrecoverable. Deliberately an absolute cap rather than a multiple of
#: the model's size, because the model's size is frequently ~0 on exactly the
#: rows a human is most likely to override.
MAX_ORDER_STAKE_USD = Decimal(os.environ.get("MERIDIAN_MAX_ORDER_STAKE_USD", "25"))


def _stake_cap(allow_fetch: bool = True, cap: Decimal | None = None) -> Decimal:
    """The most one order may stake: the fat-finger cap **or the account**,
    whichever is smaller. ``cap`` defaults to the per-order cap; the ARB tab
    passes its own pair cap through the same rule so the two paths cannot
    disagree about what "the account" means.

    The $25 cap was written when the balance was $35. The account has since
    drifted to $23.82, so the "cap" stopped capping anything — a single ticket
    could have staked more money than exists, and the first thing the human
    would have learned about it is a rejection from the venue. A cap that is
    larger than the bankroll is not a guard, it is decoration.

    An unreadable balance falls back to the configured cap and **not** to a
    guessed bankroll: the env cap is a stated policy, whereas a made-up balance
    would be a fabricated fact about the account.
    """
    from core.bankroll import BankrollUnavailable, current

    cap = MAX_ORDER_STAKE_USD if cap is None else cap
    try:
        return min(cap, current(
            allow_fetch=allow_fetch,
            max_age_seconds=1800.0 if allow_fetch else 86400.0,
        ).bankroll)
    except BankrollUnavailable as exc:
        log.warning("stake_cap_without_bankroll", error=str(exc)[:160],
                    cap=float(cap))
        return cap


def _bankroll_block(allow_fetch: bool = True) -> dict | None:
    """The account balance for display, or ``None`` when it is not known.

    ``None`` is a real answer and the pages render it as such. The alternative
    — a plausible number standing in for one we could not read — is the exact
    failure this replaced: `35.68` looked like a balance on every screen for
    weeks after it stopped being one.
    """
    from core.bankroll import BankrollUnavailable, current

    try:
        # Display reads take the stored reading up to a day old — its age is
        # rendered honestly, and the page's own 60s refresh poll keeps it
        # genuinely fresh. Blocking a page-load GET on a synchronous venue
        # round-trip was ~1.4s of the measured 8.5s /api/picks load.
        return current(
            allow_fetch=allow_fetch,
            max_age_seconds=1800.0 if allow_fetch else 86400.0,
        ).to_dict()
    except BankrollUnavailable as exc:
        return {"bankroll": None, "unavailable": str(exc)[:160]}


def _derive_order_terms(pred, stake_cap: Decimal | None = None) -> dict | None:
    """The order the executor *would* build for this pick, computed on demand.

    Why this exists: `shadow_orders` only holds rows the Kelly sizer sized above
    the venue minimum. At a $35 bankroll that is one row in fourteen, so keying
    the confirm button off stored shadow orders put a button on 7% of the board
    and labelled the rest "too small" — which was not even true. They are not
    too small to *trade*; they are too small for the *sizer*, which is a
    statement about bankroll, not about the market.

    The price is derived here and never accepted from the client. It reproduces
    `Executor.decide` exactly: side is always BUY and a buy rests at the bid, so
    the limit is the tick-rounded bid. That keeps the confirm path and the
    shadow path quoting the same number, and keeps the one field where the
    maker/taker economics live out of the caller's hands.

    **Both outcomes are supported, and the NO side is where the care is.**

    A totals market is one binary contract per line: YES is OVER, verified
    against 490 settled markets. There is no separate UNDER slug, so betting
    UNDER means buying the *NO* outcome of the same contract. The shadow
    pipeline hardcodes `OrderSide.BUY` on YES, which is correct for an OVER
    pick and the **opposite trade** for an UNDER one.

    Two prices, and conflating them is the whole hazard:

    ================  ==================  ==================
    outcome           rests at            costs
    ================  ==================  ==================
    YES (OVER)        ``bid``             ``bid``
    NO  (UNDER)       ``ask``             ``1 - ask``
    ================  ==================  ==================

    Buying NO is selling YES, so a *resting* NO buy sits at the YES **ask** —
    joining the offer queue rather than crossing it. The venue then wants that
    same ask in ``price.value``, because it documents "to trade the NO side at
    any price X, set price.value = 1.00 - X", and X here is ``1 - ask``.

    So ``limit_price`` below is the YES-side number in both cases, and
    ``cost_per_contract`` is what the human actually pays. On the 2026-08-04
    TOR-GSV board, `UNDER 155.5` (bid 0.81 / ask 0.84) becomes price.value 0.84
    for a cost of 0.16 — against 0.19 to cross, and against the 0.81 that
    buying YES at the bid would have cost for the reverse bet.
    """
    bid, ask, model = _f(pred.market_bid), _f(pred.market_ask), _f(pred.model_probability)
    if bid is None or ask is None:
        return None

    # Same YES/NO determination the picks table uses for its label, so the
    # button and the row it sits on can never disagree about direction.
    is_no = model is not None and (bid - model) > (model - ask)

    # A resting buy joins the near side: the bid for YES, the ask for NO.
    limit_price = round_to_tick(ask if is_no else bid)
    if not (VENUE_MIN_PRICE <= limit_price <= VENUE_MAX_PRICE):
        return None

    cost = (Decimal("1") - limit_price) if is_no else limit_price
    if cost <= 0:
        return None
    # The whole book and the model, in the COST frame of this outcome. The
    # ticket edits and validates in this frame only; the YES-frame price.value
    # is derived once, server-side, at submit (V15: one row, one frame).
    cross = Decimal(str(1 - bid)) if is_no else Decimal(str(ask))
    fair = (
        None if model is None
        else round(1 - model, 4) if is_no else round(model, 4)
    )
    cap = _stake_cap() if stake_cap is None else stake_cap
    max_qty = (cap / cost).quantize(Decimal("0.01"))
    return {
        "supported": True,
        "outcome": OutcomeSide.NO.value if is_no else OutcomeSide.YES.value,
        #: What the venue receives — always the YES-side price.
        "limit_price": float(limit_price),
        #: What you actually pay per contract. These differ on a NO order and
        #: the ticket shows both, so a bad inversion is visible before sending.
        "cost_per_contract": float(cost),
        #: Cost-frame cross price (the far touch). A typed price at or above
        #: this fills immediately as a taker; more than 5¢ beyond it needs the
        #: hard confirm (`acknowledge_crossing`).
        "cross_price": float(cross),
        #: Model fair value in this outcome's cost frame — the exit prefill
        #: (hypothesis #8: the edge is collected when the market reaches the
        #: model, so fair value IS the sell target).
        "fair_value": fair,
        "min_quantity": float(VENUE_MIN_QTY),
        "max_quantity": float(max_qty),
        #: The binding cap, already reduced to the account balance when that is
        #: the smaller of the two. The ticket shows this number, so the human
        #: never sees a ceiling their money cannot reach.
        "max_stake_usd": float(cap),
    }

#: Model and market this close is not a disagreement, so it is not a bet.
NO_BET_TOLERANCE = 0.02

#: A -110 two-way market needs this to break even.
BREAKEVEN_HIT_RATE = 0.524
#: The dashboard serves several endpoints concurrently — status, board, events
#: and a sparkline per visible row — so it needs more than the 2+1 a recorder
#: does. With every request holding a connection for the length of its query, a
#: 3-connection pool exhausted itself the moment one query got slow, turning a
#: latency problem into 500s. Safe now that app processes are on the transaction
#: pooler, which multiplexes.
_ENGINE = get_engine(pool_size=5, max_overflow=5)
_Session = get_sessionmaker(_ENGINE)

STATIC = Path(__file__).parent.parent / "static"


def _f(value) -> float | None:
    return None if value is None else float(value)



def _position_label(market_type: str | None, bet_side: str | None,
                    human: str) -> str | None:
    """What position was actually taken, in words."""
    if bet_side is None:
        return None
    if (market_type or "").endswith("total"):
        return f"{'OVER' if bet_side == 'YES' else 'UNDER'} {human.replace('Total ', '')}"
    return f"{'BUY' if bet_side == 'YES' else 'SELL'} {human}"


#: The pregame recorder polls every 15 min near tip-off and every 60 min when
#: idle, so silence beyond 90 minutes means it has genuinely stopped. Same
#: bound the prediction job uses to decide a quote is too stale to price.
PREGAME_STALE_SECONDS = 90 * 60

#: The dashboard polls /api/status continuously. One round trip to Supabase is
#: ~60ms, which is cheap but not free at 1Hz forever, and it contends with a
#: recorder writing five times a second. Five seconds of cache makes repeated
#: polling free while keeping the number fresh enough to watch a recorder die.
STATUS_CACHE_SECONDS = 5.0

#: Everything the health page needs, in ONE round trip.
#:
#: `count(*)` is gone. On 857k snapshots and 735k book levels it took **over
#: two minutes** and hit the statement timeout — it had already gone from
#: "3.2s" to "fails", and it is on a path the dashboard polls continuously.
#: Exact counts were never worth that: nothing on the page acts on the
#: difference between 857,000 and 857,041.
#:
#: `pg_class.reltuples` is the planner's own estimate, maintained by autovacuum,
#: and reads in ~1ms. It is approximate and the payload says so
#: (`counts_estimated`), which is the honest trade — an estimate labelled as an
#: estimate beats an exact number that times out.
#:
#: Freshness is reported **per writer**, keyed on `book_tier`: the pregame
#: recorder leaves it NULL, the live recorder always sets it. That split is what
#: makes the health signal work at all now — a global `max(captured_at)` is
#: always ~0 seconds old while a game is live, so the page would read healthy
#: with the pregame recorder dead for hours.
_HEALTH_SQL = text("""
select
  -- Schema-qualified deliberately. `relname` alone is NOT unique: the
  -- `merge_stage` schema left over from the 2026-08-20 Supabase migration
  -- still holds same-named copies of all four tables, so an unqualified
  -- lookup returns two rows and the whole endpoint dies with
  -- CardinalityViolation -- measured 2026-09-01, /api/status returning 500
  -- while /api/games and /api/picks were fine. A leftover schema is a live
  -- hazard, not just clutter; it already caused a column miscount once.
  (select reltuples::bigint from pg_class c join pg_namespace n
     on n.oid = c.relnamespace
   where c.relname = 'market_snapshots' and n.nspname = 'public'),
  (select reltuples::bigint from pg_class c join pg_namespace n
     on n.oid = c.relnamespace
   where c.relname = 'book_levels' and n.nspname = 'public'),
  (select reltuples::bigint from pg_class c join pg_namespace n
     on n.oid = c.relnamespace
   where c.relname = 'predictions' and n.nspname = 'public'),
  (select reltuples::bigint from pg_class c join pg_namespace n
     on n.oid = c.relnamespace
   where c.relname = 'shadow_orders' and n.nspname = 'public'),
  (select max(captured_at) from market_snapshots),
  (select max(captured_at) from market_snapshots where book_tier is null),
  (select max(captured_at) from market_snapshots where book_tier is not null),
  pg_total_relation_size('market_snapshots')
    + pg_total_relation_size('book_levels'),
  (select coalesce(jsonb_object_agg(service, jsonb_build_object(
       'age_seconds', round(extract(epoch from now() - beat_at)::numeric, 1),
       'interval_seconds', interval_seconds,
       'rows_written', rows_written,
       'game_live', game_live)), '{}'::jsonb)
     from service_heartbeats)
""")

#: The live recorder's heartbeat lives in LOCAL Postgres, with its data — the
#: whole point of B11's fix is that a heartbeat must be written where the
#: writer writes, and this writer deliberately does not write to Supabase. The
#: dashboard runs on the same host, so it reads both. Ages are computed by each
#: database's own clock, immune to container clock skew.
_LOCAL_HEARTBEAT_URL = os.environ.get(
    "MERIDIAN_LOCAL_DATABASE_URL",
    "postgresql+psycopg://meridian:meridian@localhost:5433/meridian",
)

_LOCAL_HEARTBEAT_SQL = text("""
select
  extract(epoch from now() - beat_at),
  interval_seconds,
  rows_written,
  game_live,
  (select count(*) from market_snapshots
    where captured_at > now() - interval '5 minutes')
from service_heartbeats where service = :service
""")

#: The two safety counters, read from the `orders` table on **every** call.
#:
#: Three deliberate choices, each of which the obvious alternative gets wrong:
#:
#: 1. **Exact `count(*)`, not `reltuples`.** Everything else on this endpoint
#:    uses planner estimates because exact counts on 857k-row tables time out.
#:    `orders` holds single digits, so an exact count is ~1ms — and an estimate
#:    is worthless for an invariant that reads "must be 0 forever". `reltuples`
#:    is also -1 until the first autovacuum, which would render as "-1 real
#:    orders" on a fresh database.
#:
#: 2. **Not cached.** The five-second status cache is right for freshness
#:    signals and wrong for this. The number that answers "has this system ever
#:    traded autonomously?" should never be a value remembered from before.
#:
#: 3. **Derived from stored rows, never incremented.** There is no counter
#:    variable anywhere in this process. A tally in memory is a claim about
#:    history that resets on deploy; this is a query against what happened.
#:
#: `orders_autonomous` is a tripwire, not the defence. The defence is the CHECK
#: constraint `ck_orders_accepted_requires_human`, which makes the row this
#: counts unrepresentable. If this ever reads non-zero, the constraint is gone.
_ORDER_COUNTS_SQL = text("""
select
  count(*) filter (where accepted and mode = 'HUMAN_CONFIRM')  as orders_human,
  count(*) filter (where accepted and mode <> 'HUMAN_CONFIRM') as orders_autonomous,
  count(*) filter (where not accepted)                         as orders_rejected
from orders
""")


def _order_counts(session) -> dict:
    """Both counters, straight from the table. Never a cached or in-memory tally."""
    human, autonomous, rejected = session.execute(_ORDER_COUNTS_SQL).one()
    return {
        "orders_human": int(human or 0),
        "orders_autonomous": int(autonomous or 0),
        "orders_rejected": int(rejected or 0),
    }


_status_cache: dict = {"at": 0.0, "value": None}


def _age_seconds(then, now: dt.datetime) -> float | None:
    return None if then is None else (now - then).total_seconds()



def _ticket(bid: float | None, ask: float | None, model: float | None,
            market_type: str | None, human: str,
            shadow_qty: float | None) -> dict | None:
    """The whole trade as one instruction: side, buy price, sell price, size.

    Every number here already existed on the row — the side, the ask, the
    model probability, the shadow quantity — but only as ingredients. Turning
    them into a ticket is not cosmetic: the sell target IS the model column,
    and nobody reading a probability next to a price would guess that. It was
    asked for out loud several times before this existed.

    The two flips that make it non-obvious:

    * On a NO/UNDER, you pay ``1 - bid`` and it is worth ``1 - model``. The
      bid/ask/model shown are always for the YES side, so an UNDER row's real
      cost appears nowhere on screen.
    * The sell target is fair value, **not** a multiple of entry. Buy at 19c
      against a 27c model and you exit at 27c, not at 38c: the edge is
      ``fair value - price``, so it is fully collected the moment the market
      reaches the model. Holding past it is holding a fair coin.
    """
    if bid is None or ask is None or model is None:
        return None

    edge_yes, edge_no = model - ask, bid - model
    yes = edge_yes >= edge_no
    # BUY AT is the RESTING price — the number the order actually sends — not
    # the crossing cost. The old ticket showed the ask while the order posted
    # at the bid (0.33 shown, 0.32 sent) and computed the return off the
    # display number; now buy_at, return_pct and orders.limit_price are the
    # same number in the same cost frame, with the crossing cost shown
    # separately as cross_at.
    buy = bid if yes else 1.0 - ask
    cross = ask if yes else 1.0 - bid
    worth = model if yes else 1.0 - model
    if buy <= 0:
        return None

    is_total = (market_type or "").endswith("total")
    if is_total:
        side = "OVER" if yes else "UNDER"
        label = f"{side} {human.replace('Total ', '')}"
    else:
        side = "BUY" if yes else "SELL"
        label = f"{side} {human}"

    qty = shadow_qty or 0.0
    return {
        "label": label,
        "buy_at": round(buy, 4),
        "cross_at": round(cross, 4),
        "sell_at": round(worth, 4),
        # Return on the money staked, not the probability edge. A 5-point edge
        # on a 20c contract returns 25%; on an 80c contract, 6%. The screen
        # showed points, and points are not what the wallet receives.
        "return_pct": round(worth / buy - 1.0, 4),
        "size": round(qty, 2),
        "stake": round(qty * buy, 2),
        # Below the venue minimum the model wanted the bet but not enough of it
        # to be worth a ticket. Say so rather than showing a size of 0.0.
        "too_small": qty < MIN_TICKET_QTY,
    }


def _local_live_heartbeat() -> dict:
    """The live recorder's beat, read from local Postgres.

    Unreachable and missing both rule DEAD rather than unknown: the cost
    asymmetry (a missed outage loses games permanently, a false alarm costs a
    glance) says round ambiguity down, and "the health check cannot see the
    writer" is precisely the state B11 sat in.
    """
    try:
        engine = get_engine(_LOCAL_HEARTBEAT_URL, pool_size=1, max_overflow=0)
        with engine.connect() as c:
            row = c.execute(
                _LOCAL_HEARTBEAT_SQL, {"service": heartbeat.SERVICE_LIVE}
            ).one_or_none()
    except Exception as exc:
        return {"verdict": heartbeat.DEAD, "unreachable": str(exc)[:80]}
    if row is None:
        return {"verdict": heartbeat.DEAD, "missing": True}

    age, interval, rows_written, game_live, rows_5min = row
    age, interval = float(age), float(interval)
    return {
        "age_seconds": round(age, 1),
        "interval_seconds": interval,
        "stale_after_seconds": round(heartbeat.stale_after_seconds(interval), 1),
        "rows_written": rows_written,
        "game_live": game_live,
        "rows_5min": int(rows_5min or 0),
        "verdict": heartbeat.verdict(
            age, interval, game_live=bool(game_live), rows_recent=int(rows_5min or 0)
        ),
    }


def _heartbeat_report(beats: dict) -> dict:
    """Verdicts for every expected writer, from the beats the primary DB holds
    plus the live recorder's local one. A service with no row has never run
    this code or is dead — DEAD either way."""
    report: dict[str, dict] = {}
    for service in heartbeat.APP_DB_SERVICES:
        entry = beats.get(service)
        if entry is None:
            report[service] = {"verdict": heartbeat.DEAD, "missing": True}
            continue
        age = float(entry["age_seconds"])
        interval = float(entry["interval_seconds"])
        report[service] = {
            "age_seconds": age,
            "interval_seconds": interval,
            "stale_after_seconds": round(heartbeat.stale_after_seconds(interval), 1),
            "rows_written": entry.get("rows_written"),
            "verdict": heartbeat.verdict(age, interval),
        }
    # The fill watcher is judged only where it could have started: ordering
    # enabled in THIS process (token set — the same gate the order endpoint
    # fails closed on). On such a host a silent watcher is exactly the B11
    # shape — accepted orders quietly diverging from venue truth — so it is
    # DEAD like any other missing writer. On a host that cannot order, there
    # is nothing to reconcile and no verdict to give.
    if (os.environ.get("MERIDIAN_ORDER_TOKEN") or "").strip():
        entry = beats.get(heartbeat.SERVICE_FILL_WATCHER)
        if entry is None:
            report[heartbeat.SERVICE_FILL_WATCHER] = {
                "verdict": heartbeat.DEAD, "missing": True,
            }
        else:
            age = float(entry["age_seconds"])
            interval = float(entry["interval_seconds"])
            report[heartbeat.SERVICE_FILL_WATCHER] = {
                "age_seconds": age,
                "interval_seconds": interval,
                "stale_after_seconds": round(heartbeat.stale_after_seconds(interval), 1),
                "rows_written": entry.get("rows_written"),
                "verdict": heartbeat.verdict(age, interval),
            }
    report[heartbeat.SERVICE_LIVE] = _local_live_heartbeat()
    return report


@app.get("/api/status")
def status() -> dict:
    """Recorder health, in one cached round trip.

    Deliberately does **not** report a gap count any more. The old one took the
    200 most recent distinct `captured_at` values and looked for holes over 90
    minutes — but at 200ms sampling those 200 instants span *forty seconds*, so
    it could not have detected a 90-minute gap even in principle. It reported 0
    unconditionally, which is worse than reporting nothing. Counting distinct
    instants over a useful window is not affordable either: the equivalent query
    over 24 hours hits the statement timeout.

    Per-writer age replaces it, and is the signal that actually matters: a
    recorder that has stopped shows up immediately in its own timestamp.
    """
    now_mono = time.monotonic()
    cached = _status_cache["value"]
    if cached is not None and now_mono - _status_cache["at"] < STATUS_CACHE_SECONDS:
        # The order counters are re-read even on a cache hit. Everything else
        # here is a freshness signal that tolerates five seconds of staleness;
        # "has this system ever traded autonomously?" does not.
        with _Session() as s:
            return {**cached, **_order_counts(s)}

    with _Session() as s:
        row = s.execute(_HEALTH_SQL).one()
        counts = _order_counts(s)

    (n_snap, n_levels, n_preds, n_orders,
     newest, pregame_newest, live_newest, stream_bytes, beats) = row

    now = dt.datetime.now(UTC)
    pregame_age = _age_seconds(pregame_newest, now)
    live_age = _age_seconds(live_newest, now)

    heartbeats = _heartbeat_report(beats or {})

    # The pregame-freshness rule stays, and the heartbeat rule joins it (B11):
    # any writer whose beat is older than 3x its own cycle interval is dead,
    # **including the live recorder between games**. Its data is legitimately
    # silent overnight; its heartbeat never is — that distinction is exactly
    # what this endpoint could not express while two games of tick data were
    # being lost.
    healthy = (
        pregame_age is not None
        and pregame_age < PREGAME_STALE_SECONDS
        and not any(v["verdict"] == heartbeat.DEAD for v in heartbeats.values())
    )

    # Overlay engines (PULSE, QUOTE), reported beside — never inside — the
    # recorder verdict. They are excluded from APP_DB_SERVICES on purpose (an
    # operator-stopped overlay must not read DEAD on every host), which left
    # this endpoint structurally unable to say whether the two processes the
    # research program depends on were running — the same blindness
    # scripts/health.py had until 2026-09-02. `healthy` deliberately ignores
    # them: absence here is a fact for the header dot, not a recorder failure.
    overlays = {}
    # quote_engine_nfl = GRIDIRON (service_quote_for('nfl')); quote_engine_cfb
    # its CFB twin (the meridian-quote-cfb container, live since 2026-09-12 and
    # invisible here until 2026-09-18: a running engine read as nothing at all).
    for svc in ("pulse_engine", "quote_engine", "quote_engine_nfl", "quote_engine_cfb"):  # SERVICE_PULSE / SERVICE_QUOTE(+nfl,+cfb);
        # literals, not imports: pulling core.pulse.live in here would load the
        # whole engine module into the API process just to name a row key.
        entry = (beats or {}).get(svc)
        if entry is None:
            overlays[svc] = {"verdict": "absent"}
        else:
            age = float(entry["age_seconds"])
            interval = float(entry["interval_seconds"])
            overlays[svc] = {
                "age_seconds": age,
                "interval_seconds": interval,
                "verdict": heartbeat.verdict(age, interval),
            }

    value = {
        "newest": newest.isoformat() if newest else None,
        "age_minutes": (
            round(_age_seconds(newest, now) / 60, 1) if newest else None
        ),
        #: Per-writer freshness. `pregame` is the health signal; `live` is
        #: informational and is expected to be stale between games.
        "pregame_age_seconds": round(pregame_age, 1) if pregame_age is not None else None,
        "live_age_seconds": round(live_age, 1) if live_age is not None else None,
        #: Per-service liveness (B11). `verdict` is 'dead' | 'degraded' |
        #: 'idle' | 'ok'; any 'dead' fails `healthy`. 'degraded' means a live
        #: game, a fresh beat, and zero rows — alive but writing nothing.
        "heartbeats": heartbeats,
        #: The two model engines, for the main-page header dots. Same verdict
        #: vocabulary plus 'absent' (no beat row ever) — and deliberately NOT
        #: part of `healthy`; see the comment where this is built.
        "overlays": overlays,
        "healthy": healthy,
        #: Approximate — planner statistics, not a scan. See _HEALTH_SQL.
        "counts_estimated": True,
        "counts": {
            "snapshots": int(n_snap or 0),
            "book_levels": int(n_levels or 0),
            "predictions": int(n_preds or 0),
            "shadow_orders": int(n_orders or 0),
        },
        "stream_bytes": int(stream_bytes or 0),
        #: The account, read from the venue. Every dollar figure on every page
        #: is a fraction of this, so it belongs next to the freshness signals:
        #: a bankroll nobody has refreshed is as stale as a recorder nobody has
        #: restarted, and used to be just as invisible.
        "bankroll": _bankroll_block(allow_fetch=False),
    }
    _status_cache["at"] = now_mono
    _status_cache["value"] = value
    # Counters are merged *after* the cache is written, so a cached payload can
    # never carry a stale count of real orders.
    return {**value, **counts}


def _pricing_state(snap: MarketSnapshot, prediction, *, as_of: dt.datetime) -> str:
    """Why a row has no edge, so the UI never has to guess.

    An in-play market showing no model price is the model working correctly —
    it is pregame-only and refuses to price a game in progress — but on screen
    that is indistinguishable from a malfunction. Naming the state fixes that.

    Uses `market_state` rather than the raw `is_live` flag, which freezes at
    `True` forever once a game's markets leave the venue's board.
    """
    state = market_state(snap, as_of=as_of)
    if state == IN_PLAY:
        return "in_play"
    if state == FINISHED:
        return "finished"
    if prediction is None:
        return "unpriced"
    return "priced"


def _live_board(s, *, as_of: dt.datetime, include_finished: bool):
    """Markets still worth looking at: everything but the games that are over.

    A finished game's markets keep their last quote forever — nothing
    overwrites them once they leave the venue's board — so leaving them in
    means showing hours-old prices, and an *edge* computed against them, beside
    live ones. They are dropped rather than dimmed because nothing on this page
    is actionable for a game that has already been played.
    """
    snaps = latest_snapshot_per_market(s, as_of=as_of)
    if include_finished:
        return snaps
    return [x for x in snaps if market_state(x, as_of=as_of) != FINISHED]


@app.get("/api/board")
def board(include_finished: bool = False, league: str | None = None) -> dict:
    """Latest snapshot of every market still on the board, with its prediction.

    ``league`` filters on the slug prefix the venue itself uses. Filtered here
    rather than in the query because the board reads the newest snapshot per
    market and the league is a property of the slug, not of a column — see
    `core/leagues.py` for why the mapping is an explicit table.
    """
    lg = _league_or_400(league)
    now = dt.datetime.now(UTC)
    with _Session() as s:
        snaps = _live_board(s, as_of=now, include_finished=include_finished)
        snaps = [
            x for x in snaps
            if league_of_slug(x.event_slug or x.market_slug) is not None
            and league_of_slug(x.event_slug or x.market_slug).slug == lg.slug
        ]
        if not snaps:
            return {"captured_at": None, "markets": [], "league": lg.slug,
                    "league_name": lg.name, "recorded": lg.recorded,
                    "empty_state": lg.empty_state}
        latest = max(snap.captured_at for snap in snaps)

        pred_time = s.scalar(select(func.max(Prediction.predicted_at)))
        preds = {}
        if pred_time is not None:
            for p in s.scalars(
                select(Prediction).where(Prediction.predicted_at == pred_time)
            ).all():
                preds[p.market_slug] = p

        # Only for market types the executor would still place. Shadow rows
        # written before the moneyline was refused on measured evidence are
        # historical artifacts of a superseded policy; showing them implies an
        # order that would never be sent now.
        shadow = {
            o.market_slug: o
            for o in s.scalars(select(ShadowOrder)).all()
            if _EXECUTOR_POLICY.is_tradable(o.sports_market_type)
        }

        rows = []
        for snap in snaps:
            p = preds.get(snap.market_slug)
            bid, ask = _f(snap.best_bid), _f(snap.best_ask)
            rows.append({
                "market_slug": snap.market_slug,
                "event_slug": snap.event_slug,
                "type": (snap.sports_market_type or "").replace(
                    "basketball_team_full_game_", ""),
                "line": _f(snap.line),
                "bid": bid,
                "ask": ask,
                "spread": None if bid is None or ask is None else round(ask - bid, 4),
                "mid": None if bid is None or ask is None else round((ask + bid) / 2, 4),
                "model": _f(p.model_probability) if p else None,
                "edge": _f(p.edge) if p else None,
                "is_live": market_state(snap, as_of=now) == IN_PLAY,
                # Per-row freshness. Rows now come from writers on very
                # different cadences, so a single board-level timestamp would
                # present a 15-minute-old pregame quote as though it were as
                # fresh as a 200ms live one.
                "captured_at": snap.captured_at.isoformat(),
                "age_seconds": round((now - snap.captured_at).total_seconds(), 1),
                #: Which writer produced this quote: the pregame sweeper (15min
                #: cycle, book_tier NULL) or the live recorder's tier (200ms
                #: price / near / deep). The AGE column's tooltip names it, so
                #: an 8s row and a 12m row are never silently the same kind of
                #: fresh — both recorders share one table and the newest row
                #: wins; this says which one that was.
                "source": snap.book_tier or "pregame",
                "pricing_state": _pricing_state(snap, p, as_of=now),
                "game_start": snap.game_start_time.isoformat() if snap.game_start_time else None,
                "shadow": (
                    {
                        "limit_price": _f(shadow[snap.market_slug].limit_price),
                        "quantity": _f(shadow[snap.market_slug].quantity),
                        "would_rest": shadow[snap.market_slug].would_rest,
                    }
                    if snap.market_slug in shadow else None
                ),
                "ticket": _ticket(
                    bid, ask, _f(p.model_probability) if p else None,
                    snap.sports_market_type,
                    _human_market(snap.market_slug, snap.sports_market_type, _f(snap.line)),
                    _f(shadow[snap.market_slug].quantity)
                    if snap.market_slug in shadow else None,
                ),
            })

    return {
        "captured_at": latest.isoformat(),
        "predicted_at": pred_time.isoformat() if pred_time else None,
        "league": lg.slug,
        "league_name": lg.name,
        "recorded": lg.recorded,
        "empty_state": lg.empty_state,
        "markets": rows,
    }


@app.get("/api/history/{market_slug}")
def history(market_slug: str,
            limit: int = Query(60, ge=1, le=2000)) -> dict:
    """Recent mid-price history for one market — drives the sparklines."""
    with _Session() as s:
        rows = s.execute(
            select(
                MarketSnapshot.captured_at,
                MarketSnapshot.best_bid,
                MarketSnapshot.best_ask,
            )
            .where(MarketSnapshot.market_slug == market_slug)
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(limit)
        ).all()

    points = []
    for captured_at, bid, ask in reversed(rows):
        if bid is None or ask is None:
            continue
        points.append({
            "t": captured_at.isoformat(),
            "mid": round((float(bid) + float(ask)) / 2, 4),
        })
    return {"market_slug": market_slug, "points": points}


@app.get("/api/events")
def events(league: str | None = None) -> dict:
    """Games being tracked, each from its own latest snapshot.

    Had the same defect as `/api/board`: grouping the single newest instant
    meant the sidebar listed only whichever game the live recorder had just
    written, so a full slate rendered as one game.
    """
    lg = _league_or_400(league)
    now = dt.datetime.now(UTC)
    with _Session() as s:
        snaps = _live_board(s, as_of=now, include_finished=False)

    grouped: dict[str, dict] = {}
    for snap in snaps:
        found = league_of_slug(snap.event_slug or snap.market_slug)
        if found is None or found.slug != lg.slug:
            continue
        slug = snap.event_slug or "?"
        e = grouped.setdefault(slug, {
            "event_slug": slug,
            "markets": 0,
            "start": snap.game_start_time,
            "is_live": False,
            "oldest": snap.captured_at,
        })
        e["markets"] += 1
        e["is_live"] = e["is_live"] or bool(snap.is_live)
        if snap.game_start_time and (
            e["start"] is None or snap.game_start_time < e["start"]
        ):
            e["start"] = snap.game_start_time
        e["oldest"] = min(e["oldest"], snap.captured_at)

    out = sorted(
        grouped.values(),
        key=lambda e: (e["start"] is None, e["start"] or now),
    )
    return {
        "events": [
            {
                "event_slug": e["event_slug"],
                "markets": e["markets"],
                "start": e["start"].isoformat() if e["start"] else None,
                "is_live": e["is_live"],
                # Staleness of the least-recently-written market in this game.
                "age_seconds": round((now - e["oldest"]).total_seconds(), 1),
            }
            for e in out
        ],
        "league": lg.slug,
        "league_name": lg.name,
    }


#: Markets this far past tipoff-minus-N hours are unformed. Measured on a live
#: board: 0-6h out the median spread is 1c with 0% wider than 10c; 6-24h out it
#: is 20c with 67% wide. Prices like 0.99/0.01 appear on far-dated games that
#: nobody has quoted yet. Default horizon is same-day.
DEFAULT_PICK_HORIZON_HOURS = 14.0
#: A quote wider than this is not a tradeable price, whatever the timing.
MAX_TRADEABLE_SPREAD = 0.06


@app.get("/api/picks")
def picks(horizon_hours: float = DEFAULT_PICK_HORIZON_HOURS,
          include_illiquid: bool = False,
          league: str | None = None) -> dict:
    """Actionable pregame picks, ordered by tipoff.

    Four filters, all empirical:
      * `horizon_hours` — far-dated boards are not really quoted yet.
      * spread width — a 20c market has no usable price regardless of when
        the game is.
      * **market type** — the executor refuses the moneyline on measured
        evidence (25-33% hit rate, whole CI below the 52.4% breakeven). A pick
        the executor would never place must not appear on a page used to
        decide what to bet.
      * **not actionable** — chiefly games the books have not priced yet.
        With no book line there is nothing to anchor the model against, so the
        number is raw model opinion, and it is reliably the *largest* edge on
        the board. Those are the picks most likely to be taken and least
        deserving of it.

    `include_illiquid=true` relaxes the spread filter only; the market-type and
    actionability gates are not overridable from a URL. `league` filters on the
    venue's own slug prefix (`core/leagues.py`) and is not a gate — it selects
    which board you are looking at.
    """
    lg = _league_or_400(league)
    if not lg.recorded:
        # Short-circuit before the query, matching /api/games. Without this an
        # unrecorded league still walks every prediction on record and discards
        # all of them — seconds of work to return nothing, and seconds is
        # exactly the window the page's stale-response guard has to cover.
        #
        # `bankroll` rides along, as on every other return in this function.
        # The balance is a fact about the ACCOUNT, so it is true on a league we
        # do not record, and omitting it makes the page report "unknown" about
        # a number sitting in the database. It arrives here in the same PR that
        # defines `_bankroll_block` — adding it when the short-circuit itself
        # landed would have been a NameError, which is why it waited rather
        # than being fixed at the point it was found.
        return {"picks": [], "predicted_at": None, "league": lg.slug,
                "league_name": lg.name, "recorded": False,
                "empty_state": lg.empty_state,
                "bankroll": _bankroll_block(allow_fetch=False)}
    with _Session() as s:
        pred_time = s.scalar(select(func.max(Prediction.predicted_at)))
        if pred_time is None:
            # Both the league context and the bankroll survive an empty board,
            # and for the same reason: they are facts about the account and the
            # tab, not about tonight's slate. `bankroll` is an ALWAYS-PRESENT
            # field, not a usually-present one — a consumer reading
            # `d.bankroll.bankroll` throws on a missing key, and one reading
            # `d.bankroll?.bankroll` renders nothing at all. The second is this
            # endpoint's own bug arrived at from the other side: a balance
            # absent with no explanation is the same failure as a balance that
            # is quietly wrong. (Found by Builder C, who hit the identical hole
            # adding the league keys immediately below.)
            return {"picks": [], "predicted_at": None, "league": lg.slug,
                    "league_name": lg.name, "recorded": lg.recorded,
                    "empty_state": lg.empty_state,
                    "bankroll": _bankroll_block(allow_fetch=False)}
        preds = s.scalars(
            select(Prediction).where(Prediction.predicted_at == pred_time)
        ).all()
        shadow = {o.market_slug: o for o in s.scalars(select(ShadowOrder)).all()}
        # Bounded to the prediction set's own slugs. The unbounded version
        # GROUP BYed every market ever recorded — harmless at 3k pregame rows,
        # 7 seconds once the 200ms recorder had written millions. Measured on
        # the mirror: /api/picks 8.5s -> sub-second with this and the
        # stored-bankroll change below.
        pred_slugs = list({p.market_slug for p in preds})
        # LIMIT 1 per slug via LATERAL, not max()-GROUP BY: a market that
        # went live carries millions of 200ms rows and the aggregate reads
        # every one (1.1s measured even bounded). The tip is constant per
        # market in practice; any non-null row answers in ~2ms.
        starts = {
            r.market_slug: r.tipoff for r in s.execute(text("""
                SELECT slugs.slug AS market_slug, ts.tipoff
                  FROM unnest(CAST(:slugs AS text[])) AS slugs(slug)
                  JOIN LATERAL (
                        SELECT game_start_time AS tipoff
                          FROM market_snapshots ms
                         WHERE ms.market_slug = slugs.slug
                           AND ms.game_start_time IS NOT NULL
                         LIMIT 1
                  ) ts ON true
            """), {"slugs": pred_slugs}).all()
        } if pred_slugs else {}

    now = dt.datetime.now(UTC)
    # Resolved once per request, not once per row: every ticket on the board is
    # capped by the same account, and thirty rows must not become thirty reads.
    stake_cap = _stake_cap(allow_fetch=False)
    out, filtered_far, filtered_wide = [], 0, 0
    filtered_untradable = filtered_unanchored = filtered_unknown_league = 0
    filtered_no_tipoff = 0
    for p in preds:
        # League first: everything below is per-board bookkeeping, and counting
        # another league's filtered rows into this board's tallies would make
        # the "N far-dated hidden" hint describe games that were never here.
        found = league_of_slug(p.event_slug or p.market_slug)
        if found is None:
            # A slug we cannot place in any league. Counted, not swallowed:
            # this is exactly the silent-empty-board failure `core/leagues.py`
            # is written to avoid, and a rising number here means the venue
            # changed its slug format.
            filtered_unknown_league += 1
            continue
        if found.slug != lg.slug:
            continue
        start = starts.get(p.market_slug)
        if start is None:
            # No snapshot row for this market has ever carried a tipoff —
            # futures/series markets by design, or a recording gap. Counted:
            # this skip was silent, and a rising number here is the only way
            # to see a slate vanishing from the board.
            filtered_no_tipoff += 1
            continue
        if start <= now:                       # pregame only
            continue
        hours = (start - now).total_seconds() / 3600
        if hours > horizon_hours:
            filtered_far += 1
            continue
        bid, ask = _f(p.market_bid), _f(p.market_ask)
        model = _f(p.model_probability)
        if bid is None or ask is None or model is None:
            continue
        spread = ask - bid
        if spread > MAX_TRADEABLE_SPREAD and not include_illiquid:
            filtered_wide += 1
            continue
        if not _EXECUTOR_POLICY.is_tradable(p.sports_market_type):
            filtered_untradable += 1
            continue
        if not p.is_actionable:
            filtered_unanchored += 1
            continue
        edge_yes, edge_no = model - ask, bid - model
        side, edge = ("YES", edge_yes) if edge_yes >= edge_no else ("NO", edge_no)
        mtype = (p.sports_market_type or "").replace("basketball_team_full_game_", "")
        if mtype == "total":
            side = "OVER" if side == "YES" else "UNDER"
        o = shadow.get(p.market_slug)
        _order_terms = _derive_order_terms(p, stake_cap)
        human = _human_market(p.market_slug, p.sports_market_type, _f(p.line))
        out.append({
            "market_slug": p.market_slug,
            "event_slug": p.event_slug,
            "human": human,
            "position": _position_label(
                p.sports_market_type,
                "YES" if side in ("YES", "OVER") else "NO",
                human,
            ),
            "type": mtype,
            "line": _f(p.line),
            "side": side,
            "edge": round(edge, 4),
            # Bid, ask and model are shown **in the frame of the position on
            # this row**, which for a NO/UNDER pick is not the YES frame the
            # database stores.
            #
            # This was the bug: a row read `UNDER 155.5 · BUY AT 0.20 · bid 0.80
            # / ask 0.83`. Every number was individually right and the row as a
            # whole was incoherent — BUY AT and SELL AT were already inverted to
            # the UNDER side, while BID, ASK and MODEL were still quoting OVER.
            # On the venue that market shows **bid 0.17 / ask 0.20**, which is
            # exactly `1 - ask` and `1 - bid` of what we were printing.
            #
            # A binary's two sides are one book seen from opposite ends:
            # `NO bid = 1 - YES ask`, `NO ask = 1 - YES bid`. Flipping the whole
            # row into one frame makes BUY AT the NO ask (what crossing costs)
            # and the resting price the NO bid — and makes the screen agree with
            # the venue. The spread is frame-invariant, so it is unchanged.
            **(
                {"model": round(1.0 - model, 4), "bid": round(1.0 - ask, 4),
                 "ask": round(1.0 - bid, 4)}
                if side in ("NO", "UNDER")
                else {"model": model, "bid": bid, "ask": ask}
            ),
            # The raw YES-side book, kept because every stored price, the venue
            # payload's `price.value` and `shadow_orders` are all in this frame.
            # Without it there is no way to reconcile the screen against the
            # database.
            "yes_frame": {"bid": bid, "ask": ask, "model": model},
            "game_start": start.isoformat(),
            "hours_to_tipoff": round(hours, 1),
            "spread": round(spread, 4),
            "suspect": edge > 0.15,
            "shadow": None if o is None else {
                "limit_price": _f(o.limit_price),
                "quantity": _f(o.quantity),
                "would_rest": o.would_rest,
            },
            # What the confirm button offers. Present on every row the venue
            # could accept, not only the ones the sizer sized.
            #
            # `default_quantity` is the model's size where it exists and the
            # venue minimum where it does not. `sized_by_model` says which,
            # so the ticket can be honest about whether the number in the box
            # is a recommendation or just a floor.
            # `default_quantity` inherits the model's size ONLY when the stored
            # size was computed for the side we are actually taking.
            #
            # `shadow_run.py` sizes every pick as a YES buy — it passes
            # `probability=model` and `price=market_ask`, both YES-frame, and
            # has no concept of a NO position. So a shadow quantity on a NO row
            # is Kelly's answer to a different question: how much YES to buy,
            # not how much NO. Inheriting it would prefill the confirm box with
            # a size derived from the opposite trade.
            #
            # Concretely, `SELL TOR +11.5` showed `SIZE 1.1` from a shadow order
            # that was a YES buy, priced off a 0.42 bid from 18 hours earlier,
            # while the live pick is NO at 0.50. Wrong side, wrong price, wrong
            # time. NO rows therefore start at the venue minimum and say so.
            "order": None if _order_terms is None else {
                **_order_terms,
                "default_quantity": (
                    _f(o.quantity)
                    if o is not None and _order_terms["outcome"] == OutcomeSide.YES.value
                    else float(VENUE_MIN_QTY)
                ),
                "sized_by_model": (
                    o is not None and _order_terms["outcome"] == OutcomeSide.YES.value
                ),
            },
            # The whole trade as one instruction. Every ingredient was already
            # on this row; none of them said what to actually do.
            "ticket": _ticket(
                bid, ask, model, p.sports_market_type, human,
                # Same rule as `default_quantity` above: a YES-side size is not
                # the model's answer for a NO position, so the SIZE and STAKE
                # columns show "not sized" rather than a number from the
                # opposite trade.
                _f(o.quantity)
                if o is not None
                and _order_terms is not None
                and _order_terms["outcome"] == OutcomeSide.YES.value
                else None,
            ),
        })
    # Ordered by tipoff: the soonest game is the one you can actually act on.
    out.sort(key=lambda r: (r["game_start"], -r["edge"]))
    return {
        "predicted_at": pred_time.isoformat(),
        "horizon_hours": horizon_hours,
        "league": lg.slug,
        "league_name": lg.name,
        "recorded": lg.recorded,
        "empty_state": lg.empty_state,
        #: The account the STAKE column is a fraction of. On the page so that a
        #: size and the money behind it are never read apart — `null` when the
        #: balance could not be established, which the page says out loud rather
        #: than filling in. Same keys as the empty-board return above; the two
        #: shapes must not drift.
        "bankroll": _bankroll_block(allow_fetch=False),
        "filtered": {
            "beyond_horizon": filtered_far,
            "spread_too_wide": filtered_wide,
            "market_not_traded": filtered_untradable,
            "no_book_line_yet": filtered_unanchored,
            "no_tipoff_recorded": filtered_no_tipoff,
            "unknown_league": filtered_unknown_league,
        },
        "picks": out,
    }


def _era_window(s, era: str):
    """(since, before, meta) for an operator-facing query. Presentation only.

    `pulse` (the default everywhere) shows the record from PULSE's first live
    decision onward; `archive` shows the pregame ANCHOR record before it.
    While no live decision exists the PULSE era has not started: pulse shows
    an honestly empty record — the operator's clean slate — rather than the
    archive under a new name.
    """
    from core.era import ANCHOR_LABEL, era_boundary

    if era not in ("pulse", "archive"):
        raise HTTPException(status_code=400,
                            detail=f"era must be 'pulse' or 'archive', not {era!r}")
    boundary = era_boundary(s)
    meta = {
        "era": era,
        "era_boundary": boundary.isoformat() if boundary else None,
        "era_started": boundary is not None,
        "archive_label": ANCHOR_LABEL,
    }
    if era == "archive":
        # Everything before the boundary; the whole record while no boundary
        # exists — the archive IS the history, and hiding it because the new
        # era has not begun would delete it from view entirely.
        return None, boundary, meta
    if boundary is None:
        # PULSE era requested, not started: an impossible window (empty set).
        return dt.datetime.max.replace(tzinfo=UTC), None, meta
    return boundary, None, meta


@app.get("/api/results")
def results(limit: int = Query(2000, ge=1, le=5000), era: str = "pulse",
            include_rows: bool = False) -> dict:
    """Resolved live predictions — what the model called, and what happened.

    **`direction_rate_DIAGNOSTIC` is not performance and is reported only as a
    foil.** It asks "was the probability on the correct side of 0.50", which is
    not a bet and is trivially high because most contracts are lopsided.
    Measured on the first 614 resolved rows it read 84% while the actual bets
    ran 38.5%, and 243 rows flagged "correct" were losing positions.

    **`bet_win_rate` is a diagnostic too, as of C11.** Comparing a flat win
    rate against the 0.524 breakeven is a category error on this portfolio:
    0.524 is the breakeven for ~50¢ bets, and the average entry here is ~30¢,
    where losing most bets and being paid multiples on hits is the *design*.
    It read "0.188 vs 0.524" on the picks page — a scary number that measured
    nothing. Retired from the headline exactly as `direction_correct` was.

    The metrics that mean something:

    * `money` — dollars staked → dollars returned at actual prices, the C11
      method: one bet per market (the latest resolved prediction for it),
      entered at the taker price — YES costs the ask, NO costs `1 − bid` —
      one contract per bet, fees excluded. ROI is the only bar.
    * `n_games` — rows are NOT independent. One game produces ~120 correlated
      ladder rows, so 600 rows can be five games. Sample size is games.
    * `brier_model` vs `brier_market` — squared error of each forecast on the
      same events. Lower is better. If the market wins, the model is not
      adding information no matter what the hit rate says.
    """
    with _Session() as s:
        since, before, era_meta = _era_window(s, era)
        q = (select(Prediction)
             .where(Prediction.resolved_outcome.is_not(None)))
        # Era filter — presentation only. The registered measurements
        # (core/analytics.py and friends) never route through here.
        if since is not None:
            q = q.where(Prediction.predicted_at >= since)
        if before is not None:
            q = q.where(Prediction.predicted_at < before)
        rows = s.scalars(
            q.order_by(Prediction.predicted_at.desc()).limit(limit)
        ).all()

    out, games = [], set()
    n_bets = n_bet_wins = n_no_bet = 0
    se_model = se_market = 0.0
    n_scored = 0
    # Money at price (C11): one bet per market, taken from its LATEST resolved
    # prediction — rows arrive newest-first, so first occurrence wins.
    money_seen: set[str] = set()
    money_staked = money_returned = 0.0
    money_bets = 0
    money_games: set[str] = set()

    for p in rows:
        model = _f(p.model_probability)
        market = _f(p.market_mid)
        settled = p.resolved_outcome
        if model is None or settled is None:
            continue
        games.add(p.event_slug or p.market_slug)

        # The bet: model above market -> buy YES; below -> buy NO. Where the
        # two agree there is no position, and scoring it as a win or a loss
        # would flatter or punish the model for doing nothing.
        bet_side = bet_won = None
        if market is not None:
            if abs(model - market) < NO_BET_TOLERANCE:
                n_no_bet += 1
            else:
                bet_side = "YES" if model > market else "NO"
                bet_won = (settled == 1) if bet_side == "YES" else (settled == 0)
                n_bets += 1
                n_bet_wins += int(bet_won)
                # Money at price: what one contract of this bet actually cost
                # (taker frame — YES pays the ask, NO pays 1 − bid) and what
                # settlement actually paid. This is the C11 scoring, and the
                # only aggregate on this endpoint allowed to call itself
                # performance.
                bid, ask = _f(p.market_bid), _f(p.market_ask)
                if p.market_slug not in money_seen and bid is not None and ask is not None:
                    cost = ask if bet_side == "YES" else 1.0 - bid
                    if 0 < cost < 1:
                        money_seen.add(p.market_slug)
                        money_staked += cost
                        money_returned += 1.0 if bet_won else 0.0
                        money_bets += 1
                        money_games.add(p.event_slug or p.market_slug)
            se_model += (model - settled) ** 2
            se_market += (market - settled) ** 2
            n_scored += 1

        human = _human_market(p.market_slug, p.sports_market_type, _f(p.line))
        out.append({
            "market_slug": p.market_slug,
            "event_slug": p.event_slug,
            "human": human,
            "position": _position_label(p.sports_market_type, bet_side, human),
            "type": (p.sports_market_type or "").replace(
                "basketball_team_full_game_", ""),
            "line": _f(p.line),
            "model": model,
            "market": market,
            "settled": settled,
            # DIAGNOSTIC: direction only, not a bet result.
            "direction_correct": (model > 0.5) == (settled == 1),
            "bet_side": bet_side,
            "bet_won": bet_won,
            "model_version": p.model_version,
            "predicted_at": p.predicted_at.isoformat(),
            "tradeable": p.market_ask is not None,
        })

    return {
        **era_meta,
        # The summary is computed over the full window regardless; the rows
        # themselves ship only on request. The page renders KPIs and an era
        # message — shipping 2,000 serialized predictions (700KB, measured)
        # on every load bought nothing anyone displayed.
        "results": out if include_rows else [],
        "n_rows_computed": len(out),
        "summary": {
            "rows": len(out),
            "n_games": len(games),
            "rows_per_game": round(len(out) / len(games), 1) if games else None,
            "n_bets": n_bets,
            "n_no_bet": n_no_bet,
            # THE performance number (C11): dollars staked → dollars returned
            # at actual taker prices, one contract per market, fees excluded.
            "money": {
                "staked": round(money_staked, 2),
                "returned": round(money_returned, 2),
                "roi": (
                    round(money_returned / money_staked - 1.0, 4)
                    if money_staked else None
                ),
                "n_bets": money_bets,
                "n_games": len(money_games),
            },
            "brier_model": round(se_model / n_scored, 4) if n_scored else None,
            "brier_market": round(se_market / n_scored, 4) if n_scored else None,
            # DIAGNOSTIC ONLY (C11): a flat win rate compared to a 0.524
            # breakeven is a category error on ~30¢ tail bets — the portfolio
            # is designed to lose most bets and get paid multiples on hits.
            # Kept, like direction_rate, as a foil — never as performance.
            "bet_win_rate_DIAGNOSTIC": (
                round(n_bet_wins / n_bets, 4) if n_bets else None
            ),
            # Kept last so it reads as the footnote it is. Direction only —
            # never a win rate, and never in a performance aggregate.
            "direction_rate_DIAGNOSTIC": round(
                sum(1 for r in out if r["direction_correct"]) / len(out), 4
            ) if out else None,
        },
    }


# --------------------------------------------------------------------------- #
# The human-confirmed order path
# --------------------------------------------------------------------------- #
#
# This is the only route in the system that can move money, and it is the only
# one that is authenticated. `core/api.py` is otherwise unauthenticated by
# design — it serves a read-only dashboard — so the token here is not a login,
# it is a second physical fact the caller must possess.
#
# Five independent gates, each of which alone is sufficient to refuse:
#
#   1. `MERIDIAN_ORDER_TOKEN` set in the server's environment, and matched.
#   2. `mode` in the request body must be exactly HUMAN_CONFIRM.
#   3. The price and size must match a ShadowOrder the system already computed.
#   4. The market type must pass the same executor policy the picks page uses.
#   5. Postgres refuses to record an accepted order in any other mode.
#
# Gate 3 is the one that is easy to skip and shouldn't be. Without it the token
# holder can submit *any* price and size — the endpoint would be a generic
# trading API with a password. With it, the endpoint can only ever transmit a
# decision the model already made and the shadow pipeline already recorded.

#: Paced well under the ~5 req/s at which the authenticated host starts
#: returning 429 (findings.md V12). Order submission is human-driven and
#: therefore naturally slow; this exists to make a stuck retry loop impossible
#: rather than to shape normal traffic.
_ORDER_BUCKET = TokenBucket(2.0, 2)

class OrderRequest(BaseModel):
    """What the confirm button sends.

    ``limit_price`` and ``quantity`` are both the human's instructions, within
    bounds. The price used to be a server-derived echo; it became editable so
    the human can nudge a limit when the book is a cent away from the model's
    number. What the caller still **cannot** choose: the outcome (the server
    determines direction from the model and the book), the order type (limit,
    by construction), and the mode.

    **Every price in this request is in the COST frame** — the frame the
    ticket displays, where the number is what one contract costs you. For a
    YES order that equals the venue's ``price.value``; for a NO order the
    server converts once, ``price.value = 1 − cost`` (V14). The client never
    performs the conversion, so the wrong-side trade (paying 0.81 for a 0.16
    bet) is not expressible from the UI.

    Validation the server enforces on both prices: within [0.01, 0.99], on the
    1¢ tick (V2). A price more than 5¢ through the far touch additionally
    requires ``acknowledge_crossing`` — the hard confirm the page shows with
    both frames spelled out.
    """

    model_config = ConfigDict(extra="forbid")

    market_slug: str
    mode: str
    #: Human-edited price in the outcome's cost frame. Pre-filled by the page
    #: with the current resting price.
    limit_price: Decimal
    #: Human-chosen. Bounded by the venue minimum and the stake cap.
    quantity: Decimal
    #: Optional attached exit: "then sell at ___", in the same cost frame,
    #: pre-filled with model fair value and human-editable. Stored as a
    #: pre-authorized pending order; submitted by the fill watcher when the
    #: entry fills, exactly as typed, for the filled quantity.
    exit_price: Decimal | None = None
    #: Hard-confirm flag for a price more than 5¢ through the far touch. The
    #: page only sets it after showing the both-frames warning.
    acknowledge_crossing: bool = False


#: Tick and fat-finger bounds for a human-typed price.
_TICK = Decimal("0.01")
_MAX_THROUGH_FAR_TOUCH = Decimal("0.05")


def _validate_typed_price(price: Decimal, *, what: str) -> None:
    """[0.01, 0.99] and 1¢-tick alignment (V2), for a human-typed cost price.

    422 rather than silent rounding: a price the venue would reject, or one
    between ticks, is a typo — and correcting a typo silently is how the
    number on screen stops being the number sent.
    """
    if not (VENUE_MIN_PRICE <= price <= VENUE_MAX_PRICE):
        raise HTTPException(
            status_code=422,
            detail=f"{what} {price} outside the venue's "
                   f"[{VENUE_MIN_PRICE}, {VENUE_MAX_PRICE}] range",
        )
    if price != price.quantize(_TICK):
        raise HTTPException(
            status_code=422,
            detail=f"{what} {price} is not on the 1¢ tick (V2: tick is 0.01 "
                   "on all 96/96 markets measured)",
        )


def _require_order_token(request: Request) -> None:
    """403 unless the caller presents the server's token.

    A missing server-side token is also a 403, not a bypass. The failure mode
    that matters is deploying without the variable set: if absent meant "no
    check", the safest configuration would be the most permissive one.
    """
    expected = (os.environ.get("MERIDIAN_ORDER_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="ordering disabled: MERIDIAN_ORDER_TOKEN is not set on the server",
        )
    presented = (request.headers.get("X-Meridian-Order-Token") or "").strip()
    # Constant-time compare: this is a bearer secret and the endpoint is remote.
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="invalid or missing order token")


@app.post("/api/orders")
def submit_order(req: OrderRequest, request: Request) -> dict:
    """Submit ONE human-confirmed limit order to the venue.

    Returns the venue's answer plus the measured write latency, which is the
    last unmeasured term in `docs/math/write-latency.md`.
    """
    _require_order_token(request)

    # Gate 2. Not a default, not a coercion — an exact match or a refusal.
    # This is checked before anything else touches the database or the venue.
    if req.mode != ExecutionMode.HUMAN_CONFIRM.value:
        raise HTTPException(
            status_code=403,
            detail=(
                f"mode must be {ExecutionMode.HUMAN_CONFIRM.value}; got {req.mode!r}. "
                "No other mode may reach the venue."
            ),
        )

    with _Session() as s:
        # Keyed off the latest *prediction*, not off `shadow_orders`. A pick the
        # Kelly sizer declined to size still has a real market, a real book and
        # a real price — it just has no stored order — and refusing to confirm
        # it would put a button on 7% of the board for no safety reason.
        latest = s.scalar(select(func.max(Prediction.predicted_at)))
        pred = s.scalars(
            select(Prediction).where(
                Prediction.predicted_at == latest,
                Prediction.market_slug == req.market_slug,
            )
        ).first() if latest is not None else None
        if pred is None:
            raise HTTPException(
                status_code=404,
                detail=f"no current pick for {req.market_slug}; nothing to confirm",
            )

        # Gate 4 — the same policy the picks page filters on.
        if not _EXECUTOR_POLICY.is_tradable(pred.sports_market_type):
            raise HTTPException(
                status_code=403,
                detail=f"executor policy refuses {pred.sports_market_type}",
            )

        terms = _derive_order_terms(pred)
        if terms is None:
            raise HTTPException(
                status_code=409,
                detail=f"no usable book for {req.market_slug} right now",
            )
        # Gate 3c — direction. The outcome is the server's determination, never
        # the caller's: a NO pick sent as a YES buy is the opposite trade, and
        # the client does not get a say in which one it is.
        outcome = OutcomeSide(terms["outcome"])

        # Gate 3a — the PRICE is the human's, inside validation. It arrives in
        # the outcome's COST frame (the frame the ticket displays and the
        # human edited); the YES-frame price.value the venue wants is derived
        # HERE, once, from the server's own outcome determination. The client
        # never converts, so a frame error is not expressible from the UI.
        _validate_typed_price(req.limit_price, what="limit price")
        cost = req.limit_price
        server_price = (
            (Decimal("1") - cost) if outcome is OutcomeSide.NO else cost
        )

        # Fat-finger guard: more than 5¢ through the far touch is almost
        # never a nudge — it is the V14 wrong-side shape (paying 0.81 for a
        # 0.16 bet). Refused unless the page's hard confirm was clicked, and
        # the refusal spells out both frames so the human can see which trade
        # they are actually about to make.
        far_touch = Decimal(str(terms["cross_price"]))
        if cost > far_touch + _MAX_THROUGH_FAR_TOUCH and not req.acknowledge_crossing:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"price {cost} is more than {_MAX_THROUGH_FAR_TOUCH} through "
                    f"the far touch ({far_touch} to cross, {terms['outcome']} "
                    f"cost frame; venue price.value would be {server_price}). "
                    "If this is really intended, confirm the crossing on the "
                    "ticket (acknowledge_crossing)."
                ),
            )

        # The attached exit, validated BEFORE any row is written or any money
        # moves: a request that would store an invalid exit must fail whole.
        exit_yes_price = None
        if req.exit_price is not None:
            _validate_typed_price(req.exit_price, what="exit price")
            exit_yes_price = (
                (Decimal("1") - req.exit_price)
                if outcome is OutcomeSide.NO else req.exit_price
            )

        # Gate 3b — the SIZE is the human's, inside bounds. Below the venue
        # minimum is unfillable; above the stake cap is almost always a typo,
        # and there is no cancel button to undo one.
        if req.quantity < VENUE_MIN_QTY:
            raise HTTPException(
                status_code=422,
                detail=f"quantity {req.quantity} is below the venue minimum "
                       f"{VENUE_MIN_QTY}",
            )
        # Stake is computed from the COST, not the price. On a NO order those
        # differ by 1 - price, so charging the cap against `price` would size a
        # cheap NO five times too small and an expensive one five times too big.
        stake = (cost * req.quantity).quantize(Decimal("0.01"))
        cap = _stake_cap()
        if stake > cap:
            # Which limit bound matters to whoever reads the error: "lower your
            # size" and "you do not have the money" are different problems.
            why = ("the account balance" if cap < MAX_ORDER_STAKE_USD
                   else "the per-order cap (MERIDIAN_MAX_ORDER_STAKE_USD)")
            raise HTTPException(
                status_code=422,
                detail=f"stake ${stake} exceeds ${cap} — {why}",
            )

        shadow = s.scalars(
            select(ShadowOrder)
            .where(ShadowOrder.market_slug == req.market_slug)
            .order_by(ShadowOrder.decided_at.desc())
            .limit(1)
        ).first()

        order = build_order(
            market_slug=pred.market_slug,
            side=OrderSide.BUY,          # we only ever open, never close
            limit_price=server_price,    # YES-side price, both outcomes
            quantity=req.quantity,
            decided_at=latest,
            outcome=outcome,
        )

        # Reserve the idempotency key BEFORE going to the venue. The UNIQUE
        # constraint turns a double-click, a duplicated tab, or a retry into an
        # integrity error instead of a second order. accepted=False, so this row
        # is also the record of an attempt that never came back.
        row = PlacedOrder(
            submitted_at=dt.datetime.now(UTC),
            idempotency_key=order.idempotency_key,
            mode=ExecutionMode.HUMAN_CONFIRM.value,
            market_slug=order.market_slug,
            event_slug=pred.event_slug,
            sports_market_type=pred.sports_market_type,
            # `side` records the full direction: a bare "buy" would not
            # distinguish buying OVER from buying UNDER, and those are opposite
            # positions at the same price.
            side=f"{order.side.value}_{order.outcome.value}".lower(),
            order_type=order.order_type,
            limit_price=order.limit_price,
            quantity=order.quantity,
            accepted=False,
            market_bid=pred.market_bid,
            market_ask=pred.market_ask,
            # No longer true by construction now the price is editable: a
            # typed price at or beyond the far touch crosses and pays taker.
            would_rest=cost < far_touch,
            shadow_order_id=shadow.id if shadow is not None else None,
            prediction_id=pred.id,
            notes=(
                None if shadow is not None
                else "size chosen by human; Kelly sizer declined this row"
            ),
        )
        s.add(row)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(
                status_code=409,
                detail="this exact order was already submitted (idempotency key exists)",
            ) from None
        row_id = row.id

        # The attached exit is stored NOW, at click time, linked to the entry
        # by OUR order id — explicit, one-to-one, never matched by similarity.
        # Market slug and price are frozen here (rules 1–2): the watcher sends
        # them as stored and never re-derives either.
        exit_row_id = None
        if exit_yes_price is not None:
            exit_row = PendingExit(
                entry_order_id=row_id,
                market_slug=row.market_slug,     # copied from the entry row
                outcome=outcome.value,
                limit_price=exit_yes_price,      # YES-frame, immutable
                typed_price=req.exit_price,      # what the human saw and typed
                state="PENDING",
            )
            s.add(exit_row)
            s.commit()
            exit_row_id = exit_row.id

    # --- the venue call. Outside the session: never hold a DB connection open
    # --- across a network round trip to a third party.
    _ORDER_BUCKET.acquire()
    try:
        creds = USCredentials.from_env()
    except MissingCredentialsError as exc:
        # Nothing was sent, so the entry definitively does not exist — the
        # attached exit is deleted along with the attempt.
        _fail_order(row_id, error=str(exc), delete_exit_id=exit_row_id)
        raise HTTPException(status_code=503, detail=str(exc)) from None

    payload = order.to_payload()
    try:
        with PolymarketOrderClient(creds) as client:
            result = client.submit_limit_order(payload)
    except OrderSubmissionError as exc:
        # Ambiguous: the order may or may not exist at the venue. The row stays
        # accepted=False and records why, which is the honest state — and the
        # pending exit stays PENDING for the same reason: if the entry does
        # exist and later fills, the exit the human typed must still fire.
        _fail_order(row_id, error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from None

    accepted = result.status_code in (200, 201)
    body = _parse_venue_body(result.body_text)
    venue_id = None
    venue_status = None
    if isinstance(body, dict):
        venue_id = body.get("orderId") or body.get("id") or body.get("clientOrderId")
        venue_status = body.get("status") or body.get("state")

    with _Session() as s:
        stored = s.get(PlacedOrder, row_id)
        stored.accepted = accepted
        stored.http_status = result.status_code
        stored.venue_order_id = str(venue_id) if venue_id else None
        stored.venue_status = str(venue_status) if venue_status else None
        stored.submit_latency_ms = Decimal(str(round(result.elapsed_ms, 2)))
        if result.server_latency_ms is not None:
            stored.venue_latency_ms = Decimal(str(round(result.server_latency_ms, 2)))
        if not accepted:
            stored.error = result.body_text[:1000]
            # A definitively rejected entry never existed at the venue, so its
            # attached exit has nothing to protect. Deleted with a log line
            # (rule 5). A transport error takes the other branch above and
            # leaves the exit PENDING, because the entry MAY exist.
            if exit_row_id is not None:
                x = s.get(PendingExit, exit_row_id)
                x.state = "DELETED"
                x.updated_at = dt.datetime.now(UTC)
                log.info(
                    "pending_exit_deleted", exit_id=exit_row_id,
                    entry_order_id=row_id,
                    reason="entry rejected by the venue — nothing to exit",
                )
        s.commit()
        counts = _order_counts(s)

    log.info(
        "human_confirmed_order",
        market=order.market_slug,
        accepted=accepted,
        http_status=result.status_code,
        submit_latency_ms=round(result.elapsed_ms, 1),
        venue_latency_ms=result.server_latency_ms,
    )

    return {
        "accepted": accepted,
        "http_status": result.status_code,
        "venue_order_id": venue_id,
        "venue_status": venue_status,
        # The measurement this whole path was also built to produce.
        "submit_latency_ms": round(result.elapsed_ms, 1),
        "venue_latency_ms": result.server_latency_ms,
        "order": {
            "market_slug": order.market_slug,
            "side": order.side.value,
            "outcome": order.outcome.value,
            # Both numbers, because on a NO order they differ and only one of
            # them is money leaving the account.
            "limit_price": str(order.limit_price),      # sent as price.value
            "cost_per_contract": str(order.cost_per_contract),
            "quantity": str(order.quantity),
            "stake": str(order.stake),
            "order_type": order.order_type,
        },
        # The attached exit, if one was stored. `state` is PENDING until the
        # fill watcher confirms the entry's fill and submits it.
        "exit": None if exit_row_id is None else {
            "pending_exit_id": exit_row_id,
            "state": "DELETED" if not accepted else "PENDING",
            "sell_at": str(req.exit_price),           # cost frame, as typed
            "price_value": str(exit_yes_price),       # YES frame, as will be sent
        },
        "response": result.body_text[:600],
        **counts,
    }


def _parse_venue_body(text_body: str):
    import json as _json
    try:
        return _json.loads(text_body)
    except (ValueError, TypeError):
        return None


def _fail_order(row_id: int, *, error: str, delete_exit_id: int | None = None) -> None:
    """Record why a submission never produced a venue answer.

    ``delete_exit_id`` is passed only when the failure is definitive (nothing
    was ever sent). An ambiguous transport failure must NOT delete the exit —
    the entry may exist at the venue, and the exit protecting it must survive.
    """
    with _Session() as s:
        stored = s.get(PlacedOrder, row_id)
        if stored is not None:
            stored.error = error[:1000]
        if delete_exit_id is not None:
            x = s.get(PendingExit, delete_exit_id)
            if x is not None:
                x.state = "DELETED"
                x.updated_at = dt.datetime.now(UTC)
                log.info("pending_exit_deleted", exit_id=delete_exit_id,
                         reason="entry was never sent — nothing to exit")
        s.commit()


@app.post("/api/orders/{order_id}/cancel")
def cancel_order(order_id: int, request: Request) -> dict:
    """Cancel ONE resting human order. Human-initiated only, by construction.

    Same invariants as SEND: the server token gates it, the order being
    cancelled is a HUMAN_CONFIRM row this system placed, and no machine path
    exists — the fill watcher has no reference to `cancel_order`, and a test
    pins that. The venue's cancel endpoint is UNVERIFIED (V21): whatever it
    answers is recorded verbatim on the row, which is both the audit trail
    and the measurement — cancel latency is the last unmeasured number in
    docs/math/write-latency.md.

    On a 2xx ack the row goes CANCELLED locally (fills preserved — the
    watcher's exit rules then apply: fills > 0 submits the exit for the
    filled quantity, zero deletes it). On anything else the row's fill state
    is untouched: an unacknowledged cancel proves nothing, and the settlement
    fallback remains the terminal backstop either way.
    """
    _require_order_token(request)

    with _Session() as s:
        row = s.get(PlacedOrder, order_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"no order #{order_id}")
        if not row.accepted or not row.venue_order_id:
            raise HTTPException(
                status_code=409,
                detail=f"order #{order_id} was never accepted by the venue — "
                       "there is nothing resting to cancel",
            )
        if row.fill_status in ("FILLED", "CANCELLED", "EXPIRED"):
            raise HTTPException(
                status_code=409,
                detail=f"order #{order_id} is already terminal "
                       f"({row.fill_status}) — nothing resting to cancel",
            )
        if row.mode != ExecutionMode.HUMAN_CONFIRM.value:
            raise HTTPException(
                status_code=403,
                detail="only HUMAN_CONFIRM orders exist to be cancelled",
            )
        venue_order_id = row.venue_order_id
        # The attempt is recorded BEFORE the venue call, so a cancel that
        # never comes back is still visible as an attempt.
        row.cancel_requested_at = dt.datetime.now(UTC)
        s.commit()

    _ORDER_BUCKET.acquire()
    try:
        creds = USCredentials.from_env()
    except MissingCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    try:
        with PolymarketOrderClient(creds) as client:
            result = client.cancel_order(venue_order_id)
    except OrderSubmissionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None

    acknowledged = result.status_code in (200, 201, 202, 204)
    with _Session() as s:
        row = s.get(PlacedOrder, order_id)
        row.cancel_http_status = result.status_code
        row.cancel_latency_ms = Decimal(str(round(result.elapsed_ms, 2)))
        if result.server_latency_ms is not None:
            row.cancel_venue_latency_ms = Decimal(
                str(round(result.server_latency_ms, 2)))
        # The V21 evidence: whatever the venue actually said, verbatim.
        row.cancel_response = result.body_text[:1000]
        if acknowledged:
            row.fill_status = "CANCELLED"
        s.commit()

    log.info(
        "human_cancel",
        order_id=order_id,
        venue_order_id=venue_order_id,
        acknowledged=acknowledged,
        http_status=result.status_code,
        cancel_latency_ms=round(result.elapsed_ms, 1),
        venue_latency_ms=result.server_latency_ms,
        note="record the response body into findings V21 — this endpoint "
             "shape was unverified until this very request",
    )

    return {
        "acknowledged": acknowledged,
        "http_status": result.status_code,
        # The measurement this endpoint exists to produce.
        "cancel_latency_ms": round(result.elapsed_ms, 1),
        "venue_latency_ms": result.server_latency_ms,
        "response": result.body_text[:600],
    }


@app.get("/api/orders/recent")
def recent_orders(limit: int = Query(25, ge=1, le=100)) -> dict:
    """Real orders with their venue-truth fill state, plus attached exits.

    This is what the picks page's order panel reads. `fill_status` of null
    means the fill watcher has never reconciled the row — shown as such, never
    as OPEN, because "we have not looked" and "we looked and it is resting"
    are different claims (the book_tier lesson, applied to orders).

    A FAILED exit is the loudest thing on this payload: it means the human
    believes a position has a resting exit protecting it and it does not.
    """
    with _Session() as s:
        rows = s.scalars(
            select(PlacedOrder)
            .order_by(PlacedOrder.submitted_at.desc())
            .limit(limit)
        ).all()
        exits = {
            x.entry_order_id: x
            for x in s.scalars(select(PendingExit)).all()
        }

    out = []
    for o in rows:
        x = exits.get(o.id)
        out.append({
            "id": o.id,
            "submitted_at": o.submitted_at.isoformat(),
            "market_slug": o.market_slug,
            "side": o.side,
            "limit_price": _f(o.limit_price),          # YES frame (stored)
            "quantity": _f(o.quantity),
            "accepted": o.accepted,
            "pre_authorized": o.pre_authorized,
            "venue_order_id": o.venue_order_id,
            "fill_status": o.fill_status,               # null = never reconciled
            "filled_quantity": _f(o.filled_quantity),
            "avg_fill_price": _f(o.avg_fill_price),     # YES frame; null = not reported
            "fill_checked_at": (
                o.fill_checked_at.isoformat() if o.fill_checked_at else None
            ),
            "error": (o.error or "")[:200] or None,
            # Cancel state, for the panel's button and the latency readout.
            "cancellable": bool(
                o.accepted and o.venue_order_id
                and o.fill_status not in ("FILLED", "CANCELLED", "EXPIRED")
            ),
            "cancel_requested_at": (
                o.cancel_requested_at.isoformat() if o.cancel_requested_at else None
            ),
            "cancel_http_status": o.cancel_http_status,
            "cancel_latency_ms": _f(o.cancel_latency_ms),
            "exit": None if x is None else {
                "state": x.state,
                "sell_at": _f(x.typed_price),           # cost frame, as typed
                "price_value": _f(x.limit_price),       # YES frame, as sent
                "error": (x.error or "")[:200] or None,
            },
        })
    return {"orders": out}


# --------------------------------------------------------------------------- #
# Fill watcher lifecycle
# --------------------------------------------------------------------------- #
#
# The watcher runs inside this process because this process is the only one
# that places orders — the read-back loop belongs next to the write path. It
# starts only when ordering itself is enabled (token + credentials), which is
# also the condition under which /api/status judges its heartbeat: a host that
# cannot order has nothing to reconcile.

_fill_watcher = None


@app.on_event("startup")
def _maybe_start_fill_watcher() -> None:
    global _fill_watcher
    if os.environ.get("MERIDIAN_FILL_WATCHER", "1") != "1":
        log.info("fill_watcher_disabled", reason="MERIDIAN_FILL_WATCHER != 1")
        return
    if not (os.environ.get("MERIDIAN_ORDER_TOKEN") or "").strip():
        return                      # ordering disabled; nothing to reconcile
    try:
        creds = USCredentials.from_env()
    except MissingCredentialsError as exc:
        log.warning("fill_watcher_not_started", reason=str(exc))
        return
    from core.fill_watcher import FillWatcher

    _fill_watcher = FillWatcher(_Session, creds)
    _fill_watcher.start()


@app.on_event("shutdown")
def _stop_fill_watcher() -> None:
    if _fill_watcher is not None:
        _fill_watcher.stop()


@app.get("/api/live-fv")
def live_fv() -> dict:
    """Formula fair value for in-game moneylines. **Display only.**

    Deliberately separate from `/api/picks`. That endpoint returns *picks* —
    things with an order, a size and a confirm button behind them. This
    returns an unvalidated number for looking at, and keeping them apart is
    what stops the second becoming the first by accident. See
    `core/live_fv.py`; nothing here imports the executor.
    """
    from core.live_fv import DEFAULT_SIGMA, GAP_HIGHLIGHT, as_dict, build_live_fv

    with _Session() as s:
        rows = build_live_fv(s)
    return {
        "rows": [as_dict(r) for r in rows],
        "sigma": DEFAULT_SIGMA,
        "gap_highlight": GAP_HIGHLIGHT,
        "caption": "formula FV — unvalidated, display only",
        "tradable": False,
    }


@app.get("/api/ev-guard")
def ev_guard() -> dict:
    """Hypothesis #9 as an alert: open button positions vs live formula FV.

    Information only — the guard has no code path to an order, and the FV it
    runs on is the same UNVALIDATED formula as the strip. The background
    thread (started below when an ntfy topic is configured) pushes EDGE-GONE
    transitions to the phone; this endpoint is the same rows for the page.
    """
    from core.ev_guard import CAPTION, build_guard_rows

    with _Session() as s:
        rows = build_guard_rows(s)
    return {
        "rows": [r.as_dict() for r in rows],
        "caption": CAPTION,
        "tradable": False,
    }


_ev_guard = None


@app.on_event("startup")
def _maybe_start_ev_guard() -> None:
    """Alert loop only — and only when there is a phone to alert. The rows
    are always served by the endpoint; the thread exists for the pushes.

    The pushes themselves go through core.notify.push under kind "ev", so
    with the default MERIDIAN_NTFY_SCOPE=tickets they are written to the
    muted log rather than the phone (docs/ops/notifications.md)."""
    global _ev_guard
    if os.environ.get("MERIDIAN_EV_GUARD", "1") != "1":
        return
    topic = (os.environ.get("MERIDIAN_NTFY_TOPIC") or "").strip()
    if not topic:
        return
    from core.ev_guard import EVGuard

    _ev_guard = EVGuard(_Session, topic=topic)
    _ev_guard.start()


@app.on_event("shutdown")
def _stop_ev_guard() -> None:
    if _ev_guard is not None:
        _ev_guard.stop()


@app.get("/api/live-totals-fv")
def live_totals_fv() -> dict:
    """Formula fair value for in-game TOTALS rungs. **Display only.**

    Sibling of `/api/live-fv`. Same contract: an unvalidated number for
    looking at, kept away from `/api/picks` so it cannot become a pick by
    accident. Nothing here imports the executor.
    """
    from core.live_totals_fv import GAP_HIGHLIGHT, as_dict, build_live_totals_fv

    with _Session() as s:
        rows = build_live_totals_fv(s)
    return {
        "rows": [as_dict(r) for r in rows],
        "gap_highlight": GAP_HIGHLIGHT,
        "caption": "formula FV — unvalidated, display only",
        "tradable": False,
    }


# --------------------------------------------------------------------------- #
# Leagues, and the per-game deep dive
# --------------------------------------------------------------------------- #


@app.get("/api/quote")
def quote_status() -> dict:
    """The QUOTE shadow run, for its page. **Read-only, display only.**

    Three parts, three different truths:

    * ``heartbeat`` — the engine's own beat row, the only thing that says the
      process is alive. The engine runs in its own container; this API cannot
      see its memory.
    * ``quoting`` — what the engine is quoting NOW, reconstructed from the
      same observations through the same imported code (`Observation`,
      including its `is_quotable` band). Reconstructed, not read: labelled so
      on the page. Two renderings of one decision is the drift this repo
      keeps re-learning about, which is why this reuses the engine's class
      rather than restating its rules.
    * ``regimes`` — the pre-registered measurement (docs/math/quote-shadow.md)
      from `core.quote.report.build_report`, verbatim: floors, counts, and a
      verdict that stays "NO DATA" until 500 settled fills AND 10 games per
      regime. The page must render accruing-ness, never invent a verdict.
    """
    from core.quote.engine import SERVICE_QUOTE, ShadowQuoter
    from core.quote.report import FLOOR_FILLS, FLOOR_GAMES, build_report

    now = dt.datetime.now(UTC)
    with _Session() as s:
        beats = s.execute(text(
            "SELECT beat_at, interval_seconds, cycle_seconds, rows_written, "
            "rows_total, game_live FROM service_heartbeats WHERE service = :svc"
        ), {"svc": SERVICE_QUOTE}).first()

        # The engine's own observation query, via the engine's own method —
        # bound as a plain function so no engine (and no writer) is built.
        observations = ShadowQuoter._observations(None, s)

        recent = s.execute(text("""
            SELECT market_slug, regime, side, quote_price, mid_at_quote,
                   mid_at_fill, filled_at, settlement
            FROM shadow_quote_fills ORDER BY filled_at DESC LIMIT 40
        """)).all()

        reports = build_report(s)

    hb_age = (now - beats.beat_at).total_seconds() if beats else None
    quoting = [{
        "market_slug": ob.market_slug,
        "regime": "ingame" if ob.is_live else "pregame",
        "bid": ob.bid, "ask": ob.ask,
        "spread": round(ob.ask - ob.bid, 4),
        "age_seconds": round((now - ob.captured_at).total_seconds(), 1),
    } for ob in observations if ob.is_quotable]

    def _cm(cm):
        return None if cm is None else {
            "mean": cm.mean, "lo": cm.lo, "hi": cm.hi,
            "n": cm.n, "n_clusters": cm.n_clusters, "stderr": cm.stderr,
        }

    return {
        "heartbeat": None if not beats else {
            "age_seconds": round(hb_age, 1),
            "interval_seconds": float(beats.interval_seconds),
            "cycle_seconds": _f(beats.cycle_seconds),
            "fills_last_cycle": beats.rows_written,
            "fills_total": beats.rows_total,
            "game_live": beats.game_live,
            "verdict": heartbeat.verdict(hb_age, float(beats.interval_seconds)),
        },
        "quotable_now": len(quoting),
        "observed_now": len(observations),
        "quoting": sorted(quoting, key=lambda q: q["market_slug"])[:60],
        "recent_fills": [{
            "market_slug": r.market_slug, "regime": r.regime, "side": r.side,
            "quote_price": _f(r.quote_price), "mid_at_quote": _f(r.mid_at_quote),
            "mid_at_fill": _f(r.mid_at_fill),
            "filled_at": r.filled_at.isoformat(),
            "settlement": r.settlement,
        } for r in recent],
        "floors": {"fills": FLOOR_FILLS, "games": FLOOR_GAMES},
        "regimes": {name: {
            "n_fills": rep.n_fills, "n_settled": rep.n_settled,
            "n_games": rep.n_games, "staked": round(rep.staked, 2),
            "returned": round(rep.returned, 2),
            "roi": _cm(rep.roi_clustered),
            "capture": _cm(rep.capture_clustered),
            "at_floor": rep.at_floor, "verdict": rep.verdict,
        } for name, rep in sorted(reports.items())},
    }


# ── Wallet cache (2026-09-04) ────────────────────────────────────────────
# The wallet folds every shadow fill and depth-joins each one against
# book_levels (19.7M rows). At 38k fills that takes MINUTES, and the page polls
# every 15s — so /api/wallet never returned and the page sat on "loading..."
# forever. It looked like a render bug and was a latency bug; before the wallet
# was seeded the endpoint short-circuited on seeded=false and never did the
# fold, which is why this only appeared once a seed line existed.
#
# The wallet is a DISPLAY instrument, so a minute-old fold is fine. What is not
# fine is a request that hangs: the endpoint now ALWAYS returns immediately,
# serving the last good value and refreshing in the background.
_WALLET_CACHE: dict = {"value": None, "at": 0.0, "computing": False}
_WALLET_TTL_S = 90.0
_WALLET_LOCK = __import__("threading").Lock()


def _wallet_refresh() -> None:
    """Recompute the fold off-request. Failures leave the last good value."""
    import time as _t
    try:
        value = _wallet_compute()
        _WALLET_CACHE["value"] = value
        _WALLET_CACHE["at"] = _t.time()
    except Exception:  # noqa: BLE001 — a failed refresh must not kill the thread
        log.exception("wallet_refresh_failed")
    finally:
        _WALLET_CACHE["computing"] = False


@app.get("/api/wallet")
def wallet_status() -> dict:
    """Cached wrapper. NEVER blocks — see the note above."""
    import threading
    import time as _t
    fresh = (_t.time() - _WALLET_CACHE["at"]) < _WALLET_TTL_S
    if _WALLET_CACHE["value"] is not None and fresh:
        return _WALLET_CACHE["value"]

    with _WALLET_LOCK:
        if not _WALLET_CACHE["computing"]:
            _WALLET_CACHE["computing"] = True
            threading.Thread(target=_wallet_refresh, daemon=True).start()

    if _WALLET_CACHE["value"] is not None:
        out = dict(_WALLET_CACHE["value"])
        out["stale_s"] = round(_t.time() - _WALLET_CACHE["at"], 1)
        return out
    # First call ever: say so rather than hang. The page renders this state.
    return {"available": False,
            "note": "computing the fold for the first time — reload in a moment",
            "computing": True,
            "live": {"seeded": False, "books": {}, "unseeded": []},
            "historical": {"books": {}},
            "bars": {"daily": 3.29, "monthly": 100.0}}


def _wallet_compute() -> dict:
    """The paper-wallet scoreboard (docs/math/paper-wallet-scoreboard.md), for
    its page. **Read-only, display only — an instrument, never evidence.** Folds
    shadow_quote_fills live through core.quote.wallet; both P&L arms always, the
    toll meter, the drawdown + capital-clip 'bleeding' meters, and the
    depth-absent suppression line, per league. Not league-tabbed: the wallet is
    two ledgers shown side by side (money separation applies most of all)."""
    from core.quote import wallet as W

    try:
        with _Session() as s:
            live, historical, meta = W.gather(s)
    except Exception as exc:  # noqa: BLE001 — tables may be absent pre-deploy
        m = str(exc).lower()
        if ("does not exist" in m or "could not connect" in m
                or "connection refused" in m):
            return {"available": False, "note": "wallet tables not present yet",
                    "live": {"seeded": False, "books": {}, "unseeded": []},
                    "historical": {"books": {}},
                    "bars": {"daily": W.DAILY_BAR, "monthly": W.MONTHLY_BAR}}
        raise

    def _absent(am) -> dict:
        return {
            "count": am["depth_absent"], "rate": am["depth_absent_rate"],
            "ingame_rate": am["ingame_absent_rate"],
            "wouldbe_opt_sum": am["absent_wouldbe_opt_sum"],
            "wouldbe_conc_sum": am["absent_wouldbe_conc_sum"],
            "wouldbe_opt_mean_c": am["absent_wouldbe_opt_mean_c"],
            "wouldbe_conc_mean_c": am["absent_wouldbe_conc_mean_c"],
            "trigger_10pct_ingame": am["trigger_10pct_ingame"],
            "n_depth_sized": am["n_depth_sized"],
            "n_depth_parent_stamped": am["n_depth_parent_stamped"],
            "depth_parent_stamped_rate": am["depth_parent_stamped_rate"],
            "parent_stamped_staleness_max_s": am["parent_stamped_staleness_max_s"],
            "parent_stamped_staleness_mean_s": am["parent_stamped_staleness_mean_s"],
        }

    def _book(b) -> dict:
        return {
            "seed": b.seed,
            "optimistic": b.optimistic, "concession": b.concession,
            "pnl_opt": b.optimistic - b.seed, "pnl_conc": b.concession - b.seed,
            "toll": b.toll,
            "reserved": max(b.reserved_conc, 0.0),
            "available": b.available_to_size,
            "drawdown": (1.0 - b.concession / b.seed) if b.seed else 0.0,
            "capital_clip_rate": (b.n_clipped_reservation / b.n_fills)
                                 if b.n_fills else 0.0,
            "halted": b.halted,
            "halt_note": b.halt_line.note if b.halt_line else None,
            "n_fills": b.n_fills, "n_clipped_depth": b.n_clipped_depth,
            "n_clipped_reservation": b.n_clipped_reservation, "n_zero": b.n_zero,
            "n_zero_no_depth": b.n_zero_no_depth,
            "n_zero_no_capital": b.n_zero_no_capital,
            "n_zero_both": b.n_zero_both,
            "unrealized_opt": b.unrealized_opt,
            "unrealized_conc": b.unrealized_conc,
            "daily_opt": b.daily_opt, "daily_conc": b.daily_conc,
            "peak_concurrent_markets": b.peak_concurrent_markets,
            "peak_concurrent_contracts": b.peak_concurrent_contracts,
            "tw_concurrent_markets": b.tw_concurrent_markets,
            "tw_concurrent_contracts": b.tw_concurrent_contracts,
        }

    return {
        "available": True,
        "as_of": dt.datetime.now(UTC).isoformat(),
        "bars": {"daily": W.DAILY_BAR, "monthly": W.MONTHLY_BAR},
        # LIVE wallet: forward-only from each seed line; refused if unseeded
        # (ruling ab8be48). Never the August cohort.
        "live": {
            "seeded": meta["seeded"],
            "unseeded": meta["unseeded"],
            "seeds": meta["seeds"],
            "books": {slug: _book(b) for slug, b in live.books.items()},
            "depth_absent": _absent(meta["live_absent"]),
        },
        # HISTORICAL print: the full cohort, LABELLED — not the live balance.
        "historical": {
            "books": {slug: _book(b) for slug, b in historical.books.items()},
            "depth_absent": _absent(meta["historical_absent"]),
        },
        # Anomaly (should be 0): NULL own-stamp at/after the own-stamp epoch —
        # a broken invariant, counted out of the join. Nonzero = investigate.
        "post_epoch_null_levels": meta.get("post_epoch_null_levels", 0),
        # Registered caveat (term 3): depth-sized numbers are per-fill optimistic
        # (recorded depth is others' resting size holding time priority).
        "caveat": ("instrument not evidence; depth-sized fills are per-fill "
                   "optimistic (others' resting size, time priority)"),
    }


#: A PULSE estimate older than this does not paint the board. The engine
#: cycles every 1s and decides every few seconds during a live game, so ten
#: minutes of silence means the game ended or the engine stopped — either
#: way, a stale FV on a live row is worse than a dash.
PULSE_LATEST_MAX_AGE_SECONDS = 600.0

#: PULSE runs on exactly one league. It is fitted and gated on WNBA
#: (core/pulse, docs/math/pulse-live.md) and has never run on another, so a
#: count — or a zero — under any other league's tab would read as "PULSE ran
#: here and found this", which is false. Both PULSE endpoints name this league
#: and the pages render one line, not numbers, anywhere else.
PULSE_LEAGUE = "wnba"


def _pulse_scope_note(lg) -> str:
    return ("PULSE exists only for WNBA — it is fitted and gated there (core/pulse) "
            f"and resumes with the WNBA playoffs. No PULSE runs on {lg.name}, so there "
            "are no numbers to show.")


@app.get("/api/pulse/latest")
def pulse_latest(league: str | None = None) -> dict:
    """The newest PULSE decision per market, for the board's in-play rows.

    Read-only, display only — the same rows the deep-dive tape reads, one per
    market, so the operator watching a live game sees what the model is
    thinking instead of a dead board. Serves recent decisions only
    (`PULSE_LATEST_MAX_AGE_SECONDS`); no decision logic lives here, and
    nothing served here can become an order — the page pins that.

    `fair_value` is the YES-frame probability (the board's Model FV column's
    own frame). `edge_net` is PULSE's edge at ITS limit in the position's
    cost frame, net of fees — a different quantity from anything the page
    derives against the current touch, and labelled as such there.
    """
    lg = _league_or_400(league)
    with _Session() as s:
        rows = s.execute(text("""
            SELECT DISTINCT ON (market_slug)
                   market_slug, event_slug, decided_at, phase, action, side,
                   limit_price, fair_value, edge_net, market_bid, market_ask,
                   score, period, strategy, line, margin, minutes_left,
                   minutes_left_is_estimate, total_so_far, projected_total,
                   total_sigma
              FROM pulse_decisions
             WHERE event_slug LIKE :prefix
               AND decided_at > now() - make_interval(secs => :max_age)
             ORDER BY market_slug, decided_at DESC
        """), {"prefix": f"{lg.slug}-%",
               "max_age": PULSE_LATEST_MAX_AGE_SECONDS}).all()

        # Open shadow positions: a filled entry, unsettled, with no filled
        # exit. The resting exit (unfilled, not withdrawn) rides along so the
        # row can show what protects the position. Frames per the table's own
        # docstring: every price YES frame, `no` costs 1 − limit_price, and
        # entry/exit subtract directly.
        positions = s.execute(text("""
            SELECT e.market_slug, e.event_slug, e.side,
                   e.limit_price AS entry_price, e.contracts, e.stake_usd,
                   e.filled_at, e.decided_at,
                   x.limit_price AS exit_limit, x.filled_at AS exit_filled_at
              FROM pulse_decisions e
              LEFT JOIN LATERAL (
                    SELECT limit_price, filled_at FROM pulse_decisions
                     WHERE entry_id = e.id AND action = 'exit'
                       AND withdrawn_at IS NULL
                     ORDER BY decided_at DESC LIMIT 1
              ) x ON true
             WHERE e.event_slug LIKE :prefix
               AND e.action = 'enter'
               AND e.filled_at IS NOT NULL
               AND e.settlement IS NULL
               AND (x.filled_at IS NULL)
        """), {"prefix": f"{lg.slug}-%"}).all()

        # The activity feed: recent enters/exits across all games, newest
        # first. Window is a whole game (3h) rather than the estimate window —
        # the feed is the story so far, not the current thought.
        feed = s.execute(text("""
            SELECT decided_at, event_slug, market_slug, sports_market_type,
                   strategy, action, side, limit_price, contracts, reason,
                   entry_id, id, filled_at, withdrawn_at
              FROM pulse_decisions
             WHERE event_slug LIKE :prefix
               AND action IN ('enter', 'exit')
               AND decided_at > now() - interval '3 hours'
             ORDER BY decided_at DESC
             LIMIT 30
        """), {"prefix": f"{lg.slug}-%"}).all()
    now = dt.datetime.now(UTC)
    return {
        "league": lg.slug,
        "pulse_league": PULSE_LEAGUE,
        "max_age_seconds": PULSE_LATEST_MAX_AGE_SECONDS,
        "markets": {r.market_slug: {
            "event_slug": r.event_slug,
            "decided_at": r.decided_at.isoformat(),
            "age_seconds": round((now - r.decided_at).total_seconds(), 1),
            "phase": r.phase,
            "action": r.action,
            "side": r.side,
            "limit_price": _f(r.limit_price),
            "fair_value": _f(r.fair_value),
            "edge_net": _f(r.edge_net),
            "bid_at_decision": _f(r.market_bid),
            "ask_at_decision": _f(r.market_ask),
            "score": r.score,
            "period": r.period,
            "strategy": r.strategy,
            "line": _f(r.line),
            "margin": r.margin,
            "minutes_left": _f(r.minutes_left),
            "minutes_left_is_estimate": bool(r.minutes_left_is_estimate),
            # The engine's own projections, recorded per decision — the
            # ribbon's "what the model thinks the game IS". Serialized, never
            # derived here.
            "total_so_far": r.total_so_far,
            "projected_total": _f(r.projected_total),
            "total_sigma": _f(r.total_sigma),
        } for r in rows},
        "positions": {r.market_slug: {
            "side": r.side,
            "entry_price": _f(r.entry_price),          # YES frame
            "contracts": _f(r.contracts),
            "stake_usd": _f(r.stake_usd),
            "entered_at": r.filled_at.isoformat(),
            "exit_limit": _f(r.exit_limit),            # YES frame; null = no rest
        } for r in positions},
        "feed": [{
            "id": r.id,
            "decided_at": r.decided_at.isoformat(),
            "age_seconds": round((now - r.decided_at).total_seconds(), 1),
            "event_slug": r.event_slug,
            "market_slug": r.market_slug,
            "type": (r.sports_market_type or "").replace(
                "basketball_team_full_game_", ""),
            "action": r.action,
            "side": r.side,
            "limit_price": _f(r.limit_price),
            "contracts": _f(r.contracts),
            "reason": r.reason,
            "entry_id": r.entry_id,
            "filled": r.filled_at is not None,
            "withdrawn": r.withdrawn_at is not None,
        } for r in feed],
    }


@app.get("/api/pulse")
def pulse_status(league: str | None = None) -> dict:
    """PULSE's accruing record, for the Model performance page. Read-only.

    Serializes `core.pulse.live_report.build_report` verbatim — the same
    contract as `/api/quote`: the registered floors are the module's own
    constants, the verdict string is the report's own, and this endpoint adds
    nothing that could disagree with `python -m core.pulse.live_report`.
    Below the floors the page renders counts and an accruing state, never a
    performance number.

    League-honest (2026-09-13). PULSE runs on `PULSE_LEAGUE` alone, so any
    other league gets `available: False`, one line saying so, and no counts.
    Before this the endpoint took no league and the page drew the WNBA count
    under whichever tab was selected: a number that legitimately stopped
    moving when the WNBA regular season ended (2026-08-31) sat, unlabelled,
    under the CFB tab and read as a CFB PULSE that never worked. The count
    still stands still between the season and the playoffs; `last_decision`
    now sits beside it, and both describe the same estimates version.
    """
    from core.pulse.live_report import (
        FLOOR_ENTRY_FILLS,
        FLOOR_GAMES,
        build_report,
    )

    lg = _league_or_400(league)
    if lg.slug != PULSE_LEAGUE:
        return {"available": False, "league": lg.slug, "pulse_league": PULSE_LEAGUE,
                "note": _pulse_scope_note(lg)}

    with _Session() as s:
        # build_report returns one report PER ESTIMATES VERSION (era separation,
        # PR #23) and must never be blended. This endpoint shows the NEWEST
        # version; the API previously treated the dict as a single report and
        # 500'd on every call, which is why the PULSE page showed nothing.
        _reports = build_report(s)
        if not _reports:
            return {"available": False, "league": lg.slug, "pulse_league": PULSE_LEAGUE,
                    "note": "no PULSE decisions recorded yet",
                    "floors": {"entry_fills": FLOOR_ENTRY_FILLS, "games": FLOOR_GAMES}}
        _version = sorted(_reports)[-1]
        r = _reports[_version]
        # The timestamps describe the population that was counted. The count
        # is per estimates version; min/max over the whole table would date a
        # v2 count with v1's first decision.
        bounds = s.execute(text(
            "SELECT min(decided_at), max(decided_at) FROM pulse_decisions "
            "WHERE estimates_version = :v"
        ), {"v": _version}).one()

    def _cm(cm):
        return None if cm is None else {
            "mean": cm.mean, "lo": cm.lo, "hi": cm.hi,
            "n": cm.n, "n_clusters": cm.n_clusters, "stderr": cm.stderr,
        }

    return {
        "available": True,
        "league": lg.slug,
        "pulse_league": PULSE_LEAGUE,
        "estimates_version": _version,
        "floors": {"entry_fills": FLOOR_ENTRY_FILLS, "games": FLOOR_GAMES},
        "n_decisions": r.n_decisions,
        "n_entries": r.n_entries,
        "n_entry_fills": r.n_entry_fills,
        "n_round_trips": r.n_round_trips,
        "n_rides_settled": r.n_rides_settled,
        "n_games": r.n_games,
        "trip_staked": round(r.trip_staked, 4),
        "trip_pnl": round(r.trip_pnl, 4),
        "ride_staked": round(r.ride_staked, 4),
        "ride_returned": round(r.ride_returned, 4),
        "trip_roi": _cm(r.trip_roi_clustered),
        "ride_roi": _cm(r.ride_roi_clustered),
        "at_floor": r.at_floor,
        "verdict": r.verdict,
        "first_decision": bounds[0].isoformat() if bounds[0] else None,
        "last_decision": bounds[1].isoformat() if bounds[1] else None,
    }


@app.get("/api/leagues")
def leagues() -> dict:
    """The league tabs, and what to say when one has no data.

    The header used to read a hardcoded "MERIDIAN · WNBA". League is now a
    parameter end to end (`core/leagues.py`), so a second league is a table
    entry and a tab rather than a search-and-replace across three pages.
    """
    return {
        "default": default_league().slug,
        "leagues": [
            {
                "slug": lg.slug,
                "name": lg.name,
                "recorded": lg.recorded,
                "empty_state": lg.empty_state,
            }
            for lg in LEAGUES.values()
        ],
    }


def _league_or_400(slug: str | None):
    try:
        return get_league(slug)
    except UnknownLeagueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/games")
def games(league: str | None = None, limit: int = Query(60, ge=1, le=500),
          era: str = "pulse") -> dict:
    """Games this league's model has shadow-traded, newest first.

    Driven by `shadow_orders`: a game the model never decided anything in has
    nothing for the deep dive to show, and listing it would promise a page
    that turns out empty.

    ``era`` filters the LIST only — `/api/game/{slug}` opens any game clicked
    from either view, so the archive stays readable in full. A game belongs
    to the era of its last decision (core/era.py).
    """
    lg = _league_or_400(league)
    if not lg.recorded:
        return {"league": lg.slug, "league_name": lg.name,
                "recorded": False, "empty_state": lg.empty_state, "games": []}

    with _Session() as s:
        since, before, era_meta = _era_window(s, era)
        rows = list_games(s, league=lg.slug, limit=limit,
                          since=since, before=before)
    return {
        **era_meta,
        "league": lg.slug,
        "league_name": lg.name,
        "recorded": True,
        "empty_state": lg.empty_state,
        "games": [
            {
                "event_slug": g["event_slug"],
                "label": g["label"],
                "n_trades": g["n_trades"],
                "n_resolved": g["n_resolved"],
                "first_decision": g["first_decision"].isoformat() if g["first_decision"] else None,
                "last_decision": g["last_decision"].isoformat() if g["last_decision"] else None,
                "tipoff": g["tipoff"],
            }
            for g in rows
        ],
    }


@app.get("/api/game/{event_slug}")
def game(event_slug: str, timeline: bool = True, bucket_seconds: int = 30) -> dict:
    """One game, every shadow trade, in the order the model decided them.

    Read the two halves of this payload differently, because they sit on
    opposite sides of the decision boundary:

    * ``trades[].context`` is the game **as of** each decision — the latest
      snapshot at or before ``decided_at``, never a later one. Attaching the
      newest score to an old decision would show the model trading a game it
      had not seen (`core/game_detail.py`).
    * ``timeline`` is what happened **after**, and is context for the reader
      only. Nothing in it was an input to any decision on this page.

    ``pnl_if_filled`` is conditional and named for it: these orders were never
    sent, and most of them would have rested on the book.
    """
    lg = league_of_slug(event_slug)
    if lg is None:
        raise HTTPException(
            status_code=400,
            detail=f"no known league in event slug {event_slug!r}",
        )

    with _Session() as s:
        detail = build_game_detail(
            s,
            event_slug,
            league=lg.slug,
            human_label=_human_market,
            bucket_seconds=max(5, min(bucket_seconds, 600)),
            with_timeline=timeline,
        )

    if not detail.trades:
        raise HTTPException(
            status_code=404,
            detail=f"no shadow trades recorded for {event_slug!r}",
        )

    return {
        "event_slug": detail.event_slug,
        "league": detail.league,
        "league_name": lg.name,
        "label": detail.label,
        "tipoff": detail.tipoff.isoformat() if detail.tipoff else None,
        "final_score": detail.final_score,
        "n_trades": len(detail.trades),
        "n_anchor": detail.n_anchor,
        "n_pulse": detail.n_pulse,
        "n_live_decisions": detail.n_live_decisions,
        "timeline_market": detail.timeline_market,
        "trades": [
            {
                "id": t.shadow_order_id,
                "decided_at": t.decided_at.isoformat(),
                "hours_to_tipoff": (
                    round(t.hours_to_tipoff, 2) if t.hours_to_tipoff is not None else None
                ),
                "market_slug": t.market_slug,
                "human": t.human,
                # ANCHOR shadow orders are always the YES side; a PULSE row's
                # side is its own and the label must say which.
                "position": _position_label(
                    t.market_type,
                    "YES" if t.model == "anchor" or t.side == "yes" else "NO",
                    t.human),
                "type": (t.market_type or "").replace(
                    "basketball_team_full_game_", ""),
                "line": t.line,
                "side": t.side,
                "limit_price": t.limit_price,
                "quantity": round(t.quantity, 4),
                "would_rest": t.would_rest,
                "binding_constraint": t.binding_constraint,
                "model": t.model,
                "action": t.action,
                "filled": t.filled,
                "model_fv": t.model_fv,
                "bid": t.market_bid,
                "ask": t.market_ask,
                "spread": round(t.spread, 4) if t.spread is not None else None,
                "edge": t.edge_net,
                "context": {
                    "score": t.context.score,
                    "margin": t.context.margin,
                    "period": t.context.period,
                    "minutes_left": (
                        round(t.context.minutes_left, 1)
                        if t.context.minutes_left is not None else None
                    ),
                    "minutes_left_is_estimate": t.context.minutes_left_is_estimate,
                    "is_live": t.context.is_live,
                    "age_seconds": (
                        round(t.context.context_age_seconds)
                        if t.context.context_age_seconds is not None else None
                    ),
                    "note": t.context.note,
                },
                "resolved_outcome": t.resolved_outcome,
                "bet_won": t.bet_won,
                "pnl_if_filled": (
                    round(t.pnl_if_filled, 4) if t.pnl_if_filled is not None else None
                ),
            }
            for t in detail.trades
        ],
        "timeline": [
            {
                "at": p.at.isoformat(),
                "score": p.score,
                "margin": p.margin,
                "period": p.period,
                "bid": p.bid,
                "ask": p.ask,
                "mid": round(p.mid, 4) if p.mid is not None else None,
            }
            for p in detail.timeline
        ],
    }
@app.get("/api/bankroll")
def bankroll(refresh: bool = False) -> dict:
    """The account balance. **Read-only** — a GET against a signed GET.

    `refresh=true` polls the venue now instead of serving the stored reading:
    the on-demand half of the poller, for the moment after a fill when the
    scheduler's twenty-minute cadence is too slow to trust. It cannot place,
    modify or cancel anything — `PolymarketAuthedClient` has no verb but `get`.
    """
    from core.bankroll import BankrollUnavailable
    from core.bankroll import refresh as refresh_bankroll
    from core.polymarket.client import MissingCredentialsError

    if not refresh:
        return _bankroll_block() or {}
    try:
        return refresh_bankroll().to_dict()
    # MissingCredentialsError is a SIBLING of BankrollUnavailable, not a
    # subclass -- both derive straight from RuntimeError -- so it used to escape
    # this handler and surface as a bare 500 "Internal Server Error". It is a
    # NAMED, expected condition, and on a credential rotation or expiry the
    # operator would get no reason at all from the one endpoint whose job is to
    # say what the account looks like. Same 503, and the detail names the
    # missing variables.
    except (BankrollUnavailable, MissingCredentialsError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:200]) from exc


@app.get("/picks")
def picks_page() -> RedirectResponse:
    """Kept as a permanent alias, not a page.

    The picks page *is* the landing page now — the old live board it used to
    sit behind was a click the operator spent every session getting past. One
    page means one URL, so this redirects rather than serving a second copy;
    two documents rendering the same picks is exactly how the send button and
    the numbers beside it drift apart.

    302 rather than 301: a permanently-cached redirect in the operator's
    browser would survive any future decision to give `/picks` its own page
    again, and there is no cost to re-asking.
    """
    return RedirectResponse(url="/", status_code=302)


@app.get("/api/analytics")
def analytics() -> dict:
    """Pre-computed model-performance data.

    Built by `python -m core.analytics`, not computed here: a walk-forward run
    takes ~17s locally and far longer against a remote database.

    The path comes from `core.paths.analytics_path()` — the same call the
    writer makes, never a second expression that happens to look the same.

    **The error names the path.** For six weeks this returned a bare "run
    `python -m core.analytics` first" while the operator was running exactly
    that, successfully, on the host: the api container had no mount for the
    artifact root, so writer and reader resolved the same code to different
    disks. An error that cannot distinguish "never built" from "built where I
    cannot see it" sends you to re-run a job that already worked.
    """
    import json

    from core.paths import DATA_DIR_CONTAINER, analytics_path, data_dir

    path = analytics_path()
    if not path.exists():
        root = data_dir()
        if not root.is_dir():
            # The artifact root itself is missing. Inside a container that
            # means the compose mount is absent, not that analytics never ran.
            return {
                "error": (
                    f"no artifact root at {root} — nothing has been built here, "
                    f"and if this is the api container the {DATA_DIR_CONTAINER} "
                    "mount is missing (see docs/infra/analytics-path.md)"
                ),
                "looked_in": str(path),
                "data_dir": str(root),
                "data_dir_exists": False,
            }
        return {
            "error": f"no analytics blob at {path} — run `python -m core.analytics`",
            "looked_in": str(path),
            "data_dir": str(root),
            "data_dir_exists": True,
        }
    body = json.loads(path.read_text())
    # The artifact records no build time of its own, so the file's mtime is
    # the truth about when it was generated — surfaced so the page can say
    # "generated 3h ago" instead of presenting a stale record as current.
    body["generated_age_seconds"] = round(
        dt.datetime.now(UTC).timestamp() - path.stat().st_mtime, 1)
    return body


@app.get("/api/paper-book")
def paper_book() -> dict:
    """The latest paper book on disk, served verbatim — the SCOREBOARD's source.

    `cfb/run_paper_book.py` now writes `paper_book_<UTC>.json` beside its txt,
    with the rows already shaped for the page. This reads the newest one and
    returns it unchanged: **nothing here parses, derives or recomputes.** The
    producer owns the shape, because it is the only thing that has the numbers.

    It replaced 198 lines of fixed-width regex plus 262 lines of tests for
    them. That parser could only ever be a guess at a table written for a
    human, and a column drifting by one space was a silent row loss — the
    reason it carried an `unparsed` list at all.

    Absent, it says so in one line and serves no tables: the api container sees
    the directory only if compose mounts it, and "no paper book yet" must not
    look like an empty book.
    """
    directory = Path((os.environ.get("MERIDIAN_READS_DIR") or "").strip()
                     or "/opt/meridian/artifacts/reads")
    files = sorted((p for p in directory.glob("paper_book*.json") if p.is_file()),
                   key=lambda p: (p.stat().st_mtime, p.name)) if directory.is_dir() else []
    if not files:
        return {"available": False,
                "note": f"no paper book yet — nothing matching paper_book*.json in {directory}"}
    path = files[-1]
    try:
        doc = json.loads(path.read_text(errors="replace"))
    except ValueError as exc:
        return {"available": False, "note": f"{path.name} is not readable JSON: {exc}"}
    doc.setdefault("file", path.name)
    doc.setdefault("generated_at",
                   dt.datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat())
    return doc


@app.get("/api/scalps")
def scalps(limit: int = Query(200, ge=1, le=1000)) -> dict:
    """The paper scalp engine's last rows, plus a per-league total.

    `core/gridiron/scalp.py` writes one row per CLOSED position. **Nothing here
    is a trade**: the engine reads the recorders' tape and can place no order.

    `totals` is computed in SQL over EVERY row, not over the `rows` page --
    summing the 200 returned would silently become a different statistic the
    moment the table outgrew the page, and it would keep looking right.
    """
    from sqlalchemy import text
    from core.storage.base import get_engine

    # No clamp: the bound is declared on the parameter above, so an
    # out-of-range limit is a 422 from validation rather than a value
    # silently rewritten to something the caller did not ask for.
    n = limit
    with get_engine().connect() as c:
        rows = [dict(r._mapping) for r in c.execute(text(
            "SELECT league, game_id, market_slug, side, trigger, entered_at,"
            " entry_px::float, exit_at, exit_px::float, exit_reason,"
            " pnl::float, fee::float, params FROM paper_scalps"
            " ORDER BY exit_at DESC LIMIT :n"), {"n": n})]
        totals = [dict(r._mapping) for r in c.execute(text(
            "SELECT league, count(*) n, sum(pnl)::float pnl, sum(fee)::float fee,"
            " count(*) FILTER (WHERE pnl > 0) wins"
            " FROM paper_scalps GROUP BY league ORDER BY league"))]
    return {"rows": rows, "totals": totals, "limit": n,
            "note": "paper only — the scalp engine reads the tape and places nothing"}


# --------------------------------------------------------------------------- #
# ARB tab — the ladder desk on the dashboard, and the one two-leg SEND
# --------------------------------------------------------------------------- #
#
# The desk on :8011 (cfb/ladder_desk_app.py) reads the executor's intents and
# writes the lock and the operator's records; this is the same desk served
# from the dashboard, reading and writing the SAME files through
# core.ladder.desk, plus the one thing the desk could not do: send the two
# legs. The venue vocabulary is from docs.polymarket.us create-order (read
# 2026-09-18): an IMMEDIATE_OR_CANCEL limit with synchronousExecution takes
# what is there, rests nothing, and answers with its own fill — so a zero fill
# in a TERMINAL state is a fact in the reply, not the invisible state the
# activities feed leaves a cancelled order in (V19). A zero fill in a pending
# state (PENDING_NEW, NEW, PENDING_RISK) is not that fact: no maxBlockTime is
# sent, so whether the venue blocks until the IOC is terminal is unobserved,
# and such a reply is "pending", never "unfilled". None of it had been
# exercised live when this was written; the first send is the first
# observation.
#
# What is defended, in order, on every send:
#   the server token; the HUMAN_CONFIRM literal; the ticket must be one the
#   executor wrote, and still open on the desk's record; the submitted legs
#   must match that ticket (slug, side, price within a cent, size not above
#   it); spread rungs only; tick and bounds; per-leg and pair stake under the
#   pair cap AND the account; the acknowledge flag; and the lock file — locked
#   means refused. Only then are the two idempotency rows written (refused if
#   a leg-1 row for the ticket already exists), and only then is leg 1 sent.
#   Leg 2 is sent only for the quantity leg 1 filled, or not at all.
#
# What the desk's record says after a send: `recorded` with fills only when
#   every sent leg's fill was OBSERVED (accepted, and either filled or in a
#   terminal state). A venue refusal, an unreadable reply, a pending state or
#   a leg-2 transport error is protocol noise, not a fill observation, and is
#   written as `placed` with the outcome, for the operator to record by hand
#   once the fill watcher has reconciled the row. The tally's "leg 1 filled
#   nothing" count must never include a 401.
#
# UNWIND is deliberately exempt from the lock file: it is the operator's way
#   out of a half-filled pair, and locking the desk must not lock them in.
#   It still needs the token, the HUMAN_CONFIRM literal and the acknowledge
#   flag, and never sells more than the venue reported filled.
#
# The sampler thread reads the venue's public books through the recorder's
# unauthenticated gateway client; the ladder handler serves its cache and
# never calls the venue itself.

#: The executor's ticket-issuing filters, shown on the page beside the live
#: violations so the operator can see why a violation is or is not a ticket.
_ARB_FLOOR_USD = 25.0
#: The executor's default --attempt-usd; the previewed ticket is sized as the
#: executor would size it, so the two screens show the same contract count.
_ARB_TICKET_ATTEMPT_USD = 1.0
#: How long one /api/arb/ladder?game= request keeps that game sampled. The
#: page asks every 5 s while a game is on screen, so 45 s means "still being
#: looked at". It was 30 MINUTES: on an NFL Sunday every game the operator
#: had glanced at stayed in a strictly serial rotation at ~4 s a sample, the
#: cycle reached a minute, and a newly picked game -- appended LAST -- showed
#: "first sample pending" for the whole of it while every route answered in
#: milliseconds. The route was never slow; what the page waited on was.
_ARB_WATCH_SECONDS = 45
#: The recorder's slug listing for a game is re-read this often; rungs are
#: listed pregame and do not change during a game.
_ARB_SLUGS_TTL_S = 10 * 60
#: An EMPTY listing is cached too, for this long. It used to be re-queried
#: every cycle -- an unindexable LIKE '%..%' scan -- for as long as the game
#: stayed watched, because the cache test required a non-empty result.
_ARB_SLUGS_EMPTY_TTL_S = 60
#: A game prefix as the executor spells it (aec-cfb-mia-wake-2026-09-18) or
#: as the intents file spells it (cfb-mia-wake-2026-09-18).
_ARB_PREFIX = re.compile(r"^(?:aec-)?([a-z0-9]+-[a-z0-9-]+-\d{4}-\d{2}-\d{2})$")
#: How far a submitted leg price may sit from the ticket's: one tick. The
#: human may nudge; the human may not re-price.
_ARB_PRICE_SLACK = Decimal("0.01")
#: How near a current price must be to a ticketed one to count as the same
#: price. A tick is 0.01 and a cost frame is round(1 - bid, 4), so this is a
#: float-equality slack, never a price concession: at the boundary (current
#: ask == the ticketed price) the ticket is LIVE.
_ARB_LIVE_EPS = 1e-6
#: A cached ladder touch older than this many sample intervals is not a touch:
#: the unwind's "at market" default must come from a book the sampler has
#: seen recently, not from a sample taken hours ago by an expired watch.
_ARB_STALE_TOUCH_INTERVALS = 2.0
#: The venue's quantity precision (contracts to the cent). Every quantity
#: this module derives from a venue-reported Decimal is spelled through
#: `_arb_qty` so the payload reads "1", never "1.0" or "1.0000".
_ARB_QTY_STEP = Decimal("0.01")
#: The desk's `via` marks: what the ARB tab's SEND writes, and what a hand
#: record through /api/arb/record writes. The page offers UNWIND only on the
#: first, because only a sent ticket has rows to sell from.
_ARB_VIA_SEND = "send"
_ARB_VIA_DESK = "desk"

_ARB_LADDER: dict = {"watch": {}, "cache": {}, "slugs": {}, "thread": None,
                     "wake": threading.Event()}
_ARB_LOCK = threading.Lock()


def _arb_out_dir() -> str:
    return _ladder_desk.api_out_dir()


def _arb_max_pair_usd() -> Decimal:
    """Read per call, not at import: the operator's cap for the pair, and a
    test's."""
    try:
        return Decimal(os.environ.get("MERIDIAN_ARB_MAX_PAIR_USD") or "25")
    except InvalidOperation:
        return Decimal("25")


def _arb_allow_size_up() -> bool:
    return (os.environ.get("MERIDIAN_ARB_ALLOW_SIZE_UP") or "").strip() == "1"


def _arb_sample_seconds() -> float:
    try:
        return max(2.0, float(os.environ.get("MERIDIAN_ARB_SAMPLE_SECONDS") or 10))
    except ValueError:
        return 10.0


def _arb_qty(q: Decimal) -> Decimal:
    """A quantity as the venue has always received it: to the cent, no
    trailing zeros, never exponent form. Decimal('2.0000') - Decimal('1.0000')
    is '1.0000' and float(1) is '1.0'; the venue has only ever seen "1"."""
    q = Decimal(str(q)).quantize(_ARB_QTY_STEP)
    q = q.normalize()
    if q == q.to_integral():
        return q.quantize(Decimal("1"))
    return q


def _arb_prefix(game: str) -> tuple[str, str]:
    """('aec-cfb-mia-wake-2026-09-18', 'cfb-mia-wake-2026-09-18') from either
    spelling; 422 for anything that is not a game."""
    m = _ARB_PREFIX.match((game or "").strip().lower())
    if not m:
        raise HTTPException(
            status_code=422,
            detail=f"game {game!r} must look like aec-cfb-mia-wake-2026-09-18")
    return "aec-" + m.group(1), m.group(1)


def _arb_filters() -> dict:
    return {"floor_usd": _ARB_FLOOR_USD, "spread_only": True, "mid_first": True,
            "mid_ladder": list(MID_LADDER), "attempt_usd": _ARB_TICKET_ATTEMPT_USD}


def _arb_ticket_view(t: dict) -> dict:
    """A ticket as the page shows it: the executor's intent plus screen words
    for any leg that lacks them (older intents), and whether SEND applies."""
    t = dict(t)
    game = str(t.get("game") or "")
    for key in ("leg1", "leg2"):
        leg = dict(t.get(key) or {})
        if leg and not leg.get("screen_row"):
            try:
                leg["screen_row"], leg["screen_button"] = ui_wording(
                    game, float(leg["market_line"]), str(leg["side"]))
            except (ValueError, KeyError, TypeError):
                pass
        t[key] = leg
    lines = [float((t.get(k) or {}).get("market_line") or 0) for k in ("leg1", "leg2")]
    t["spread_pair"] = 0.0 not in lines
    # Past the game's cap the executor keeps WRITING tickets (so the operator
    # sees what went by) and stops pushing them; the send route refuses them.
    # The page must not offer a SEND the server will certainly refuse.
    t["over_budget"] = bool(t.get("over_budget"))
    t["sendable"] = t.get("status") == "open" and t["spread_pair"] and not t["over_budget"]
    return t


def _arb_live_block(t: dict, snap: dict | None, now: float) -> dict | None:
    """The ticket's two legs against a CURRENT ladder sample, or None.

    A ticket is a snapshot of one instant, not a standing offer. On
    2026-09-18 a 62-minute-old ticket sat on the page under a SEND button
    showing prices from a book that had long since moved, and nothing said
    so. This is what the page needs to say so.

    Per leg, in the ticket's own COST frame:
      * a BUY YES leg is still available while that rung's ask is at or under
        the ticketed cost;
      * a BUY NO leg's ticketed cost is ``1 - that rung's YES bid``, so it is
        still available while the bid is at or above ``1 - cost``.
    A price alone is not availability. Both guards the executor trades by
    are SIZE and PLAUSIBILITY, and both come from `core.ladder.scan`, never
    from a second copy here:

      * the tradeable size of a pair is the MIN of the two legs' displayed
        size on the side we take (the ask we lift, the bid we hit), capped
        at ``MAX_PLAUSIBLE_SIZE`` exactly as ``scan_ladder`` caps it, so
        ``size_now`` / ``dollars_now`` ARE the centre pane's violation row;
      * an edge above ``MAX_PLAUSIBLE_EDGE`` is a stale deep rung nobody has
        re-quoted, not a market (scan.py:5-10) — the centre pane drops those
        entirely, so a ticket must not read as the best thing on the page
        because one of its rungs went stale.

    The state, in the order the checks bind:
      * STALE  — ``edge_now`` is above the scan module's plausibility bound.
        Not a price; ``implausible`` is True and the page must not select it.
      * MOVED  — a leg is dearer than ticketed but the pair still clears
        fee-netted; GONE when it no longer clears.
      * THIN   — priced at the ticket or better with less size behind it
        than the ticket asks for. Before 2026-09-18 this read LIVE while the
        SAME snapshot's violation row said $0.00 / not a candidate.
      * LIVE   — both legs at the ticketed price or better, with at least the
        ticket's own quantity displayed on each side.
    None is UNKNOWN: no sample, an unavailable one, one older than the
    unwind's own staleness bound, or a rung this sample does not carry.
    **Never LIVE for want of data — absence is not confirmation.**

    The edge is ``core.ladder.scan.fee``, the one definition, never a second
    copy in JavaScript. In the cost frame it is
    ``1 - c1 - c2 - fee(c1) - fee(c2)``, which is scan_ladder's
    ``sell - buy - fee(buy) - fee(sell)`` with ``sell = 1 - c2`` and the fee
    curve's own symmetry (``0.06 p (1 - p)`` is unchanged by ``p -> 1 - p``).
    """
    if not snap or snap.get("available") is not True:
        return None
    try:
        age_s = now - float(snap.get("sampled_ts"))
    except (TypeError, ValueError):
        return None
    if age_s > _ARB_STALE_TOUCH_INTERVALS * _arb_sample_seconds():
        return None
    legs, costs, oks, sizes, thin = {}, [], [], [], []
    for key in ("leg1", "leg2"):
        leg = t.get(key) or {}
        try:
            cost = float(leg["price"])
            qty = float(leg.get("qty") or 0)
            rung = snap["rungs"][f"{float(leg['market_line']):g}"]
            if str(leg.get("side") or "").upper().endswith("YES"):
                now_cost = float(rung["ask"])              # we lift the ask
                now_size = float(rung["ask_sz"])           # and only what it shows
            else:
                now_cost = round(1.0 - float(rung["bid"]), 4)   # we hit the bid
                now_size = float(rung["bid_sz"])
        except (KeyError, TypeError, ValueError):
            return None
        legs[key] = now_cost
        costs.append(now_cost)
        sizes.append(now_size)
        oks.append(now_cost <= cost + _ARB_LIVE_EPS)
        # A zero-size quote is never available, whatever the ticket asks for:
        # an intent written off an empty book carries qty 0 and would
        # otherwise clear this test by asking for nothing.
        thin.append(now_size <= 0.0 or now_size + _ARB_LIVE_EPS < qty)
    c1, c2 = costs
    edge_now = 1.0 - c1 - c2 - fee(c1) - fee(c2)
    # The pair is only as large as its smaller side, and the scan module's own
    # cap applies: this is Violation.size, so the two panes report one number.
    size_now = min(sizes + [MAX_PLAUSIBLE_SIZE])
    implausible = edge_now > MAX_PLAUSIBLE_EDGE
    if implausible:
        state = "STALE"
    elif not all(oks):
        state = "MOVED" if edge_now > 0 else "GONE"
    elif any(thin):
        state = "THIN"
    else:
        state = "LIVE"
    moved = [n for n, ok in zip((1, 2), oks) if not ok]
    return {
        "state": state,
        "implausible": implausible,
        "size_now": size_now,
        "dollars_now": round(edge_now * size_now, 2),
        "thin_leg": None if not any(thin) else (
            "both" if all(thin) else f"leg {1 if thin[0] else 2}"),
        "leg1_now": legs["leg1"], "leg2_now": legs["leg2"],
        "leg1_delta_c": round((legs["leg1"] - float((t.get("leg1") or {})["price"])) * 100, 2),
        "leg2_delta_c": round((legs["leg2"] - float((t.get("leg2") or {})["price"])) * 100, 2),
        "edge_now_c": round(edge_now * 100, 2),
        "moved_leg": None if not moved else ("both" if len(moved) == 2 else f"leg {moved[0]}"),
        "age_s": round(age_s, 1),
    }


def _arb_ticket_live(t: dict, now: float) -> dict | None:
    """`_arb_live_block` against whatever the sampler last left for the
    ticket's own game — the same cache /api/arb/ladder serves, so the centre
    pane and the ticket panel can never disagree."""
    game = str(t.get("game") or "")
    prefix = game if game.startswith("aec-") else "aec-" + game
    return _arb_live_block(t, _ARB_LADDER["cache"].get(prefix), now)


@app.get("/api/arb/state")
def arb_state() -> dict:
    """The desk's files, read fresh on every call: the lock, every ticket
    with the operator's latest record merged in, the registered tally, the
    executor and freshness tails, and the games seen tonight.

    File-backed and never a 500: the api container sees the reads directory
    only if compose mounts it, and "no desk here" must not look like an empty
    desk. Nothing here touches the database or the venue.
    """
    out = _arb_out_dir()
    if not os.path.isdir(out):
        return {"available": False, "dir": out,
                "note": f"reads directory {out} is not mounted in this container"}
    try:
        now = time.time()
        games = _ladder_desk.recent_games(out)
        on_board = {g.replace("aec-", "", 1) for g in games}
        raw = _ladder_desk.load_tickets(out)
        # Only tickets for a game on the board are sent and priced. The page
        # hides every other one as history anyway, and pricing 678 of them
        # against the ladder on every 10-second poll was 7.2 s and 451 KB per
        # call -- the desk was spending most of each interval loading itself.
        # The tally still runs over the full file: its "placed" and "recorded"
        # counts are about all time, and it reads nothing that needs pricing.
        tickets = [_arb_ticket_view(t) for t in raw
                   if str(t.get("game") or "").replace("aec-", "", 1) in on_board]
        for t in tickets:
            # Only an open ticket can be sent, so only an open ticket needs
            # its legs priced against the book the operator is looking at.
            if t.get("status") == "open":
                live = _arb_ticket_live(t, now)
                if live is not None:
                    t["live"] = live
        tails = {
            kind: [{"file": os.path.basename(p), "lines": _ladder_desk.tail(p)}
                   for p in _ladder_desk.log_files(out, kind)]
            for kind in ("executor", "freshness")
        }
    except OSError as exc:
        return {"available": False, "dir": out, "note": f"cannot read {out}: {exc}"}
    return {
        "available": True,
        "dir": out,
        "tickets_on_file": len(raw),
        "armed": _ladder_desk.armed(out),
        # 0 means NO cap, which is what the launcher now runs: the executor
        # stopped taking --budget-usd on 2026-09-19 because a $2 ceiling had
        # been silencing a game for the rest of the night. The page must not
        # keep advertising a ceiling that is not there.
        "budget_usd": float(os.environ.get("LADDER_BUDGET_USD", "0")),
        "max_pair_usd": float(_arb_max_pair_usd()),
        "allow_size_up": _arb_allow_size_up(),
        "sample_seconds": _arb_sample_seconds(),
        "filters": _arb_filters(),
        "tickets": tickets,
        "tally": _ladder_desk.tally(raw),
        "tails": tails,
        "games": games,
        "watching": sorted(_arb_watched(time.time())),
    }


# --- the live ladder: a daemon sampler and a cache ------------------------- #


def _arb_ladder_snapshot(game: str, rungs: dict, meta: dict, took_s: float,
                         now: float) -> dict:
    """One sample rendered for the page. Pure: rungs is what
    core.ladder.live.sample returned (line -> (bid, ask, bid_sz, ask_sz)),
    meta the venue's transactTime per line.

    Bounds per rung, from the ordering the settled tape proved (84,646 pairs,
    STATUS 0bk): covering a higher line is easier, so a rung's price must sit
    at or above every harder rung's bid (``lo``, the max bid over lower lines)
    and at or below every easier rung's ask (``hi``, the min ask over higher
    lines). An ask under ``lo`` or a bid over ``hi`` is flagged; those are the
    gross terms, and the fee-netted pairs are the ``violations``, computed by
    the same scan_ladder the executor runs so the two never disagree.
    """
    lines = sorted(rungs)
    out_rungs: dict[str, dict] = {}
    bounds: dict[str, dict] = {}
    for line in lines:
        bid, ask, bid_sz, ask_sz = rungs[line]
        harder = [rungs[k][0] for k in lines if k < line]
        easier = [rungs[k][1] for k in lines if k > line]
        lo = max(harder) if harder else None
        hi = min(easier) if easier else None
        flags = []
        if lo is not None and ask < lo:
            flags.append("ask below a harder rung's bid")
        if hi is not None and bid > hi:
            flags.append("bid above an easier rung's ask")
        try:
            row, our_yes_is = ui_wording(game, line, "BUY YES") if line != 0.0 else ("winner", None)
        except ValueError:
            row, our_yes_is = None, None
        # bid/ask are the slug frame (the first team's YES at this line). The
        # venue's screen prices the ROW's Yes: on a neg rung the row is the
        # first team's, on a pos rung the second team's, whose Yes is our NO,
        # so the screen pair there is (1 - ask, 1 - bid). Both are served so
        # the page never pairs one team's row text with the other's prices.
        if line < 0:
            screen_bid, screen_ask = bid, ask
        elif line > 0:
            screen_bid, screen_ask = round(1.0 - ask, 4), round(1.0 - bid, 4)
        else:
            screen_bid = screen_ask = None
        key = f"{line:g}"
        bounds[key] = {"lo": lo, "hi": hi}
        out_rungs[key] = {
            "line": line, "row": row, "our_yes_is": our_yes_is,
            "bid": bid, "ask": ask, "bid_sz": bid_sz, "ask_sz": ask_sz,
            "screen_bid": screen_bid, "screen_ask": screen_ask,
            "tt": meta.get(line), "age_s": book_age_s(meta.get(line), now),
            "lo": lo, "hi": hi, "flags": flags,
        }
    when = dt.datetime.fromtimestamp(now, UTC).strftime("%H:%M:%S")
    violations = []
    found = scan_ladder(game, rungs, max_size=1e12)
    for v in found:
        spread = is_spread_pair(v)
        violations.append({
            "high_line": v.high_line, "low_line": v.low_line,
            "buy_price": v.buy_price, "sell_price": v.sell_price,
            "edge_c": round(v.edge * 100, 2), "size": v.size,
            "dollars": round(v.dollars, 2),
            "mid_ladder": is_mid(v), "spread_pair": spread,
            # The executor's own rule: floor, spread-only; mid-ladder first.
            "candidate": spread and clears_floor(v.dollars, _ARB_FLOOR_USD),
            "ticket": ticket_for(v, game, when, _ARB_TICKET_ATTEMPT_USD),
        })
    violations.sort(key=lambda x: (not x["candidate"], not x["mid_ladder"], -x["dollars"]))
    return {
        "available": True, "game": game,
        "sampled_at": dt.datetime.fromtimestamp(now, UTC).isoformat(),
        "sampled_ts": now, "took_s": round(took_s, 2),
        "n_rungs": len(lines),
        "rungs": out_rungs, "bounds": bounds, "violations": violations,
        "best_per_game": {g: round(d, 2) for g, d in best_per_game(found).items()},
        "filters": _arb_filters(),
    }


def _arb_watch(prefix: str) -> float:
    """Register a game for sampling. A game the sampler has not seen wakes
    it, so the first ladder lands after the sample in flight rather than
    after a whole cycle -- with the same one client and the same request
    budget, because waking is not a second sampler."""
    until = time.time() + _ARB_WATCH_SECONDS
    with _ARB_LOCK:
        new = prefix not in _ARB_LADDER["watch"]
        _ARB_LADDER["watch"][prefix] = until
    if new:
        _ARB_LADDER["wake"].set()
    return until


def _arb_watched(now: float) -> list[str]:
    """Live watches, MOST RECENTLY ASKED FIRST: the game the operator just
    picked is sampled before the one they left. Dict order was insertion
    order, which put it last."""
    with _ARB_LOCK:
        watch = _ARB_LADDER["watch"]
        for prefix in [p for p, until in watch.items() if until <= now]:
            del watch[prefix]
        return sorted(watch, key=watch.get, reverse=True)


def _arb_slugs(prefix: str, game: str, now: float) -> list[str]:
    """The game's rungs from the recorder's listing, through the api's own
    engine, cached for a while: the listing is a query over two days of
    snapshots and the rungs do not change in-game."""
    cached = _ARB_LADDER["slugs"].get(prefix)
    if cached is not None:
        ttl = _ARB_SLUGS_TTL_S if cached[1] else _ARB_SLUGS_EMPTY_TTL_S
        if now - cached[0] < ttl:
            return cached[1]
    t0 = time.monotonic()
    slugs = slugs_for(game, _ENGINE)
    # Timed on the MISS only: a hit is a dict lookup, and logging it would bury
    # the one measurement anybody wants. The first miss in a fresh process is
    # 50x the later ones -- 2.56s against 0.03-0.05s measured 2026-09-21 in the
    # running container -- so "the listing costs 0.8s" is neither figure and a
    # cold ask cannot be reasoned about from a warm one.
    log.info("arb_phase_listing", game=game, listing_s=round(time.monotonic() - t0, 3),
             n_slugs=len(slugs), cache="miss")
    _ARB_LADDER["slugs"][prefix] = (now, slugs)
    return slugs


def _arb_sample_one(client, prefix: str) -> None:
    """Sample one watched game and store the rendering; a failure is stored
    too, as the reason the page shows, and never stops the thread."""
    game = prefix.replace("aec-", "", 1)
    try:
        now = time.time()
        t_list = time.monotonic()
        slugs = _arb_slugs(prefix, game, now)
        listing_s = time.monotonic() - t_list
        if not slugs:
            _ARB_LADDER["cache"][prefix] = {
                "available": False, "game": game, "prefix": prefix,
                "sampled_at": dt.datetime.fromtimestamp(now, UTC).isoformat(), "sampled_ts": now,
                "reason": f"no rungs recorded for {game} in the last two days"}
            return
        meta: dict = {}
        t_venue = time.monotonic()
        rungs, took = sample(client, slugs, prefix, meta,
                             on_error=lambda s, e: log.warning("arb_rung_failed", slug=s, error=e))
        venue_s = time.monotonic() - t_venue
        # One line per sample carrying BOTH phases. The venue leg is the larger
        # and the more variable: 3.22s best of three against a 4.20s median on
        # 42 rungs, so an arithmetic built on its best case understates a cold
        # ask by about a second before any other phase is counted.
        log.info("arb_phase_sample", game=game, n_slugs=len(slugs),
                 listing_s=round(listing_s, 3), venue_s=round(venue_s, 3),
                 rungs=len(rungs))
        now = time.time()
        snap = _arb_ladder_snapshot(game, rungs, meta, took, now)
        snap["prefix"] = prefix
        snap["n_slugs"] = len(slugs)
        _ARB_LADDER["cache"][prefix] = snap
    except Exception as exc:  # noqa: BLE001 — one game's failure must not stop the sampler
        log.warning("arb_sample_failed", game=prefix, error=str(exc)[:200])
        _ARB_LADDER["cache"][prefix] = {
            "available": False, "game": game, "prefix": prefix,
            "sampled_at": dt.datetime.now(UTC).isoformat(), "sampled_ts": time.time(),
            "reason": str(exc)[:200]}


def _arb_sampler_loop() -> None:
    """Daemon: ONE gateway client, every watched game every N seconds. Same
    shape as the wallet refresh thread — the request never waits on the venue,
    it reads whatever the last cycle left."""
    wake = _ARB_LADDER["wake"]
    t_client = time.monotonic()
    with PolymarketGatewayClient() as client:
        # Measured 2026-09-21 in the running container: 0.006s best of three,
        # 0.269s worst. Logged anyway because it was the leading suspect for a
        # missing ~5s on a cold ask and it is not; a phase ruled out by
        # measurement should stay measured rather than be ruled out by memory.
        log.info("arb_phase_client", client_s=round(time.monotonic() - t_client, 3))
        cycle = 0
        while True:
            t0 = time.time()
            t_cycle = time.monotonic()
            wake.clear()
            # Bound once, exactly as the original `for prefix in _arb_watched(t0)`
            # did: calling it again to report the count would evaluate the watch
            # list twice per cycle, which is a behaviour change, not a timing.
            watched = _arb_watched(t0)
            for prefix in watched:
                _arb_sample_one(client, prefix)
                if wake.is_set():
                    break              # a new game was asked for: restart, it goes first
            cycle += 1
            cycle_s = time.monotonic() - t_cycle
            # The cold cycles always, and after that only a cycle that overran
            # its own interval -- the loop falling behind is the thing worth a
            # line. Logging all of them is ~8,600 lines a day at the 10s
            # default, which is how a timing nobody reads gets added.
            if cycle <= 3 or cycle_s > _arb_sample_seconds():
                log.info("arb_phase_cycle", cycle=cycle,
                         cycle_s=round(cycle_s, 3),
                         games=len(watched), woken=wake.is_set())
            if not wake.is_set():
                # Sleep the remainder, but a new watch ends the sleep early.
                wake.wait(timeout=max(0.5, _arb_sample_seconds() - (time.time() - t0)))


def _arb_ensure_sampler() -> None:
    with _ARB_LOCK:
        t = _ARB_LADDER["thread"]
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_arb_sampler_loop, name="arb-ladder-sampler", daemon=True)
        _ARB_LADDER["thread"] = t
        t.start()


@app.get("/api/arb/ladder")
def arb_ladder(game: str = Query(..., min_length=8, max_length=120)) -> dict:
    """The live ladder for one game, from the sampler's cache. Asking for a
    game keeps it sampled for _ARB_WATCH_SECONDS and wakes the sampler if it
    is new; the first answer says the sample is pending. **This handler
    never calls the venue.**"""
    prefix, plain = _arb_prefix(game)
    until = _arb_watch(prefix)
    try:
        _arb_ensure_sampler()
    except Exception as exc:  # noqa: BLE001 — a thread that cannot start is a reason, not a 500
        return {"available": False, "game": plain, "prefix": prefix,
                "reason": f"sampler could not start: {str(exc)[:160]}"}
    snap = _ARB_LADDER["cache"].get(prefix)
    if snap is None:
        return {"available": False, "game": plain, "prefix": prefix,
                "reason": "first sample pending", "watching_until": until,
                "sample_seconds": _arb_sample_seconds()}
    out = dict(snap)
    out["age_s"] = round(time.time() - snap["sampled_ts"], 1)
    out["watching_until"] = until
    out["sample_seconds"] = _arb_sample_seconds()
    return out


# --- the lock and the operator's records ----------------------------------- #


def _arb_dir_or_409() -> str:
    out = _arb_out_dir()
    if not os.path.isdir(out):
        raise HTTPException(status_code=409,
                            detail=f"reads directory {out} is not mounted; nothing to write")
    return out


@app.post("/api/arb/lock")
def arb_lock(request: Request) -> dict:
    """Create the lock file the executor re-reads every cycle, and the send
    refuses on. Token-gated like every write here: the lock is the operator's."""
    _require_order_token(request)
    out = _arb_dir_or_409()
    path = _ladder_desk.lock(out, "the dashboard")
    log.info("arb_lock", path=path)
    return {"armed": False, "lock": path}


@app.post("/api/arb/arm")
def arb_arm(request: Request) -> dict:
    _require_order_token(request)
    out = _arb_dir_or_409()
    _ladder_desk.arm(out)
    log.info("arb_arm", dir=out)
    return {"armed": True}


class ArbFills(BaseModel):
    """What the operator saw, per leg: filled qty, price, seconds. A missing
    qty is 0 -- "did not fill" is a result."""

    model_config = ConfigDict(extra="forbid")

    l1q: float | None = None
    l1p: float | None = None
    l1s: float | None = None
    l2q: float | None = None
    l2p: float | None = None
    l2s: float | None = None


class ArbRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    status: Literal["placed", "skipped", "reopen", "recorded"]
    fills: ArbFills | None = None


def _arb_resolve_ticket(out: str, ticket_id: str) -> dict:
    """The intent the executor wrote, or 404. A ticket the executor did not
    write is not a ticket, however well-formed."""
    for t in _ladder_desk.load_tickets(out):
        if t.get("id") == ticket_id:
            return t
    raise HTTPException(status_code=404, detail=f"no ticket {ticket_id!r} in {out}")


@app.post("/api/arb/record")
def arb_record(req: ArbRecordRequest, request: Request) -> dict:
    """The desk's "I placed it" / "Skipped" / fills, written to the same
    ladder_attempts.jsonl the desk and the tally read."""
    _require_order_token(request)
    out = _arb_dir_or_409()
    _arb_resolve_ticket(out, req.ticket_id)
    status = "open" if req.status == "reopen" else req.status
    fills = None
    if status == "recorded":
        if req.fills is None:
            raise HTTPException(status_code=422, detail="a recorded attempt needs its fills")
        fills = req.fills.model_dump()
    row = _ladder_desk.record_attempt(out, req.ticket_id, status, fills, via=_ARB_VIA_DESK)
    log.info("arb_record", ticket=req.ticket_id, status=status)
    return {"ticket_id": req.ticket_id, "status": status, "record": row}


# --- the send ------------------------------------------------------------- #


class ArbLeg(BaseModel):
    """One leg as the page sends it back: the ticket's own slug, side, price
    and size, in the COST frame the ticket displays."""

    model_config = ConfigDict(extra="forbid")

    market_slug: str
    side: str
    cost_price: Decimal
    quantity: Decimal


class ArbSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    mode: str
    legs: list[ArbLeg]
    acknowledge: bool = False


def _arb_require_mode(mode: str) -> None:
    if mode != ExecutionMode.HUMAN_CONFIRM.value:
        raise HTTPException(
            status_code=403,
            detail=(f"mode must be {ExecutionMode.HUMAN_CONFIRM.value}; got {mode!r}. "
                    "No other mode may reach the venue."))


def _arb_decided_at(intent: dict) -> dt.datetime:
    """The ticket's instant, for the idempotency key: the game's date from
    its slug plus the executor's HH:MM:SS stamp. Deterministic per ticket, so
    a double-click or a second tab collides on the UNIQUE key instead of
    sending the pair twice."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", str(intent.get("game") or ""))
    day = dt.date.fromisoformat(m.group(1)) if m else dt.datetime.now(UTC).date()
    try:
        clock = dt.time.fromisoformat(str(intent.get("ts")))
    except ValueError:
        clock = dt.time(0)
    return dt.datetime.combine(day, clock, tzinfo=UTC)


def _arb_check_legs(intent: dict, legs: list[ArbLeg], slug_of_line: dict[float, str],
                    *, allow_size_up: bool) -> list[dict]:
    """The submitted legs against the ticket, leg by leg. Pure, and every
    refusal names the term that failed. Returns the resolved terms per leg.

    Slugs are rebuilt from the ticket's game and line through the recorder's
    own listing, never taken from the caller; the caller's slug must equal
    that. A price may differ from the ticket's by one tick; a size may not
    exceed the ticket's (or, with MERIDIAN_ARB_ALLOW_SIZE_UP=1, the displayed
    size). The winner market is never a leg.
    """
    if len(legs) != 2:
        raise HTTPException(status_code=422, detail=f"a ticket has two legs; got {len(legs)}")
    resolved = []
    for n, (leg, key) in enumerate(zip(legs, ("leg1", "leg2")), start=1):
        want = intent.get(key) or {}
        try:
            line = float(want["market_line"])
            want_price = Decimal(str(want["price"]))
            want_qty = Decimal(str(want["qty"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise HTTPException(status_code=409, detail=f"ticket leg {n} is malformed") from None
        if line == 0.0:
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} is the winner market; only spread rungs are ticket legs")
        want_slug = slug_of_line.get(line)
        if want_slug is None:
            raise HTTPException(
                status_code=409,
                detail=f"leg {n}: no recorded market for line {line:+g} in {intent.get('game')}")
        if leg.market_slug.strip() != want_slug:
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} slug {leg.market_slug!r} is not the ticket's line "
                       f"{line:+g} ({want_slug})")
        side = " ".join(leg.side.upper().split())
        if side not in ("BUY YES", "BUY NO"):
            raise HTTPException(status_code=422, detail=f"leg {n} side must be BUY YES or BUY NO")
        if side != " ".join(str(want.get("side", "")).upper().split()):
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} side {side} is not the ticket's ({want.get('side')})")
        _validate_typed_price(leg.cost_price, what=f"leg {n} price")
        if abs(leg.cost_price - want_price) > _ARB_PRICE_SLACK:
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} price {leg.cost_price} is more than {_ARB_PRICE_SLACK} "
                       f"from the ticket's {want_price}")
        if leg.quantity < VENUE_MIN_QTY:
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} quantity {leg.quantity} is below the venue minimum {VENUE_MIN_QTY}")
        max_qty = want_qty
        if allow_size_up:
            try:
                max_qty = max(max_qty, Decimal(str(intent.get("displayed_size") or 0)))
            except InvalidOperation:
                pass
        if leg.quantity > max_qty:
            raise HTTPException(
                status_code=422,
                detail=f"leg {n} quantity {leg.quantity} exceeds the ticket's {max_qty}"
                       + ("" if allow_size_up else " (MERIDIAN_ARB_ALLOW_SIZE_UP is not set)"))
        outcome = OutcomeSide.YES if side.endswith("YES") else OutcomeSide.NO
        resolved.append({
            "n": n, "line": line, "market_slug": want_slug, "side": side, "outcome": outcome,
            "cost": leg.cost_price, "quantity": leg.quantity,
            # YES-frame price.value, derived HERE from the side (V14).
            "yes_price": (Decimal("1") - leg.cost_price) if outcome is OutcomeSide.NO else leg.cost_price,
        })
    return resolved


def _arb_pair_cost_bound(costs: list[Decimal]) -> tuple[Decimal, Decimal]:
    """(sum of costs, sum of taker fees) for a pair, with the scanner's own fee
    model at the price paid. A pair pays $1.00 per contract at settlement, so
    the send is refused when cost + fees >= 1: that is exactly "net edge <= 0"
    in the scanner's algebra, re-checked here because one tick of slack per
    leg can carry a thin ticket over the line."""
    cost = sum(costs, Decimal("0"))
    fees = sum((Decimal(str(fee(float(c))) ) for c in costs), Decimal("0"))
    return cost, fees.quantize(Decimal("0.0001"))


def _arb_check_stakes(resolved: list[dict]) -> Decimal:
    """Per-leg stake under min(pair cap, the per-order fat-finger cap, the
    account); pair stake under min(pair cap, the account); pair cost plus
    fees under $1.00. Returns the pair cap.

    The per-leg bound goes through `_stake_cap()` with its default so a pair
    cap raised by env cannot let one leg stake more than /api/orders/confirm
    would allow for the same order."""
    cap = _stake_cap(cap=_arb_max_pair_usd())
    leg_cap = min(cap, _stake_cap())
    pair = Decimal("0")
    for r in resolved:
        stake = (r["cost"] * r["quantity"]).quantize(Decimal("0.01"))
        r["stake"] = stake
        pair += stake
        if stake > leg_cap:
            raise HTTPException(
                status_code=422,
                detail=f"leg {r['n']} stake ${stake} exceeds the per-leg cap ${leg_cap}"
                       + (" (MERIDIAN_MAX_ORDER_STAKE_USD)" if leg_cap < cap else ""))
    if pair > cap:
        raise HTTPException(
            status_code=422,
            detail=f"pair stake ${pair} exceeds ${cap} — "
                   + ("the account balance" if cap < _arb_max_pair_usd()
                      else "the pair cap (MERIDIAN_ARB_MAX_PAIR_USD)"))
    cost, fees = _arb_pair_cost_bound([r["cost"] for r in resolved])
    if cost + fees >= Decimal("1"):
        raise HTTPException(
            status_code=422,
            detail=f"pair cost {cost} plus taker fees {fees} is not under $1.00: "
                   "both legs filled at these prices would lock a loss, not a pair")
    return cap


def _arb_parse_sync(body_text: str) -> dict:
    """The venue's synchronous create-order reply, read for what the two-leg
    rule needs: the order id, its state, the filled quantity and the average
    price. Per the create-order doc the reply carries ``executions[]``, each
    with the embedded ``order`` (``id``, ``state``, ``cumQuantity``), the
    execution's ``lastPx``/``lastShares`` and ``avgPx``. Filled is the MAX
    ``cumQuantity`` across executions (the venue's own cumulative count, as
    the fill watcher reads it), never a sum of shares. The average is
    ``avgPx.value`` when present, else the VWAP of ``lastPx x lastShares``.
    Prices are YES frame, as every price the venue serves is.

    An unreadable body is a zero fill with no id: the row keeps the raw text
    and the fill watcher may still reconcile it later if an id turns up."""
    body = _parse_venue_body(body_text)
    if not isinstance(body, dict):
        return {"venue_id": None, "state": None, "filled": Decimal("0"),
                "avg_yes": None, "executions": 0}
    order_obj = body.get("order") if isinstance(body.get("order"), dict) else {}
    execs = body.get("executions")
    if not isinstance(execs, list):
        execs = order_obj.get("executions") if isinstance(order_obj.get("executions"), list) else []
    venue_id = body.get("orderId") or body.get("id") or order_obj.get("id")
    state = body.get("status") or body.get("state") or order_obj.get("state")

    def _dec(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    filled = _dec(body.get("cumQuantity")) or _dec(order_obj.get("cumQuantity")) or Decimal("0")
    execs = [ex for ex in execs if isinstance(ex, dict)]
    # The LATEST execution carries the order's state. By transactTime when
    # every execution has one (the fill watcher's own rule), else list order:
    # a newest-first list of [CANCELED cum 1, PARTIALLY_FILLED cum 1] must not
    # read as a still-open order.
    if execs and all(isinstance(ex.get("transactTime"), str) for ex in execs):
        execs = sorted(execs, key=lambda ex: ex["transactTime"])
    best = None
    num = Decimal("0")
    den = Decimal("0")
    priced = 0
    for ex in execs:
        o = ex.get("order") if isinstance(ex.get("order"), dict) else {}
        cum = _dec(o.get("cumQuantity"))
        if cum is not None and (best is None or cum >= filled):
            filled = max(filled, cum)
            best = ex
        venue_id = venue_id or o.get("id")
        px = _dec((ex.get("lastPx") or {}).get("value") if isinstance(ex.get("lastPx"), dict) else None)
        shares = _dec(ex.get("lastShares"))
        if px is not None and shares is not None and shares > 0:
            num += px * shares
            den += shares
            priced += 1
    reported = None
    if best is not None:
        o = best.get("order") if isinstance(best.get("order"), dict) else {}
        state = o.get("state") or state
        # The embedded order's avgPx is the order's (cumulative by nature);
        # the execution's may be its own. The doc is silent, so the order's
        # is read first.
        for holder in (o, best):
            px = holder.get("avgPx")
            reported = _dec(px.get("value") if isinstance(px, dict) else px)
            if reported is not None:
                break
    vwap = (num / den).quantize(Decimal("0.0001")) if den > 0 else None
    # Over several priced executions the VWAP of lastPx x lastShares is the
    # one average that cannot be a single execution's; with one it is the
    # same number and the reported figure is preferred. The caller logs a
    # disagreement so the first live multi-execution reply settles it.
    avg = vwap if (priced >= 2 and vwap is not None) else (reported if reported is not None else vwap)
    return {"venue_id": str(venue_id) if venue_id else None,
            "state": str(state) if state else None,
            "filled": filled, "avg_yes": avg, "executions": len(execs),
            "avg_reported": reported, "avg_vwap": vwap}


def _arb_fill_status(parsed: dict, quantity: Decimal) -> str | None:
    """The row's fill_status from an ACCEPTED synchronous reply, with the fill
    watcher's own state mapping so the two writers agree. A reply with a
    count but no readable state is judged by the count; one with neither
    stays NULL ("never reconciled") for the watcher."""
    from core.fill_watcher import FILLED, OPEN, PARTIAL, status_from_state

    up = (parsed["state"] or "").upper()
    if "REJECT" in up:
        # The venue answered and refused: nothing to reconcile. The caller
        # writes accepted=False for it; the status stays NULL as for any
        # refusal, never a terminal fill state.
        return None
    if "PENDING" in up:
        # PENDING_NEW / PENDING_RISK / PENDING_CANCEL / PENDING_REPLACE are
        # all non-terminal: a fill may still land (or a cancel may still
        # complete), so the watcher must keep polling. status_from_state
        # would read PENDING_CANCEL as CANCELLED, a terminal state it is not.
        return OPEN
    status = status_from_state(up)
    if status is not None:
        return status
    if parsed["filled"] >= quantity > 0:
        return FILLED
    if parsed["filled"] > 0:
        return PARTIAL
    return None


def _arb_leg_unsent(n: int, r: dict, error: str | None, *, transport: bool = False) -> dict:
    """A leg that was not sent, or -- ``transport`` -- one that was sent and
    got no answer, which is not the same claim: that leg may exist."""
    return {"leg": n, "market_slug": r["market_slug"], "side": r["side"],
            "line": r["line"], "order_id": r.get("order_id"),
            "sent": False, "accepted": False, "venue_order_id": None, "state": None,
            "observed": False, "transport_error": transport,
            "fill_status": None, "filled_quantity": 0.0, "avg_cost_price": None,
            "limit_cost_price": float(r["cost"]), "quantity_sent": None,
            "http_status": None, "latency_ms": None, "venue_latency_ms": None,
            "error": error, "response": None}


def _arb_persist_leg(row_id: int, r: dict, sent_qty: Decimal, result, parsed: dict) -> dict:
    """The venue's answer onto the leg's row, and the leg's result for the
    page. Same fields the human-confirm path records, plus the fill the
    reply itself carries -- the whole point of asking synchronously."""
    from core.fill_watcher import TERMINAL

    ok_code = 200 <= result.status_code < 300
    if ok_code and result.status_code not in (200, 201):
        # Unobserved: the synchronous reply's code is the doc's, not seen.
        # A 202 is plausible for an endpoint that may answer before the IOC
        # completes; it must not be misread as a rejection.
        log.warning("arb_unexpected_2xx", status=result.status_code, body=result.body_text[:600])
    rejected = "REJECT" in (parsed["state"] or "").upper()
    accepted = ok_code and not rejected
    fill_status = _arb_fill_status(parsed, sent_qty) if accepted else None
    filled = parsed["filled"] if accepted else Decimal("0")
    # A fill OBSERVATION: the venue accepted and either filled something or
    # ended the order. Zero filled in a pending state is not one.
    observed = accepted and (filled > 0 or fill_status in TERMINAL)
    avg_yes = parsed["avg_yes"]
    avg_cost = None if avg_yes is None else (
        (Decimal("1") - avg_yes) if r["outcome"] is OutcomeSide.NO else avg_yes)
    now = dt.datetime.now(UTC)
    with _Session() as s:
        stored = s.get(PlacedOrder, row_id)
        stored.accepted = accepted
        stored.http_status = result.status_code
        stored.venue_order_id = parsed["venue_id"]
        stored.venue_status = parsed["state"]
        stored.quantity = sent_qty
        stored.submit_latency_ms = Decimal(str(round(result.elapsed_ms, 2)))
        if result.server_latency_ms is not None:
            stored.venue_latency_ms = Decimal(str(round(result.server_latency_ms, 2)))
        if accepted:
            stored.fill_status = fill_status
            stored.filled_quantity = filled
            stored.fill_checked_at = now
            if avg_yes is not None:
                stored.avg_fill_price = avg_yes
        else:
            stored.error = result.body_text[:1000]
        s.commit()
    return {"leg": r["n"], "market_slug": r["market_slug"], "side": r["side"],
            "line": r["line"], "order_id": row_id,
            "sent": True, "accepted": accepted,
            "venue_order_id": parsed["venue_id"], "state": parsed["state"],
            "observed": observed, "transport_error": False,
            "fill_status": fill_status,
            "filled_quantity": float(filled),
            "avg_cost_price": None if avg_cost is None else float(avg_cost),
            "limit_cost_price": float(r["cost"]), "quantity_sent": float(sent_qty),
            "http_status": result.status_code,
            "latency_ms": round(result.elapsed_ms, 1),
            "venue_latency_ms": result.server_latency_ms,
            "error": None if accepted else result.body_text[:300],
            # The whole reply: its shape is the first live observation.
            "response": result.body_text}


def _arb_pair_summary(legs: list[dict]) -> dict:
    """What the pair is now, in dollars, from the venue-reported fills. The
    outcome "leg 1 filled, leg 2 unfilled" is first-class: it is the one way
    the protocol says money is lost, and it must never read as a success."""
    l1, l2 = legs
    q1 = Decimal(str(l1["filled_quantity"]))
    q2 = Decimal(str(l2["filled_quantity"]))
    c1 = Decimal(str(l1["avg_cost_price"] if l1["avg_cost_price"] is not None else l1["limit_cost_price"]))
    c2 = Decimal(str(l2["avg_cost_price"] if l2["avg_cost_price"] is not None else l2["limit_cost_price"]))
    paired = min(q1, q2)
    cost = q1 * c1 + q2 * c2
    guaranteed = paired * (Decimal("1") - (c1 + c2))

    def _kind(leg, q):
        """What a sent leg's reply was: 'filled', 'unfilled' (a terminal zero,
        the observation), 'rejected', 'pending' (accepted, zero, not
        terminal) or 'unknown' (accepted, zero, no readable state)."""
        if q > 0:
            return "filled"
        if not leg.get("accepted", True):
            return "rejected"
        if leg.get("observed", True):
            return "unfilled"
        return "pending" if leg.get("state") else "unknown"

    held = (f"You hold {q1} {l1['side']} on line {l1['line']:+g} unpaired: "
            "record it, let it settle, or UNWIND. Do not chase.")
    pending = False
    if not l1["sent"]:
        outcome, note = "not sent", l1["error"] or "leg 1 was not sent"
    elif _kind(l1, q1) == "rejected":
        outcome = "leg 1 rejected"
        note = (f"the venue refused leg 1 (HTTP {l1.get('http_status')}: {(l1.get('error') or '')[:120]}); "
                "leg 2 was not sent. Nothing is held. Not a fill observation: the record says placed.")
    elif _kind(l1, q1) in ("pending", "unknown"):
        pending = True
        outcome = "leg 1 pending at the venue" if _kind(l1, q1) == "pending" else "leg 1 unknown"
        note = (f"leg 1 was accepted (state {l1.get('state') or 'unreadable'}, venue id "
                f"{l1.get('venue_order_id') or '?'}) with no fill in the reply; leg 2 was not sent. "
                "The fill watcher reconciles the row: check it before UNWIND or a resend. "
                "Not a fill observation: the record says placed.")
    elif q1 <= 0:
        outcome, note = "leg 1 unfilled", "leg 1 filled nothing; leg 2 was not sent. A result: nothing is held."
    elif not l2["sent"] and l2.get("transport_error"):
        pending = True
        outcome = "leg 1 filled, leg 2 unknown"
        note = (f"leg 1 filled {q1}; leg 2 got no answer ({l2['error']}) and MAY exist at the venue. "
                "Reconcile leg 2 by its row's idempotency key before unwinding leg 1. " + held)
    elif not l2["sent"]:
        outcome = "leg 1 filled, leg 2 unsent"
        note = f"leg 1 filled {q1} and leg 2 could not be sent ({l2['error']}). " + held
    elif _kind(l2, q2) == "rejected":
        outcome = "leg 1 filled, leg 2 rejected"
        note = (f"leg 1 filled {q1}; the venue refused leg 2 (HTTP {l2.get('http_status')}: "
                f"{(l2.get('error') or '')[:120]}). " + held)
    elif _kind(l2, q2) in ("pending", "unknown"):
        pending = True
        outcome = "leg 1 filled, leg 2 pending"
        note = (f"leg 1 filled {q1}; leg 2 was accepted (state {l2.get('state') or 'unreadable'}) with no "
                "fill in the reply. The fill watcher reconciles it: check the row before UNWIND. " + held)
    elif q2 <= 0:
        outcome = "leg 1 filled, leg 2 unfilled"
        note = f"leg 1 filled {q1}, leg 2 filled nothing. " + held
    elif q2 < q1:
        outcome = "partially paired"
        note = (f"{paired} pairs locked; {q1 - paired} {l1['side']} on line {l1['line']:+g} unpaired.")
    else:
        outcome = "both legs filled"
        note = f"{paired} pairs locked at {c1 + c2} per pair; pays $1.00 per pair at settlement any score."
    # Settled: every sent leg's fill was observed, and a leg 2 that was not
    # sent was not sent for a definitive reason. Only a settled pair is the
    # desk's `recorded` attempt; anything else is `placed` with the outcome.
    settled = (l1["sent"] and l1.get("observed", q1 > 0)
               and (l2.get("observed", q2 > 0) if l2["sent"] else not l2.get("transport_error")))
    return {"outcome": outcome, "paired_quantity": float(paired),
            "cost_usd_filled": float(cost.quantize(Decimal("0.0001"))),
            "guaranteed_usd": float(guaranteed.quantize(Decimal("0.0001"))),
            "pair_cost": float((c1 + c2).quantize(Decimal("0.0001"))), "note": note,
            "pending": pending, "settled": bool(settled)}


def _arb_book_at(prefix: str, line: float) -> tuple[Decimal | None, Decimal | None]:
    """The cached ladder's touch for a rung, for the row's book-at-submission
    fields and for the unwind's default price. (None, None) when the sampler
    has not seen that rung."""
    snap = _ARB_LADDER["cache"].get(prefix) or {}
    age = time.time() - float(snap.get("sampled_ts") or 0)
    if age > _ARB_STALE_TOUCH_INTERVALS * _arb_sample_seconds():
        # The cache is never evicted, only the watch expires: a sample from
        # hours ago would price a SELL below today's market.
        return None, None
    rung = (snap.get("rungs") or {}).get(f"{line:g}")
    if not rung:
        return None, None
    return Decimal(str(rung["bid"])), Decimal(str(rung["ask"]))


def _arb_mark_unsent(ticket_id: str, row_ids: list[int], error: str) -> None:
    """Nothing reached the venue: say so on both rows and take them out of
    the "already sent" gate's match, so the ticket stays sendable once the
    environment is fixed. Only for a definitive failure (no credentials);
    a transport error is ambiguous and keeps its rows in the gate.

    **The idempotency key is released too, and that is the whole point.**
    The key claims "this exact order was submitted once"; a row whose order
    never left the process makes no such claim, and leaving the key on it
    made the row's own UNIQUE constraint refuse the retry — the notes gate
    would pass, the INSERT would collide, and the ticket was unsendable at
    that price for good. Suffixing keeps the row readable (and unique)
    while freeing the key the retry needs.
    """
    with _Session() as s:
        for n, row_id in enumerate(row_ids, start=1):
            stored = s.get(PlacedOrder, row_id)
            if stored is not None:
                stored.error = error[:1000] if n == 1 else f"leg 1 not sent: {error}"[:1000]
                stored.notes = f"arb ticket {ticket_id} leg {n} unsent"
                stored.idempotency_key = f"{stored.idempotency_key}-unsent-{stored.id}"[:120]
        s.commit()


@app.post("/api/arb/send")
def arb_send(req: ArbSendRequest, request: Request) -> dict:
    """SEND both legs of one executor ticket, leg 1 first, as IOC synchronous
    limit orders at the ticket's prices. Leg 2 goes only for the quantity leg 1
    filled; a zero fill on leg 1 ends the attempt with nothing held.

    Every term is the ticket's, checked here against the intent the executor
    wrote; the human's contribution is the two clicks and the token. The
    gates run in the order the module comment lists, and both idempotency
    rows exist before anything is sent.
    """
    _require_order_token(request)
    _arb_require_mode(req.mode)
    out = _arb_dir_or_409()
    intent = _arb_resolve_ticket(out, req.ticket_id)
    if intent.get("status", "open") != "open":
        # The desk's own record: placed by hand, skipped, or already sent
        # from here. A ticket leaves "open" once and only the operator's
        # explicit reopen puts it back; SEND never argues with that.
        raise HTTPException(
            status_code=409,
            detail=f"ticket {req.ticket_id} is {intent['status']!r}, not open; "
                   "reopen it on the desk first if that record is wrong")
    if len(req.legs) != 2:
        raise HTTPException(status_code=422, detail=f"a ticket has two legs; got {len(req.legs)}")
    prefix, game = _arb_prefix(str(intent.get("game") or ""))

    # The recorder's own listing, through the api's engine: the slugs the
    # caller sent are checked against these, never trusted.
    try:
        slug_of_line = {line_of(s_, prefix): s_ for s_ in slugs_for(game, _ENGINE)}
    except Exception as exc:  # noqa: BLE001 — the listing is a precondition, reported as one
        raise HTTPException(status_code=503, detail=f"cannot list {game}'s rungs: {str(exc)[:160]}") from None
    slug_of_line.pop(None, None)

    resolved = _arb_check_legs(intent, req.legs, slug_of_line, allow_size_up=_arb_allow_size_up())
    cap = _arb_check_stakes(resolved)
    if not req.acknowledge:
        raise HTTPException(
            status_code=422,
            detail="acknowledge must be true: the page shows every term and the second click sets it")
    if not _ladder_desk.armed(out):
        raise HTTPException(status_code=409, detail="LOCKED: the lock file exists; arm the desk first")
    # The executor keeps ticketing after a game passes its cap so the operator
    # can SEE what went by -- 281 pairs cleared the floor on one night and the
    # old behaviour showed four. Those tickets carry over_budget and are the
    # one kind the send route refuses: the cap limits what may be PLACED.
    if intent.get("over_budget"):
        raise HTTPException(
            status_code=409,
            detail="this game is past its ticket cap: the ticket is shown for the record, "
                   "not to be placed. Raise the cap for the game if you mean to trade it.")

    decided_at = _arb_decided_at(intent)
    orders = [build_order(market_slug=r["market_slug"], side=OrderSide.BUY,
                          limit_price=r["yes_price"], quantity=r["quantity"],
                          decided_at=decided_at, outcome=r["outcome"]) for r in resolved]

    # Both idempotency rows BEFORE any venue call (the human-confirm rule): a
    # double-click, a second tab or a retry collides on the UNIQUE key and
    # becomes a 409, never a second pair. accepted=False, so an attempt that
    # never comes back is still a row.
    with _Session() as s:
        # Serialise on the ticket: two clicks in two tabs with different
        # nudges have different keys, and check-then-insert in two sessions
        # would let both pass the SELECT below. The transaction-scoped
        # advisory lock is released with the commit.
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:tid))"), {"tid": req.ticket_id})
        # The key has no quantity or side term and a one-tick nudge changes
        # it, so the UNIQUE key alone would let a nudged ticket go twice. The
        # leg-1 note is the same across nudges: one row with it means sent.
        if s.scalars(select(PlacedOrder).where(
                PlacedOrder.notes == f"arb ticket {req.ticket_id} leg 1")).first() is not None:
            raise HTTPException(
                status_code=409,
                detail="this ticket was already sent (its leg 1 row exists); "
                       "record or unwind it, do not send it twice")
        rows = []
        for r, order in zip(resolved, orders):
            bid, ask = _arb_book_at(prefix, r["line"])
            rows.append(PlacedOrder(
                submitted_at=dt.datetime.now(UTC),
                idempotency_key=order.idempotency_key,
                mode=ExecutionMode.HUMAN_CONFIRM.value,
                market_slug=order.market_slug,
                side=f"{order.side.value}_{order.outcome.value}".lower(),
                order_type=order.order_type,
                limit_price=order.limit_price,
                quantity=order.quantity,
                accepted=False,
                market_bid=bid,
                market_ask=ask,
                would_rest=False,                 # IOC: it fills now or it is gone
                notes=f"arb ticket {req.ticket_id} leg {r['n']}",
            ))
        s.add_all(rows)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise HTTPException(
                status_code=409,
                detail="this ticket was already sent (idempotency key exists); "
                       "record or unwind it, do not send it twice") from None
        for r, row in zip(resolved, rows):
            r["order_id"] = row.id

    results = [_arb_leg_unsent(r["n"], r, None) for r in resolved]
    r1, r2 = resolved
    order1, order2 = orders

    _ORDER_BUCKET.acquire()
    try:
        creds = USCredentials.from_env()
    except MissingCredentialsError as exc:
        # Definitive: nothing was sent, so the ticket must stay sendable.
        _arb_mark_unsent(req.ticket_id, [r1["order_id"], r2["order_id"]], str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from None

    qty2 = None
    with PolymarketOrderClient(creds) as client:
        payload1 = order1.to_payload(post_only=False, tif=ARB_TIF, synchronous=True)
        try:
            resp1 = client.submit_limit_order(payload1)
        except OrderSubmissionError as exc:
            # Ambiguous: leg 1 may exist at the venue. Its row says so; leg 2
            # is not sent into that ambiguity, and the ticket is marked placed
            # so it cannot be sent again without the operator looking.
            _fail_order(r1["order_id"], error=str(exc))
            _fail_order(r2["order_id"], error="leg 1 got no answer (transport error); leg 2 not sent")
            _ladder_desk.record_attempt(out, req.ticket_id, "placed", via=_ARB_VIA_SEND,
                                        outcome="leg 1 transport error", l1_sent=float(r1["quantity"]),
                                        error=str(exc)[:200], order_ids=[r1["order_id"], r2["order_id"]])
            log.error("arb_send", ticket=req.ticket_id, outcome="leg 1 transport error",
                      error=str(exc)[:200])
            raise HTTPException(status_code=502, detail=f"leg 1: {exc}; leg 2 was not sent") from None
        parsed1 = _arb_parse_sync(resp1.body_text)
        results[0] = _arb_persist_leg(r1["order_id"], r1, r1["quantity"], resp1, parsed1)
        # The venue's own Decimal sizes leg 2, never a float round trip.
        filled1 = parsed1["filled"] if results[0]["accepted"] else Decimal("0")

        if filled1 <= 0:
            # Three different facts, one action (nothing more is sent): a
            # terminal zero is the observation; a refusal and a pending or
            # unreadable reply are not, and the record below says placed.
            reason = ("leg 1 unfilled" if results[0]["observed"]
                      else "leg 1 rejected" if not results[0]["accepted"]
                      else "leg 1 pending at the venue")
            _fail_order(r2["order_id"], error=f"{reason}; leg 2 not sent")
            results[1] = _arb_leg_unsent(2, r2, f"{reason}; leg 2 not sent")
        else:
            qty2 = _arb_qty(min(r2["quantity"], filled1))
            if qty2 != order2.quantity:
                # Same key (the key has no quantity term); the row's quantity
                # becomes what is actually sent.
                order2 = build_order(market_slug=r2["market_slug"], side=OrderSide.BUY,
                                     limit_price=r2["yes_price"], quantity=qty2,
                                     decided_at=decided_at, outcome=r2["outcome"])
                with _Session() as s:
                    s.get(PlacedOrder, r2["order_id"]).quantity = qty2
                    s.commit()
            _ORDER_BUCKET.acquire()
            payload2 = order2.to_payload(post_only=False, tif=ARB_TIF, synchronous=True)
            try:
                resp2 = client.submit_limit_order(payload2)
            except OrderSubmissionError as exc:
                # Ambiguous: leg 2 may exist. Its row keeps the key the
                # venue would match a retry on; the outcome says "unknown".
                _fail_order(r2["order_id"], error=str(exc))
                results[1] = _arb_leg_unsent(2, r2, f"transport error: {exc}", transport=True)
            else:
                parsed2 = _arb_parse_sync(resp2.body_text)
                results[1] = _arb_persist_leg(r2["order_id"], r2, qty2, resp2, parsed2)
                if (parsed2["avg_reported"] is not None and parsed2["avg_vwap"] is not None
                        and parsed2["avg_reported"] != parsed2["avg_vwap"]):
                    log.warning("arb_avg_px_disagrees", leg=2, reported=str(parsed2["avg_reported"]),
                                vwap=str(parsed2["avg_vwap"]), executions=parsed2["executions"])
        if (parsed1["avg_reported"] is not None and parsed1["avg_vwap"] is not None
                and parsed1["avg_reported"] != parsed1["avg_vwap"]):
            log.warning("arb_avg_px_disagrees", leg=1, reported=str(parsed1["avg_reported"]),
                        vwap=str(parsed1["avg_vwap"]), executions=parsed1["executions"])

    pair = _arb_pair_summary(results)
    # The record the tally reads. `recorded` with fills only for a settled
    # pair (every sent leg's fill observed); otherwise `placed` with the
    # outcome, and the operator records the real fill by hand once the
    # watcher has reconciled the rows. A 401 is not "leg 1 filled nothing".
    fills = None
    if pair["settled"]:
        fills = {"l1q": results[0]["filled_quantity"], "l1p": results[0]["avg_cost_price"],
                 "l1s": None if results[0]["latency_ms"] is None else round(results[0]["latency_ms"] / 1000, 3),
                 "l2q": results[1]["filled_quantity"], "l2p": results[1]["avg_cost_price"],
                 "l2s": None if results[1]["latency_ms"] is None else round(results[1]["latency_ms"] / 1000, 3)}
    record = _ladder_desk.record_attempt(
        out, req.ticket_id, "recorded" if pair["settled"] else "placed", fills,
        via=_ARB_VIA_SEND, outcome=pair["outcome"],
        # Sizes SENT, so the tally's 80% is of what went, not of the ticket.
        l1_sent=float(r1["quantity"]), l2_sent=None if qty2 is None else float(qty2),
        error=next((x["error"] for x in results if x["error"]), None),
        venue_order_ids=[x["venue_order_id"] for x in results],
        order_ids=[x["order_id"] for x in results])
    with _Session() as s:
        counts = _order_counts(s)
    log.info(
        "arb_send",
        ticket=req.ticket_id, game=game, outcome=pair["outcome"],
        leg1_filled=results[0]["filled_quantity"], leg2_filled=results[1]["filled_quantity"],
        leg1_state=results[0]["state"], leg2_state=results[1]["state"],
        leg1_latency_ms=results[0]["latency_ms"], leg2_latency_ms=results[1]["latency_ms"],
        cap=float(cap), pending=pair["pending"], settled=pair["settled"],
        # The first synchronous reply IS the finding: the shape was read, not
        # seen, so the whole body is logged, both legs.
        leg1_response=results[0]["response"] or "",
        leg2_response=results[1]["response"] or "",
    )
    return {"ticket_id": req.ticket_id, "game": game, "outcome": pair["outcome"],
            "legs": results, "pair": pair, "record": record, **counts}


# --- the unwind ----------------------------------------------------------- #


class ArbUnwindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    mode: str
    leg: Literal[1, 2, "both"] = "both"
    #: Cost frame, as the page shows it. Absent: the cached ladder's touch
    #: for that rung, which for an IOC is "at market".
    limit_cost_price: Decimal | None = None
    acknowledge: bool = False


def _arb_sold_so_far(s, ticket_id: str, n: int) -> Decimal:
    """Contracts already sold (or possibly sold) by earlier unwinds of this
    leg: a terminal sell counts its fill; a sell the venue refused counts
    nothing; a sell still unreconciled -- or one that never got an answer --
    counts its whole quantity, because the venue may yet report it filled.
    Never sell more than filled, across clicks as well as within one; an
    ambiguous earlier unwind therefore blocks the button, and the hand path
    remains."""
    from core.fill_watcher import TERMINAL

    sold = Decimal("0")
    for row in s.scalars(select(PlacedOrder).where(
            PlacedOrder.notes == f"arb ticket {ticket_id} leg {n} unwind")).all():
        if not row.accepted and row.http_status is not None:
            continue                      # the venue answered and refused: nothing sold
        if row.fill_status in TERMINAL:
            sold += row.filled_quantity or Decimal("0")
        else:
            sold += row.quantity
    return sold


@app.post("/api/arb/unwind")
def arb_unwind(req: ArbUnwindRequest, request: Request) -> dict:
    """SELL what a leg bought, for the quantity the venue reported filled,
    IOC synchronous at the ticket's rung touch or a typed price. The protocol's
    "leg 1 filled, leg 2 did not" remedy, on a button. Never sells more than
    filled, and the second click on an unwound leg is refused."""
    _require_order_token(request)
    _arb_require_mode(req.mode)
    if not req.acknowledge:
        raise HTTPException(status_code=422, detail="acknowledge must be true")
    out = _arb_dir_or_409()
    intent = _arb_resolve_ticket(out, req.ticket_id)
    prefix, game = _arb_prefix(str(intent.get("game") or ""))
    if req.limit_cost_price is not None:
        _validate_typed_price(req.limit_cost_price, what="unwind price")
    legs = [1, 2] if req.leg == "both" else [int(req.leg)]

    results = []
    for n in legs:
        line = float((intent.get(f"leg{n}") or {}).get("market_line") or 0)
        # The read of what is sold so far and the insert of this sell are ONE
        # transaction under a per-leg advisory lock: two clicks in two tabs
        # (distinct keys, decided_at = now) must not both see the full
        # remaining quantity. The lock is released with the commit.
        with _Session() as s:
            s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                      {"k": f"arb ticket {req.ticket_id} leg {n} unwind"})
            buy = s.scalars(
                select(PlacedOrder)
                .where(PlacedOrder.notes == f"arb ticket {req.ticket_id} leg {n}",
                       PlacedOrder.side.in_(("buy_yes", "buy_no")))
                .order_by(PlacedOrder.submitted_at.desc())
            ).first()
            if buy is None or not buy.accepted or not buy.filled_quantity or buy.filled_quantity <= 0:
                results.append({"leg": n, "sent": False, "accepted": False, "filled_quantity": 0.0,
                                "error": "nothing filled on this leg to unwind"})
                continue
            sold = _arb_sold_so_far(s, req.ticket_id, n)
            # Numeric(18, 4) comes back as Decimal('2.0000'); the venue has
            # only ever seen "2".
            remaining = _arb_qty(buy.filled_quantity - sold)
            buy_id, buy_slug, buy_side = buy.id, buy.market_slug, buy.side
            if remaining <= 0:
                results.append({"leg": n, "sent": False, "accepted": False, "filled_quantity": 0.0,
                                "error": f"already unwound: {sold} of {sold + remaining} sold or pending"})
                continue
            outcome = OutcomeSide.YES if buy_side == "buy_yes" else OutcomeSide.NO
            bid, ask = _arb_book_at(prefix, line)
            if req.limit_cost_price is not None:
                cost = req.limit_cost_price
            else:
                # Selling YES hits the YES bid; selling NO hits the NO bid,
                # which is 1 - the YES ask. Both in the position's cost frame.
                touch = bid if outcome is OutcomeSide.YES else (None if ask is None else Decimal("1") - ask)
                if touch is None:
                    raise HTTPException(
                        status_code=409,
                        detail=f"no cached ladder touch for line {line:+g} (none, or older than "
                               f"{_ARB_STALE_TOUCH_INTERVALS:g} sample intervals); open the game's "
                               "ladder or pass limit_cost_price")
                cost = round_to_tick(touch)
                _validate_typed_price(cost, what=f"leg {n} unwind touch")
            yes_price = (Decimal("1") - cost) if outcome is OutcomeSide.NO else cost
            try:
                order = build_order(market_slug=buy_slug, side=OrderSide.SELL, limit_price=yes_price,
                                    quantity=remaining, decided_at=dt.datetime.now(UTC), outcome=outcome)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
            r = {"n": n, "line": line, "market_slug": buy_slug, "side": f"SELL {outcome.value}",
                 "outcome": outcome, "cost": cost, "quantity": remaining, "yes_price": yes_price}
            row = PlacedOrder(
                submitted_at=dt.datetime.now(UTC),
                idempotency_key=order.idempotency_key,
                mode=ExecutionMode.HUMAN_CONFIRM.value,
                market_slug=buy_slug,
                side=f"sell_{outcome.value}".lower(),
                order_type=order.order_type,
                limit_price=order.limit_price,
                quantity=remaining,
                accepted=False,
                market_bid=bid,
                market_ask=ask,
                would_rest=False,
                notes=f"arb ticket {req.ticket_id} leg {n} unwind",
            )
            s.add(row)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise HTTPException(status_code=409, detail="this unwind was already submitted") from None
            r["order_id"] = row.id

        _ORDER_BUCKET.acquire()
        try:
            creds = USCredentials.from_env()
        except MissingCredentialsError as exc:
            _fail_order(r["order_id"], error=str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from None
        payload = order.to_payload(post_only=False, tif=ARB_TIF, synchronous=True)
        try:
            with PolymarketOrderClient(creds) as client:
                resp = client.submit_limit_order(payload)
        except OrderSubmissionError as exc:
            _fail_order(r["order_id"], error=str(exc))
            results.append(dict(_arb_leg_unsent(n, r, f"transport error: {exc}"),
                                unwind_of=buy_id))
            continue
        parsed = _arb_parse_sync(resp.body_text)
        results.append(dict(_arb_persist_leg(r["order_id"], r, remaining, resp, parsed),
                            unwind_of=buy_id))

    with _Session() as s:
        counts = _order_counts(s)
    log.info("arb_unwind", ticket=req.ticket_id, game=game,
             legs=[(x["leg"], x.get("sent"), x.get("filled_quantity")) for x in results])
    return {"ticket_id": req.ticket_id, "game": game, "legs": results, **counts}


@app.get("/arb")
def arb_page() -> FileResponse:
    """The ARB tab: the ladder desk on the dashboard.

    A build without the page answers 404, not 500: the routes and the page
    land in separate commits, and a FileResponse on a missing file is a
    handler crash the route smoke test rightly refuses.
    """
    page = STATIC / "arb.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="static/arb.html is not present in this build")
    return FileResponse(page)


@app.get("/pnl", response_class=HTMLResponse)
def arb_pnl_page() -> str:
    """What the night committed, what a filled pair returns, and what the tape
    showed that nobody caught.

    Server-rendered rather than another JSON route plus JavaScript: it reads
    the same files `/api/arb/state` does and every number on it is arithmetic
    over them, so there is nothing for a client to poll and nothing that can
    disagree with the ARB tab. It carried the operator's "i wanna see PnL"
    on the temporary desk; that desk is gone and this is where it lives.
    """
    out = _ladder_desk.api_out_dir()
    stamp = dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M") + "Z"
    return _ladder_pnl_page.render(_ladder_pnl.session(out), _ladder_pnl.opportunity(out), out, stamp)


@app.get("/log", response_class=HTMLResponse)
def arb_gamelog_page(game: str = Query("", max_length=120)) -> str:
    """Every opportunity a game's tape showed, acted on or not.

    The ARB tab's ticket list is a to-do list — a ticket that no longer clears
    is hidden — so nothing on the dashboard held the FULL record of a night.
    This is that record: one row per episode, with the operator's own tickets
    joined on, so an episode with no ticket beside it is visible as what it is.

    Server-rendered for the same reason /pnl is: every number is arithmetic
    over files `/api/arb/state` already reads, so there is nothing to poll and
    nothing that can disagree with the tab.

    `game` is empty for the most recently written tape, which is what opening
    /log mid-slate should show.
    """
    out = _ladder_desk.api_out_dir()
    stamp = dt.datetime.now(UTC).strftime("%Y-%m-%d %H:%M") + "Z"
    return _ladder_gamelog_page.render(
        _ladder_gamelog.game_log(out, game or None),
        _ladder_gamelog.slate_log(out),
        _ladder_tape.games(out), out, stamp)


@app.get("/instructions", response_class=HTMLResponse)
def arb_instructions_page() -> str:
    """How to place a ladder ticket, in plain words, for a person holding a
    phone.

    It answers the one question the ARB tab cannot fit on a ticket: the
    venue prices the UNDERDOG while its row is titled after the team laying
    the points, so "buy the easier line" reaches the screen as a tap on the
    OTHER team's row. Getting that backwards is the way this trade loses
    money, and it is the only way it loses money to the score.

    A constant, not a file read: it is baked into the image beside the code
    it describes, so it cannot 404 the way it did while it lived in cfb/ and
    only the temporary desk served it.
    """
    return _ladder_instructions.HTML


@app.get("/quote")
def quote_page() -> FileResponse:
    return FileResponse(STATIC / "quote.html")


@app.get("/wallet")
def wallet_page() -> FileResponse:
    return FileResponse(STATIC / "wallet.html")


@app.get("/analytics")
def analytics_page() -> FileResponse:
    return FileResponse(STATIC / "analytics.html")


@app.get("/scoreboard")
def scoreboard_page() -> FileResponse:
    return FileResponse(STATIC / "scoreboard.html")


@app.get("/")
def index() -> FileResponse:
    """The picks page. There is no separate live board any more.

    `/api/board` outlives the page it was written for and is still served —
    it is the only endpoint that returns every rung with its prediction, and
    the replay and board-cadence tests read it — but nothing renders it.
    """
    return FileResponse(STATIC / "index.html")
