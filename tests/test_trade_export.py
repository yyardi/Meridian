"""The per-fill WNBA export: what each row claims, and what it refuses to.

The export is the input to the operator's hand-written `reason` column, and
those annotations become pre-registered hypotheses. So the arithmetic under it
has to be the audit's arithmetic (C11 money-at-price, V14 YES frame), one level
finer — per fill rather than per round trip — and the places it cannot compute
a number have to stay **blank** rather than zero. A zero is a claim.
"""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal

import pytest

from core.audit.hand_trades import Fill, Resolution
from core.audit.trade_export import (
    COLUMNS,
    build_rows,
    export,
    game_label,
    is_wnba,
    season_of,
    write_csv,
    write_xlsx,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 6, 22, 0, tzinfo=UTC)
TIP = dt.datetime(2026, 8, 6, 23, 0, tzinfo=UTC)

WNBA = "tsc-wnba-ny-phx-2026-08-06-168pt5"
NBA = "tsc-nba-bos-lal-2026-01-06-220pt5"


def _fill(minutes, *, buy, yes, px, shares, slug=WNBA, oid="H1",
          mtype="basketball_team_full_game_total", start=TIP, manual=True,
          commission="0", line="168.5"):
    return Fill(
        market_slug=slug, market_type=mtype, game_start=start,
        at=T0 + dt.timedelta(minutes=minutes), venue_order_id=oid,
        is_buy=buy, outcome_yes=yes,
        yes_price=Decimal(str(px)), shares=Decimal(str(shares)),
        manual=manual, commission=Decimal(commission),
        line=None if line is None else Decimal(str(line)),
    )


def _no_settlement(_slug):
    raise AssertionError("settlement must not be consulted here")


# ------------------------------------------------------------------ #
# Scope: WNBA, this season, and nothing else
# ------------------------------------------------------------------ #


def test_wnba_filter_is_slug_grammar_not_a_keyword():
    assert is_wnba(WNBA)
    assert not is_wnba(NBA)
    assert not is_wnba("some-tennis-market")
    assert not is_wnba("")


def test_season_is_the_year_in_the_slug():
    assert season_of(WNBA) == 2026
    assert season_of("tsc-wnba-ny-phx-2025-06-01-160pt5") == 2025
    assert season_of(NBA) is None


def test_game_label_does_not_claim_home_and_away():
    """Slug order encoded away/home 267 times and home/away 18 — an `@` would
    be silently wrong for the early-May games."""
    label = game_label(WNBA)
    assert label == "NY-PHX 2026-08-06"
    assert "@" not in label


def test_export_drops_other_leagues_and_other_seasons(tmp_path):
    acts = [_trade_activity(WNBA), _trade_activity(NBA)]
    result = export(acts, season=2026, settlement_lookup=lambda _s: None,
                    out_dir=tmp_path)
    assert result.stats["fills"] == 1
    assert {r.market_slug for r in result.rows} == {WNBA}

    result_2025 = export(acts, season=2025, settlement_lookup=lambda _s: None,
                         out_dir=tmp_path)
    assert result_2025.stats["fills"] == 0


def _trade_activity(slug: str) -> dict:
    """A venue activity in the shape observed live (V19 + 2026-08-07)."""
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": slug,
            "market": {"sportsMarketType": "basketball_team_full_game_total",
                       "gameStartTime": TIP.isoformat().replace("+00:00", "Z"),
                       "line": "168.5"},
            "aggressorExecution": None,
            "passiveExecution": {
                "order": {"id": "H1", "side": "ORDER_SIDE_BUY",
                          "outcomeSide": "OUTCOME_SIDE_YES",
                          "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL"},
                "lastPx": {"value": "0.30"},
                "lastShares": "10",
                "transactTime": T0.isoformat().replace("+00:00", "Z"),
                "commissionNotionalCollected": {"value": "0.05"},
            },
        },
    }


# ------------------------------------------------------------------ #
# Per-fill P&L, in the C11 frame
# ------------------------------------------------------------------ #


def test_opening_fill_realizes_nothing_and_says_so_with_a_blank():
    """Blank, not 0.00. A zero would assert that the trade broke even."""
    rows, _ = build_rows([_fill(0, buy=True, yes=True, px=0.30, shares=10)],
                         [], _no_settlement)
    assert len(rows) == 1
    assert rows[0].realized_pnl_usd is None
    assert rows[0].stake_usd == pytest.approx(3.0)
    assert rows[0].opened_contracts == 10
    assert rows[0].closed_contracts == 0
    assert rows[0].position_after == 10


