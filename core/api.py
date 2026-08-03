"""Read-only JSON API behind the Meridian dashboard.

Serves the live board, recorder health, prediction/edge data and shadow orders.

**Read-only by construction.** There is no write endpoint and no order path —
the dashboard is a window, not a control panel. Placing orders stays in
`core/executor.py`, in shadow mode, behind a kill switch.

Binds to localhost only. Nothing here is authenticated, so it must not be
exposed to a network.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text

from core.board import FINISHED, IN_PLAY, latest_snapshot_per_market, market_state
from core.executor import ExecutorConfig
from core.storage import (
    MarketSnapshot,
    Prediction,
    ShadowOrder,
    get_engine,
    get_sessionmaker,
)
from core.team_mapping import parse_market_slug

UTC = dt.timezone.utc

app = FastAPI(title="Meridian", docs_url=None, redoc_url=None)

#: The same policy the executor enforces. Read from one place so the page and
#: the order path can never disagree about what is tradable.
_EXECUTOR_POLICY = ExecutorConfig()

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
_Session = get_sessionmaker(get_engine(pool_size=5, max_overflow=5))

STATIC = Path(__file__).parent.parent / "static"


def _f(value) -> float | None:
    return None if value is None else float(value)



def _human_market(market_slug: str, market_type: str | None, line: float | None) -> str:
    """Turn a Polymarket slug into something a human can act on.

    `ny-phx-pos-10pt5` is unreadable and, worse, invites the wrong reading:
    it looks like "NY by 10.5" when it means "NY **+**10.5" — NY *getting* the
    points. Those are opposite bets. The slug's first team is the side the
    market is quoted from (positional only; it is NOT necessarily the away
    team), so the label names it explicitly.
    """
    parsed = parse_market_slug(market_slug)
    first = parsed.first_espn.upper() if parsed else "?"

    if (market_type or "").endswith("total"):
        return f"Total {line:g}" if line is not None else "Total"
    if (market_type or "").endswith("winner"):
        return f"{first} to win"
    if (market_type or "").endswith("spread"):
        if line is None:
            return f"{first} spread"
        # `-pos-` in the slug means the quoted team is GETTING points.
        sign = "+" if "-pos-" in market_slug else "-"
        return f"{first} {sign}{abs(line):g}"
    return market_slug


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
  (select reltuples::bigint from pg_class where relname = 'market_snapshots'),
  (select reltuples::bigint from pg_class where relname = 'book_levels'),
  (select reltuples::bigint from pg_class where relname = 'predictions'),
  (select reltuples::bigint from pg_class where relname = 'shadow_orders'),
  (select max(captured_at) from market_snapshots),
  (select max(captured_at) from market_snapshots where book_tier is null),
  (select max(captured_at) from market_snapshots where book_tier is not null),
  pg_total_relation_size('market_snapshots')
    + pg_total_relation_size('book_levels')
""")

_status_cache: dict = {"at": 0.0, "value": None}


def _age_seconds(then, now: dt.datetime) -> float | None:
    return None if then is None else (now - then).total_seconds()


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
        return cached

    with _Session() as s:
        row = s.execute(_HEALTH_SQL).one()

    (n_snap, n_levels, n_preds, n_orders,
     newest, pregame_newest, live_newest, stream_bytes) = row

    now = dt.datetime.now(UTC)
    pregame_age = _age_seconds(pregame_newest, now)
    live_age = _age_seconds(live_newest, now)

    # Health is the pregame recorder's, because it is the only writer expected
    # to be running at all times. The live recorder is legitimately silent
    # whenever no game is in progress, so its age is reported but never fails
    # the check — otherwise the dashboard would show STALE every night.
    healthy = pregame_age is not None and pregame_age < PREGAME_STALE_SECONDS

    value = {
        "newest": newest.isoformat() if newest else None,
        "age_minutes": (
            round(_age_seconds(newest, now) / 60, 1) if newest else None
        ),
        #: Per-writer freshness. `pregame` is the health signal; `live` is
        #: informational and is expected to be stale between games.
        "pregame_age_seconds": round(pregame_age, 1) if pregame_age is not None else None,
        "live_age_seconds": round(live_age, 1) if live_age is not None else None,
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
        "real_orders_placed": 0,   # shadow mode; nothing is ever sent
    }
    _status_cache["at"] = now_mono
    _status_cache["value"] = value
    return value


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
def board(include_finished: bool = False) -> dict:
    """Latest snapshot of every market still on the board, with its prediction."""
    now = dt.datetime.now(UTC)
    with _Session() as s:
        snaps = _live_board(s, as_of=now, include_finished=include_finished)
        if not snaps:
            return {"captured_at": None, "markets": []}
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
            })

    return {
        "captured_at": latest.isoformat(),
        "predicted_at": pred_time.isoformat() if pred_time else None,
        "markets": rows,
    }


