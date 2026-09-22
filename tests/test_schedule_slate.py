"""The daily scheduler: the board in, the day's launches out, no hands.

    pytest --noconftest tests/test_schedule_slate.py

For three days the launches were typed into cron by hand; on the third day
they were not, and NFL Sunday ran for 82 minutes with nothing recording.
These pin the rules the scheduler encodes, on a fixture shaped like that
Sunday: eight games at 17:00Z, two at 20:05Z, three at 20:25Z, one at
00:20Z the next day, plus a WNBA game and an MLB game.
"""
from __future__ import annotations

import datetime as dt
import importlib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
SS = importlib.import_module("scripts.schedule_slate")

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 20, 12, 10, tzinfo=UTC)


def _g(game, league, tip, rungs=42):
    return {"game": f"{league}-{game}-2026-09-20", "league": league, "tip": tip, "rungs": rungs}


def _t(h, m, day=20):
    return dt.datetime(2026, 9, day, h, m, tzinfo=UTC)


SUNDAY = (
    [_g(f"a{i}-b{i}", "nfl", _t(17, 0)) for i in range(8)]
    + [_g("jax-den", "nfl", _t(20, 5)), _g("lv-lac", "nfl", _t(20, 5))]
    + [_g("mia-sf", "nfl", _t(20, 25)), _g("sea-ari", "nfl", _t(20, 25)), _g("was-dal", "nfl", _t(20, 25))]
    + [_g("ind-kc", "nfl", _t(0, 20, day=21))]
    + [_g("atl-ny", "wnba", _t(23, 0), rungs=9), _g("tor-tex", "mlb", _t(23, 5), rungs=5)]
)


def _by(p, script):
    return [l for l in p.launches if l.script == script]


def test_every_game_with_a_ladder_gets_the_stream_detector_two_minutes_before_tip():
    p = SS.plan(SUNDAY, NOW)
    dets = _by(p, "launch_stream_exec.sh")
    assert len(dets) == 16, "14 NFL + WNBA + MLB"
    for l in dets:
        slug = l.args.split()[0]
        g = next(x for x in SUNDAY if f"aec-{x['game']}" == slug)
        assert l.at == g["tip"] - dt.timedelta(minutes=SS.LEAD_MIN)
        assert l.args.endswith(f"{SS.FLOOR_USD} {SS.FRESH_S}"), "the measured floor and gate"


def test_a_thin_ladder_is_not_scheduled():
    p = SS.plan([_g("x-y", "cfb", _t(16, 0), rungs=3)], NOW)
    assert p.launches == [] and p.skipped == []


def test_rest_executors_are_capped_per_kickoff_bucket_and_two_carry_the_comparator():
    """Five REST clients ran cleanly on 2026-09-19; the live recorder holds
    twelve of the venue's twenty requests a second. The cap is per kickoff
    slot, so the 17:00 wave and the 20:05 wave each get their own three."""
    p = SS.plan(SUNDAY, NOW)
    rest = _by(p, "launch_ladder.sh")
    at17 = [l for l in rest if l.at == _t(16, 58)]
    at20 = [l for l in rest if l.at in (_t(20, 3), _t(20, 23))]
    assert len(at17) == SS.REST_PER_BUCKET, "eight games at 17:00, three REST"
    assert sum(l.args.endswith(" ws") for l in at17) == SS.WS_PER_BUCKET
    assert len(at20) == SS.REST_PER_BUCKET, "20:05 and 20:25 share one 90-minute slot"
    assert not any("wnba" in l.args or "mlb" in l.args for l in rest), "REST is football only"


def test_basketball_and_baseball_get_the_sampler_not_the_executor():
    p = SS.plan(SUNDAY, NOW)
    samp = _by(p, "launch_sampler.sh")
    assert sorted(l.args.split()[0] for l in samp) == ["aec-mlb-tor-tex-2026-09-20", "aec-wnba-atl-ny-2026-09-20"]


