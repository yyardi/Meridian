"""Hand-trade audit: score the human's app trading honestly, at prices.

**DESCRIPTIVE, not a gated hypothesis.** This module reports what happened —
dollars staked, dollars returned, ROI, win rate at entry price — and draws no
conclusion. No pre-registered gate governs it, so per this project's rules it
is not allowed to have a verdict, only numbers. The user's in-game trading is
the one live-money-positive activity in the project; this replaces the feeling
with a measurement.

Scoring rules (C11 — money-at-price, the only honest frame)
-----------------------------------------------------------
Flat win rate against a 52.4% breakeven was a category error on a portfolio of
32¢ entries (findings C11). Everything here is scored in money at the actual
entry price:

* **YES cost = the price paid.** Buying YES at 0.25 stakes \\$0.25/contract.
* **NO cost = 1 − price.** The venue reports every price in the YES frame
  (V14/V19: a NO order's ``price.value`` is 1 − cost), so buying NO at
  price.value 0.80 stakes \\$0.20/contract. Short YES is the same trade.
* A round trip **wins** if it returned more dollars than it staked. The win
  rate is reported next to the stake-weighted average entry cost, which IS its
  breakeven — a 30% win rate on 25¢ entries is profit, not failure.
* **Fees are reported separately, never netted silently.** The venue's own
  per-execution commission fields are summed and shown as reported; headline
  ROI is gross, matching how C11's numbers were scored.

Round-trip reconstruction
-------------------------
Every execution becomes a signed YES-exposure delta: +q for (BUY, YES) and
(SELL, NO); −q for (SELL, YES) and (BUY, NO). Within one market, an episode
runs from the moment net exposure leaves zero until it returns to zero — by
trades, by settlement (``ACTIVITY_TYPE_POSITION_RESOLUTION`` closes whatever
remains at the market's 0/1 settlement), or both. A fill that crosses zero is
split; the crossing starts a new round trip in the other direction. Settlement
payout comes from the venue's **public settlement endpoint** (0/1 = the YES
payout), not from the resolution activity's before/after bookkeeping, whose
sign conventions are undocumented — ground truth over inference.

What is excluded, and how
-------------------------
Button orders — every ``orders`` row with a ``venue_order_id`` (entries and
pre-authorized exits alike) — are excluded by **venue order id only**, the
same attribution rule the fill watcher lives by: never by market, price, size,
or timing similarity, because the human trades the same markets at similar
prices. The venue's ``manualOrderIndicator`` is recorded per fill as a
cross-check but is deliberately not the filter; our own order ids are the
stronger claim.

    python -m core.audit.hand_trades              # text report
    python -m core.audit.hand_trades --json       # machine-readable
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import structlog

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

ACTIVITIES_PATH = "/v1/portfolio/activities"
PAGE_LIMIT = 100
#: Generous: the whole account history is a few hundred events. Paced well
#: under the authenticated host's ~5 req/s throttle (V12).
MAX_PAGES = 50
PAGE_PAUSE_SECONDS = 0.35

ACTIVITY_TRADE = "ACTIVITY_TYPE_TRADE"
ACTIVITY_RESOLUTION = "ACTIVITY_TYPE_POSITION_RESOLUTION"

ZERO = Decimal("0")
ONE = Decimal("1")


# --------------------------------------------------------------------------- #
# Parsing — against the schema observed live 2026-08-07 (superset of V19)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Fill:
    """One of OUR executions, in the venue's YES frame."""

    market_slug: str
    market_type: str | None          # market.sportsMarketType
    game_start: dt.datetime | None   # market.gameStartTime
    at: dt.datetime
    venue_order_id: str
    is_buy: bool                     # ORDER_SIDE_BUY
    outcome_yes: bool                # OUTCOME_SIDE_YES
    yes_price: Decimal               # lastPx.value — YES frame (V14)
    shares: Decimal                  # lastShares
    manual: bool                     # manualOrderIndicator == ..._MANUAL
    commission: Decimal              # commissionNotionalCollected, as reported

    @property
    def yes_delta(self) -> Decimal:
        """Signed YES exposure: buying YES or selling NO is +, else −."""
        sign = 1 if self.is_buy == self.outcome_yes else -1
        return sign * self.shares


@dataclass(frozen=True)
class Resolution:
    market_slug: str
    at: dt.datetime


