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
    block = SS.cron_block(p, "/opt/meridian/artifacts/reads")
    lines = [l for l in block.splitlines() if l and not l.startswith("#")]
    for l in lines[:-1]:
        f = l.split()
        assert f[4] == "*" and all(x.isdigit() for x in f[:4]), l
        assert "# TEMP" in l and ">> /opt/meridian/artifacts/reads/cron.log 2>&1" in l, l
        assert "sudo -n /opt/meridian/artifacts/reads/launch_" in l or "slate_verdict.sh" in l, l
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
    assert 'grep -v "TEMP"' in src and "| crontab -" in src
    assert 'grep -q "^[0-9]"' in src, "an empty block installs nothing"
    assert "set -euo pipefail" in src
    assert "docker run" in src and "schedule_slate.py" in src
