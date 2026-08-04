"""Round-trip every table, and pin the guarantees the schema is supposed to make.

Requires the Compose Postgres to be up and `alembic upgrade head` to have run.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select

from core.config_hash import compute_config_hash
from core.storage import (
    BookLevel,
    MarketSnapshot,
    Prediction,
    ResolvedOutcome,
    SportsbookOdds,
    TeamGameLog,
    get_engine,
    get_sessionmaker,
)

UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def session():
    """Session that removes everything it wrote.

    Tests share the development database with the recorder, so anything left
    behind becomes fake market data that would silently contaminate a later
    backtest. Every fixture here cleans up after itself.
    """
    engine = get_engine()
    Session = get_sessionmaker(engine)
    with Session() as s:
        yield s
        s.rollback()
        _purge(s)
        s.commit()


def _purge(s) -> None:
    """Delete all rows created by this module (everything is tagged 'test-')."""
    from sqlalchemy import delete

    s.execute(delete(BookLevel).where(
        BookLevel.snapshot_id.in_(
            select(MarketSnapshot.id).where(MarketSnapshot.market_slug.like("%test-%"))
        )
    ))
    s.execute(delete(MarketSnapshot).where(MarketSnapshot.market_slug.like("%test-%")))
    s.execute(delete(Prediction).where(Prediction.market_slug.like("%test-%")))
    s.execute(delete(TeamGameLog).where(TeamGameLog.espn_game_id.like("g-test-%")))
    s.execute(delete(SportsbookOdds).where(SportsbookOdds.espn_game_id.like("g-test-%")))
    s.execute(delete(ResolvedOutcome).where(ResolvedOutcome.market_slug.like("%test-%")))


def test_roundtrip_all_tables(session):
    """Insert and read back one row per table."""
    now = dt.datetime.now(UTC)
    tag = f"test-{now.timestamp()}"

    snap = MarketSnapshot(
        captured_at=now,
        market_slug=f"tsc-{tag}",
        market_id="298081",
        event_slug=f"evt-{tag}",
        game_id="13002436",
        sports_market_type="basketball_team_full_game_total",
        line=Decimal("144.5"),
        best_bid=Decimal("0.9100"),
        best_ask=Decimal("0.9600"),
        min_tick_size=Decimal("0.0100"),
        min_trade_qty=Decimal("0.0100"),
        fee_coefficient=Decimal("0.060000"),
        is_live=False,
        raw={"source": "test"},
    )
    session.add(snap)
    session.flush()

    session.add(
        BookLevel(
            snapshot_id=snap.id,
            side="bid",
            price=Decimal("0.5100"),
            quantity=Decimal("1559.0000"),
            level_index=0,
        )
    )
    session.add(
        TeamGameLog(
            game_date=now,
            season=2026,
            espn_game_id=f"g-{tag}",
            team_id="9",
            team_abbrev="NY",
            opponent_id="8",
            opponent_abbrev="MIN",
            is_home=True,
            points_scored=88,
            points_allowed=81,
            is_completed=True,
            season_type=2,
        )
    )
    session.add(
        SportsbookOdds(
            espn_game_id=f"g-{tag}",
            game_date=now,
            provider_name="ESPN BET",
            captured_at=now,
            spread=Decimal("-5.50"),
            over_under=Decimal("166.50"),
            over_odds=Decimal("-105.00"),
            under_odds=Decimal("-115.00"),
            open_total=Decimal("164.50"),
            close_total=Decimal("166.50"),
            is_closing_line=True,
            raw={"source": "test"},
        )
    )
    cfg = {"beta": 0.0, "shrinkage_k": 5}
    session.add(
        Prediction(
            predicted_at=now,
            model_version="v2",
            strategy="wnba_totals",
            market_slug=f"tsc-{tag}",
            sports_market_type="basketball_team_full_game_total",
            line=Decimal("144.5"),
            model_probability=Decimal("0.5500"),
            market_bid=Decimal("0.5100"),
            market_ask=Decimal("0.5300"),
            market_mid=Decimal("0.5200"),
            edge=Decimal("0.030000"),
            features={"offense_ppg": 84.2},
            model_config_snapshot=cfg,
            config_hash=compute_config_hash(cfg),
            reduced_confidence=True,
            confidence_notes="playoff game",
        )
    )
    session.add(
        ResolvedOutcome(
            market_slug=f"aec-{tag}",
            game_id="13002436",
            settlement=1,
            resolved_at=now,
            final_score_home=88,
            final_score_away=81,
            actual_total=169,
        )
    )
    session.commit()

    got = session.scalar(select(MarketSnapshot).where(MarketSnapshot.market_slug == f"tsc-{tag}"))
    assert got is not None
    # NUMERIC round-trips as Decimal, not float — this is the point of the type choice.
    assert isinstance(got.best_bid, Decimal)
    assert got.best_bid == Decimal("0.9100")

    assert session.scalar(select(BookLevel).where(BookLevel.snapshot_id == snap.id)) is not None
    tgl = session.scalar(select(TeamGameLog).where(TeamGameLog.espn_game_id == f"g-{tag}"))
    assert tgl is not None and tgl.season_type == 2
    assert session.scalar(select(SportsbookOdds).where(SportsbookOdds.espn_game_id == f"g-{tag}"))
    pred = session.scalar(select(Prediction).where(Prediction.market_slug == f"tsc-{tag}"))
    assert pred is not None and pred.config_hash and pred.reduced_confidence
    assert session.scalar(select(ResolvedOutcome).where(ResolvedOutcome.market_slug == f"aec-{tag}"))


def test_no_float_columns_anywhere():
    """Prices must be NUMERIC. A FLOAT column would silently drift cents."""
    engine = get_engine()
    insp = inspect(engine)
    offenders = []
    for table in insp.get_table_names():
        for col in insp.get_columns(table):
            if "float" in str(col["type"]).lower() or "double" in str(col["type"]).lower():
                offenders.append(f"{table}.{col['name']} = {col['type']}")
    assert not offenders, f"FLOAT columns found: {offenders}"


def test_season_type_is_indexed():
    insp = inspect(get_engine())
    indexed = {
        tuple(ix["column_names"]) for ix in insp.get_indexes("team_game_logs")
    }
    assert any("season_type" in cols for cols in indexed), indexed


def test_predictions_has_versioning_columns():
    insp = inspect(get_engine())
    cols = {c["name"] for c in insp.get_columns("predictions")}
    for required in ("model_config", "config_hash", "reduced_confidence", "confidence_notes"):
        assert required in cols, f"missing {required}"


def test_config_hash_is_order_independent():
    """Reordering keys must not change the hash."""
    a = {"beta": 0.25, "shrinkage_k": 5, "pythagorean_k": 11.09}
    b = {"pythagorean_k": 11.09, "shrinkage_k": 5, "beta": 0.25}
    assert compute_config_hash(a) == compute_config_hash(b)


def test_config_hash_detects_real_changes():
    """A changed parameter must produce a different hash — this is the whole point."""
    base = {"beta": 0.25, "shrinkage_k": 5}
    assert compute_config_hash(base) != compute_config_hash({"beta": 0.26, "shrinkage_k": 5})
    assert compute_config_hash(base) != compute_config_hash({"beta": 0.25, "shrinkage_k": 6})


def test_config_hash_stable_across_processes():
    """Hashing in a separate interpreter must agree — no PYTHONHASHSEED dependence."""
    cfg = {"beta": 0.25, "shrinkage_k": 5, "pythagorean_k": 11.09, "nested": {"a": [1, 2]}}
    here = compute_config_hash(cfg)
    code = (
        "from core.config_hash import compute_config_hash;"
        "print(compute_config_hash("
        "{'beta': 0.25, 'shrinkage_k': 5, 'pythagorean_k': 11.09, 'nested': {'a': [1, 2]}}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == here, f"cross-process mismatch: {out} != {here}"


# ------------------------------------------------------------------ #
# Connection pooling — Supabase session mode caps the PROJECT at 15
# ------------------------------------------------------------------ #


def test_app_url_is_untouched_without_the_flag(monkeypatch):
    from core.storage.base import app_database_url

    monkeypatch.delenv("MERIDIAN_TX_POOLER", raising=False)
    url = "postgresql+psycopg://u:p@host.pooler.supabase.com:5432/postgres"
    assert app_database_url(url) == url


def test_app_url_moves_to_the_transaction_pooler_when_enabled(monkeypatch):
    """Session mode allows 15 clients across the whole project; four
    containers plus the dashboard exhaust it. Transaction mode does not."""
    from core.storage.base import app_database_url

    monkeypatch.setenv("MERIDIAN_TX_POOLER", "1")
    url = "postgresql+psycopg://u:p@host.pooler.supabase.com:5432/postgres"
    assert app_database_url(url).endswith(":6543/postgres")


def test_local_urls_are_never_rewritten(monkeypatch):
    """Local Docker Postgres has no pooler; rewriting its port breaks it.

    Both URLs matter and only the second one can regress. `localhost:5433`
    never contained ':5432/' so it passed vacuously while the rewrite was
    matching on port alone — and the recorder, which uses the *other* form,
    spent 23 hours logging `Connection refused` on every tick.
    """
    from core.storage.base import app_database_url

    monkeypatch.setenv("MERIDIAN_TX_POOLER", "1")

    mapped = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"
    assert app_database_url(mapped) == mapped

    # Exactly what docker-compose gives the live recorder: standard port,
    # container hostname. This is the one that broke.
    in_compose = "postgresql+psycopg://meridian:meridian@postgres:5432/meridian"
    assert app_database_url(in_compose) == in_compose, (
        "a non-Supabase host must keep 5432 — nothing else listens on 6543"
    )


def test_migrations_keep_session_mode(monkeypatch):
    """Alembic reads get_database_url() directly and must NOT be rewritten —
    transaction mode has no advisory locks."""
    from core.storage.base import get_database_url

    monkeypatch.setenv("MERIDIAN_TX_POOLER", "1")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@host.pooler.supabase.com:5432/postgres"
    )
    assert ":5432/" in get_database_url()


def test_transaction_pooler_disables_prepared_statements(monkeypatch):
    """psycopg prepares after 5 executions; a prepared statement cannot
    survive being rotated onto a different backend connection."""
    from core.storage.base import get_engine

    monkeypatch.setenv("MERIDIAN_TX_POOLER", "1")
    engine = get_engine("postgresql+psycopg://u:p@host.pooler.supabase.com:5432/postgres")
    assert engine.url.port == 6543
    assert engine.dialect.create_connect_args(engine.url)[1].get("prepare_threshold") is None


def test_pool_stays_small_enough_for_several_processes():
    from core.storage.base import DEFAULT_MAX_OVERFLOW, DEFAULT_POOL_SIZE

    assert DEFAULT_POOL_SIZE + DEFAULT_MAX_OVERFLOW <= 3