def _parse_ts(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        # RFC3339 with nanoseconds — trim to microseconds for fromisoformat.
        if "." in text and text.endswith("Z"):
            head, frac = text[:-1].split(".", 1)
            text = f"{head}.{frac[:6]}Z"
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_activity(raw: dict) -> tuple[list[Fill], Resolution | None, bool]:
    """One raw activity → (our fills, resolution, parsed_ok).

    Unknown shapes return ``ok=False`` and are counted loudly by the caller —
    the fill watcher's rule: schema drift is never silently dropped.
    """
    kind = raw.get("type")
    if kind == ACTIVITY_RESOLUTION:
        pr = raw.get("positionResolution") or {}
        slug = pr.get("marketSlug")
        at = _parse_ts(pr.get("updateTime"))
        if not slug or at is None:
            return [], None, False
        return [], Resolution(market_slug=slug, at=at), True
    if kind != ACTIVITY_TRADE:
        return [], None, True        # TRANSFER etc. — benign, nothing to score

    trade = raw.get("trade") or {}
    market = trade.get("market") or {}
    fills: list[Fill] = []
    saw_execution = False
    for side_key in ("aggressorExecution", "passiveExecution"):
        ex = trade.get(side_key)
        if not isinstance(ex, dict):
            continue                 # the feed nulls the side that is not ours
        saw_execution = True
        order = ex.get("order") or {}
        oid = order.get("id")
        px = _dec(((ex.get("lastPx") or {}).get("value")))
        shares = _dec(ex.get("lastShares"))
        at = _parse_ts(ex.get("transactTime"))
        side = str(order.get("side") or "")
        outcome = str(order.get("outcomeSide") or "")
        if not oid or px is None or shares is None or at is None \
                or "SIDE" not in side or "OUTCOME" not in outcome:
            return fills, None, False
        fills.append(Fill(
            market_slug=str(trade.get("marketSlug") or order.get("marketSlug") or ""),
            market_type=market.get("sportsMarketType"),
            game_start=_parse_ts(market.get("gameStartTime")),
            at=at,
            venue_order_id=str(oid),
            is_buy="BUY" in side,
            outcome_yes=outcome.endswith("_YES"),
            yes_price=px,
            shares=shares,
            manual="MANUAL_ORDER_INDICATOR_MANUAL" == order.get("manualOrderIndicator"),
            commission=_dec(((ex.get("commissionNotionalCollected") or {}).get("value")))
            or ZERO,
        ))
    return fills, None, saw_execution


# --------------------------------------------------------------------------- #
# Round-trip reconstruction
# --------------------------------------------------------------------------- #


@dataclass
class RoundTrip:
    market_slug: str
    market_type: str | None
    phase: str                       # 'live' | 'pregame' | 'unknown'
    direction: str                   # 'YES' | 'NO' (NO == short YES exposure)
    opened_at: dt.datetime
    closed_at: dt.datetime | None
    closed_by: str                   # 'trades' | 'settlement' | 'mixed' | 'open'
    contracts: Decimal = ZERO        # peak |exposure|
    staked: Decimal = ZERO
    returned: Decimal = ZERO
    fees_reported: Decimal = ZERO
    entering_shares: Decimal = ZERO

    @property
    def profit(self) -> Decimal:
        return self.returned - self.staked

    @property
    def roi(self) -> Decimal | None:
        return None if self.staked == 0 else self.profit / self.staked

    @property
    def entry_cost(self) -> Decimal | None:
        """Stake-weighted cost per contract — this round trip's breakeven."""
        return None if self.entering_shares == 0 else self.staked / self.entering_shares

    @property
    def win(self) -> bool:
        return self.profit > 0


def _cost_per_contract(direction_long: bool, yes_price: Decimal) -> Decimal:
    """C11: YES cost = price paid; NO (short YES) cost = 1 − price."""
    return yes_price if direction_long else ONE - yes_price


def build_round_trips(
    fills: list[Fill],
    resolutions: list[Resolution],
    settlement_lookup,
) -> tuple[list[RoundTrip], list[RoundTrip]]:
    """(closed round trips, open positions) from one account's ledger.

    ``settlement_lookup(market_slug) -> Decimal | None`` returns the YES
    payout (0 or 1) for a settled market, None when unknown. A resolution
    with an unknown payout leaves the episode OPEN rather than guessing —
    an unscored row is honest, a guessed payout is not.
    """
    by_market: dict[str, list] = {}
    for f in fills:
        by_market.setdefault(f.market_slug, []).append(("fill", f.at, f))
    for r in resolutions:
        by_market.setdefault(r.market_slug, []).append(("resolution", r.at, r))

    closed: list[RoundTrip] = []
    open_: list[RoundTrip] = []

    for slug, events in sorted(by_market.items()):
        events.sort(key=lambda e: e[1])
        net = ZERO
        trip: RoundTrip | None = None
        saw_settlement_exit = False
        saw_trade_exit = False

        def _open(f: Fill, direction_long: bool) -> RoundTrip:
            phase = "unknown"
            if f.game_start is not None:
                phase = "live" if f.at >= f.game_start else "pregame"
            return RoundTrip(
                market_slug=slug, market_type=f.market_type, phase=phase,
                direction="YES" if direction_long else "NO",
                opened_at=f.at, closed_at=None, closed_by="open",
            )

        def _close(at: dt.datetime) -> None:
            nonlocal trip, saw_settlement_exit, saw_trade_exit
            trip.closed_at = at
            trip.closed_by = (
                "mixed" if saw_settlement_exit and saw_trade_exit
                else "settlement" if saw_settlement_exit else "trades"
            )
            closed.append(trip)
            trip = None
            saw_settlement_exit = saw_trade_exit = False

        for kind, at, ev in events:
            if kind == "resolution":
                if net == 0:
                    continue
                payout = settlement_lookup(slug)
                if payout is None:
                    log.warning("hand_audit_settlement_unknown", market=slug)
                    continue         # leave open; reported unscored below
                long_side = net > 0
                per = payout if long_side else ONE - payout
                trip.returned += abs(net) * per
                trip.fees_reported += ZERO
                saw_settlement_exit = True
                net = ZERO
                _close(at)
                continue

            f: Fill = ev
            delta = f.yes_delta
            trip_fees_added = False
            # Closing part first: any portion of this fill that reduces |net|.
            if net != 0 and (delta > 0) != (net > 0):
                closing = min(abs(delta), abs(net))
                per = _cost_per_contract(net > 0, f.yes_price)
                trip.returned += closing * per
                trip.fees_reported += f.commission
                trip_fees_added = True
                saw_trade_exit = True
                net += closing if net < 0 else -closing
                delta += closing if delta < 0 else -closing
                if net == 0:
                    _close(f.at)
            # Opening part: whatever remains of the fill.
            if delta != 0:
                if trip is None:
                    trip = _open(f, delta > 0)
                per = _cost_per_contract(delta > 0, f.yes_price)
                trip.staked += abs(delta) * per
                trip.entering_shares += abs(delta)
                if not trip_fees_added:
                    trip.fees_reported += f.commission
                net += delta
                trip.contracts = max(trip.contracts, abs(net))

        if trip is not None:
            open_.append(trip)

    return closed, open_


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


@dataclass
class Bucket:
    label: str
    trips: list[RoundTrip] = field(default_factory=list)

    @property
    def staked(self) -> Decimal:
        return sum((t.staked for t in self.trips), ZERO)

    @property
    def returned(self) -> Decimal:
        return sum((t.returned for t in self.trips), ZERO)

    @property
    def roi(self) -> Decimal | None:
        return None if self.staked == 0 else (self.returned - self.staked) / self.staked

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trips if t.win)

    @property
    def entry_cost(self) -> Decimal | None:
        """Stake-weighted entry cost — the breakeven the win rate must beat."""
        shares = sum((t.entering_shares for t in self.trips), ZERO)
        return None if shares == 0 else self.staked / shares

    def summary(self) -> dict:
        n = len(self.trips)
        return {
            "label": self.label,
            "round_trips": n,
            "staked": _money(self.staked),
            "returned": _money(self.returned),
            "profit": _money(self.returned - self.staked),
            "roi": None if self.roi is None else round(float(self.roi), 4),
            "wins": self.wins,
            "win_rate": None if n == 0 else round(self.wins / n, 4),
            "entry_cost_stake_weighted": (
                None if self.entry_cost is None else round(float(self.entry_cost), 4)
            ),
            "fees_as_reported": _money(sum((t.fees_reported for t in self.trips), ZERO)),
        }