def test_the_recorder_windows_group_kickoffs_within_three_hours():
    p = SS.plan(SUNDAY, NOW)
    rec = [l for l in _by(p, "launch_stream_slate.sh") if l.args.startswith("nfl ")]
    assert len(rec) == 2, "17:00 through 20:25 is one window; 00:20 next day is another"
    first, second = sorted(rec, key=lambda l: l.at)
    assert first.at == _t(16, 50) and second.at == _t(0, 10, day=21)
    mins = int(first.args.split()[1])
    assert mins == int((_t(20, 25) + dt.timedelta(minutes=230) - _t(16, 50)).total_seconds() // 60), \
        "the window runs until the LAST game in it should be over"
    assert re.fullmatch(r"nfl \d+ nfl-\d{8}", first.args), first.args


def test_the_verdict_runs_after_the_last_game_and_the_clean_at_the_next_0800():
    p = SS.plan(SUNDAY, NOW)
    last_over = _t(0, 20, day=21) + dt.timedelta(minutes=230)
    assert p.verdict_at == last_over + dt.timedelta(minutes=SS.VERDICT_AFTER_MIN)
    assert _by(p, "slate_verdict.sh")[0].at == p.verdict_at
    assert p.clean_at == dt.datetime(2026, 9, 21, 8, 0, tzinfo=UTC)


def test_a_verdict_after_0700_pushes_the_clean_to_the_following_day():
    late = [_g("x-y", "cfb", _t(3, 30, day=21))]
    p = SS.plan(late, NOW)
    assert p.verdict_at == _t(3, 30, day=21) + dt.timedelta(minutes=230 + SS.VERDICT_AFTER_MIN)
    assert p.clean_at == dt.datetime(2026, 9, 22, 8, 0, tzinfo=UTC), \
        "the 08:00 an hour after the verdict would race it; take the next one"


def test_a_game_whose_launch_time_is_past_is_named_not_dropped_and_not_launched():
    """Cron cannot fire in the past. A mid-slate run must say what it could
    not cover rather than silently schedule nothing for it."""
    p = SS.plan(SUNDAY, _t(17, 30))
    assert not any(l.at <= _t(17, 30) for l in p.launches)
    assert len(p.skipped) >= 8 and all("already past" in s for s in p.skipped)
    assert any("a0-b0" in s for s in p.skipped)


def test_the_cron_block_is_five_field_lines_tagged_temp_with_a_self_removing_clean():
    p = SS.plan(SUNDAY, NOW)
    block = SS.cron_block(p, "/opt/meridian/scripts/launchers", "/opt/meridian/artifacts/reads")
    lines = [l for l in block.splitlines() if l and not l.startswith("#")]
    for l in lines[:-1]:
        f = l.split()
        assert f[4] == "*" and all(x.isdigit() for x in f[:4]), l
        assert "# TEMP" in l and ">> /opt/meridian/artifacts/reads/cron.log 2>&1" in l, l
        assert "sudo -n /opt/meridian/scripts/launchers/launch_" in l \
            or "sudo -n /opt/meridian/scripts/launchers/slate_verdict.sh" in l, l
    clean = lines[-1]
    assert clean.startswith("0 8 21 9 * crontab -l | grep -v") and "TEMP" in clean, \
        "the self-clean carries the word TEMP inside its quotes and so removes itself"
    ind = next(l for l in lines if "ind-kc" in l and "stream_exec" in l)
    assert ind.split()[:4] == ["18", "0", "21", "9"], "a next-day game gets the next day's date"


def test_the_plan_is_ordered_by_time_and_deterministic():
    p1, p2 = SS.plan(SUNDAY, NOW), SS.plan(list(reversed(SUNDAY)), NOW)
    assert [l.at for l in p1.launches] == sorted(l.at for l in p1.launches)
    assert p1.launches == p2.launches, "input order does not change the plan"


def test_the_slug_comes_from_the_dated_key_not_the_phone_s_short_game_name():
    """The board query returns `game` without its date for the phone and
    `key` with it for the launchers. A dry run against the live board on
    2026-09-21 built `aec-mlb-tor-bal` from `game`; the recorder has never
    heard of that slug and every launch would have found zero rungs."""
    row = {"game": "mlb-tor-bal", "key": "mlb-tor-bal-2026-09-21", "league": "mlb",
           "tip": _t(22, 35), "rungs": 5}
    p = SS.plan([row], NOW)
    slugs = {l.args.split()[0] for l in p.launches if l.script != "launch_stream_slate.sh"
             and l.script != "slate_verdict.sh"}
    assert slugs == {"aec-mlb-tor-bal-2026-09-21"}
    # A fixture row with only a dated `game` (no key) still works.
    p2 = SS.plan([dict(row, key=None, game="mlb-tor-bal-2026-09-21")], NOW)
    assert {l.args.split()[0] for l in p2.launches if "launch_s" in l.script and "slate" not in l.script} \
        == {"aec-mlb-tor-bal-2026-09-21"}


def test_the_window_runs_to_the_next_noon_utc_not_a_fixed_span():
    """A fixed 26 h from a 19:41Z run reached the next afternoon's baseball
    and pushed Monday Night Football's verdict to the following evening."""
    assert SS.hours_until(dt.datetime(2026, 9, 21, 12, 10, tzinfo=UTC), 12) == 23 + 50 / 60
    assert SS.hours_until(dt.datetime(2026, 9, 21, 19, 41, tzinfo=UTC), 12) == 16 + 19 / 60
    assert SS.hours_until(dt.datetime(2026, 9, 21, 11, 30, tzinfo=UTC), 12) == 24.5, \
        "a noon less than an hour away is this run's own boundary; go to the next"
    assert SS.hours_until(dt.datetime(2026, 9, 21, 3, 0, tzinfo=UTC), 12) == 9.0


def test_the_host_wrapper_drops_only_temp_lines_and_never_runs_without_a_plan():
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "schedule_slate.sh").read_text()
    assert 'grep -v "TEMP"' in src
    assert 'grep -q "^[0-9]"' in src, "an empty block installs nothing"
    assert "set -euo pipefail" in src
    assert "docker run" in src and "schedule_slate.py" in src
    # It runs under sudo, and a bare `crontab -` under sudo edits ROOT's
    # crontab: the first real run put the day's block there while the
    # pings and its own line lived in ubuntu's, so the night would have
    # launched twice. Both the read and the write must name the user.
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert 'crontab -u "$CRON_USER" -l' in code and '| crontab -u "$CRON_USER" -' in code
    assert "| crontab -\n" not in code and "| crontab - " not in code, "never the bare form"
    assert "CRON_USER=${CRON_USER:-ubuntu}" in code
    assert "--launchers-dir /opt/meridian/scripts/launchers" in code, \
        "the cron lines call the VERSIONED launchers, not hand-copied ones under artifacts/"