def test_closing_fill_realizes_against_average_cost():
    """Buy 10 YES at 0.30, sell at 0.50: $3 in, $5 out, +$2 on the sell."""
    rows, stats = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=10),
        _fill(30, buy=False, yes=True, px=0.50, shares=10),
    ], [], _no_settlement)
    assert rows[0].realized_pnl_usd is None
    assert rows[1].realized_pnl_usd == pytest.approx(2.0)
    assert rows[1].proceeds_usd == pytest.approx(5.0)
    assert rows[1].position_after == 0
    assert stats["realized_pnl_usd"] == pytest.approx(2.0)


def test_average_cost_is_used_across_two_entries():
    """5 at 0.20 and 5 at 0.40 average 0.30; selling all 10 at 0.50 makes $2."""
    rows, _ = build_rows([
        _fill(0, buy=True, yes=True, px=0.20, shares=5),
        _fill(10, buy=True, yes=True, px=0.40, shares=5),
        _fill(20, buy=False, yes=True, px=0.50, shares=10),
    ], [], _no_settlement)
    assert rows[2].realized_pnl_usd == pytest.approx(2.0)


def test_partial_close_realizes_only_the_part_closed():
    rows, _ = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=10),
        _fill(10, buy=False, yes=True, px=0.50, shares=4),
    ], [], _no_settlement)
    assert rows[1].closed_contracts == 4
    assert rows[1].realized_pnl_usd == pytest.approx(0.8)   # 4 x (0.50-0.30)
    assert rows[1].position_after == 6


def test_no_side_is_scored_at_one_minus_price():
    """V14: the venue prices everything in the YES frame, so buying NO at a
    reported 0.80 stakes 0.20 per contract. Selling it back at a reported 0.60
    returns 0.40 — a $2 gain on 10 contracts, not a $2 loss."""
    rows, _ = build_rows([
        _fill(0, buy=True, yes=False, px=0.80, shares=10),
        _fill(30, buy=False, yes=False, px=0.60, shares=10),
    ], [], _no_settlement)
    assert rows[0].stake_usd == pytest.approx(2.0)
    assert rows[0].cost_per_contract == pytest.approx(0.20)
    assert rows[1].realized_pnl_usd == pytest.approx(2.0)


def test_a_fill_that_crosses_zero_is_split():
    """Long 10, sell 15: 10 close the long and 5 open a short. The row records
    both halves, and the realized number covers only the closing part."""
    rows, _ = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=10),
        _fill(10, buy=False, yes=True, px=0.50, shares=15),
    ], [], _no_settlement)
    crossing = rows[1]
    assert crossing.closed_contracts == 10
    assert crossing.opened_contracts == 5
    assert crossing.realized_pnl_usd == pytest.approx(2.0)
    assert crossing.position_after == -5
    # The new short opened at 1 - 0.50 = 0.50/contract.
    assert crossing.stake_usd == pytest.approx(2.5)
    assert crossing.round_trip == 2


def test_settlement_closes_the_position_and_carries_the_pnl():
    """Most positions here end at 0/1 rather than by a closing trade. Without
    a settlement row the P&L column would silently omit how they resolved."""
    rows, stats = build_rows(
        [_fill(0, buy=True, yes=True, px=0.30, shares=10)],
        [Resolution(market_slug=WNBA, at=T0 + dt.timedelta(hours=3))],
        lambda _s: Decimal("1"),
    )
    assert [r.event_type for r in rows] == ["fill", "settlement"]
    assert rows[1].realized_pnl_usd == pytest.approx(7.0)   # $10 back on $3
    assert rows[1].position_after == 0
    assert stats["fills"] == 1 and stats["settlements"] == 1


def test_unknown_settlement_leaves_the_position_open_and_reports_it():
    rows, stats = build_rows(
        [_fill(0, buy=True, yes=True, px=0.30, shares=10)],
        [Resolution(market_slug=WNBA, at=T0 + dt.timedelta(hours=3))],
        lambda _s: None,
    )
    assert [r.event_type for r in rows] == ["fill"]
    assert stats["markets_with_unknown_settlement"] == [WNBA]
    assert stats["realized_pnl_usd"] == 0.0


def test_fees_are_reported_never_netted_into_pnl():
    rows, stats = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=10, commission="0.05"),
        _fill(30, buy=False, yes=True, px=0.50, shares=10, commission="0.07"),
    ], [], _no_settlement)
    assert stats["fees_as_reported_usd"] == pytest.approx(0.12)
    assert rows[1].realized_pnl_usd == pytest.approx(2.0)   # gross, per C11