def _money(x: Decimal) -> float:
    return float(round(x, 2))


def summarize(closed: list[RoundTrip]) -> dict:
    total = Bucket("all hand round trips", list(closed))
    by_type: dict[str, Bucket] = {}
    by_phase: dict[str, Bucket] = {}
    by_cross: dict[str, Bucket] = {}
    for t in closed:
        mtype = t.market_type or "unknown"
        by_type.setdefault(mtype, Bucket(mtype)).trips.append(t)
        by_phase.setdefault(t.phase, Bucket(t.phase)).trips.append(t)
        cross = f"{mtype} · {t.phase}"
        by_cross.setdefault(cross, Bucket(cross)).trips.append(t)
    return {
        "totals": total.summary(),
        "by_market_type": [b.summary() for _, b in sorted(by_type.items())],
        "by_phase": [b.summary() for _, b in sorted(by_phase.items())],
        "by_type_and_phase": [b.summary() for _, b in sorted(by_cross.items())],
    }


# --------------------------------------------------------------------------- #
# Data acquisition
# --------------------------------------------------------------------------- #


def fetch_activities(client) -> list[dict]:
    """Walk the whole feed to eof. A few hundred events; paced (V12)."""
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        params: dict = {"limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(ACTIVITIES_PATH, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"activities HTTP {resp.status_code}: "
                               f"{resp.body_text[:200]}")
        body = json.loads(resp.body_text)
        out.extend(a for a in (body.get("activities") or []) if isinstance(a, dict))
        cursor = body.get("nextCursor")
        if body.get("eof") or not cursor:
            return out
        time.sleep(PAGE_PAUSE_SECONDS)
    log.warning("hand_audit_pagination_truncated", pages=MAX_PAGES,
                note="feed longer than MAX_PAGES; oldest activity not reached")
    return out