def test_the_recorder_window_equals_the_launcher_s_lookahead():
    """The recorder resolves its slate once, at start, and subscribes only
    games tipping inside --lookahead-hours. A scheduler window wider than
    that leaves later games unrecorded; narrower opens sockets for nothing.
    The constant and the flag are pinned to each other here, which is the
    reason the launchers were brought into the repo."""
    launcher = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "launchers"
                / "launch_stream_slate.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in launcher.splitlines() if not l.lstrip().startswith("#"))
    m = re.search(r"--lookahead-hours\s+(\d+(?:\.\d+)?)", code)
    assert m, "the launcher must pass --lookahead-hours explicitly"
    assert float(m.group(1)) == SS.RECORDER_LOOKAHEAD_H


# ------------------------------------------------------------- cricket: recorder-only
# docs/math/cricket-inplay-dip.md. The board hands the scheduler one rung per
# cricket match (the winner); nothing but the stream recorder may act on it.
CRICKET = SUNDAY + [
    {"game": "t20icr-japan-india", "key": "t20icr-japan-india-2026-09-22", "league": "t20icr",
     "tip": _t(4, 0, day=22), "rungs": 1},
    {"game": "t20icr-nepal-uae", "key": "t20icr-nepal-uae-2026-09-22", "league": "t20icr",
     "tip": _t(5, 30, day=22), "rungs": 1},
    {"game": "odicr-eng-slr", "key": "odicr-eng-slr-2026-09-21", "league": "odicr",
     "tip": _t(13, 0, day=21), "rungs": 1},
    {"game": "county-surrey-kent", "key": "county-surrey-kent-2026-09-21", "league": "county",
     "tip": _t(9, 0, day=21), "rungs": 1},
]


