"""The CFB backfill tables, and that a migrated schema can create them.

Both were created by `archive/cfb/backfill_cfb.py` with no migration and no
model, so they existed only on the box where that script was once run. 55 games
and 9,537 plays, of which 44 games have no `post` row in the live tape and
cannot be reacquired — they finished before the recorder existed.

These tests run against the per-run test database, which conftest migrates to
head. If the migration does not create the tables, they fail here rather than
on the day someone rebuilds a schema.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import text

from cfb.run_ladder_calibration import GAMES_SQL
from core.feeds.espn_cfb_backfill_storage import CfbBackfillGame, CfbBackfillPlay
from core.storage import get_engine, get_sessionmaker

UTC = dt.timezone.utc
_Session = get_sessionmaker(get_engine())
NOW = dt.datetime.now(UTC)
NOW_PER_TEST = True

EG = "test-bf-espn-1"


@pytest.fixture(autouse=True)
def clean():
    yield
    with _Session() as s:
        for t in ("espn_cfb_backfill_plays", "espn_cfb_backfill_games",
                  "espn_cfb_game_state", "cfb_game_map"):
            col = "espn_game_id" if t == "cfb_game_map" else "game_id"
            s.execute(text(f"delete from {t} where {col} like :p"),
                      {"p": "test-bf-%"})
        s.commit()


def _cols(table: str) -> dict[str, str]:
    with _Session() as s:
        return {r[0]: r[1] for r in s.execute(text(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='public' and table_name=:t"), {"t": table})}


@pytest.mark.parametrize("table", ["espn_cfb_backfill_games",
                                   "espn_cfb_backfill_plays"])
def test_the_table_exists_in_a_migrated_schema(table):
    """★ THE POINT. Before the migration these existed only where an archived
    script had run, so `cfb/run_ladder_calibration.py`'s GAMES_SQL could not
    execute against a fresh database at all — which is why the
    post-beats-backfill precedence could be verified on prod and not tested."""
    assert _cols(table), (
        f"{table} is not in a migrated schema; it exists only where "
        "archive/cfb/backfill_cfb.py was run, and 44 of its 55 games cannot "
        "be reacquired")


@pytest.mark.parametrize("model", [CfbBackfillGame, CfbBackfillPlay])
def test_the_model_matches_what_the_migration_created(model):
    """Model and migration are two spellings of one table and drift silently.

    The LIVE table is the artifact and the model is the hypothesis, so a
    mismatch here is reported rather than reconciled — but model-vs-migration
    is a disagreement inside the repo, which is ours to keep at zero.
    """
    db = _cols(model.__tablename__)
    mine = {c.name for c in model.__table__.columns}
    assert mine == set(db), (
        f"model and migration disagree on {model.__tablename__}: "
        f"model-only {sorted(mine - set(db))}, "
        f"migration-only {sorted(set(db) - mine)}")


def test_the_unique_key_on_plays_is_present():
    """`(game_id, play_id)` is what lets the archive script be re-run without
    duplicating 9,537 rows. A migration that creates the table without it turns
    a re-import into silent duplication."""
    with _Session() as s:
        got = [r[0] for r in s.execute(text(
            "select indexdef from pg_indexes "
            "where tablename='espn_cfb_backfill_plays'"))]
    assert any("game_id, play_id" in d.replace('"', '') for d in got), got
    assert any("ix_cfb_bf_game_wall" in d for d in got), (
        "the (game_id, wall_clock) index is missing; run_making_touch's "
        "price bisect depends on it being bounded")


def test_the_downgrade_does_not_drop_the_tables():
    """★ 44 of the 55 games exist nowhere else. A downgrade that drops them
    trades a schema inconvenience for permanent data loss, so it must not."""
    src = pathlib.Path("alembic/versions/b4e9f1c73d85_cfb_backfill_tables.py"
                       ).read_text()
    down = src.split("def downgrade()", 1)[1]
    assert "drop_table" not in down and "DROP TABLE" not in down.upper(), (
        "the downgrade drops a table holding 44 irrecoverable finals")


def test_the_post_row_beats_the_backfill_final():
    """★ THE TEST THAT COULD NOT BE WRITTEN BEFORE THIS MIGRATION.

    The two sources overlap on 11 games and disagree on 1 total: game
    401856660 holds 31-3 (34) in the backfill against 51-10 (61) in the post
    row, and truncation settles which is wrong — a game cut short cannot score
    MORE than its final. So a confirmed `post` row wins, and the error
    direction matters: a low total settles a totals market UNDER, and
    `cfb_total_under_all` is registered.

    AGAINST GAMES_SQL, not LIVE_FINALS_SQL. My first version of this test read
    the live route, where the precedence between the two SOURCES does not
    live — so it passed with the precedence reverted, which is a test failing
    for the wrong reason rather than a test that cannot fail. Mutating in both
    directions is what exposed it, within minutes of agreeing to do that.
    """
    with _Session() as s:
        s.execute(text("""
            insert into cfb_game_map (first_seen_at, espn_game_id,
                                      venue_game_id, event_slug, match_method)
            values (now(), :eg, :vg, :slug, 'test')"""),
                  {"eg": EG, "vg": "test-bf-venue-1", "slug": "test-bf-slug"})
        s.execute(text("""
            insert into espn_cfb_backfill_games
              (game_id, home_score, away_score, spread, provider)
            values (:eg, 3, 31, -7.5, 'test')"""), {"eg": EG})
        s.execute(text("""
            insert into espn_cfb_game_state
              (first_seen_at, league, game_id, state, period, home, away,
               home_score, away_score)
            values (:at, 'cfb', :eg, 'post', NULL, '1', '2', 10, 51)"""),
                  {"at": NOW - dt.timedelta(minutes=5), "eg": EG})
        s.commit()

    with _Session() as s:
        rows = {r._mapping["eg"]: dict(r._mapping)
                for r in s.execute(text(GAMES_SQL))
                if str(r._mapping["eg"]).startswith("test-bf-")}
    got = rows[EG]
    assert got["src"] == "post", (
        f"the backfill won: src={got['src']}. A game cut short cannot score "
        "more than its final, so the higher POST row is the correct one")
    assert (got["h"], got["a"]) == (10, 51), (
        "returned the backfill's 3-31 rather than the post row's 10-51")

    # And the backfill still holds its own value: the precedence is a choice
    # made at read time, not a rewrite of history.
    with _Session() as s:
        bf = s.execute(text("select home_score, away_score from "
                            "espn_cfb_backfill_games where game_id = :eg"),
                       {"eg": EG}).one()
    assert tuple(bf) == (3, 31)


def test_a_game_with_only_a_backfill_final_still_reaches_the_calibration():
    """The other direction of the same precedence. Preferring `post` must not
    DISCARD the 44 games that have no post row — that is 80% of what the table
    supplies and none of it can be reacquired."""
    with _Session() as s:
        s.execute(text("""
            insert into cfb_game_map (first_seen_at, espn_game_id,
                                      venue_game_id, event_slug, match_method)
            values (now(), :eg, :vg, :slug, 'test')"""),
                  {"eg": EG, "vg": "test-bf-venue-2", "slug": "test-bf-slug-2"})
        s.execute(text("""
            insert into espn_cfb_backfill_games
              (game_id, home_score, away_score, spread, provider)
            values (:eg, 17, 24, -3.5, 'test')"""), {"eg": EG})
        s.commit()

    with _Session() as s:
        rows = {r._mapping["eg"]: dict(r._mapping)
                for r in s.execute(text(GAMES_SQL))
                if str(r._mapping["eg"]).startswith("test-bf-")}
    assert EG in rows, (
        "a backfill-only game vanished; 44 of the 55 are backfill-only and "
        "cannot be reacquired")
    assert rows[EG]["src"] == "backfill"
    assert (rows[EG]["h"], rows[EG]["a"]) == (17, 24)
