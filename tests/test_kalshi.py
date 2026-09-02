"""Kalshi recorder: ticker parsing, venue matching, and write discipline.

What is under test and why it matters:

1. **Game-key parsing.** Kalshi concatenates two team codes with no delimiter
   (``26AUG05PHXATL``), so parsing tries every split and demands exactly one
   valid one. The exhaustive pair test proves uniqueness holds for every
   franchise pair — a future code that breaks the property fails here rather
   than silently mis-parsing tickers.
2. **The third abbreviation space.** CONN -> CON and PDX -> POR are the two
   codes that differ from ESPN; a `.upper()`-style shortcut would silently
   drop those teams' games (the gsv/conn lesson from Polymarket).
3. **Snapshots are idempotent** on (ticker, captured_at) — a crashed-and-rerun
   cycle re-inserts harmlessly.
4. **Contract terms are a change log**, warmed from the database on restart:
   unchanged terms are never re-written, so the verbatim rules text costs one
   row per contract, not one per poll.
5. **Polymarket matching is structural**: a game only becomes pollable by
   acquiring a game_start_time from our own market_snapshots.

DB fixtures use deliberately fake keys (year 2099) and delete only their own
rows — the B6 lesson: teardown must not eat real data.
"""

from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from core.config import KalshiConfig
from core.kalshi.analysis import gate_status
from core.kalshi.mapping import (
    KALSHI_TO_ESPN,
    KALSHI_TO_ESPN_NFL,
    LEAGUE_NFL,
    LEAGUE_SERIES,
    SERIES_MONEYLINE,
    SERIES_SPREAD,
    SERIES_TOTAL,
    game_key_from_event_ticker,
    parse_game_key,
)
from core.kalshi.recorder import POLLED_SERIES, KalshiRecorder
from core.storage import (
    KalshiContract,
    KalshiGame,
    KalshiSnapshot,
    MarketSnapshot,
    get_engine,
    get_sessionmaker,
)
from core.team_mapping import UnknownTeamError

UTC = dt.timezone.utc

# ---------------------------------------------------------------------- #
# Parsing (pure)
# ---------------------------------------------------------------------- #


def test_parse_game_key_basic():
    parsed = parse_game_key("26AUG05PHXATL")
    assert parsed is not None
    assert parsed.local_date == dt.date(2026, 8, 5)
    assert (parsed.first_code, parsed.second_code) == ("PHX", "ATL")
    assert parsed.espn_pair == frozenset({"PHX", "ATL"})


def test_parse_game_key_divergent_codes():
    # The two codes that differ from ESPN — the ones a shortcut would drop.
    parsed = parse_game_key("26AUG02CONNDAL")
    assert parsed is not None
    assert (parsed.first_espn, parsed.second_espn) == ("CON", "DAL")

    parsed = parse_game_key("26AUG06TORPDX")
    assert parsed is not None
    assert (parsed.first_espn, parsed.second_espn) == ("TOR", "POR")


def test_parse_game_key_rejects_non_franchise():
    # All-star exhibition observed on the venue: Team Spoon vs Team Coop.
    assert parse_game_key("26JUL25SPNCOO") is None


def test_parse_game_key_rejects_garbage():
    assert parse_game_key("") is None
    assert parse_game_key("26XXX05PHXATL") is None
    assert parse_game_key("26AUG05") is None


def test_every_franchise_pair_splits_uniquely():
    """The no-delimiter format is only parseable if, for every ordered pair of
    codes, exactly one split of the concatenation yields two known codes. This
    is the guard that makes adding a future franchise code safe or loud."""
    codes = list(KALSHI_TO_ESPN)
    for a, b in itertools.permutations(codes, 2):
        blob = a + b
        splits = [
            (blob[:i], blob[i:])
            for i in range(1, len(blob))
            if blob[:i] in KALSHI_TO_ESPN and blob[i:] in KALSHI_TO_ESPN
        ]
        assert splits == [(a, b)], f"ambiguous or unparseable pair: {a}+{b} -> {splits}"


def test_unknown_code_raises_loudly():
    parsed = parse_game_key("26AUG05PHXATL")
    object.__setattr__(parsed, "first_code", "XYZ")
    with pytest.raises(UnknownTeamError):
        _ = parsed.first_espn


def test_game_key_from_event_ticker():
    assert game_key_from_event_ticker("KXWNBAGAME-26AUG05PHXATL") == "26AUG05PHXATL"


