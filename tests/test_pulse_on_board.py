"""PULSE's estimates on the board's in-play rows — alive, labelled, unorderable.

During a live game the pregame model is correctly silent, so the board showed
dashes while PULSE decided one table away. In-play rows now wear PULSE's
latest estimate — from the same rows the deep-dive tape reads — clearly
labelled as PULSE, and structurally unable to become an order.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.api import PULSE_LATEST_MAX_AGE_SECONDS, app
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
PAGE = Path("static/index.html")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def Session():
    return get_sessionmaker(get_engine())


def _fn(html: str, signature: str) -> str:
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


@pytest.fixture()
def pulse_rows(Session):
    now = dt.datetime.now(UTC)
    with Session() as s:
        s.execute(text("DELETE FROM pulse_decisions WHERE market_slug LIKE '%pobtest%'"))
        for at, slug, action, fv in (
            (now - dt.timedelta(seconds=30), "tsc-wnba-pobtest-1", "hold", 0.61),
            (now - dt.timedelta(seconds=5), "tsc-wnba-pobtest-1", "enter", 0.63),
            # stale: outside the window, must not be served
            (now - dt.timedelta(seconds=PULSE_LATEST_MAX_AGE_SECONDS + 60),
             "tsc-wnba-pobtest-2", "enter", 0.40),
        ):
            s.execute(text("""
                INSERT INTO pulse_decisions
                    (decided_at, event_slug, market_slug, sports_market_type,
                     strategy, phase, action, side, limit_price, contracts,
                     stake_usd, minutes_left_is_estimate, fair_value, edge_net,
                     market_bid, market_ask, score, period)
                VALUES (:at, 'wnba-pobtest-9999-01-01', :slug, 'total', 'total',
                        'in_play', :action, 'yes', 0.55, 1, 0.55, false,
                        :fv, 0.021, 0.54, 0.58, '40-38', 'Q3')
            """), {"at": at, "slug": slug, "action": action, "fv": fv})
        # An open position: filled entry + resting (unfilled) exit — the
        # operator's real 02:32:34 ENTER -> 02:32:38 EXIT-reprice story.
        eid = s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate, filled_at)
            VALUES (:at, 'wnba-pobtest-9999-01-01', 'aec-wnba-pobtest-3', 'winner',
                    'winner', 'in_play', 'enter', 'no', 0.36, 2.0,
                    1.28, false, :at)
            RETURNING id
        """), {"at": now - dt.timedelta(minutes=2)}).scalar()
        s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate, entry_id, reason)
            VALUES (:at, 'wnba-pobtest-9999-01-01', 'aec-wnba-pobtest-3', 'winner',
                    'winner', 'in_play', 'exit', 'no', 0.31, 2.0,
                    0, false, :eid, 'stop repriced to the touch')
        """), {"at": now - dt.timedelta(minutes=1, seconds=56), "eid": eid})
        # A CLOSED position (exit filled) — must not appear in positions.
        eid2 = s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate, filled_at)
            VALUES (:at, 'wnba-pobtest-9999-01-01', 'aec-wnba-pobtest-4', 'winner',
                    'winner', 'in_play', 'enter', 'yes', 0.50, 1.0,
                    0.50, false, :at)
            RETURNING id
        """), {"at": now - dt.timedelta(minutes=3)}).scalar()
        s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate, entry_id, filled_at)
            VALUES (:at, 'wnba-pobtest-9999-01-01', 'aec-wnba-pobtest-4', 'winner',
                    'winner', 'in_play', 'exit', 'yes', 0.55, 1.0,
                    0, false, :eid, :at)
        """), {"at": now - dt.timedelta(minutes=1), "eid": eid2})
        s.commit()
    yield
    with Session() as s:
        s.execute(text("DELETE FROM pulse_decisions WHERE market_slug LIKE '%pobtest%'"))
        s.commit()


# ------------------------------------------------------------------ #
# The endpoint
# ------------------------------------------------------------------ #


def test_latest_decision_per_market_and_only_fresh_ones(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=wnba").json()
    m = d["markets"]
    assert "tsc-wnba-pobtest-1" in m
    row = m["tsc-wnba-pobtest-1"]
    assert row["action"] == "enter", "must be the NEWEST decision, not the first"
    assert row["fair_value"] == 0.63
    assert row["edge_net"] == 0.021
    assert "tsc-wnba-pobtest-2" not in m, (
        "a decision older than the freshness window must not paint the board")


def test_the_endpoint_is_league_scoped_and_get_only(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=nba").json()
    assert "tsc-wnba-pobtest-1" not in d["markets"]
    routes = {r.path: r.methods for r in app.routes if hasattr(r, "methods")}
    assert routes.get("/api/pulse/latest") == {"GET"}


def test_open_positions_are_served_and_closed_ones_are_not(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=wnba").json()
    pos = d["positions"]
    assert "aec-wnba-pobtest-3" in pos, "filled entry + resting exit = open"
    p3 = pos["aec-wnba-pobtest-3"]
    assert p3["side"] == "no" and p3["entry_price"] == 0.36
    assert p3["exit_limit"] == 0.31, "the resting exit's limit rides along"
    assert "aec-wnba-pobtest-4" not in pos, "a filled exit closes the position"


def test_the_feed_tells_the_enter_exit_story_newest_first(client, pulse_rows):
    d = client.get("/api/pulse/latest?league=wnba").json()
    feed = [f for f in d["feed"] if "pobtest-3" in f["market_slug"]]
    assert [f["action"] for f in feed] == ["exit", "enter"], "newest first"
    ex = feed[0]
    assert ex["entry_id"] is not None, "the exit names its entry — one story"
    assert ex["reason"] == "stop repriced to the touch"
    assert ex["filled"] is False, "a resting exit says so"


# ------------------------------------------------------------------ #
# The page
# ------------------------------------------------------------------ #


@pytest.fixture(scope="module")
def html() -> str:
    return PAGE.read_text()


def test_a_pulse_row_is_labelled_and_phase_distinct(html):
    row = _fn(html, "function boardRow(r, hrs){")
    assert "PULSE_LATEST[r.market_slug]" in row
    assert "r.is_live" in row, "PULSE decorates IN-PLAY rows only"
    assert "pubadge" in row and ">PULSE</span>" in row
    assert "pulserow" in row, "phase must be visually distinct from ANCHOR rows"


def test_a_pulse_row_can_never_become_an_order(html):
    """PULSE is shadow structurally; its board presence is display only.

    Comments are stripped before scanning: the first version of this test
    tripped on a comment that NAMED the forbidden functions while promising
    their absence — the word-ban-on-prose mistake, third instance, one day
    after findings.md recorded it. Code is what can call a function; prose
    is not."""
    import re

    row = _fn(html, "function boardRow(r, hrs){")
    code = re.sub(r"/\*.*?\*/", "", row, flags=re.DOTALL)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.MULTILINE)
    for forbidden in ("sendCell", "openTicket", "PICKS[", "sendbtn"):
        assert forbidden not in code, f"{forbidden} reachable from a PULSE row"


def test_the_two_edges_are_never_conflated(html):
    """The rendered edge is PULSE FV against the CURRENT touch, gross. PULSE's
    own edge_net was net of fees at ITS limit at decision time. Different
    quantities; the tooltip names both rather than letting one wear the
    other's number."""
    row = _fn(html, "function boardRow(r, hrs){")
    assert "gross" in row and "edge_net" in row
    assert "positionView({...r, model: pu.fair_value})" in row, (
        "one derivation on the page: the ANCHOR rows' own positionView")