def test_a_cricket_match_gets_the_stream_recorder_and_nothing_else():
    p = SS.plan(CRICKET, NOW)
    acted = [l for l in p.launches if l.script not in ("launch_stream_slate.sh", "slate_verdict.sh")
             and ("t20icr" in l.args or "odicr" in l.args)]
    assert acted == [], acted
    rec = [l for l in _by(p, "launch_stream_slate.sh") if l.args.split()[0] in ("t20icr", "odicr", "county")]
    assert sorted(l.args.split()[0] for l in rec) == ["county", "odicr", "t20icr"]


def test_one_rung_is_a_winner_not_a_thin_ladder_when_the_league_is_recorder_only():
    """MIN_RUNGS drops a four-rung football game; it must not drop a one-rung
    cricket match, and a one-rung football game is still dropped."""
    thin_nfl = [_g("thin-game", "nfl", _t(17, 0), rungs=1)]
    p = SS.plan(CRICKET + thin_nfl, NOW)
    names = " ".join(l.args for l in p.launches)
    assert "thin-game" not in names
    assert "t20icr" in names


def test_the_cricket_window_runs_a_t20_four_hours_and_an_odi_nine_from_the_first_ball():
    p = SS.plan(CRICKET, NOW)
    rec = {l.args.split()[0]: l for l in _by(p, "launch_stream_slate.sh")}
    t20 = rec["t20icr"]
    assert t20.at == _t(3, 50, day=22)
    assert int(t20.args.split()[1]) == int((_t(5, 30, day=22) + dt.timedelta(minutes=240) - _t(3, 50, day=22)).total_seconds() // 60), \
        "both T20s tip inside one lookahead; the window runs to the later one's end"
    odi = rec["odicr"]
    assert int(odi.args.split()[1]) == 540 + SS.RECORDER_LEAD_MIN


def test_county_gets_a_four_day_recorder_window_and_nothing_else():
    """Four-day cricket, on the operator's ask (2026-09-22): recorded as its
    own row of the in-play read, never a detector. An EXCLUDED_LEAGUES entry
    would be named in the skipped list; the table is empty today."""
    p = SS.plan(CRICKET, NOW)
    rec = [l for l in _by(p, "launch_stream_slate.sh") if l.args.startswith("county ")]
    assert len(rec) == 1 and int(rec[0].args.split()[1]) == 4 * 24 * 60 + SS.RECORDER_LEAD_MIN
    assert not any("county" in l.args for l in p.launches if l.script != "launch_stream_slate.sh")
    assert not any("county" in s for s in p.skipped)


def test_an_excluded_league_is_named_in_the_skipped_list_never_silently_dropped(monkeypatch):
    monkeypatch.setitem(SS.EXCLUDED_LEAGUES, "county", "a reason")
    p = SS.plan(CRICKET, NOW)
    assert not any("county" in l.args for l in p.launches)
    assert any(s.startswith("county-surrey-kent excluded: a reason") for s in p.skipped), p.skipped


def test_the_verdict_waits_for_the_last_cricket_match_too():
    p = SS.plan([g for g in CRICKET if g["league"] != "county"], NOW)
    assert p.verdict_at == _t(5, 30, day=22) + dt.timedelta(minutes=240 + SS.VERDICT_AFTER_MIN)


def test_a_four_day_match_does_not_hold_the_nightly_verdict_for_four_days():
    """The verdict is a NIGHTLY report; a county match spanning four nights
    must not push it to the fifth. It is scheduled off the limited-overs and
    US slates; the county tape is read when the match settles."""
    p = SS.plan(CRICKET, NOW)
    t20_over = _t(5, 30, day=22) + dt.timedelta(minutes=240)
    assert p.verdict_at == t20_over + dt.timedelta(minutes=SS.VERDICT_AFTER_MIN), "set by the last T20, not by county"
    assert p.verdict_at < _t(9, 0, day=21) + dt.timedelta(days=4)


def test_the_recorder_only_set_and_the_stream_runner_agree():
    src = (pathlib.Path(__file__).resolve().parents[1] / "cfb" / "run_stream_slate.py").read_text()
    assert "CRICKET_STREAM_LEAGUES" in src, "the runner must accept every league the scheduler launches it for"
    for lg in SS.RECORDER_ONLY:
        assert lg in SS.GAME_MINUTES, f"{lg} has no game length"
