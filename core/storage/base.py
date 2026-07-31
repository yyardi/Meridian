"""Database engine, session factory, and declarative base.

`DATABASE_URL` comes from the environment — never hardcoded. Stock Postgres
only, so this connects identically to local Docker, Supabase Pro, AWS RDS, or
a small Hetzner box.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"


def get_database_url() -> str:
    """Read DATABASE_URL from the environment, falling back to local Docker."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    """Declarative base for all Meridian ORM models."""


def get_engine(url: str | None = None, **kwargs):
    """Create a SQLAlchemy engine.

    `pool_pre_ping` matters for the recorder: it runs for days at a time and
    managed Postgres providers drop idle connections without warning.
    """
    return create_engine(url or get_database_url(), pool_pre_ping=True, future=True, **kwargs)


def get_sessionmaker(engine=None):
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False, future=True)
