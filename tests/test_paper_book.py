"""The SCOREBOARD page renders the paper book; it never recomputes it.

`cfb/run_paper_book.py` prints two fixed-width tables — per strategy x week,
then ALL WEEKS with a verdict — and a cron leaves that output under the reads
directory. `core/paper_book.py` finds the newest file and parses it;
`/api/paper-book` serves the result with the file's timestamp. Every number
on the page is the producer's, so the parser's job is fidelity: the sample
below is the producer's own format strings evaluated on made-up inputs, and a
line the parser does not recognise must surface, not vanish.

No database anywhere in here: `pytest --noconftest tests/test_paper_book.py`.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.paper_book import (
    ALL_WEEKS_COLUMNS,
    LEGEND,
    WEEKLY_COLUMNS,
    latest_paper_book,
    league_of,
    parse_paper_book,
    reads_dir,
    verdict_kind,
)

#: The producer's stdout for a small run. Built with its own print statements
#: (widths, signs, the `G<25` flag, a one-game week's infinite interval, an
#: unsettled-only week, a strategy with no markets on tape), then saved here
#: verbatim so a drift in the producer's format is visible in a diff.
SAMPLE = """cfb: 1,234 markets with a pregame close, 88 games
wnba: 410 markets with a pregame close, 36 games

strategy                  week          bets games unsettled  staked $    P&L $   net/$1    95% CI on mean bet (c)
cfb_spread_no_20_30       2026-09-07      41    30         2        31    +1.87   +0.060     +4.56 [-5.14, +14.26]
cfb_spread_no_20_30       2026-08-31      12     9         0         9    -0.62   -0.069     -5.17 [-19.41, +9.07]  G<25
nfl_spread_no_20_30       2026-09-07       0     0         7
mlb_total_under_all       -                0   no markets on tape
wnba_total_under_all      2026-08-24       1     1         0         1    +0.10   +0.125       +12.50 [-inf, +inf]  G<25

strategy, ALL WEEKS         bets games  staked $    P&L $   net/$1    95% CI on mean bet (c)   verdict
cfb_spread_no_20_30           53    39        40    +1.25   +0.031      +2.36 [+0.35, +4.37]   POSITIVE, excludes 0
wnba_spread_yes_80_100        30    22        25    -2.10   -0.083     -8.27 [-11.27, -5.27]   UNDERPOWERED (G<25)
wnba_total_under_all         120    60        60    -9.80   -0.162   -16.20 [-20.30, -12.10]   NEGATIVE, excludes 0
cfb_spread_home_all          300    88       150    +3.30   +0.022      +2.20 [-3.30, +7.70]   spans 0

