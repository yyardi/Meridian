"""The schedule pings: the day's slate, and one warning per game as it tips."""
from __future__ import annotations

import datetime as dt
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
GS = importlib.import_module("scripts.game_schedule")
SRC = pathlib.Path(GS.__file__).read_text(encoding="utf-8")

NOW = dt.datetime(2026, 9, 19, 14, 0, tzinfo=dt.timezone.utc)


def _g(game, mins, rungs=30, league="cfb"):
    return {"game": game, "league": league, "rungs": rungs,
            "tip": NOW + dt.timedelta(minutes=mins)}


def test_the_slate_groups_by_league_and_says_how_far_off_each_game_is():
    body = GS.compose([_g("cfb-a-b", 120), _g("cfb-c-d", 300),
                       _g("nfl-e-f", 60, league="nfl")], NOW)[1]
    assert "CFB (2)" in body and "NFL (1)" in body
    assert "16:00Z  +2.0h" in body, "UTC clock and hours-from-now, for a phone abroad"
    assert "cfb-a-b" in body and "nfl-e-f" in body


def test_a_game_already_under_way_reads_as_live_not_as_a_negative_countdown():
    body = GS.compose([_g("cfb-a-b", -40)], NOW)[1]
    assert "live" in body and "-" not in body.split("live")[0].split("Z")[-1]


def test_thin_ladders_are_counted_but_not_named():
    """Three rungs is three pairs. Listing them would bury the real games on a
    49-game morning."""
    games = [_g("cfb-real", 60, rungs=30), _g("cfb-thin", 90, rungs=2)]
    title, body = GS.compose(games, NOW)
    assert "cfb-real" in body and "cfb-thin" not in body
    assert "1 thin" in body and title.endswith("1 games")


def test_an_empty_board_says_so_rather_than_sending_an_empty_list():
    title, body = GS.compose([], NOW)
    assert "no ladder" in title.lower() and body


def test_the_tipoff_message_counts_minutes_and_names_one_game_or_many():
    title, body = GS.compose_tipoff([_g("cfb-a-b", 12)], NOW)
    assert title == "Starting soon: cfb-a-b" and "in 12m" in body and "14:12Z" in body
    title2, _ = GS.compose_tipoff([_g("cfb-a-b", 12), _g("cfb-c-d", 9)], NOW)
    assert title2 == "Starting soon: 2 games"


def test_a_game_is_pinged_once_ever_and_the_memory_is_the_file(tmp_path):
    """Cron runs this every few minutes; the process cannot remember, so the
    file must."""
    p = str(tmp_path / "pinged.txt")
    assert GS.already_pinged("cfb-a-b", p) is False, "a missing file is not an error"
    GS.mark_pinged("cfb-a-b", p)
    assert GS.already_pinged("cfb-a-b", p) is True
    assert GS.already_pinged("cfb-c-d", p) is False, "one game does not silence another"
    GS.mark_pinged("cfb-a-b", p)
    assert pathlib.Path(p).read_text().count("cfb-a-b") == 2, "append is fine; the read dedupes"


def test_the_tipoff_window_is_forward_only():
    """A live game is not 'starting soon'. Without this a five-minute cron
    would ping a game that started an hour ago, every five minutes, until it
    ended -- which is the spam this replaced."""
    body = SRC[SRC.index("if a.starting_within is not None:"):]
    assert 'g["tip"] > now' in body
    assert "mark_pinged" in body and "already_pinged" in body
    assert "if result == notify.SENT" in body, "a failed push is retried, not recorded"


def test_it_sends_through_the_one_door_and_never_reads_the_topic_itself():
    assert "notify.push(" in SRC
    assert "MERIDIAN_NTFY_TOPIC" not in SRC and "ntfy.sh" not in SRC
    assert '"schedule"' in SRC, "its own kind, so it can be muted without muting tickets"