def button_order_ids() -> set[str]:
    """Venue order ids of every order THIS system placed — the exclusion set."""
    from sqlalchemy import text as sql
    from core.storage import get_engine

    with get_engine().connect() as c:
        rows = c.execute(sql(
            "select venue_order_id from orders where venue_order_id is not null"
        )).all()
    return {str(r[0]) for r in rows}


def _gateway_settlement(slug: str, _cache: dict = {}) -> Decimal | None:
    if slug in _cache:
        return _cache[slug]
    from core.polymarket.client import PolymarketGatewayClient

    try:
        with PolymarketGatewayClient() as gw:
            body = gw.get_settlement(slug)
        value = body.get("settlement")
        result = Decimal(value) if value in (0, 1) else None
    except Exception as exc:
        log.warning("hand_audit_settlement_fetch_failed", market=slug,
                    error=str(exc)[:120])
        result = None
    _cache[slug] = result
    return result


def run_audit(activities: list[dict], excluded_ids: set[str],
              settlement_lookup=_gateway_settlement) -> dict:
    fills: list[Fill] = []
    resolutions: list[Resolution] = []
    unparsed = 0
    excluded = 0
    non_manual_kept = 0
    for raw in activities:
        got, resolution, ok = parse_activity(raw)
        if not ok:
            unparsed += 1
            log.warning("hand_audit_unparsed_activity", type=raw.get("type"),
                        keys=sorted(raw.keys())[:10])
        if resolution:
            resolutions.append(resolution)
        for f in got:
            if f.venue_order_id in excluded_ids:
                excluded += 1
                continue
            if not f.manual:
                # Kept, and correctly so. The exclusion rule is venue id, not
                # this flag: 28 fills marked AUTOMATIC were observed spanning
                # May–August across NBA/IPL/EPL/ATP — months before this
                # system could place an order — so the indicator marks some
                # app flow, not machine trading, and is recorded here only as
                # context. If this count ever grows in step with button
                # orders, THEN revisit the exclusion set.
                non_manual_kept += 1
            fills.append(f)

    closed, open_ = build_round_trips(fills, resolutions, settlement_lookup)
    report = summarize(closed)
    report["round_trips"] = [_trip_row(t) for t in
                             sorted(closed, key=lambda t: t.opened_at)]
    report["open_positions_unscored"] = [_trip_row(t) for t in open_]
    report["provenance"] = {
        "kind": "DESCRIPTIVE AUDIT — no gate, no verdict",
        "activities_scanned": len(activities),
        "hand_fills_scored": len(fills),
        "button_fills_excluded_by_venue_order_id": excluded,
        "unparsed_activities": unparsed,
        "kept_fills_not_marked_MANUAL": non_manual_kept,
        "scoring": "C11 money-at-price: YES cost = price paid, NO cost = 1 - price; "
                   "ROI gross of fees; venue-reported commissions shown separately",
        "as_of": dt.datetime.now(UTC).isoformat(),
    }
    return report