P&L is per $1-contract bets, taker fee charged, venue-settled. A positive line becomes a candidate
at G >= 25 AND excludes 0 AND its home/away twin does not contradict it; nothing here is sized or armed.
"""

STATIC = Path(__file__).resolve().parent.parent / "static"
PAGES = ["index.html", "quote.html", "wallet.html", "analytics.html", "scoreboard.html"]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def book():
    return parse_paper_book(SAMPLE)


# ------------------------------------------------------------------ #
# The parser
# ------------------------------------------------------------------ #


def test_both_tables_parse_completely(book):
    assert [r["strategy"] for r in book["weekly"]["rows"]] == [
        "cfb_spread_no_20_30", "cfb_spread_no_20_30", "nfl_spread_no_20_30",
        "mlb_total_under_all", "wnba_total_under_all"]
    assert [r["strategy"] for r in book["all_weeks"]["rows"]] == [
        "cfb_spread_no_20_30", "wnba_spread_yes_80_100",
        "wnba_total_under_all", "cfb_spread_home_all"]
    assert book["unparsed"] == [], "every table line in the sample has a known shape"
    assert book["weekly"]["columns"] == WEEKLY_COLUMNS
    assert book["all_weeks"]["columns"] == ALL_WEEKS_COLUMNS


def test_a_full_week_row_carries_every_field_as_printed(book):
    r = book["weekly"]["rows"][0]
    assert r == {
        "strategy": "cfb_spread_no_20_30", "league": "cfb", "week": "2026-09-07",
        "bets": 41, "games": 30, "unsettled": 2, "staked": 31,
        "pnl": 1.87, "net_per_dollar": 0.060,
        "ci": "+4.56 [-5.14, +14.26]", "ci_mean": 4.56, "ci_lo": -5.14, "ci_hi": 14.26,
        "underpowered": False, "note": None,
    }
    assert book["weekly"]["rows"][1]["underpowered"] is True, "the trailing G<25 flag"


def test_partial_week_rows_keep_their_note_and_no_invented_numbers(book):
    unsettled, none = book["weekly"]["rows"][2], book["weekly"]["rows"][3]
    assert (unsettled["week"], unsettled["bets"], unsettled["games"],
            unsettled["unsettled"]) == ("2026-09-07", 0, 0, 7)
    assert unsettled["note"] == "unsettled only"
    assert none["note"] == "no markets on tape" and none["week"] is None
    for r in (unsettled, none):
        assert r["pnl"] is None and r["ci"] is None and r["staked"] is None, (
            "a week the producer did not score must not show a zero P&L")


def test_an_infinite_interval_is_null_in_json_and_verbatim_in_text(book):
    r = book["weekly"]["rows"][4]
    assert r["ci"] == "+12.50 [-inf, +inf]"
    assert r["ci_mean"] == 12.5 and r["ci_lo"] is None and r["ci_hi"] is None


def test_the_all_weeks_row_and_its_verdict(book):
    r = book["all_weeks"]["rows"][2]
    assert r == {
        "strategy": "wnba_total_under_all", "league": "wnba",
        "bets": 120, "games": 60, "staked": 60, "pnl": -9.80, "net_per_dollar": -0.162,
        "ci": "-16.20 [-20.30, -12.10]", "ci_mean": -16.2, "ci_lo": -20.3, "ci_hi": -12.1,
        "verdict": "NEGATIVE, excludes 0", "verdict_kind": "negative",
    }
    assert [r["verdict_kind"] for r in book["all_weeks"]["rows"]] == [
        "positive", "underpowered", "negative", "spans"]


@pytest.mark.parametrize("verdict,kind", [
    ("POSITIVE, excludes 0", "positive"),
    ("NEGATIVE, excludes 0", "negative"),
    ("UNDERPOWERED (G<25)", "underpowered"),
    ("spans 0", "spans"),
    ("something new", "unknown"),
])
def test_verdict_kinds_are_the_producers_four_strings(verdict, kind):
    assert verdict_kind(verdict) == kind


def test_league_is_the_strategy_name_prefix():
    assert league_of("cfb_spread_no_20_30") == "cfb"
    assert league_of("wnba_total_under_all") == "wnba"


def test_preamble_and_footer_travel_with_the_tables(book):
    assert book["preamble"] == ["cfb: 1,234 markets with a pregame close, 88 games",
                                "wnba: 410 markets with a pregame close, 36 games"]
    assert len(book["footer"]) == 2 and book["footer"][0].startswith("P&L is per")
    assert "nothing here is sized or armed" in book["footer"][1]
    assert "legend" not in book, "the page's one-line LEGEND is the endpoint's, not the file's"


def test_an_unrecognised_table_line_is_reported_not_dropped():
    drifted = SAMPLE.replace(
        "cfb_spread_home_all          300    88       150    +3.30   +0.022      +2.20 [-3.30, +7.70]   spans 0",
        "cfb_spread_home_all          300    88       150    +3.30   +0.022   sharpe 0.4   spans 0")
    book = parse_paper_book(drifted)
    assert len(book["all_weeks"]["rows"]) == 3
    assert book["unparsed"] == [
        "cfb_spread_home_all          300    88       150    +3.30   +0.022   sharpe 0.4   spans 0"]


# ------------------------------------------------------------------ #
# Finding the file
# ------------------------------------------------------------------ #


def test_the_newest_paper_book_by_mtime_wins(tmp_path):
    older = tmp_path / "paper_book_2026-09-07.txt"
    newer = tmp_path / "paper_book_2026-09-01.txt"     # older-looking name, newer bytes
    other = tmp_path / "2026-09-13T1020Z-gate.txt"      # a weekend read, not a book
    for p in (older, newer, other):
        p.write_text(SAMPLE)
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))
    os.utime(other, (1_700_000_200, 1_700_000_200))
    assert latest_paper_book(tmp_path) == newer


def test_absent_directory_or_no_matching_file_is_none(tmp_path):
    assert latest_paper_book(tmp_path / "missing") is None
    (tmp_path / "notes.txt").write_text("x")
    assert latest_paper_book(tmp_path) is None


def test_reads_dir_is_the_env_override_else_the_prod_default(monkeypatch):
    monkeypatch.delenv("MERIDIAN_READS_DIR", raising=False)
    assert reads_dir() == Path("/opt/meridian/artifacts/reads")
    monkeypatch.setenv("MERIDIAN_READS_DIR", "/somewhere/else")
    assert reads_dir() == Path("/somewhere/else")


# ------------------------------------------------------------------ #
# The endpoint and the page
# ------------------------------------------------------------------ #


def test_endpoint_says_no_paper_book_yet_in_one_line(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path))
    d = client.get("/api/paper-book").json()
    assert d["available"] is False
    assert d["note"].startswith("no paper book yet")
    assert "\n" not in d["note"]
    assert "all_weeks" not in d, "no empty tables that could read as a zero book"


def test_endpoint_serves_the_latest_book_with_its_timestamp(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_READS_DIR", str(tmp_path))
    path = tmp_path / "paper_book_2026-09-14T1020Z.txt"
    path.write_text(SAMPLE)
    os.utime(path, (1_757_800_800, 1_757_800_800))
    d = client.get("/api/paper-book").json()
    assert d["available"] is True
    assert d["file"] == path.name
    assert d["generated_at"] == dt.datetime.fromtimestamp(
        1_757_800_800, dt.timezone.utc).isoformat()
    assert d["legend"] == LEGEND
    assert d["footer"][1].endswith("nothing here is sized or armed.")
    assert [r["verdict_kind"] for r in d["all_weeks"]["rows"]] == [
        "positive", "underpowered", "negative", "spans"]
    assert d["weekly"]["rows"][4]["ci_hi"] is None, "inf must not reach JSON"


def test_scoreboard_page_is_served_and_every_header_links_to_it(client):
    r = client.get("/scoreboard")
    assert r.status_code == 200 and "SCOREBOARD" in r.text
    for page in PAGES:
        assert 'href="/scoreboard"' in (STATIC / page).read_text(), page


def test_scoreboard_page_carries_the_legend_and_loads_no_library():
    html = (STATIC / "scoreboard.html").read_text()
    assert "nothing is armed" in html and "taker fee charged" in html
    assert "<script src=" not in html, "no charts, no libraries"
    for kind in ("vpositive", "vnegative", "vspans", "vunderpowered"):
        assert f".{kind}" in html, "each verdict kind has a colour rule"