@app.get("/api/history/{market_slug}")
def history(market_slug: str, limit: int = 60) -> dict:
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
def events() -> dict:
    """Games being tracked, each from its own latest snapshot.

    Had the same defect as `/api/board`: grouping the single newest instant
    meant the sidebar listed only whichever game the live recorder had just
    written, so a full slate rendered as one game.
    """
    now = dt.datetime.now(UTC)
    with _Session() as s:
        snaps = _live_board(s, as_of=now, include_finished=False)

    grouped: dict[str, dict] = {}
    for snap in snaps:
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
        ]
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
          include_illiquid: bool = False) -> dict:
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
    actionability gates are not overridable from a URL.
    """
    with _Session() as s:
        pred_time = s.scalar(select(func.max(Prediction.predicted_at)))
        if pred_time is None:
            return {"picks": [], "predicted_at": None}
        preds = s.scalars(
            select(Prediction).where(Prediction.predicted_at == pred_time)
        ).all()
        shadow = {o.market_slug: o for o in s.scalars(select(ShadowOrder)).all()}
        starts = {
            slug: start for slug, start in s.execute(
                select(MarketSnapshot.market_slug,
                       func.max(MarketSnapshot.game_start_time))
                .group_by(MarketSnapshot.market_slug)
            ).all()
        }

    now = dt.datetime.now(UTC)
    out, filtered_far, filtered_wide = [], 0, 0
    filtered_untradable = filtered_unanchored = 0
    for p in preds:
        start = starts.get(p.market_slug)
        if start is None or start <= now:      # pregame only
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
            "model": model,
            "bid": bid, "ask": ask,
            "game_start": start.isoformat(),
            "hours_to_tipoff": round(hours, 1),
            "spread": round(spread, 4),
            "suspect": edge > 0.15,
            "shadow": None if o is None else {
                "limit_price": _f(o.limit_price),
                "quantity": _f(o.quantity),
                "would_rest": o.would_rest,
            },
        })
    # Ordered by tipoff: the soonest game is the one you can actually act on.
    out.sort(key=lambda r: (r["game_start"], -r["edge"]))
    return {
        "predicted_at": pred_time.isoformat(),
        "horizon_hours": horizon_hours,
        "filtered": {
            "beyond_horizon": filtered_far,
            "spread_too_wide": filtered_wide,
            "market_not_traded": filtered_untradable,
            "no_book_line_yet": filtered_unanchored,
        },
        "picks": out,
    }


@app.get("/api/results")
def results(limit: int = 2000) -> dict:
    """Resolved live predictions — what the model called, and what happened.

    **Hit rate is the wrong metric and is reported only as a foil.** It asks
    "was the probability on the correct side of 0.50", which is not a bet and
    is trivially high because most contracts are lopsided. Measured on the
    first 614 resolved rows it read 84% while the actual bets ran 38.5%, and
    243 rows flagged "correct" were losing positions.

    The metrics that mean something:

    * `bet_win_rate` — of the rows where the model actually disagreed with the
      market (the only ones that are bets), how many won. Breakeven is 0.524.
    * `n_games` — rows are NOT independent. One game produces ~120 correlated
      ladder rows, so 600 rows can be five games. Sample size is games.
    * `brier_model` vs `brier_market` — squared error of each forecast on the
      same events. Lower is better. If the market wins, the model is not
      adding information no matter what the hit rate says.
    """
    with _Session() as s:
        rows = s.scalars(
            select(Prediction)
            .where(Prediction.resolved_outcome.is_not(None))
            .order_by(Prediction.predicted_at.desc())
            .limit(limit)
        ).all()

    out, games = [], set()
    n_bets = n_bet_wins = n_no_bet = 0
    se_model = se_market = 0.0
    n_scored = 0

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
            # Kept for continuity, and deliberately NOT the headline.
            "correct": (model > 0.5) == (settled == 1),
            "bet_side": bet_side,
            "bet_won": bet_won,
            "model_version": p.model_version,
            "predicted_at": p.predicted_at.isoformat(),
            "tradeable": p.market_ask is not None,
        })

    return {
        "results": out,
        "summary": {
            "rows": len(out),
            "n_games": len(games),
            "rows_per_game": round(len(out) / len(games), 1) if games else None,
            "n_bets": n_bets,
            "n_no_bet": n_no_bet,
            "bet_win_rate": round(n_bet_wins / n_bets, 4) if n_bets else None,
            "breakeven": BREAKEVEN_HIT_RATE,
            "brier_model": round(se_model / n_scored, 4) if n_scored else None,
            "brier_market": round(se_market / n_scored, 4) if n_scored else None,
            # The honest headline, kept last so it reads as the footnote it is.
            "hit_rate_MISLEADING": round(
                sum(1 for r in out if r["correct"]) / len(out), 4
            ) if out else None,
        },
    }


@app.get("/picks")
def picks_page() -> FileResponse:
    return FileResponse(STATIC / "picks.html")


@app.get("/api/analytics")
def analytics() -> dict:
    """Pre-computed model-performance data.

    Built by `python -m core.analytics`, not computed here: a walk-forward run
    takes ~17s locally and far longer against a remote database.
    """
    import json
    path = Path(__file__).parent.parent / "reports" / "analytics.json"
    if not path.exists():
        return {"error": "run `python -m core.analytics` first"}
    return json.loads(path.read_text())


@app.get("/analytics")
def analytics_page() -> FileResponse:
    return FileResponse(STATIC / "analytics.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
