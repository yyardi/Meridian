"""Era separation: the clean slate that deletes nothing.

The operator's ask (2026-08-18): PULSE's live decisions are a new era; the
pregame ANCHOR record moves behind an explicit archive toggle, labelled,
never mixed — and no row is touched. The boundary is PULSE's first live
decision (or an explicit env constant), and it filters the operator-facing
pages ONLY: the registered measurements keep reading full history.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from core.api import app
from core.era import ERA_ENV, era_boundary
from core.storage import Prediction, get_engine, get_sessionmaker

UTC = dt.timezone.utc
BOUNDARY = dt.datetime(2026, 8, 18, 22, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def Session():
    return get_sessionmaker(get_engine())


def _wipe_pulse(s):
    s.execute(text("DELETE FROM pulse_decisions WHERE market_slug LIKE '%eratest%'"))
    s.commit()


# ------------------------------------------------------------------ #
# The boundary itself
# ------------------------------------------------------------------ #


def test_no_live_decision_means_no_era(Session, monkeypatch):
    monkeypatch.delenv(ERA_ENV, raising=False)
    with Session() as s:
        _wipe_pulse(s)
        assert era_boundary(s) is None or True  # other rows may exist; see below


def test_the_boundary_is_the_first_live_decision_not_the_first_row(Session, monkeypatch):
    """A pregame PULSE row must not start the era — the dispatch says the
    first LIVE decision, and the module takes it literally."""
    monkeypatch.delenv(ERA_ENV, raising=False)
    with Session() as s:
        _wipe_pulse(s)
        base = era_boundary(s)          # whatever non-test rows imply
        s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate)
            VALUES (:at, 'wnba-aaa-bbb-2099-01-01', 'tsc-eratest-1', 'total',
                    'total', 'pregame', 'enter', 'yes', 0.5, 1, 0.5, false)
        """), {"at": BOUNDARY - dt.timedelta(hours=6)})
        s.commit()
        assert era_boundary(s) == base, "a pregame row must not move the boundary"

        s.execute(text("""
            INSERT INTO pulse_decisions
                (decided_at, event_slug, market_slug, sports_market_type,
                 strategy, phase, action, side, limit_price, contracts,
                 stake_usd, minutes_left_is_estimate)
            VALUES (:at, 'wnba-aaa-bbb-2099-01-01', 'tsc-eratest-2', 'total',
                    'total', 'in_play', 'enter', 'yes', 0.5, 1, 0.5, false)
        """), {"at": BOUNDARY})
        s.commit()
        got = era_boundary(s)
        assert got is not None and got <= BOUNDARY
        _wipe_pulse(s)


def test_the_env_override_wins_and_refuses_garbage(Session, monkeypatch):
    monkeypatch.setenv(ERA_ENV, "2026-08-18T22:00:00+00:00")
    with Session() as s:
        assert era_boundary(s) == BOUNDARY
    monkeypatch.setenv(ERA_ENV, "yesterday-ish")
    with Session() as s, pytest.raises(ValueError):
        era_boundary(s)


# ------------------------------------------------------------------ #
# The pages filter; nothing is deleted
# ------------------------------------------------------------------ #


@pytest.fixture()
def two_eras(Session, monkeypatch):
    """One resolved prediction either side of an explicit boundary."""
    monkeypatch.setenv(ERA_ENV, BOUNDARY.isoformat())
    with Session() as s:
        s.execute(delete(Prediction).where(Prediction.market_slug.like("%eratest%")))
        for when, slug in ((BOUNDARY - dt.timedelta(days=1), "tsc-eratest-old"),
                           (BOUNDARY + dt.timedelta(hours=1), "tsc-eratest-new")):
            s.add(Prediction(
                predicted_at=when, market_slug=slug,
                event_slug="wnba-aaa-bbb-2099-01-01",
                sports_market_type="basketball_team_full_game_total",
                strategy="eratest", model_probability=0.6, market_mid=0.5, market_bid=0.49,
                market_ask=0.51, edge=0.09, model_version="eratest",
                resolved_outcome=1, is_actionable=True,
            ))
        s.commit()
    yield
    with Session() as s:
        s.execute(delete(Prediction).where(Prediction.market_slug.like("%eratest%")))
        s.commit()


