"""Every WNBA fill the operator has ever made, one row each, to a spreadsheet.

    python -m core.audit.trade_export                 # this season, CSV + xlsx
    python -m core.audit.trade_export --season 2025
    python -m core.audit.trade_export --all-seasons

**Read-only.** The venue is reached through
:class:`core.polymarket.client.PolymarketAuthedClient`, which exposes ``get``
and ``close`` and no other verb. Nothing here can place, modify or cancel an
order; there is no code path that could.

Why a spreadsheet and not another report
----------------------------------------
`core.audit.hand_trades` already scores this history — it is the module this
one extends, and every parsing and reconstruction rule below is imported from
it rather than reimplemented. But it answers *"how did the trading do"*, at the
round-trip level, and the question now is a different one: **why was each trade
taken.** That answer exists only in the operator's head, so the export ships
two empty columns, ``reason`` and ``hypothesis_tag``, for them to fill in by
hand. The annotated file is the input to the next round of pre-registered
hypotheses — which is also why the writer never overwrites (see `_stamp`).

The row set, stated exactly
---------------------------
One row per **fill**, plus one row per **settlement** that closed a position.
The settlements are not padding: most WNBA positions here ended at 0/1 rather
than by a closing trade, so a file of fills alone would carry a realized-P&L
column that silently omits how most of the money actually resolved. They are
labelled ``event_type = settlement`` and are trivially filtered out; the
counts are reported separately.

Fills from **both** sources are included — the operator's app trades and the
system's own human-confirmed button orders — with a ``source`` column
distinguishing them by venue order id, the fill watcher's attribution rule
(never by market, price, size or timing similarity). `hand_trades` excludes
button orders because it is scoring the human; this file is the account's
whole history, and a trade the operator clicked SEND on in this system is
still a trade the operator made.

Realized P&L, and where it is blank
-----------------------------------
Average cost basis within the open position, in the C11 money-at-price frame
(YES costs the price paid, NO costs 1 − price; V14). A fill that only *opens*
exposure realizes nothing and the column is blank — not zero, which would be a
claim. A fill that closes some or all of a position realizes

    closed_contracts x (proceeds_per_contract - average_cost_per_contract)

and a fill that crosses zero is split, exactly as the round-trip
reconstruction splits it: the closing part realizes, then the remainder opens
a new position in the other direction.

P&L is **gross of fees**, matching how C11 scored everything else here; the
venue's own per-execution commission is its own column and is never netted in
silently. Settlement rows carry no fee: the venue reports none on resolution.

A market whose settlement the public gateway cannot report leaves its position
open and unrealized — reported as such, never guessed.

The venue's own P&L, and an open disagreement
---------------------------------------------
The venue reports its own ``realizedPnl`` on 29 of the 94 WNBA fills, and it
is carried verbatim in ``venue_realized_pnl_usd`` alongside the two fields it
is computed from — verified on the live payload, ``realizedPnl == cost -
costBasis``.

**It does not agree with our number on any of the 29, and that is stated
rather than reconciled.** Four conventions were tested against it — FIFO and
average cost, each gross and net of the per-execution commission — and none
matches more than 3 of 29. The gap is not a rounding artifact: on the
moneyline markets it is a few cents (about the size of the fee), but on the
spread markets ours is roughly half the venue's. So the venue's ``costBasis``
is built some other way, it is undocumented, and one afternoon of guessing at
it would produce a number that looks reconciled without being understood.

Both numbers therefore ship, side by side, with their inputs. Ours is
reproducible from the rules above and matches the round-trip module it
extends; the venue's is the account's book of record. Where they differ, the
spreadsheet shows the difference instead of hiding it behind a choice — and
resolving it needs one question to the venue, not more arithmetic here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

import structlog

from core.audit.hand_trades import (
    ONE,
    ZERO,
    Fill,
    Resolution,
    _cost_per_contract,
    _gateway_settlement,
    button_order_ids,
    fetch_activities,
    parse_activity,
)
from core.paths import exports_dir
from core.team_mapping import human_market, parse_market_slug, position_label

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: The two columns the operator fills in by hand. Empty by construction: the
#: export must never pre-fill a reason, because a guessed rationale that later
#: gets promoted into a pre-registered hypothesis is how a system talks itself
#: into its own priors.
ANNOTATION_COLUMNS = ("reason", "hypothesis_tag")

COLUMNS = (
    "row",
    "event_type",           # 'fill' | 'settlement'
    "timestamp_utc",
    "game",
    "event_slug",
    "market_slug",
    "market_type",
    "line",
    "position",             # 'OVER 168.5', 'BUY NY +7.5', ...
    "game_start_utc",
    "phase",                # 'pregame' | 'live' | 'unknown'
    "side",                 # BUY | SELL | (blank on settlement)
    "outcome",              # YES | NO
    "yes_price",            # the venue's frame, verbatim
    "cost_per_contract",    # what this side actually paid/received
    "contracts",
    "opened_contracts",
    "closed_contracts",
    "stake_usd",            # cash out, on the opening part
    "proceeds_usd",         # cash in, on the closing part
    "realized_pnl_usd",     # blank unless this event closed something
    "venue_realized_pnl_usd",   # the venue's own number, for cross-checking
    "venue_cost_usd",           # and the two inputs it is computed from:
    "venue_cost_basis_usd",     #   realizedPnl == cost - costBasis (verified)
    "fees_usd",
    "position_after",       # net YES exposure once this event is applied
    "round_trip",           # per-market episode number
    "source",               # 'hand' | 'system_button'
    "venue_order_id",
    "manual_flag",          # the venue's manualOrderIndicator, as context
    *ANNOTATION_COLUMNS,
)


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #


def is_wnba(market_slug: str) -> bool:
    """WNBA by slug grammar, not by a keyword search.

    `parse_market_slug` requires `(tsc|asc|aec)-wnba-<team>-<team>-<date>` with
    both teams in the franchise table, so an NBA or tennis market cannot match
    and an unknown franchise raises rather than silently dropping out of the
    export (`UnknownTeamError` — the mapping is explicit for this reason).
    """
    return parse_market_slug(market_slug) is not None


def season_of(market_slug: str) -> int | None:
    """The WNBA season a market belongs to = the year in its slug date.

    The season runs May–October, entirely inside one calendar year, so the year
    is the season. This would need revisiting for a league that straddles New
    Year; it does not for this one.
    """
    parsed = parse_market_slug(market_slug)
    return None if parsed is None else parsed.local_date.year


def game_label(market_slug: str) -> str:
    """`NY-PHX 2026-08-05`, deliberately not `NY @ PHX`.

    Slug order does **not** reliably encode home/away — measured across 285
    closed markets, the first slug team was away 267 times and home 18 (early
    May 2026, before the venue settled its convention). An `@` here would be
    wrong for those games and unfalsifiable to a reader, so the label states
    the pair and the date and claims nothing about the venue.
    """
    parsed = parse_market_slug(market_slug)
    if parsed is None:
        return market_slug
    return (f"{parsed.first_espn}-{parsed.second_espn} "
            f"{parsed.local_date.isoformat()}")


def event_slug_of(market_slug: str) -> str:
    parsed = parse_market_slug(market_slug)
    if parsed is None:
        return ""
    return (f"wnba-{parsed.first_polymarket}-{parsed.second_polymarket}-"
            f"{parsed.local_date.isoformat()}")


def short_type(market_type: str | None) -> str:
    """`basketball_team_full_game_total` -> `total`."""
    return (market_type or "").replace("basketball_team_full_game_", "") or "unknown"


# --------------------------------------------------------------------------- #
# Per-fill reconstruction
# --------------------------------------------------------------------------- #


@dataclass
class Row:
    row: int = 0
    event_type: str = "fill"
    timestamp_utc: str = ""
    game: str = ""
    event_slug: str = ""
    market_slug: str = ""
    market_type: str = ""
    line: float | None = None
    position: str = ""
    game_start_utc: str = ""
    phase: str = "unknown"
    side: str = ""
    outcome: str = ""
    yes_price: float | None = None
    cost_per_contract: float | None = None
    contracts: float = 0.0
    opened_contracts: float = 0.0
    closed_contracts: float = 0.0
    stake_usd: float = 0.0
    proceeds_usd: float = 0.0
    realized_pnl_usd: float | None = None
    venue_realized_pnl_usd: float | None = None
    venue_cost_usd: float | None = None
    venue_cost_basis_usd: float | None = None
    fees_usd: float = 0.0
    position_after: float = 0.0
    round_trip: int = 0
    source: str = "hand"
    venue_order_id: str = ""
    manual_flag: str = ""
    reason: str = ""
    hypothesis_tag: str = ""


def _money(x: Decimal) -> float:
    return float(round(x, 4))


def _phase(at: dt.datetime, game_start: dt.datetime | None) -> str:
    if game_start is None:
        return "unknown"
    return "live" if at >= game_start else "pregame"


def _describe(fill_or_slug, market_type: str | None, line: Decimal | None,
              *, long_yes: bool) -> str:
    """The position in words, from the same helpers the picks page uses."""
    human = human_market(fill_or_slug, market_type,
                         None if line is None else float(line))
    return position_label(market_type, "YES" if long_yes else "NO", human) or human


def build_rows(
    fills: list[Fill],
    resolutions: list[Resolution],
    settlement_lookup,
    *,
    button_ids: set[str] | None = None,
) -> tuple[list[Row], dict]:
    """Fills (and the settlements that closed them) as spreadsheet rows.

    Average-cost accounting per market, walked in time order. The rules are the
    round-trip reconstruction's, one level finer: a fill that crosses zero is
    split into a closing part (which realizes) and an opening part (which does
    not), and a resolution closes whatever remains at the market's 0/1 payout.
    """
    button_ids = button_ids or set()
    by_market: dict[str, list] = {}
    for f in fills:
        by_market.setdefault(f.market_slug, []).append(("fill", f.at, f))
    for r in resolutions:
        by_market.setdefault(r.market_slug, []).append(("resolution", r.at, r))

    rows: list[Row] = []
    unresolved: list[str] = []

    for slug, events in sorted(by_market.items()):
        events.sort(key=lambda e: e[1])
        net = ZERO          # signed YES exposure
        basis = ZERO        # cost of the currently open position, >= 0
        trip = 0
        last_type: str | None = None
        last_line: Decimal | None = None
        last_start: dt.datetime | None = None

        for kind, at, ev in events:
            if kind == "resolution":
                if net == ZERO:
                    continue                     # nothing of ours was open
                payout = settlement_lookup(slug)
                if payout is None:
                    # Reported, never guessed: an unscored row is honest.
                    log.warning("trade_export_settlement_unknown", market=slug)
                    unresolved.append(slug)
                    continue
                long_yes = net > ZERO
                per = payout if long_yes else ONE - payout
                qty = abs(net)
                avg = basis / qty if qty else ZERO
                rows.append(Row(
                    event_type="settlement",
                    timestamp_utc=at.isoformat(),
                    game=game_label(slug),
                    event_slug=event_slug_of(slug),
                    market_slug=slug,
                    market_type=short_type(last_type),
                    line=None if last_line is None else float(last_line),
                    position=_describe(slug, last_type, last_line, long_yes=long_yes),
                    game_start_utc=last_start.isoformat() if last_start else "",
                    phase="settled",
                    side="",
                    outcome="YES" if long_yes else "NO",
                    yes_price=float(payout),
                    cost_per_contract=float(per),
                    contracts=float(qty),
                    closed_contracts=float(qty),
                    proceeds_usd=_money(qty * per),
                    realized_pnl_usd=_money(qty * per - basis),
                    position_after=0.0,
                    round_trip=trip,
                    source="settlement",
                ))
                net, basis = ZERO, ZERO
                continue

            f: Fill = ev
            last_type, last_line, last_start = f.market_type, f.line, f.game_start
            delta = f.yes_delta
            qty = abs(delta)

            closing = ZERO
            if net != ZERO and (delta > ZERO) != (net > ZERO):
                closing = min(qty, abs(net))
            opening = qty - closing

            realized: Decimal | None = None
            proceeds = ZERO
            stake = ZERO
            # The side being closed is the side we HELD, which on a crossing
            # fill is the opposite of the one this fill opens.
            long_before = net > ZERO
            position_long = long_before if closing else (delta > ZERO)

            if closing:
                per = _cost_per_contract(long_before, f.yes_price)
                avg = basis / abs(net)
                proceeds = closing * per
                realized = proceeds - closing * avg
                basis -= closing * avg
                net += closing if net < ZERO else -closing

            if opening:
                if net == ZERO:
                    trip += 1                    # a new episode in this market
                per = _cost_per_contract(delta > ZERO, f.yes_price)
                stake = opening * per
                basis += stake
                net += opening if delta > ZERO else -opening
                position_long = delta > ZERO
            elif net == ZERO and trip == 0:
                trip = 1                          # closed something opened pre-feed

            rows.append(Row(
                event_type="fill",
                timestamp_utc=f.at.isoformat(),
                game=game_label(slug),
                event_slug=event_slug_of(slug),
                market_slug=slug,
                market_type=short_type(f.market_type),
                line=None if f.line is None else float(f.line),
                position=_describe(slug, f.market_type, f.line,
                                   long_yes=position_long),
                game_start_utc=f.game_start.isoformat() if f.game_start else "",
                phase=_phase(f.at, f.game_start),
                side="BUY" if f.is_buy else "SELL",
                outcome="YES" if f.outcome_yes else "NO",
                yes_price=float(f.yes_price),
                cost_per_contract=float(
                    _cost_per_contract(f.outcome_yes, f.yes_price)
                ),
                contracts=float(qty),
                opened_contracts=float(opening),
                closed_contracts=float(closing),
                stake_usd=_money(stake),
                proceeds_usd=_money(proceeds),
                realized_pnl_usd=None if realized is None else _money(realized),
                venue_realized_pnl_usd=(
                    None if f.venue_realized_pnl is None
                    else _money(f.venue_realized_pnl)
                ),
                venue_cost_usd=(
                    None if f.venue_cost is None else _money(f.venue_cost)
                ),
                venue_cost_basis_usd=(
                    None if f.venue_cost_basis is None
                    else _money(f.venue_cost_basis)
                ),
                fees_usd=_money(f.commission),
                position_after=float(net),
                round_trip=trip,
                source=("system_button" if f.venue_order_id in button_ids
                        else "hand"),
                venue_order_id=f.venue_order_id,
                manual_flag="MANUAL" if f.manual else "AUTOMATIC",
            ))

    rows.sort(key=lambda r: (r.timestamp_utc, r.market_slug))
    for i, r in enumerate(rows, start=1):
        r.row = i

    fills_n = sum(1 for r in rows if r.event_type == "fill")
    stats = {
        "rows": len(rows),
        "fills": fills_n,
        "settlements": len(rows) - fills_n,
        "markets": len({r.market_slug for r in rows}),
        "games": len({r.event_slug for r in rows if r.event_slug}),
        "button_fills": sum(1 for r in rows if r.source == "system_button"),
        "markets_with_unknown_settlement": sorted(set(unresolved)),
        "realized_pnl_usd": round(
            sum(r.realized_pnl_usd or 0.0 for r in rows), 2
        ),
        # The same number restricted to fills, next to the venue's own
        # per-trade `realizedPnl` summed over those same rows. Directly
        # comparable, and a gap between them is a bug in our accounting rather
        # than a fact about the trading — "ground truth over inference", the
        # settlement rule applied one level up.
        "realized_pnl_on_fills_usd": round(
            sum(r.realized_pnl_usd or 0.0 for r in rows
                if r.event_type == "fill"), 2
        ),
        "venue_realized_pnl_usd": round(
            sum(r.venue_realized_pnl_usd or 0.0 for r in rows), 2
        ),
        "fees_as_reported_usd": round(sum(r.fees_usd for r in rows), 2),
    }
    return rows, stats


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


def _stamp(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")


def write_csv(rows: list[Row], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if v is None else v)
                             for k, v in asdict(r).items()})
    return path


def write_xlsx(rows: list[Row], path: Path) -> Path | None:
    """The same table as .xlsx, with the annotation columns wide and frozen.

    Returns None (with a warning) rather than raising when openpyxl is absent:
    the CSV is the data, the workbook is the convenience, and a missing
    optional dependency must not cost the operator the export.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        log.warning("trade_export_no_openpyxl",
                    note="pip install openpyxl for the .xlsx; the CSV is complete")
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "wnba trades"
    ws.append(list(COLUMNS))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        data = asdict(r)
        ws.append([data[c] for c in COLUMNS])

    # Freeze the header and the identifying columns so the two hand-filled
    # columns at the far right stay next to the trade they describe.
    ws.freeze_panes = "D2"
    for idx, name in enumerate(COLUMNS, start=1):
        letter = get_column_letter(idx)
        if name in ANNOTATION_COLUMNS:
            ws.column_dimensions[letter].width = 48
            for cell in ws[letter][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        elif name in ("market_slug", "position", "game", "event_slug"):
            ws.column_dimensions[letter].width = 26
        else:
            ws.column_dimensions[letter].width = 15
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    return path


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


@dataclass
class ExportResult:
    csv_path: Path
    xlsx_path: Path | None
    stats: dict
    rows: list[Row] = field(default_factory=list)


def export(
    activities: list[dict],
    *,
    season: int | None,
    button_ids: set[str] | None = None,
    settlement_lookup=_gateway_settlement,
    out_dir: Path | None = None,
    now: dt.datetime | None = None,
) -> ExportResult:
    """Activities in, spreadsheet out. Pure apart from the file write."""
    fills: list[Fill] = []
    resolutions: list[Resolution] = []
    unparsed = 0
    for raw in activities:
        got, resolution, ok = parse_activity(raw)
        if not ok:
            # Schema drift is never silently dropped — the fill watcher's rule,
            # and the reason V19 was a three-day outage instead of an alert.
            unparsed += 1
            log.warning("trade_export_unparsed_activity", type=raw.get("type"))
        if resolution and is_wnba(resolution.market_slug):
            if season is None or season_of(resolution.market_slug) == season:
                resolutions.append(resolution)
        for f in got:
            if not is_wnba(f.market_slug):
                continue
            if season is not None and season_of(f.market_slug) != season:
                continue
            fills.append(f)

    rows, stats = build_rows(fills, resolutions, settlement_lookup,
                             button_ids=button_ids)
    stats["season"] = season or "all"
    stats["activities_scanned"] = len(activities)
    stats["unparsed_activities"] = unparsed
    stats["generated_at"] = (now or dt.datetime.now(UTC)).isoformat()

    out_dir = out_dir or exports_dir()
    tag = f"season{season}" if season else "all-seasons"
    # Timestamped, never overwritten: the operator hand-annotates these files
    # and those annotations exist nowhere else. A re-run that clobbered last
    # week's reasons would destroy the only copy of the thing being built.
    base = f"wnba-trades-{tag}-{_stamp(now)}"
    csv_path = write_csv(rows, out_dir / f"{base}.csv")
    xlsx_path = write_xlsx(rows, out_dir / f"{base}.xlsx")
    return ExportResult(csv_path=csv_path, xlsx_path=xlsx_path,
                        stats=stats, rows=rows)


def _print_summary(result: ExportResult) -> None:
    s = result.stats
    print("\nWNBA TRADE EXPORT — every fill on the account, read-only")
    print("=" * 72)
    print(f"season {s['season']} · {s['activities_scanned']} activities scanned")
    if s["unparsed_activities"]:
        print(f"!! {s['unparsed_activities']} unparsed activities — schema drift?")
    print(f"{s['fills']} fills ({s['button_fills']} placed through this system's "
          f"confirm button) across {s['markets']} markets in {s['games']} games")
    print(f"{s['settlements']} settlement rows · {s['rows']} rows total")
    print(f"realized P&L (gross of fees) ${s['realized_pnl_usd']:,.2f} · "
          f"fees as reported ${s['fees_as_reported_usd']:,.2f}")
    # Our arithmetic against the venue's own, over the same rows. A gap is our
    # bug, not a finding about the trading.
    gap = s["realized_pnl_on_fills_usd"] - s["venue_realized_pnl_usd"]
    print(f"  cross-check on fills: ours ${s['realized_pnl_on_fills_usd']:,.2f} "
          f"vs the venue's own ${s['venue_realized_pnl_usd']:,.2f} "
          f"({'agrees' if abs(gap) < 0.05 else f'DIFFERS by ${gap:,.2f}'})")
    if abs(gap) >= 0.05:
        print("  the venue's costBasis convention is undocumented and is not "
              "ours (FIFO and average\n  cost, gross and net of fee, all fail "
              "to reproduce it). Both numbers are in the\n  sheet with their "
              "inputs — see the module docstring. Unresolved on purpose.")
    if s["markets_with_unknown_settlement"]:
        print("\nunscored — the gateway could not report a settlement "
              "(left open, never guessed):")
        for slug in s["markets_with_unknown_settlement"]:
            print(f"  {slug}")
    print(f"\ncsv   {result.csv_path}")
    print(f"xlsx  {result.xlsx_path if result.xlsx_path else '(openpyxl not installed)'}")
    print("\nThe `reason` and `hypothesis_tag` columns are deliberately empty. "
          "Fill them in;\nre-running writes a NEW timestamped file and never "
          "touches this one.\n")


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-trade-export")
    parser.add_argument("--season", type=int, default=None,
                        help="WNBA season (default: the current one)")
    parser.add_argument("--all-seasons", action="store_true",
                        help="every WNBA fill ever, not just one season")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.WARNING)
    import core.storage  # noqa: F401  loads .env, like every CLI here
    from core.polymarket.client import PolymarketAuthedClient, USCredentials

    season = None if args.all_seasons else (args.season or dt.date.today().year)

    client = PolymarketAuthedClient(USCredentials.from_env())
    try:
        activities = fetch_activities(client)
    finally:
        client.close()

    try:
        button_ids = button_order_ids()
    except Exception as exc:
        # The database is not required to export the venue's own history; the
        # only casualty is the hand/button split, and saying so beats failing.
        log.warning("trade_export_no_button_ids", error=str(exc)[:160],
                    note="every fill will be labelled 'hand'")
        button_ids = set()

    result = export(activities, season=season, button_ids=button_ids,
                    out_dir=args.out_dir)
    if args.json:
        print(json.dumps({**result.stats,
                          "csv": str(result.csv_path),
                          "xlsx": str(result.xlsx_path or "")}, indent=2))
    else:
        _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
