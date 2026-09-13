"""MLB ladder calibration: the away/home split and the venue-settled collection.

No database and no network: `collect_mlb` takes a connection-like object and a
`settlement` callable, so both can be faked.
"""
from __future__ import annotations

import datetime as dt

import pytest

from cfb.run_ladder_calibration import (MLB_SHORT, MLB_TYPES, away_side,
                                        bucket, collect_mlb, main)

UTC = dt.timezone.utc
SPREAD = "baseball_team_full_game_spread"
F5SPREAD = "baseball_team_first_five_spread"


@pytest.mark.parametrize("slug, mtype, want", [
    ("asc-mlb-col-det-2026-09-13-pos-1pt5", SPREAD, "away_dog"),
    ("asc-mlb-col-det-2026-09-13-neg-1pt5", SPREAD, "away_fav"),
    ("asc-mlb-col-det-2026-09-13-pos-2pt5", SPREAD, "away_dog"),
    ("asc-mlb-col-det-2026-09-13-neg-2pt5", F5SPREAD, "away_fav"),
    # no twin exists for these, so there is no split to report
    ("tsc-mlb-col-det-2026-09-13-8pt5", "baseball_team_full_game_total", "-"),
    ("aec-mlb-col-det-2026-09-13", "baseball_team_full_game_winner", "-"),
])
def test_the_split_is_read_off_the_slug(slug, mtype, want):
    assert away_side(slug, mtype) == want


def test_a_team_code_containing_pos_or_neg_does_not_flip_the_side():
    """Token match, not substring: a containment test is how 'Washington' once
    paired against 'Washington State'."""
    assert away_side("asc-mlb-posx-negy-2026-09-13-neg-1pt5", SPREAD) == "away_fav"
    assert away_side("asc-mlb-posx-negy-2026-09-13-pos-1pt5", SPREAD) == "away_dog"


def test_a_spread_slug_with_neither_token_is_unsplit_not_guessed():
    assert away_side("asc-mlb-col-det-2026-09-13-1pt5", SPREAD) == "-"


def test_first_five_is_a_market_type_in_its_own_right():
    assert F5SPREAD in MLB_TYPES and "baseball_team_first_five_total" in MLB_TYPES
    assert MLB_SHORT[F5SPREAD] == "f5_spread"
    assert len(set(MLB_SHORT.values())) == len(MLB_TYPES), "short names must be distinct"


class _Row:
    def __init__(self, d): self._mapping = d


class _Conn:
    """Returns the games query first, then one close query per game."""
    def __init__(self, games, closes):
        self._games, self._closes, self._n = games, closes, 0

    def execute(self, _stmt, params=None):
        if self._n == 0:
            self._n = 1
            return [_Row(g) for g in self._games]
        return [_Row(r) for r in self._closes.get(params["vg"], [])]


def _close(slug, mtype, mid_, line=1.5, mins=30):
    ko = dt.datetime(2026, 9, 13, 23, 0, tzinfo=UTC)
    return dict(market_slug=slug, sports_market_type=mtype, line=line,
                bid=mid_ - 0.01, ask=mid_ + 0.01,
                captured_at=ko - dt.timedelta(minutes=mins), game_start_time=ko)


def _fixture():
    ko = dt.datetime(2026, 9, 13, 23, 0, tzinfo=UTC)
    games = [dict(vg=1, ko=ko, event_slug="mlb-col-det-2026-09-13")]
    closes = {1: [_close("asc-mlb-col-det-2026-09-13-neg-1pt5", SPREAD, 0.55),
                  _close("asc-mlb-col-det-2026-09-13-pos-1pt5", SPREAD, 0.45),
                  _close("tsc-mlb-col-det-2026-09-13-8pt5",
                         "baseball_team_full_game_total", 0.50)]}
    return _Conn(games, closes), games


def test_an_unsettled_market_is_skipped_and_counted_never_guessed():
    conn, _ = _fixture()
    rows, games, unsettled, no_quote = collect_mlb(
        conn, lambda slug: 1 if slug.endswith("neg-1pt5") else None)
    assert len(rows) == 1 and unsettled == 2 and no_quote == 0
    assert rows[0]["y"] == 1 and rows[0]["side"] == "away_fav"


def test_every_row_carries_its_side_and_league():
    conn, _ = _fixture()
    rows, *_ = collect_mlb(conn, lambda _s: 0)
    assert {r["side"] for r in rows} == {"away_fav", "away_dog", "-"}
    assert {r["lg"] for r in rows} == {"mlb"}
    assert all(r["ttk_min"] == pytest.approx(30.0) for r in rows)


def test_a_game_with_no_pregame_quote_is_counted_not_dropped_silently():
    ko = dt.datetime(2026, 9, 13, 23, 0, tzinfo=UTC)
    conn = _Conn([dict(vg=9, ko=ko, event_slug="mlb-a-b-2026-09-13")], {})
    rows, games, unsettled, no_quote = collect_mlb(conn, lambda _s: 1)
    assert rows == [] and len(games) == 1 and no_quote == 1


def test_settlement_is_asked_once_per_market():
    conn, _ = _fixture()
    seen = []
    collect_mlb(conn, lambda s: (seen.append(s), 1)[1])
    assert len(seen) == len(set(seen)) == 3


def test_an_unknown_league_fails_loudly(monkeypatch):
    monkeypatch.setenv("LEAGUE", "nhl")
    with pytest.raises(SystemExit, match="nhl"):
        main()


@pytest.mark.parametrize("mid_, want", [(0.02, 0), (0.55, 5), (0.99, 9), (1.0, 9)])
def test_the_top_bucket_is_closed_so_a_mid_of_one_is_not_a_tenth_bucket(mid_, want):
    assert bucket(mid_) == want
