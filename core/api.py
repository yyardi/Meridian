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
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import Numeric, cast, func, select

from core.storage import (
    MarketSnapshot,
    Prediction,
    ShadowOrder,
    get_engine,
    get_sessionmaker,
)

UTC = dt.timezone.utc

app = FastAPI(title="Meridian", docs_url=None, redoc_url=None)
_Session = get_sessionmaker(get_engine())

STATIC = Path(__file__).parent.parent / "static"


def _f(value) -> float | None:
    return None if value is None else float(value)


@app.get("/api/status")
def status() -> dict:
    """Recorder health: freshness, cycle count, gaps."""
    with _Session() as s:
        total, newest, cycles = s.execute(
            select(
                func.count(MarketSnapshot.id),
                func.max(MarketSnapshot.captured_at),
                func.count(func.distinct(MarketSnapshot.captured_at)),
            )
        ).one()
        instants = s.scalars(
            select(func.distinct(MarketSnapshot.captured_at))
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(200)
        ).all()
        counts = {
            "snapshots": total,
            "book_levels": s.scalar(select(func.count()).select_from(
                __import__("core.storage", fromlist=["BookLevel"]).BookLevel)),
            "predictions": s.scalar(select(func.count(Prediction.id))),
            "shadow_orders": s.scalar(select(func.count(ShadowOrder.id))),
        }

    age_min = None
    if newest:
        age_min = (dt.datetime.now(UTC) - newest).total_seconds() / 60

    gaps = 0
    ordered = sorted(instants)
    for a, b in zip(ordered, ordered[1:]):
        if (b - a).total_seconds() / 60 > 90:
            gaps += 1

    return {
        "cycles": cycles,
        "newest": newest.isoformat() if newest else None,
        "age_minutes": round(age_min, 1) if age_min is not None else None,
        "healthy": age_min is not None and age_min < 90,
        "gaps_recent": gaps,
        "counts": counts,
        "real_orders_placed": 0,   # shadow mode; nothing is ever sent
    }


@app.get("/api/board")
def board() -> dict:
    """Latest snapshot of every market, joined to the newest prediction."""
    with _Session() as s:
        latest = s.scalar(select(func.max(MarketSnapshot.captured_at)))
        if latest is None:
            return {"captured_at": None, "markets": []}

        snaps = s.scalars(
            select(MarketSnapshot).where(MarketSnapshot.captured_at == latest)
        ).all()

        pred_time = s.scalar(select(func.max(Prediction.predicted_at)))
        preds = {}
        if pred_time is not None:
            for p in s.scalars(
                select(Prediction).where(Prediction.predicted_at == pred_time)
            ).all():
                preds[p.market_slug] = p

        shadow = {
            o.market_slug: o
            for o in s.scalars(select(ShadowOrder)).all()
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
                "is_live": snap.is_live,
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
    """Games being tracked, newest snapshot only."""
    with _Session() as s:
        latest = s.scalar(select(func.max(MarketSnapshot.captured_at)))
        if latest is None:
            return {"events": []}
        rows = s.execute(
            select(
                MarketSnapshot.event_slug,
                func.count(MarketSnapshot.id),
                func.min(MarketSnapshot.game_start_time),
                func.bool_or(MarketSnapshot.is_live),
            )
            .where(MarketSnapshot.captured_at == latest)
            .group_by(MarketSnapshot.event_slug)
            .order_by(func.min(MarketSnapshot.game_start_time))
        ).all()
    return {
        "events": [
            {
                "event_slug": slug,
                "markets": n,
                "start": start.isoformat() if start else None,
                "is_live": bool(live),
            }
            for slug, n, start, live in rows
        ]
    }


@app.get("/api/picks")
def picks() -> dict:
    """Tonight's actionable pregame picks, with the shadow order attached."""
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
    out = []
    for p in preds:
        start = starts.get(p.market_slug)
        if start is None or start <= now:      # pregame only
            continue
        bid, ask = _f(p.market_bid), _f(p.market_ask)
        model = _f(p.model_probability)
        if bid is None or ask is None or model is None:
            continue
        edge_yes, edge_no = model - ask, bid - model
        side, edge = ("YES", edge_yes) if edge_yes >= edge_no else ("NO", edge_no)
        mtype = (p.sports_market_type or "").replace("basketball_team_full_game_", "")
        if mtype == "total":
            side = "OVER" if side == "YES" else "UNDER"
        o = shadow.get(p.market_slug)
        out.append({
            "market_slug": p.market_slug,
            "event_slug": p.event_slug,
            "type": mtype,
            "line": _f(p.line),
            "side": side,
            "edge": round(edge, 4),
            "model": model,
            "bid": bid, "ask": ask,
            "game_start": start.isoformat(),
            "hours_to_tipoff": round((start - now).total_seconds() / 3600, 1),
            "suspect": edge > 0.15,
            "shadow": None if o is None else {
                "limit_price": _f(o.limit_price),
                "quantity": _f(o.quantity),
                "would_rest": o.would_rest,
            },
        })
    out.sort(key=lambda r: -r["edge"])
    return {"predicted_at": pred_time.isoformat(), "picks": out}


@app.get("/api/results")
def results(limit: int = 200) -> dict:
    """Resolved live predictions — what the model called, and what happened."""
    with _Session() as s:
        rows = s.scalars(
            select(Prediction)
            .where(Prediction.resolved_outcome.isnot(None))
            .order_by(Prediction.predicted_at.desc())
            .limit(limit)
        ).all()

    out, actionable = [], []
    for p in rows:
        model = _f(p.model_probability)
        mid = _f(p.market_mid)
        # Only rows with a real market price at prediction time are meaningful.
        tradeable = mid is not None and mid > 0
        rec = {
            "market_slug": p.market_slug,
            "event_slug": p.event_slug,
            "type": (p.sports_market_type or "").replace("basketball_team_full_game_", ""),
            "line": _f(p.line),
            "model": model,
            "market": mid,
            "settled": p.resolved_outcome,
            "correct": p.was_correct,
            "model_version": p.model_version,
            "predicted_at": p.predicted_at.isoformat(),
            "tradeable": tradeable,
        }
        out.append(rec)
        if tradeable and p.was_correct is not None:
            actionable.append(bool(p.was_correct))

    return {
        "results": out,
        "summary": {
            "total": len(out),
            "tradeable": len(actionable),
            "correct": sum(actionable),
            "hit_rate": (sum(actionable) / len(actionable)) if actionable else None,
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