def test_the_action_chip_carries_action_side_price_and_age(html):
    row = _fn(html, "function boardRow(r, hrs){")
    assert "puchip" in row
    for piece in ("pu.action.toUpperCase()", "pu.side", "num(pu.limit_price)",
                  "agef(pu.age_seconds)"):
        assert piece in row


# ------------------------------------------------------------------ #
# The live view: body = what the model is doing; ribbon = what it thinks
# ------------------------------------------------------------------ #


def test_a_live_game_shows_trading_not_the_pregame_ladder(html):
    board = _fn(html, "function renderBoard(b, picksBySlug){")
    assert "isLiveGame" in board and "liveTradingSection(g)" in board
    assert "pgtoggle" in board, "the pregame table survives behind a toggle"
    assert "OPEN_PREGAME" in board, "the toggle remembers per game"


def test_the_trading_section_scores_with_one_arithmetic(html):
    """puCapture is the ENGINE's frame rule, used for both closed captures
    (b = exit) and open unrealized (b = mid) — one derivation, two uses."""
    sec = _fn(html, "function liveTradingSection(g){")
    assert sec.count("puCapture(") >= 3
    cap = _fn(html, "function puCapture(side, a, b){")
    assert 'side === "yes" ? b - a : a - b' in cap


def test_holds_are_summarized_never_itemized(html):
    sec = _fn(html, "function liveTradingSection(g){")
    assert "holds summarized, not itemized" in sec
    assert '"hold"' not in sec, "no hold rows render in the trading table"