# --------------------------------------------------------------------- #
# NFL (GRIDIRON) — codes harvested from the venue 2026-09-02 via each
# open KXNFLGAME event's market-ticker suffixes
# --------------------------------------------------------------------- #


def test_parse_nfl_game_key_basic():
    parsed = parse_game_key("26SEP09NESEA", LEAGUE_NFL)
    assert parsed is not None
    assert parsed.local_date == dt.date(2026, 9, 9)
    assert (parsed.first_code, parsed.second_code) == ("NE", "SEA")
    assert parsed.league == LEAGUE_NFL
    assert parsed.espn_pair == frozenset({"NE", "SEA"})


def test_parse_nfl_variable_length_codes():
    # The pair that kills any fixed-offset split: 2-char + 3-char.
    parsed = parse_game_key("26SEP10SFLAR", LEAGUE_NFL)
    assert parsed is not None
    assert (parsed.first_code, parsed.second_code) == ("SF", "LAR")


def test_parse_nfl_divergent_codes():
    # The two NFL codes that differ from ESPN's space (CONN/PDX's species).
    parsed = parse_game_key("26SEP13CLEJAC", LEAGUE_NFL)
    assert parsed is not None
    assert (parsed.first_espn, parsed.second_espn) == ("CLE", "JAX")

    parsed = parse_game_key("26SEP13WASDAL", LEAGUE_NFL)
    assert parsed is not None
    assert (parsed.first_espn, parsed.second_espn) == ("WSH", "DAL")


def test_every_nfl_pair_splits_uniquely():
    """All 32x31 ordered NFL pairs: exactly one split — the same guard that
    makes a future code addition loud instead of silently mis-parsed."""
    codes = list(KALSHI_TO_ESPN_NFL)
    for a, b in itertools.permutations(codes, 2):
        blob = a + b
        splits = [
            (blob[:i], blob[i:])
            for i in range(1, len(blob))
            if blob[:i] in KALSHI_TO_ESPN_NFL and blob[i:] in KALSHI_TO_ESPN_NFL
        ]
        assert splits == [(a, b)], f"ambiguous NFL pair: {a}+{b} -> {splits}"


def test_cross_league_collision_is_real():
    """SEA/ATL is a valid pair in BOTH leagues — the same game_key parses
    under both tables. This is the measured fact behind keying
    kalshi_games on (league, game_key) rather than game_key alone."""
    wnba = parse_game_key("26SEP13SEAATL")
    nfl = parse_game_key("26SEP13SEAATL", LEAGUE_NFL)
    assert wnba is not None and nfl is not None
    assert wnba.game_key == nfl.game_key
    assert wnba.league != nfl.league


def test_league_series_disjoint_and_complete():
    assert set(LEAGUE_SERIES["wnba"]) == {
        "KXWNBAGAME", "KXWNBASPREAD", "KXWNBATOTAL"}
    assert set(LEAGUE_SERIES["nfl"]) == {
        "KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"}
    assert not (set(LEAGUE_SERIES["wnba"]) & set(LEAGUE_SERIES["nfl"]))
    assert game_key_from_event_ticker("KXWNBAGAME") is None
    assert game_key_from_event_ticker("") is None


# ---------------------------------------------------------------------- #
# Recorder (DB-backed, fake client)
# ---------------------------------------------------------------------- #

GAME_KEY = "99JAN01PHXATL"  # year 2099: cannot collide with real data
PM_EVENT_SLUG = "wnba-phx-atl-2099-01-01"
PM_MARKET_SLUG = "aec-wnba-phx-atl-2099-01-01-test"

_Session = get_sessionmaker(get_engine())


def _market(ticker: str, *, floor: float | None, bid: str, ask: str, rules: str) -> dict:
    return {
        "ticker": ticker,
        "yes_sub_title": "Phoenix",
        "floor_strike": floor,
        "cap_strike": None,
        "strike_type": "greater" if floor is not None else "structured",
        "rules_primary": rules,
        "rules_secondary": "Postponement rules.",
        "open_time": "2099-01-01T00:10:00Z",
        "close_time": "2099-01-03T23:00:00Z",
        "expected_expiration_time": "2099-01-02T02:00:00Z",
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "last_price_dollars": "0.3300",
        "yes_bid_size_fp": "12547.45",
        "yes_ask_size_fp": "96684.10",
        "volume_fp": "68820.37",
        "open_interest_fp": "62852.34",
        "status": "active",
        "result": "",
    }


