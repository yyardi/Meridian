"""Kalshi non-sports recorder: the venue's shape against saved payloads, and
the loop driven with a stub client and a stub session. No DB, no network:

    pytest --noconftest tests/test_kalshi_events_recorder.py

Fixtures are trimmed copies of real `GET /events?with_nested_markets=true`
responses (2026-09-13/14): tennis (two player legs, 1c grid), weather
(less/between strikes, one-sided legs) and KXNEWPOPE (the tapered deci-cent
grid, and `strike_type` absent — a case the design note's six-value list did
not contain).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pytest
import structlog
from sqlalchemy.dialects import postgresql

from core.kalshi import events_recorder as rec
from core.kalshi import events_shape as sh

FIX = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc
#: 8.5h before the tennis match, 13 days before its close_time.
NOW = dt.datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
CFG = sh.KalshiEventsConfig(series=("KXITFWMATCH",), window_hours=24.0, grace_hours=2.0,
                            depth=False, snapshot_raw=False, coverage=True)


def _load(name: str) -> dict:
    with open(FIX / f"kalshi_events_{name}.json") as fh:
        return json.load(fh)


def _event(name: str) -> tuple[dict, list[dict]]:
    """(event, its markets) from a saved nested-events payload."""
    event = _load(name)["events"][0]
    return event, event["markets"]


# --------------------------------------------------------------- the anchor #
def test_the_poll_anchor_is_the_match_not_the_two_week_close_time():
    """The defect this design avoids, stated as a test.

    On KXITFWMATCH `close_time` is the postponement backstop: +330h across the
    open board. A window hung on it opens thirteen days after the match.
    """
    _, markets = _event("tennis")
    leg = markets[0]
    close = sh._parse_ts(leg["close_time"])
    anchor = sh.poll_anchor(leg)
    assert anchor == dt.datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    assert close == dt.datetime(2026, 9, 28, 2, 30, tzinfo=UTC)
    assert close - anchor == dt.timedelta(hours=330)
    # In the window this recorder uses, and NOT in the close_time one.
    assert sh.in_window(anchor, NOW, CFG) is True
    assert sh.in_window(close, NOW, CFG) is False


def test_weather_anchors_on_close_time_because_it_is_the_earlier_field():
    """The same rule, the other way round: trading stops 14h before expiry."""
    _, markets = _event("weather")
    leg = markets[0]
    assert sh.poll_anchor(leg) == sh._parse_ts(leg["close_time"])
    assert sh._parse_ts(leg["expected_expiration_time"]) > sh.poll_anchor(leg)


@pytest.mark.parametrize("offset_hours,expected", [
    (-48.0, False),   # a day before the window opens
    (-23.0, True),    # inside W
    (-0.01, True),    # moments before the anchor
    (1.0, True),      # inside the grace: a delayed match stays on tape
    (3.0, False),     # past the grace
])
def test_the_window_is_anchor_minus_w_to_anchor_plus_grace(offset_hours, expected):
    anchor = dt.datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    now = anchor + dt.timedelta(hours=offset_hours)
    assert sh.in_window(anchor, now, CFG) is expected


def test_a_market_with_neither_time_is_never_polled():
    """Not "polled forever": an anchor we cannot compute is not a window."""
    assert sh.poll_anchor({}) is None
    assert sh.in_window(None, NOW, CFG) is False


# ------------------------------------------------------------ the allowlist #
@pytest.mark.parametrize("raw,expected", [
    ("KXRAIN", ("KXRAIN",)),
    ("kxrain, KXBTCD ,,KXRAIN", ("KXRAIN", "KXBTCD")),     # case, blanks, dupes
    ("  ", sh.DEFAULT_SERIES),                             # empty falls back, loudly
])
def test_series_allowlist_parsing(raw, expected):
    assert sh.series_allowlist(raw) == expected


def test_an_unset_allowlist_is_the_pre_registered_targets_not_nothing():
    """An allowlist defaulting to EMPTY would make a compose typo read exactly
    like a quiet venue."""
    saved = os.environ.pop("KALSHI_SERIES", None)
    try:
        assert sh.series_allowlist() == sh.DEFAULT_SERIES
        assert "KXITFWMATCH" in sh.DEFAULT_SERIES and "KXBTC15M" in sh.DEFAULT_SERIES
    finally:
        if saved is not None:
            os.environ["KALSHI_SERIES"] = saved


def test_only_allowlisted_series_are_swept():
    client = _Client({"KXITFWMATCH": _load("tennis"), "KXHIGHNY": _load("weather")})
    recorder = _recorder(client, sh.KalshiEventsConfig(series=("KXITFWMATCH",),
                                                       coverage=False))
    recorder.run_once(NOW)
    assert client.swept == ["KXITFWMATCH"]


# -------------------------------------------------------- change detection #
def test_change_detection_returns_false_on_identical_payloads():
    event, markets = _event("tennis")
    first = sh.price_row(event, markets[0], NOW)
    later = sh.price_row(event, markets[0], NOW + dt.timedelta(minutes=1))
    assert sh.changed(None, first, sh._PRICE_KEYS) is True     # nothing seen yet
    assert sh.changed(first, later, sh._PRICE_KEYS) is False   # same payload, new instant
    moved = sh.price_row(event, {**markets[0], "yes_bid_dollars": "0.8600"}, later["captured_at"])
    assert sh.changed(first, moved, sh._PRICE_KEYS) is True


def test_terms_ignore_price_moves_and_prices_ignore_rules_edits():
    event, markets = _event("tennis")
    base = sh.terms_row(event, markets[0], NOW)
    repriced = sh.terms_row(event, {**markets[0], "yes_bid_dollars": "0.0100"}, NOW)
    assert sh.changed(base, repriced, sh._TERMS_KEYS) is False
    retermed = sh.terms_row(event, {**markets[0], "rules_primary": "edited"}, NOW)
    assert sh.changed(base, retermed, sh._TERMS_KEYS) is True


def test_a_fee_change_alone_earns_a_snapshot_row():
    """The fee moves on a still book; a price-only rule would drop it."""
    event, markets = _event("tennis")
    free = sh.price_row(event, markets[0], NOW, fees={"fee_type": "quadratic", "fee_multiplier": 1})
    charged = sh.price_row(event, markets[0], NOW,
                           fees={"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1})
    assert free["yes_bid"] == charged["yes_bid"]
    assert sh.changed(free, charged, sh._PRICE_KEYS) is True


# ------------------------------------------------------------- carry-through #
@pytest.mark.parametrize("name,expected", [
    ("tennis", ["structured", "structured"]),
    ("weather", ["less", "between", "between"]),
    ("tapered", [None, None]),   # the venue leaves it unset; NOT one of the six
])
def test_strike_type_is_carried_through_verbatim(name, expected):
    event, markets = _event(name)
    rows = [sh.terms_row(event, m, NOW) for m in markets]
    assert [r["strike_type"] for r in rows] == expected


def test_strikes_survive_as_exact_decimals_including_a_between_band():
    event, markets = _event("weather")
    band = sh.terms_row(event, markets[1], NOW)
    assert (band["floor_strike"], band["cap_strike"]) == (Decimal(78), Decimal(79))
    assert band["yes_sub_title"] == "78° to 79°"


def test_mutually_exclusive_is_carried_because_a_ladder_leg_is_not_a_binary():
    event, markets = _event("weather")
    assert sh.terms_row(event, markets[0], NOW)["mutually_exclusive"] is True


# ------------------------------------------------------------- the tick grid #
def test_a_tick_grid_that_is_not_one_cent():
    """KXNEWPOPE is tapered_deci_cent: 0.0010 at the edges, 0.0100 in the
    middle. A threshold that assumed 1c would be wrong by a factor of ten
    exactly where the longshots live."""
    event, markets = _event("tapered")
    row = sh.terms_row(event, markets[0], NOW)
    assert row["price_level_structure"] == "tapered_deci_cent"
    assert row["min_tick"] == Decimal("0.0010")
    assert [r["step"] for r in row["price_ranges"]] == ["0.0010", "0.0100", "0.0010"]
    # ...and the grid itself is stored verbatim, not just its minimum.
    assert row["price_ranges"][1] == {"start": "0.1000", "end": "0.9000", "step": "0.0100"}


def test_the_common_grid_is_one_cent_and_says_so():
    event, markets = _event("tennis")
    row = sh.terms_row(event, markets[0], NOW)
    assert (row["price_level_structure"], row["min_tick"]) == ("linear_cent", Decimal("0.0100"))


def test_a_market_with_no_grid_has_no_min_tick_rather_than_a_guessed_one():
    assert sh.min_tick({}) is None
    assert sh.min_tick({"price_ranges": [{"step": "0"}]}) is None


# ------------------------------------------------ two legs, and no names #
def test_a_tennis_event_is_two_markets_and_the_pairing_needs_no_name():
    """YES on one leg is NO on the other: four tradeable positions, ONE
    statistic. The identity is the ticker suffix plus the venue's own
    competitor id — never the title, which is a bare surname."""
    event, markets = _event("tennis")
    rows = [sh.terms_row(event, m, NOW) for m in markets]
    assert len(rows) == 2
    assert {r["event_ticker"] for r in rows} == {"KXITFWMATCH-26SEP13LEYSUN"}
    assert [r["ticker_suffix"] for r in rows] == ["LEY", "SUN"]
    ids = [r["custom_strike"]["tennis_competitor"] for r in rows]
    assert len(set(ids)) == 2
    # The trap: the event title's name slots are bare surnames.
    assert rows[0]["event_title"] == "Leykina vs Sun"
    assert all(len(part.split()) == 1 for part in rows[0]["event_title"].split(" vs "))


@pytest.mark.parametrize("ticker,event_ticker,expected", [
    ("KXITFWMATCH-26SEP13LEYSUN-LEY", "KXITFWMATCH-26SEP13LEYSUN", "LEY"),
    # A strike-shaped suffix: "last dash segment" would still work here, but
    # the event-ticker prefix is what makes it right by construction.
    ("KXBTCD-26SEP1402-T67099.99", "KXBTCD-26SEP1402", "T67099.99"),
    ("KXHIGHNY-26SEP13-B78.5", "KXHIGHNY-26SEP13", "B78.5"),
    ("KXRAIN-26SEP13", "KXRAIN-26SEP13", None),      # the event itself, no leg
])
def test_ticker_suffix_is_the_remainder_after_the_event_ticker(ticker, event_ticker, expected):
    assert sh.ticker_suffix(ticker, event_ticker) == expected


# ------------------------------------------------------------ the leg gate #
def test_the_leg_bounds_of_a_healthy_pair_straddle_one():
    _, markets = _event("tennis")
    bid_sum, ask_sum, mid_sum, tick = sh.leg_bounds(markets)
    assert (bid_sum, ask_sum) == (Decimal("0.98"), Decimal("1.01"))
    assert bid_sum <= 1 <= ask_sum        # no arbitrage: the gate is quiet
    assert mid_sum == Decimal("0.995") and tick == Decimal("0.0100")


def test_the_gate_is_no_arbitrage_not_mids_summing_to_one():
    """The rule this replaced, stated as the measurement that killed it.

    The mid sum floats inside the bid/ask band, so it is NOT required to be 1.
    A mid-sum rule at `legs x tick` broke on 9 of the 71 two-sided
    mutually-exclusive events open on 2026-09-14; the no-arbitrage rule broke
    on 1. This is the widest of those nine, and it is a healthy quote.
    """
    _, markets = _event("tennis")
    wide = [{**markets[0], "yes_bid_dollars": "0.7000", "yes_ask_dollars": "0.8500"},
            {**markets[1], "yes_bid_dollars": "0.1000", "yes_ask_dollars": "0.2000"}]
    bid_sum, ask_sum, mid_sum, tick = sh.leg_bounds(wide)
    assert abs(mid_sum - 1) > 2 * tick    # a mid-sum rule would have fired...
    assert bid_sum <= 1 <= ask_sum        # ...on a quote with no arbitrage in it


@pytest.mark.parametrize("bids,asks,side", [
    (("0.9000", "0.1500"), ("0.9200", "0.1700"), "sell_all"),   # bid_sum 1.05 > 1
    (("0.5000", "0.2000"), ("0.5200", "0.2200"), "buy_all"),    # ask_sum 0.74 < 1
])
def test_the_gate_fires_on_a_leg_sum_that_cannot_be_right(bids, asks, side):
    """The control must be able to fail, on both sides."""
    _, markets = _event("tennis")
    broken = [{**m, "yes_bid_dollars": b, "yes_ask_dollars": a}
              for m, b, a in zip(markets, bids, asks)]
    bid_sum, ask_sum, _, tick = sh.leg_bounds(broken)
    fired = "sell_all" if bid_sum > 1 + tick else "buy_all" if ask_sum < 1 - tick else None
    assert fired == side


def test_a_one_sided_leg_makes_the_sum_unavailable_rather_than_wrong():
    """Weather legs quote ask 0.0100 at size 0 — a price nobody is offering."""
    _, markets = _event("weather")
    assert any(m["yes_bid_size_fp"] == "0.00" for m in markets)
    assert sh.leg_bounds(markets) is None


# ----------------------------------------------------------------- the loop #
class _Session:
    """Enough session for the inserts; no database."""

    stmts: ClassVar[list] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt):
        self.stmts.append(stmt)
        return self

    def commit(self):
        pass


class _Client:
    def __init__(self, boards: dict[str, dict], fee: str = "quadratic",
                 expected: int | None = None) -> None:
        self._boards = boards
        self._fee = fee
        self._expected = expected
        self.swept: list[str] = []
        self.fee_calls = 0

    def iter_events(self, series, *, status="open", with_nested_markets=False):
        assert with_nested_markets is True and status == "open"
        self.swept.append(series)
        return iter((self._boards.get(series) or {"events": []})["events"])

    def get_series(self, series):
        self.fee_calls += 1
        return {"fee_type": self._fee, "fee_multiplier": 1}

    def count_series_markets(self, series, *, status="open"):
        if self._expected is not None:
            return self._expected
        return sum(len(e.get("markets") or [])
                   for e in (self._boards.get(series) or {"events": []})["events"])


def _recorder(client, config=None):
    _Session.stmts = []
    recorder = rec.KalshiEventsRecorder.__new__(rec.KalshiEventsRecorder)
    recorder.config = config or CFG
    recorder._client = client
    recorder._Session = _Session
    recorder._heartbeat = None
    recorder._prices, recorder._terms, recorder._fees = {}, {}, {}
    return recorder


def _rows(table: str) -> list[dict]:
    out = []
    for stmt in _Session.stmts:
        params = stmt.compile(dialect=postgresql.dialect()).params
        if stmt.table.name == table:
            out.append(params)
    return out


def test_run_once_writes_the_in_window_markets_and_then_stops_repeating():
    client = _Client({"KXITFWMATCH": _load("tennis")})
    recorder = _recorder(client)
    first = recorder.run_once(NOW)
    assert (first.events, first.markets, first.in_window) == (1, 2, 2)
    assert (first.snapshots, first.terms, first.errors) == (2, 2, 0)
    assert len(_rows("kalshi_event_snapshots")) == 2
    assert {r["market_ticker"] for r in _rows("kalshi_events")} == {
        "KXITFWMATCH-26SEP13LEYSUN-LEY", "KXITFWMATCH-26SEP13LEYSUN-SUN"}

    _Session.stmts = []
    second = recorder.run_once(NOW + dt.timedelta(minutes=1))
    assert (second.snapshots, second.terms) == (0, 0)   # same payload, nothing written
    assert _Session.stmts == []


def test_a_market_outside_its_window_is_counted_and_not_written():
    """KXNEWPOPE closes in 2070: swept, seen, and deliberately not recorded."""
    client = _Client({"KXNEWPOPE": _load("tapered")})
    recorder = _recorder(client, sh.KalshiEventsConfig(series=("KXNEWPOPE",), coverage=False))
    stats = recorder.run_once(NOW)
    assert (stats.markets, stats.in_window, stats.snapshots) == (2, 0, 0)
    assert stats.past_anchor == 0     # ahead of its anchor, not behind it


def test_every_snapshot_row_carries_the_series_fee_regime():
    client = _Client({"KXITFWMATCH": _load("tennis")}, fee="quadratic_with_maker_fees")
    recorder = _recorder(client)
    recorder.run_once(NOW)
    rows = _rows("kalshi_event_snapshots")
    assert rows and all(r["fee_type"] == "quadratic_with_maker_fees" for r in rows)
    assert all(r["fee_multiplier"] == Decimal(1) for r in rows)
    # Re-read every cycle, never resolved once.
    recorder.run_once(NOW + dt.timedelta(minutes=1))
    assert client.fee_calls == 2


def test_a_fee_transition_is_logged_loudly_and_written():
    client = _Client({"KXITFWMATCH": _load("tennis")})
    recorder = _recorder(client)
    recorder.run_once(NOW)
    client._fee = "quadratic_with_maker_fees"
    _Session.stmts = []
    with structlog.testing.capture_logs() as logs:
        stats = recorder.run_once(NOW + dt.timedelta(minutes=1))
    assert stats.fee_changes == 1
    assert any(entry["event"] == "kalshi_events_fee_changed" for entry in logs)
    assert stats.snapshots == 2      # the fee moved, so the rows moved


def test_the_leg_gate_runs_on_a_complete_ladder_and_logs_the_break():
    board = _load("tennis")
    board["events"][0]["markets"][1] = {**board["events"][0]["markets"][1],
                                        "yes_bid_dollars": "0.4000",
                                        "yes_ask_dollars": "0.4200"}
    recorder = _recorder(_Client({"KXITFWMATCH": board}))
    with structlog.testing.capture_logs() as logs:
        stats = recorder.run_once(NOW)
    assert (stats.legs_checked, stats.leg_breaks) == (1, 1)
    break_line = next(e for e in logs if e["event"] == "kalshi_events_leg_sum_break")
    assert break_line["suffixes"] == ["LEY", "SUN"]
    assert break_line["event_ticker"] == "KXITFWMATCH-26SEP13LEYSUN"
    assert break_line["side"] == "sell_all" and break_line["bid_sum"] == "1.2500"


def test_the_leg_gate_does_not_fire_on_a_healthy_board():
    """The other half of the control: it has to be quiet when nothing is wrong."""
    recorder = _recorder(_Client({"KXITFWMATCH": _load("tennis")}))
    stats = recorder.run_once(NOW)
    assert (stats.legs_checked, stats.leg_breaks) == (1, 0)
    # The mid deviation is still REPORTED — a number to read, not a boolean.
    assert stats.worst_leg_dev == Decimal("0.005")


def test_the_gate_skips_a_ladder_the_window_cut_in_half():
    """A partial sum is a guaranteed break — it would fire on OUR window
    rather than on the venue, which is the false alarm that gets a check
    muted."""
    board = _load("tennis")
    board["events"][0]["markets"][1] = {**board["events"][0]["markets"][1],
                                        "close_time": "2070-01-01T00:00:00Z",
                                        "expected_expiration_time": "2070-01-01T00:00:00Z"}
    recorder = _recorder(_Client({"KXITFWMATCH": board}))
    stats = recorder.run_once(NOW)
    assert (stats.in_window, stats.legs_checked, stats.leg_breaks) == (1, 0, 0)


# -------------------------------------------------------------- coverage #
def test_coverage_reports_expected_versus_observed_per_series():
    recorder = _recorder(_Client({"KXITFWMATCH": _load("tennis")}))
    with structlog.testing.capture_logs() as logs:
        recorder.run_once(NOW)
    line = next(e for e in logs if e["event"] == "kalshi_events_coverage")
    assert (line["series"], line["expected"], line["observed"]) == ("KXITFWMATCH", 2, 2)
    assert line["shortfall"] == 0
    assert line["endpoints_disagree"] is False and line["swept_nothing"] is False


def test_closed_legs_inside_an_open_event_are_counted_not_called_a_shortfall():
    """`status=open` filters EVENTS, not their nested MARKETS: KXRAIN's open
    event carried 8 closed legs beside 36 active ones. Comparing the raw
    nested count to /markets made every weather cycle read as a disagreement,
    which is how a real check gets muted."""
    board = _load("tennis")
    board["events"][0]["markets"][1] = {**board["events"][0]["markets"][1], "status": "closed"}
    # /markets?status=open sees only the active one.
    recorder = _recorder(_Client({"KXITFWMATCH": board}, expected=1))
    with structlog.testing.capture_logs() as logs:
        recorder.run_once(NOW)
    line = next(e for e in logs if e["event"] == "kalshi_events_coverage")
    assert (line["observed"], line["active"], line["closed"]) == (2, 1, 1)
    assert line["shortfall"] == 0 and line["endpoints_disagree"] is False


def test_coverage_flags_a_series_the_other_endpoint_says_is_bigger():
    """The check must be able to fail: /markets says 9, the sweep found 2."""
    recorder = _recorder(_Client({"KXITFWMATCH": _load("tennis")}, expected=9))
    with structlog.testing.capture_logs() as logs:
        recorder.run_once(NOW)
    line = next(e for e in logs if e["event"] == "kalshi_events_coverage")
    assert (line["expected"], line["observed"], line["shortfall"]) == (9, 2, 7)
    assert line["endpoints_disagree"] is True


def test_coverage_flags_an_allowlisted_series_the_venue_has_nothing_under():
    recorder = _recorder(_Client({}), sh.KalshiEventsConfig(series=("KXTYPO",)))
    with structlog.testing.capture_logs() as logs:
        recorder.run_once(NOW)
    line = next(e for e in logs if e["event"] == "kalshi_events_coverage")
    assert line["swept_nothing"] is True and line["observed"] == 0


def test_one_failing_series_does_not_lose_the_sweep():
    class _Broken(_Client):
        def iter_events(self, series, *, status="open", with_nested_markets=False):
            if series == "KXBOOM":
                raise RuntimeError("venue said no")
            return super().iter_events(series, status=status,
                                       with_nested_markets=with_nested_markets)

    client = _Broken({"KXITFWMATCH": _load("tennis")})
    recorder = _recorder(client, sh.KalshiEventsConfig(series=("KXBOOM", "KXITFWMATCH"),
                                                       coverage=False))
    stats = recorder.run_once(NOW)
    assert stats.errors == 1 and stats.snapshots == 2


# ------------------------------------------------------------------ drift #
def test_the_new_container_is_in_the_health_check():
    health = (ROOT / "scripts" / "health.py").read_text(encoding="utf-8")
    assert "meridian-kalshi-events-recorder" in health


def test_the_compose_overlay_upgrades_before_it_records():
    """A recorder that starts before its tables exist crash-loops."""
    overlay = (ROOT / "docker-compose.kalshi-events.yml").read_text(encoding="utf-8")
    assert "alembic upgrade head && python -m core.kalshi.events" in overlay
    assert "container_name: meridian-kalshi-events-recorder" in overlay


# ------------------------------------------------- migration vs the models #
def _migration_tables() -> dict[str, dict[str, str]]:
    """Column name -> rendered Postgres type, as the MIGRATION declares them.

    `op` is swapped for a recorder, so `upgrade()` runs with no database and
    no alembic context. This is a SECOND route to the same schema: the models
    were written by hand and so was the migration, and either could have
    gained a column the other never got.
    """
    import importlib
    import sys

    sys.path.insert(0, str(ROOT / "alembic" / "versions"))
    try:
        module = importlib.import_module("c2d9a7e51f83_add_kalshi_events")
    finally:
        sys.path.pop(0)

    tables: dict[str, dict[str, str]] = {}

    class _Op:
        @staticmethod
        def create_table(name, *cols, **kwargs):
            tables[name] = {c.name: str(c.type.compile(postgresql.dialect()))
                            for c in cols if hasattr(c, "name") and hasattr(c, "type")}

        @staticmethod
        def create_index(*args, **kwargs):
            pass

    original, module.op = module.op, _Op()
    try:
        module.upgrade()
    finally:
        module.op = original
    return tables


@pytest.mark.parametrize("table,model_name", [
    ("kalshi_events", "KalshiEvent"),
    ("kalshi_event_snapshots", "KalshiEventSnapshot"),
])
def test_the_migration_and_the_model_declare_the_same_columns(table, model_name):
    from core.storage import models

    migration = _migration_tables()[table]
    orm = {c.name: str(c.type.compile(postgresql.dialect()))
           for c in getattr(models, model_name).__table__.columns}
    assert set(migration) == set(orm)
    assert migration == orm


def test_the_migration_chains_onto_the_head_it_was_written_against():
    """Guessing a down_revision forks the chain silently."""
    import sys

    sys.path.insert(0, str(ROOT / "alembic" / "versions"))
    try:
        import c2d9a7e51f83_add_kalshi_events as migration
    finally:
        sys.path.pop(0)
    assert migration.down_revision == "b6e4d2f7a913"
    assert (ROOT / "alembic" / "versions" /
            "b6e4d2f7a913_add_espn_cricket_events.py").exists()
