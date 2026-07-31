# SQLAlchemy + Alembic

**Roles:** SQLAlchemy is the ORM and query builder. Alembic versions the schema.

## SQLAlchemy

Typed models in one place, so the schema is readable as code:

```python
class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    best_bid: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
```

Chosen over raw SQL because the schema is central to the whole project and needs to be legible; over Django ORM because we want no web framework.

**Version 2.0 style** (`Mapped[...]`, `mapped_column`) — real type annotations, so the type checker catches a `float` where a `Decimal` belongs.

### Where we drop to Core

Bulk inserts bypass the ORM for speed and to reach Postgres-specific `ON CONFLICT`:

```python
stmt = pg_insert(MarketSnapshot).values(**values) \
    .on_conflict_do_nothing(constraint="uq_snapshot_market_time") \
    .returning(MarketSnapshot.id)
```

`ON CONFLICT DO NOTHING` is what makes the recorder idempotent. `.returning()` tells us whether the row was actually inserted — a `None` means "already recorded," which we count rather than treat as an error.

### `pool_pre_ping=True`

The recorder holds connections for days. Managed Postgres providers drop idle connections without warning; without pre-ping, the recorder dies at 3am on a stale socket. This one flag prevents a whole class of silent overnight failure.

## Alembic

Schema changes are versioned migrations, not hand-run `ALTER TABLE`.

```bash
alembic revision --autogenerate -m "add season_type"
alembic upgrade head
alembic downgrade base    # must cleanly reverse
```

Autogenerate diffs the models against the live database and writes the migration. Always read the generated file — it's a good first draft, not a finished one, and it misses things like data backfills.

### URL from the environment

`alembic.ini` deliberately omits `sqlalchemy.url`. It's read from `DATABASE_URL` in `alembic/env.py`, so no connection string is ever committed:

```python
config.set_main_option("sqlalchemy.url", get_database_url())
```

### Migrations run on deploy

`alembic upgrade head` runs before the recorder starts. Never hand-run migrations against production — that's how environments drift apart.

## Verifying a migration

The bar is that it reverses cleanly:

```bash
alembic upgrade head      # creates 6 tables
alembic downgrade base    # back to zero
alembic upgrade head      # and again
```

A migration that can't be undone is a migration you can't safely deploy.