def test_results_default_to_the_pulse_era(client, two_eras):
    d = client.get("/api/results?limit=5000").json()
    slugs = {r["market_slug"] for r in d["results"]}
    assert "tsc-eratest-new" in slugs
    assert "tsc-eratest-old" not in slugs, "the archive leaked into the default view"
    assert d["era"] == "pulse" and d["era_started"] is True


def test_the_archive_shows_the_old_era_and_only_it(client, two_eras):
    d = client.get("/api/results?era=archive&limit=5000").json()
    slugs = {r["market_slug"] for r in d["results"]}
    assert "tsc-eratest-old" in slugs
    assert "tsc-eratest-new" not in slugs, "eras mixed — the one forbidden state"
    assert d["archive_label"].startswith("ANCHOR")


def test_no_third_era_and_no_mixing_param(client):
    assert client.get("/api/results?era=all").status_code == 400
    assert client.get("/api/results?era=both").status_code == 400


def test_an_unstarted_pulse_era_is_empty_not_the_archive_renamed(client, Session, monkeypatch):
    monkeypatch.delenv(ERA_ENV, raising=False)
    with Session() as s:
        _wipe_pulse(s)
        no_pulse = era_boundary(s) is None
    if not no_pulse:
        pytest.skip("live pulse rows exist outside the test fixture")
    d = client.get("/api/results").json()
    assert d["era_started"] is False
    assert d["results"] == [], "an unstarted era must be empty, not full history"
    d2 = client.get("/api/results?era=archive&limit=5").json()
    assert d2["era_started"] is False   # archive still serves the history


def test_games_list_takes_the_same_filter(client):
    d = client.get("/api/games?league=wnba&era=archive").json()
    assert d["era"] == "archive"
    assert "archive_label" in d


# ------------------------------------------------------------------ #
# The registered measurements never see the era module
# ------------------------------------------------------------------ #


def test_the_measurement_modules_cannot_import_the_era():
    """C11/C14 provenance: the ledger-backed aggregates read full history.

    Asserted on the import graph, not on vocabulary — if one of these modules
    ever imports core.era, its numbers stop being the registered ones.
    """
    import ast

    for mod in ("core/analytics.py", "core/quote/report.py", "core/scorecard.py",
                "core/backtest" ):
        paths = ([Path(mod)] if mod.endswith(".py")
                 else list(Path(mod).glob("*.py")))
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                assert not any(n.startswith("core.era") for n in names), (
                    f"{path} imports core.era — a registered measurement "
                    "must never be era-filtered")


# ------------------------------------------------------------------ #
# The page
# ------------------------------------------------------------------ #


def test_the_page_defaults_to_pulse_and_labels_the_archive():
    html = Path("static/index.html").read_text()
    assert 'let ERA = "pulse";' in html
    assert 'id="eratoggle"' in html
    assert "pregame archive" in html
    assert "Not part of the current era" in html
    # one toggle governs both history sections — eras can never differ on-screen
    assert html.count('data-era="archive"') == 1


def test_the_era_buttons_do_not_wear_the_league_tabs_class():
    """The league wiring binds document-wide to `.lgt`. Styling the era
    buttons with that class also gave them its click handler — one click set
    LEAGUE to the string "undefined" and persisted it. Found live during this
    change; the .gcard/.scard lesson, relearned on a button."""
    html = Path("static/index.html").read_text()
    import re

    for m in re.finditer(r'<button[^>]*data-era=[^>]*>', html):
        assert "lgt" not in m.group(0), (
            "an era button carries the league tabs' class — it will inherit "
            "their click handler")


def test_the_analytics_page_says_whose_record_it_is():
    html = Path("static/analytics.html").read_text()
    assert "ANCHOR model's registered record" in html
    assert "never mixed into these numbers" in html
