"""Why the desk took a minute to show a ladder while every route answered in
milliseconds, and the four things that fix it.

    pytest --noconftest tests/test_arb_sampler_latency.py

Measured 2026-09-21 03:13Z on the box: /arb 3 ms, /api/arb/state 70 ms,
/api/arb/ladder 4 ms, api at 0.15 % CPU -- and the centre pane on "first
sample pending". The route was never slow. The sampler behind it was one
thread, sampling every game the operator had glanced at in the last THIRTY
MINUTES, strictly in order, ~4 s each, with the newly picked game appended
last. On an NFL Sunday that cycle reached a minute, and the page could only
wait, because "pending" is exactly "no cache entry yet".

Two agents traced it independently; their findings agreed on the mechanism
and on the order of causes. This file pins the fixes:

  1. a watch lasts 45 s, so the rotation is what is on screen now;
  2. the most recently asked game is sampled first;
  3. asking for a new game wakes the sampler instead of waiting a cycle,
     with the same one client and the same request budget;
  4. the slug listing prunes partitions and caches an empty answer.
"""
from __future__ import annotations

import inspect
import pathlib
import re
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import api as api_module          # noqa: E402
from core.ladder import live                # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = (ROOT / "static" / "arb.html").read_text(encoding="utf-8")


def _fresh(monkeypatch):
    monkeypatch.setitem(api_module._ARB_LADDER, "watch", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "cache", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "slugs", {})
    monkeypatch.setitem(api_module._ARB_LADDER, "wake", threading.Event())


def test_a_watch_is_seconds_not_minutes():
    """The page re-asks every 5 s while a game is on screen. 45 s means
    'being looked at'. 30 minutes meant 'glanced at once this half'."""
    assert 20 <= api_module._ARB_WATCH_SECONDS <= 60


def test_the_most_recently_asked_game_is_sampled_first(monkeypatch):
    """Insertion order put the new game LAST in a serial rotation."""
    _fresh(monkeypatch)
    now = time.time()
    api_module._ARB_LADDER["watch"] = {"aec-old": now + 10, "aec-mid": now + 20, "aec-new": now + 30}
    assert api_module._arb_watched(now) == ["aec-new", "aec-mid", "aec-old"]


def test_asking_for_a_new_game_wakes_the_sampler_and_a_repeat_does_not(monkeypatch):
    _fresh(monkeypatch)
    wake = api_module._ARB_LADDER["wake"]
    assert not wake.is_set()
    api_module._arb_watch("aec-nfl-a-b-2026-09-21")
    assert wake.is_set(), "a game the sampler has not seen ends its sleep"
    wake.clear()
    api_module._arb_watch("aec-nfl-a-b-2026-09-21")
    assert not wake.is_set(), "re-asking for a watched game is not news"


def test_the_sampler_loop_sleeps_on_the_event_and_restarts_when_woken():
    """Source-level: the loop must (a) wait on the event, not time.sleep,
    so a new watch can end the sleep; (b) check it between games, so the
    new game is sampled after the one in flight rather than after the whole
    list; (c) clear it at the top of a cycle so a stale set cannot spin."""
    src = inspect.getsource(api_module._arb_sampler_loop)
    assert "time.sleep(" not in src, "a plain sleep cannot be interrupted"
    assert "wake.wait(timeout=" in src
    assert "wake.clear()" in src
    body = src[src.index("for prefix in _arb_watched(t0):"):]
    assert "if wake.is_set():" in body and "break" in body.split("if wake.is_set():")[1][:40]
    assert src.index("wake.clear()") < src.index("for prefix in _arb_watched"), "cleared before the cycle"


def test_the_sampler_still_uses_one_client_and_the_route_never_samples():
    """Waking is not a second sampler. Priming with a second gateway client
    would double the request rate against a venue that allows 20/s per IP
    while the live recorder holds 12 of them."""
    loop = inspect.getsource(api_module._arb_sampler_loop)
    assert loop.count("PolymarketGatewayClient(") == 1
    assert "PolymarketGatewayClient" not in inspect.getsource(api_module._arb_watch)
    assert "Thread(" not in inspect.getsource(api_module._arb_watch)
    route = inspect.getsource(api_module.arb_ladder)
    for bad in ("sample(", "PolymarketGatewayClient", "slugs_for", "Thread("):
        assert bad not in route


def test_an_empty_slug_listing_is_cached_briefly_rather_than_requeried_every_cycle(monkeypatch):
    """The old test `and cached[1]` made an empty answer uncacheable: a
    watched game with no rungs re-ran the unindexable scan every cycle for
    as long as it stayed watched."""
    _fresh(monkeypatch)
    calls = []
    monkeypatch.setattr(api_module, "slugs_for", lambda game, engine=None: calls.append(game) or [])
    now = time.time()
    assert api_module._arb_slugs("aec-x", "x", now) == []
    assert api_module._arb_slugs("aec-x", "x", now + 5) == []
    assert len(calls) == 1, "the second ask inside the empty TTL hits the cache"
    assert api_module._arb_slugs("aec-x", "x", now + api_module._ARB_SLUGS_EMPTY_TTL_S + 1) == []
    assert len(calls) == 2, "and after it, the listing is asked again (rungs may have appeared)"
    assert api_module._ARB_SLUGS_EMPTY_TTL_S < api_module._ARB_SLUGS_TTL_S


def test_slugs_for_carries_the_partition_pruning_floor():
    """`slate_slugs` in the same file has both floors and says why; this
    query had only the mid-month one, which filters rows and costs MORE."""
    src = inspect.getsource(live.slugs_for)
    assert "date_trunc('month', now() - interval '2 days')" in src
    assert "now() - interval '2 days'" in src
    sib = inspect.getsource(live.slate_slugs)
    assert "date_trunc('month', now() - interval '2 days')" in sib, "the sibling is the reference"


def test_the_page_opens_on_the_game_with_the_newest_ticket():
    """`games` is ordered by file mtime and includes finished games and
    games only the stream detector watches; the ticket pane is filtered by
    league, not game. Opening on mine[0] put a finished game in the centre
    pane, pending forever, beside 129 tickets for another."""
    fn = PAGE[PAGE.index("function renderGames(){"):]
    fn = fn[:fn.index("\n}")]
    code = re.sub(r"/\*.*?\*/", "", fn, flags=re.S)
    assert "const hot = mine.find(g => tk.includes(plainGame(g)))" in code
    assert "GAME = hot || (mine.length ? mine[0] : \"\")" in code
    assert code.index("STATE.tickets") < code.index("GAME = hot"), "tickets are read before the pick"


def test_a_failed_league_fetch_is_loud_not_a_dead_page():
    """That chain had no catch: a bad reply killed the tabs, the league
    names and the follow-the-desk logic silently, and the page sat on its
    default league forever."""
    i = PAGE.index('fetch("/api/leagues")')
    chain = PAGE[i:PAGE.index("\n});", i) + 80]
    assert ".catch(" in chain and "console.error" in chain
    assert 'throw new Error("/api/leagues' in chain
