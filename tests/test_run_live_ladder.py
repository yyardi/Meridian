"""The live sampler is read-only by construction, and its line parse is the verified one."""
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
RUN = importlib.import_module("cfb.run_live_ladder")
SRC = pathlib.Path(RUN.__file__).read_text(encoding="utf-8")


LIVE = importlib.import_module("core.ladder.live")
LIVE_SRC = pathlib.Path(LIVE.__file__).read_text(encoding="utf-8")


def test_it_cannot_place_an_order():
    """The script and the core module it now delegates the sampling to."""
    for src in (SRC, LIVE_SRC):
        for bad in ("place_order", "submit_order", "MERIDIAN_ORDER_TOKEN", "requests.post", "httpx.post",
                    "PolymarketOrderClient", "/orders"):
            assert bad not in src
    assert "get_book" in inspect.getsource(RUN.sample)
    assert "PolymarketGatewayClient" not in LIVE_SRC, "core.ladder.live is handed a client; it constructs none"


def test_the_script_reexports_the_core_sampler_unchanged():
    """The dashboard imports core.ladder.live; the scripts and their tests
    import these names from here. One function, two doors."""
    for name in ("line_of", "slugs_for", "sample", "LINE"):
        assert getattr(RUN, name) is getattr(LIVE, name)


def test_line_parse_matches_the_settled_convention():
    """neg -> negative line; verified on 84,646 settled pairs with zero violations."""
    assert RUN.line_of("asc-nfl-det-buf-2026-09-17-neg-10pt5", "aec-nfl-det-buf-2026-09-17") == -10.5
    assert RUN.line_of("asc-nfl-det-buf-2026-09-17-pos-3pt5", "aec-nfl-det-buf-2026-09-17") == 3.5
    assert RUN.line_of("aec-nfl-det-buf-2026-09-17", "aec-nfl-det-buf-2026-09-17") == 0.0
    assert RUN.line_of("tsc-nfl-det-buf-2026-09-17-44pt5", "aec-nfl-det-buf-2026-09-17") is None


def test_default_is_uncapped_because_venue_depth_is_real():
    assert 'default=1e12' in SRC


def test_one_bad_rung_does_not_kill_the_sample():
    body = inspect.getsource(RUN.sample)
    assert "except Exception" in body and "continue" in body
    from types import SimpleNamespace as NS
    lvl = lambda px, qty: NS(px=NS(value=str(px)), qty=str(qty))

    class Client:
        def get_book(self, slug):
            if slug.endswith("neg-3pt5"):
                raise RuntimeError("503 from the venue")
            return NS(market_data=NS(bids=[lvl(0.40, 100)], offers=[lvl(0.42, 50)])), {}
    rungs, _ = RUN.sample(Client(), ["asc-x-2026-09-18-neg-3pt5", "asc-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18")
    assert list(rungs) == [3.5], "the bad rung is a hole, the good one is still sampled"


def test_alert_never_prints_the_topic_and_places_nothing():
    """The push carries prices and sizes; the topic comes from the environment
    and must not appear in any print or in the message body."""
    body = SRC[SRC.index("def alert("):SRC.index("def main(")]
    assert "MERIDIAN_NTFY_TOPIC" in body
    assert 'print(' not in body, "alert() must not print (the topic is in scope there)"
    assert "place_order" not in body and "orders" not in body.lower()
    assert 'ntfy.sh/{topic}' in body


def test_alert_is_off_by_default_and_deduped_per_pair():
    assert 'default=0.0' in SRC and 'alert_floor > 0' in SRC
    body = SRC[SRC.index("def alert("):SRC.index("def main(")]
    assert "cooldown_min * 60" in body and "sent[key] = now" in body


def test_an_alert_failure_cannot_stop_sampling():
    body = SRC[SRC.index("def alert("):SRC.index("def main(")]
    assert "except Exception" in body and "return False" in body


def test_sample_fills_meta_with_the_venue_transact_time():
    from types import SimpleNamespace as NS
    import cfb.run_live_ladder as L
    lvl = lambda px, qty: NS(px=NS(value=str(px)), qty=str(qty))
    class Client:
        def get_book(self, slug):
            md = NS(bids=[lvl(0.40, 100)], offers=[lvl(0.42, 50)])
            return NS(market_data=md), {"marketData": {"transactTime": "2026-09-18T13:17:58.280016334Z"}}
    meta = {}
    rungs, _ = L.sample(Client(), ["aec-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18", meta)
    assert rungs and list(meta) == list(rungs) and meta[next(iter(rungs))] == "2026-09-18T13:17:58.280016334Z"
    rungs2, _ = L.sample(Client(), ["aec-x-2026-09-18-pos-3pt5"], "aec-x-2026-09-18")   # old call shape still works
    assert rungs2 == rungs


def test_slugs_for_covers_basketball_ladders_too():
    import cfb.run_live_ladder as L
    src = inspect.getsource(L.slugs_for)
    for fam in ("football", "baseball", "basketball"):
        assert f"{fam}_team_full_game_spread" in src and f"{fam}_team_full_game_winner" in src


def test_slugs_for_takes_the_callers_engine_and_defaults_to_the_scripts_env(monkeypatch):
    """The api has its own engine and no DATABASE_URL promise; the scripts
    have DATABASE_URL and no engine. Both must reach the same query."""
    seen = {}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params):
            seen["sql"], seen["params"] = str(stmt), params
            return self

        def all(self):
            return [("aec-cfb-mia-wake-2026-09-18-pos-3pt5",), ("aec-cfb-mia-wake-2026-09-18",)]

    class Engine:
        def connect(self):
            return Conn()

    assert RUN.slugs_for("cfb-mia-wake-2026-09-18", Engine()) == [
        "aec-cfb-mia-wake-2026-09-18", "aec-cfb-mia-wake-2026-09-18-pos-3pt5"]
    assert seen["params"] == {"p": "%cfb-mia-wake-2026-09-18%"} and "market_snapshots" in seen["sql"]
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        RUN.slugs_for("cfb-mia-wake-2026-09-18")      # no engine, no env: the old behaviour, not a silent default