def _trip_row(t: RoundTrip) -> dict:
    return {
        "market": t.market_slug,
        "type": t.market_type,
        "phase": t.phase,
        "direction": t.direction,
        "opened_at": t.opened_at.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "closed_by": t.closed_by,
        "contracts": float(t.contracts),
        "entry_cost": None if t.entry_cost is None else round(float(t.entry_cost), 4),
        "staked": _money(t.staked),
        "returned": _money(t.returned),
        "profit": _money(t.profit),
        "roi": None if t.roi is None else round(float(t.roi), 4),
        "win": t.win,
        "fees_as_reported": _money(t.fees_reported),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print_text(report: dict) -> None:
    p = report["provenance"]
    print("\nHAND-TRADE AUDIT — descriptive, no verdict")
    print("=" * 74)
    print(f"{p['activities_scanned']} activities · {p['hand_fills_scored']} hand fills "
          f"scored · {p['button_fills_excluded_by_venue_order_id']} button fills "
          f"excluded by venue order id")
    if p["unparsed_activities"]:
        print(f"!! {p['unparsed_activities']} unparsed activities — schema drift?")
    if p["kept_fills_not_marked_MANUAL"]:
        print(f"({p['kept_fills_not_marked_MANUAL']} kept fills carry the venue's "
              "AUTOMATIC flag — an app-flow marker, observed on obvious hand trades "
              "long before this system could order; exclusion stays by venue id)")

    def _line(s: dict) -> str:
        roi = "n/a" if s["roi"] is None else f"{s['roi']:+.1%}"
        wr = "n/a" if s["win_rate"] is None else f"{s['win_rate']:.0%}"
        be = ("n/a" if s["entry_cost_stake_weighted"] is None
              else f"{s['entry_cost_stake_weighted']:.2f}")
        return (f"{s['label']:<34} n={s['round_trips']:<3} "
                f"staked ${s['staked']:<8.2f} returned ${s['returned']:<8.2f} "
                f"ROI {roi:<8} win {wr} @ avg entry {be}")

    print("\n" + _line(report["totals"]))
    print("\nBy market type")
    for s in report["by_market_type"]:
        print("  " + _line(s))
    print("\nBy phase (trade time vs gameStartTime)")
    for s in report["by_phase"]:
        print("  " + _line(s))
    print("\nBy market type x phase")
    for s in report["by_type_and_phase"]:
        print("  " + _line(s))

    print("\nRound trips")
    for r in report["round_trips"]:
        print(f"  {r['opened_at'][:16]}  {r['market']:<34} {r['direction']:<3} "
              f"{r['phase']:<8} {r['contracts']:>7.2f}c @ {r['entry_cost'] or 0:.2f} "
              f"-> ${r['staked']:.2f} in / ${r['returned']:.2f} out "
              f"({'+' if r['profit'] >= 0 else ''}{r['profit']:.2f}, "
              f"{r['closed_by']})")
    if report["open_positions_unscored"]:
        print("\nOpen positions (not scored)")
        for r in report["open_positions_unscored"]:
            print(f"  {r['market']:<34} {r['direction']} {r['contracts']:.2f}c "
                  f"staked ${r['staked']:.2f}")
    print(f"\nFees as reported by the venue: ${report['totals']['fees_as_reported']:.2f}"
          " (not netted into ROI)")
    print(f"As of {p['as_of']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-hand-trade-audit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    import logging
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.WARNING)

    # Credentials come from .env exactly as the api container gets them.
    import core.storage  # noqa: F401  (loads .env as a side effect, like every CLI here)
    from core.polymarket.client import PolymarketAuthedClient, USCredentials

    creds = USCredentials.from_env()
    client = PolymarketAuthedClient(creds)
    try:
        activities = fetch_activities(client)
    finally:
        client.close()

    report = run_audit(activities, button_order_ids())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