def test_the_trading_section_cannot_order(html):
    import re

    sec = _fn(html, "function liveTradingSection(g){")
    code = re.sub(r"/\*.*?\*/", "", sec, flags=re.DOTALL)
    for forbidden in ("sendCell", "openTicket", "PICKS[", "sendbtn"):
        assert forbidden not in code
    assert "nothing is sent" in sec


def test_the_ribbon_summary_reads_the_engines_projections(html):
    fn = _fn(html, "function renderPulseFeed(){")
    assert "projected_total" in fn and "total_sigma" in fn
    assert 'strategy === "winner"' in fn, "WP comes from the ML fair value"
    # the one client-side choice is WHICH line to compare against — closest
    # to the money — and nothing else is derived
    assert "Math.abs((r.bid + r.ask) / 2 - 0.5)" in fn


def test_a_position_row_fills_the_dead_columns_with_the_engines_frame(html):
    """Entry, resting exit, unrealized, size, stake go where every other
    in-play row shows dashes. Unrealized uses the ENGINE's own arithmetic
    (yes: mid − entry; no: entry − mid, YES frame throughout) — the page
    invents no frame math of its own."""
    row = _fn(html, "function boardRow(r, hrs){")
    assert "PULSE_POSITIONS[r.market_slug]" in row
    assert 'pos.side === "yes" ? mid - pos.entry_price : pos.entry_price - mid' in row
    assert "pos.exit_limit" in row
    assert "pulsepos" in row, "position rows carry the accent"
    assert "shadow dollars" in row, "unrealized is labelled as never held"


def test_the_ribbon_is_navigation_never_an_order(html):
    """Superseded by the live-view restructure (operator request): the ribbon
    is now the model's READ of each live game — WP, projected winner,
    projected total vs the main line — and the trade log moved into each
    game's own body. The invariants carried over: navigation only, never an
    order, and the entry->exit story (entry_id) now lives in
    liveTradingSection where the trades render."""
    import re

    fn = _fn(html, "function renderPulseFeed(){")
    code = re.sub(r"/\*.*?\*/", "", fn, flags=re.DOTALL)
    for forbidden in ("sendCell", "openTicket", "PICKS[", "sendbtn"):
        assert forbidden not in code
    assert "setView" in fn, "clicking a card filters the board to its game"
    assert "fair_value" in fn and "projected_total" in fn, (
        "the ribbon renders estimates, not trades")
    body = _fn(html, "function liveTradingSection(g){")
    assert "entry_id" in body, "the entry->exit story moved into the body"


def test_a_position_outlives_the_estimate_window(html):
    """Found live: two open positions rendered as dead rows because the PULSE
    branch was gated on estimate freshness. The game goes quiet and the
    engine stops re-estimating, but "the model is IN this market at X" stays
    true until the exit fills or settlement lands."""
    row = _fn(html, "function boardRow(r, hrs){")
    assert "if(pu || pos){" in row, "position alone must decorate the row"
    assert "position open · quiet" in row, (
        "a position without a fresh estimate says so instead of vanishing")


def test_new_decisions_flash(html):
    row = _fn(html, "function boardRow(r, hrs){")
    assert "PULSE_SEEN" in row and "puflash" in row
    assert "@keyframes pufl" in html