class FakeKalshiClient:
    """Serves one fake game across all three series. Read-only, like the real one."""

    def __init__(self) -> None:
        self.markets_by_event = {
            f"{SERIES_MONEYLINE}-{GAME_KEY}": [
                _market(f"{SERIES_MONEYLINE}-{GAME_KEY}-PHX", floor=None,
                        bid="0.3200", ask="0.3300", rules="If Phoenix wins..."),
            ],
            f"{SERIES_SPREAD}-{GAME_KEY}": [
                _market(f"{SERIES_SPREAD}-{GAME_KEY}-PHX4", floor=3.5,
                        bid="0.2900", ask="0.3000", rules="If Phoenix wins by more than 3.5..."),
            ],
            f"{SERIES_TOTAL}-{GAME_KEY}": [
                _market(f"{SERIES_TOTAL}-{GAME_KEY}-176", floor=175.5,
                        bid="0.6500", ask="0.6600", rules="If the teams collectively score..."),
            ],
        }

    def iter_events(self, series_ticker: str, *, status: str | None = "open", limit: int = 200):
        yield {"event_ticker": f"{series_ticker}-{GAME_KEY}", "title": "Phoenix vs Atlanta"}

    def get_markets(self, event_ticker: str) -> list[dict]:
        return list(self.markets_by_event.get(event_ticker, []))


@pytest.fixture
def clean_kalshi_rows():
    """Delete only this test's own keys, before and after."""

    def _purge() -> None:
        with _Session() as s:
            s.execute(delete(KalshiSnapshot).where(KalshiSnapshot.game_key == GAME_KEY))
            s.execute(delete(KalshiContract).where(KalshiContract.game_key == GAME_KEY))
            s.execute(delete(KalshiGame).where(KalshiGame.game_key == GAME_KEY))
            s.execute(delete(MarketSnapshot).where(MarketSnapshot.event_slug == PM_EVENT_SLUG))
            s.commit()

    _purge()
    yield
    _purge()


@pytest.fixture
def polymarket_game(clean_kalshi_rows):
    """A Polymarket snapshot for the same game, tipping off in two hours —
    the thing that makes the Kalshi game pollable at all."""
    now = dt.datetime.now(UTC)
    with _Session() as s:
        s.add(
            MarketSnapshot(
                captured_at=now,
                market_slug=PM_MARKET_SLUG,
                event_slug=PM_EVENT_SLUG,
                game_start_time=now + dt.timedelta(hours=2),
            )
        )
        s.commit()
    return now


def _recorder() -> KalshiRecorder:
    return KalshiRecorder(
        config=KalshiConfig(), client=FakeKalshiClient(), sessionmaker=_Session
    )


def test_run_once_records_matched_game(polymarket_game):
    recorder = _recorder()
    t0 = dt.datetime.now(UTC)
    stats = recorder.run_once(captured_at=t0)

    assert stats.errors == 0
    # The live recorder shares this database, so kalshi_games may hold real
    # matched games that this run also polls — global counters are not
    # assertable. The write counters still are: the fake client serves data
    # for the fixture game only, so every write below belongs to GAME_KEY.
    assert stats.games_polled >= 1
    assert stats.snapshots_written == 3   # one contract per series
    assert stats.contracts_written == 3

    with _Session() as s:
        n_mine = len(s.scalars(select(KalshiSnapshot).where(
            KalshiSnapshot.game_key == GAME_KEY)).all())
        assert n_mine == 3

        game = s.scalars(select(KalshiGame).where(KalshiGame.game_key == GAME_KEY)).one()
        assert game.polymarket_event_slug == PM_EVENT_SLUG
        assert game.game_start_time is not None
        assert (game.first_espn, game.second_espn) == ("PHX", "ATL")

        snap = s.scalars(
            select(KalshiSnapshot).where(
                KalshiSnapshot.ticker == f"{SERIES_SPREAD}-{GAME_KEY}-PHX4"
            )
        ).one()
        assert snap.yes_bid == Decimal("0.2900")
        assert snap.floor_strike == Decimal("3.5")
        assert snap.market_type == "spread"
        assert snap.captured_at == t0

        contract = s.scalars(
            select(KalshiContract).where(
                KalshiContract.ticker == f"{SERIES_SPREAD}-{GAME_KEY}-PHX4"
            )
        ).one()
        assert contract.rules_primary.startswith("If Phoenix wins by more than 3.5")
        assert contract.raw["yes_bid_dollars"] == "0.2900"  # payload verbatim