# ------------------------------------------------------------------ #
# Attribution and labels
# ------------------------------------------------------------------ #


def test_button_orders_are_labelled_by_venue_order_id_only():
    """The fill watcher's attribution rule. Never by market, price or timing —
    the operator hand-trades the same markets at similar prices."""
    rows, stats = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=1, oid="OURS"),
        _fill(1, buy=True, yes=True, px=0.30, shares=1, oid="THEIRS"),
    ], [], _no_settlement, button_ids={"OURS"})
    assert [r.source for r in rows] == ["system_button", "hand"]
    assert stats["button_fills"] == 1


def test_manual_flag_is_recorded_but_is_not_the_filter():
    """28 obvious hand fills carry the venue's AUTOMATIC flag (May-August,
    months before this system could order), so it is context, not a filter."""
    rows, stats = build_rows(
        [_fill(0, buy=True, yes=True, px=0.3, shares=1, manual=False)],
        [], _no_settlement)
    assert rows[0].manual_flag == "AUTOMATIC"
    assert rows[0].source == "hand"
    assert stats["fills"] == 1


def test_position_is_labelled_the_way_the_picks_page_labels_it():
    rows, _ = build_rows([
        _fill(0, buy=True, yes=True, px=0.30, shares=1),
        _fill(1, buy=True, yes=False, px=0.70, shares=1,
              slug="tsc-wnba-ny-phx-2026-08-06-170pt5"),
    ], [], _no_settlement)
    by_slug = {r.market_slug: r for r in rows}
    assert by_slug[WNBA].position == "OVER 168.5"
    assert by_slug["tsc-wnba-ny-phx-2026-08-06-170pt5"].position == "UNDER 168.5"


def test_phase_splits_on_the_venue_reported_tipoff():
    rows, _ = build_rows([
        _fill(-30, buy=True, yes=True, px=0.3, shares=1),   # before TIP
        _fill(90, buy=False, yes=True, px=0.4, shares=1),   # after TIP
    ], [], _no_settlement)
    assert [r.phase for r in rows] == ["pregame", "live"]


# ------------------------------------------------------------------ #
# The files themselves
# ------------------------------------------------------------------ #


def test_csv_has_the_empty_annotation_columns(tmp_path):
    rows, _ = build_rows([_fill(0, buy=True, yes=True, px=0.3, shares=1)],
                         [], _no_settlement)
    path = write_csv(rows, tmp_path / "t.csv")
    with path.open() as fh:
        data = list(csv.DictReader(fh))
    assert list(data[0].keys()) == list(COLUMNS)
    assert data[0]["reason"] == ""
    assert data[0]["hypothesis_tag"] == ""
    # Blank, not "None": a spreadsheet cell reading None is a value.
    assert data[0]["realized_pnl_usd"] == ""


def test_xlsx_is_written_with_the_same_columns(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    rows, _ = build_rows([_fill(0, buy=True, yes=True, px=0.3, shares=1)],
                         [], _no_settlement)
    path = write_xlsx(rows, tmp_path / "t.xlsx")
    assert path is not None and path.exists()
    ws = openpyxl.load_workbook(path).active
    assert [c.value for c in ws[1]] == list(COLUMNS)
    assert ws.max_row == 2


def test_export_never_overwrites_an_annotated_file(tmp_path):
    """The operator's `reason` column exists nowhere else. A re-run that
    clobbered last week's file would destroy the only copy."""
    acts = [_trade_activity(WNBA)]
    now = dt.datetime(2026, 8, 17, 18, 0, tzinfo=UTC)
    first = export(acts, season=2026, settlement_lookup=lambda _s: None,
                   out_dir=tmp_path, now=now)
    second = export(acts, season=2026, settlement_lookup=lambda _s: None,
                    out_dir=tmp_path,
                    now=now + dt.timedelta(seconds=1))
    assert first.csv_path != second.csv_path
    assert first.csv_path.exists() and second.csv_path.exists()


def test_export_defaults_under_the_one_artifact_root(monkeypatch, tmp_path):
    """`core/` may not invent a new top-level folder — `MERIDIAN_DATA_DIR` is
    the one root (docs/infra/artifact-paths.md)."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path))
    result = export([_trade_activity(WNBA)], season=2026,
                    settlement_lookup=lambda _s: None)
    assert result.csv_path.parent == tmp_path / "exports"
