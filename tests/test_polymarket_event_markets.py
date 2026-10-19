"""The venue's league listing stopped embedding spreads and totals (2026-10-16): the client puts
each event's full game/team market list back from /v1/events/{id}, props excluded."""
from __future__ import annotations

from core.polymarket.client import PolymarketGatewayClient


def _client(responses):
    c = PolymarketGatewayClient.__new__(PolymarketGatewayClient)
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        r = responses[path]
        if isinstance(r, Exception):
            raise r
        return r
    c._get = fake_get
    c.config = type("C", (), {"league_slug": "nfl", "event_limit": 50})()
    return c, calls


def _v2(markets, num=None):
    return {"events": [{"id": 7, "slug": "nfl-was-sf-2026-10-19", "markets": markets,
                        **({"marketCounts": {"numMarkets": num}} if num is not None else {})}]}


WIN = {"slug": "aec-nfl-was-sf-2026-10-19", "sportsMarketType": "football_team_full_game_winner"}
SPREAD = {"slug": "asc-nfl-was-sf-2026-10-19-pos-3pt5", "sportsMarketType": "football_team_full_game_spread", "line": 3.5}
TOTAL = {"slug": "tsc-nfl-was-sf-2026-10-19-47pt5", "sportsMarketType": "football_team_full_game_total", "line": 47.5}
PROP = {"slug": "pp-nfl-was-sf-2026-10-19-mclaurin-rec", "sportsMarketType": "football_player_receiving_yards"}
RACE = {"slug": "rtp-nfl-was-sf-2026-10-19-10", "sportsMarketType": "football_game_race_to_points"}
Q1_WIN = {"slug": "aec-nfl-was-sf-2026-10-19-1q", "sportsMarketType": "football_team_first_quarter_winner"}
TEAM_PTS = {"slug": "tts-nfl-was-sf-2026-10-19-was-20pt5", "sportsMarketType": "football_team_points_full_game_total"}


def test_an_event_listed_with_fewer_markets_than_it_counts_gets_back_the_families_it_used_to_embed():
    c, calls = _client({"/v2/leagues/nfl/events": _v2([WIN], num=7),
                        "/v1/events/7": {"event": {"id": 7, "markets": [WIN, SPREAD, TOTAL, PROP, RACE, Q1_WIN, TEAM_PTS]}}})
    parsed, raw = c.get_league_events()
    slugs = [m.slug for m in parsed.events[0].markets]
    assert slugs == [WIN["slug"], SPREAD["slug"], TOTAL["slug"], TEAM_PTS["slug"]]   # props, race-to, quarter winners: never on the board
    assert calls == ["/v2/leagues/nfl/events", "/v1/events/7"]
    assert [m["slug"] for m in raw["events"][0]["markets"]] == slugs     # the raw payload the recorder persists matches


def test_a_complete_listing_or_one_without_counts_is_not_refetched():
    c, calls = _client({"/v2/leagues/nfl/events": _v2([WIN, SPREAD], num=2)})
    c.get_league_events()
    c2, calls2 = _client({"/v2/leagues/nfl/events": _v2([WIN])})
    c2.get_league_events()
    assert calls == ["/v2/leagues/nfl/events"] and calls2 == ["/v2/leagues/nfl/events"]


def test_a_failed_event_fetch_keeps_the_winner():
    c, _ = _client({"/v2/leagues/nfl/events": _v2([WIN], num=727), "/v1/events/7": RuntimeError("429")})
    parsed, _ = c.get_league_events()
    assert [m.slug for m in parsed.events[0].markets] == [WIN["slug"]]


def test_a_schedule_only_read_skips_the_event_fetches():
    c, calls = _client({"/v2/leagues/nfl/events": _v2([WIN], num=727)})
    parsed, _ = c.get_league_events(full_markets=False)
    assert calls == ["/v2/leagues/nfl/events"] and len(parsed.events[0].markets) == 1