def test_rerun_same_instant_is_idempotent(polymarket_game):
    recorder = _recorder()
    t0 = dt.datetime.now(UTC)
    recorder.run_once(captured_at=t0)
    stats = recorder.run_once(captured_at=t0)
    assert stats.snapshots_written == 0
    assert stats.contracts_written == 0
    with _Session() as s:
        n = len(s.scalars(select(KalshiSnapshot).where(
            KalshiSnapshot.game_key == GAME_KEY)).all())
    assert n == 3


def test_contract_terms_written_once_across_polls_and_restarts(polymarket_game):
    recorder = _recorder()
    t0 = dt.datetime.now(UTC)
    recorder.run_once(captured_at=t0)

    # Next poll, same terms: snapshots accrue, contracts do not.
    stats = recorder.run_once(captured_at=t0 + dt.timedelta(seconds=60))
    assert stats.snapshots_written == 3
    assert stats.contracts_written == 0

    # Fresh process (empty in-memory cache): the cache warms from the DB and
    # still declines to re-write unchanged terms. This is the round-trip test
    # of the stored fingerprint (Decimal and timestamptz formatting included).
    stats = _recorder().run_once(captured_at=t0 + dt.timedelta(seconds=120))
    assert stats.contracts_written == 0
    assert stats.snapshots_written == 3


def test_changed_terms_earn_a_new_contract_row(polymarket_game):
    recorder = _recorder()
    t0 = dt.datetime.now(UTC)
    recorder.run_once(captured_at=t0)

    # The venue re-strikes the spread contract.
    spread = recorder._client.markets_by_event[f"{SERIES_SPREAD}-{GAME_KEY}"][0]
    spread["floor_strike"] = 4.5
    spread["rules_primary"] = "If Phoenix wins by more than 4.5..."

    stats = recorder.run_once(captured_at=t0 + dt.timedelta(seconds=60))
    assert stats.contracts_written == 1

    with _Session() as s:
        rows = s.scalars(
            select(KalshiContract)
            .where(KalshiContract.ticker == f"{SERIES_SPREAD}-{GAME_KEY}-PHX4")
            .order_by(KalshiContract.captured_at)
        ).all()
    # Change log: both the old and the new terms remain, point-in-time.
    assert [r.floor_strike for r in rows] == [Decimal("3.5"), Decimal("4.5")]


def test_unmatched_game_is_never_polled(clean_kalshi_rows):
    """No Polymarket snapshot for the game -> no start time -> no polling."""
    recorder = _recorder()
    stats = recorder.run_once(captured_at=dt.datetime.now(UTC))
    assert stats.games_discovered == 1
    # Real matched games in the shared database may be polled by this same
    # run; the invariant under test is that THIS game — matched to no
    # Polymarket event — is not. No start time, no snapshots, by shape.
    assert stats.snapshots_written == 0
    with _Session() as s:
        game = s.scalars(select(KalshiGame).where(KalshiGame.game_key == GAME_KEY)).one()
        assert game.game_start_time is None
        assert s.scalars(select(KalshiSnapshot).where(
            KalshiSnapshot.game_key == GAME_KEY)).first() is None


def test_gate_reports_but_never_concludes(polymarket_game):
    """The gate reports coverage and never a conclusion.

    Updated 2026-08-07: `gate_status` used to expose a single `matched_games`
    count taken from `count_matched_games`, which only checked that a game had
    a Polymarket *slug* and at least one **Kalshi** snapshot. The spec it
    implements requires same-minute pregame snapshots **on both venues**, and
    the two disagreed on live data (proxy 10, real gate 7). Both are now
    reported so the disagreement stays visible.
    """
    recorder = _recorder()
    recorder.run_once(captured_at=dt.datetime.now(UTC))
    with _Session() as s:
        status = gate_status(s)
    assert status["required"] == 10
    # Discovery coverage: the recorder found and mapped a game.
    assert status["discovered_games"] >= 1
    # The real gate is a subset — it also demands Polymarket data.
    assert status["comparable_games"] <= status["discovered_games"]
    # And it never concludes on its own.
    assert status["gate_met"] is (status["comparable_games"] >= 10)