def test_estimates_refresh_without_refetching_the_board(html):
    """Superseded in place by the live-board heartbeat: estimates still
    refresh every 10s from cache, but the board itself now ALSO refetches on
    the same beat when anything is live (60s idle). The property this test
    holds is unchanged — a pulse estimate must never require a board
    refetch to paint — the schedule just moved into boardHeartbeat."""
    fn = _fn(html, "async function loadPulseLatest(league){")
    assert "stale(league)" in fn, "the league guard covers this loader too"
    assert "renderBoard(LAST_BOARD" in fn, "re-render from cache, not refetch"
    hb = _fn(html, "async function boardHeartbeat(){")
    assert "loadPulseLatest(LEAGUE)" in hb, "estimates ride every beat"
    assert "setInterval(boardHeartbeat, 10000)" in html


# ------------------------------------------------------------------ #
# Tape cards date themselves by the game, not the first trade
# ------------------------------------------------------------------ #


def test_the_games_list_carries_the_games_own_tipoff(client, Session, monkeypatch):
    """Pregame trades land the night before; a card dated by its first trade
    wore yesterday's date and read as a played game with stuck trades
    ("GSV didn't play yesterday?", operator, 2026-08-19).

    Seeded, not data-dependent: a shadow order decided well before its
    game's tip (decided now, tip in 10h — post-era-boundary so the pulse-era
    list carries it), with the tip on a snapshot — the confusing shape."""
    # The suite's per-run database has no pulse decisions, so the pulse era
    # has not started there and era=pulse is empty BY DESIGN. Pin the
    # boundary behind the seed so the era contains it.
    monkeypatch.setenv("MERIDIAN_ERA_BOUNDARY",
                       (dt.datetime.now(UTC) - dt.timedelta(days=1)).isoformat())
    tip = dt.datetime.now(UTC) + dt.timedelta(hours=10)
    with Session() as s:
        s.execute(text("DELETE FROM shadow_orders WHERE market_slug LIKE '%pobtip%'"))
        s.execute(text("DELETE FROM market_snapshots WHERE market_slug LIKE '%pobtip%'"))
        s.execute(text("""
            INSERT INTO shadow_orders (decided_at, idempotency_key, market_slug,
                event_slug, side, limit_price, quantity, would_rest, mode)
            VALUES (now(), 'pobtip-1', 'tsc-wnba-pobtip-1',
                    'wnba-pobtip-9999-01-02', 'BUY_YES', 0.5, 1, true, 'SHADOW')
        """))
        s.execute(text("""
            INSERT INTO market_snapshots (captured_at, market_slug, event_slug,
                game_start_time, is_live)
            VALUES (now(), 'tsc-wnba-pobtip-1', 'wnba-pobtip-9999-01-02', :tip, false)
        """), {"tip": tip})
        s.commit()
    try:
        d = client.get("/api/games?league=wnba&era=pulse").json()
        g = next(x for x in d["games"] if x["event_slug"] == "wnba-pobtip-9999-01-02")
        assert g["tipoff"] is not None
        got = dt.datetime.fromisoformat(g["tipoff"])
        assert abs((got - tip).total_seconds()) < 2, (
            "the card's date must be the GAME's tip, not the trade's night")
    finally:
        with Session() as s:
            s.execute(text("DELETE FROM shadow_orders WHERE market_slug LIKE '%pobtip%'"))
            s.execute(text("DELETE FROM market_snapshots WHERE market_slug LIKE '%pobtip%'"))
            s.commit()


def test_card_states_are_three_and_future_unresolved_is_not_a_warning():
    html = Path("static/index.html").read_text()
    for state in ("upcoming · tips in", ">final<", "● LIVE"):
        assert state in html, f"missing card state {state!r}"
    # unresolved-because-future must not wear the stuck-warning colour
    assert "pregame trades" in html and "resolve after the game" in html
    assert "nothing has resolved — this IS worth a look" in html, (
        "played-and-unresolved keeps the warning, with words")
    # dated by the game
    assert "day(tip)" in html or "${tip ? day(tip)" in html


def test_the_footer_names_the_actual_state_not_an_error():
    html = Path("static/index.html").read_text()
    assert ">not analysed</span>" in html
    import re

    code = re.sub(r"/\*.*?\*/", "", _fn(html, "async function loadStatus(){"),
                  flags=re.DOTALL)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.MULTILINE)
    assert '"unknown"' not in code, (
        "the word that read as an error is gone from the counts (comments "
        "stripped — the un-stripped version tripped on prose describing the "
        "old behaviour, fourth instance of the pattern)")
    assert "ANALYZE fixes it" in html, "the tooltip says what fixes the state"
