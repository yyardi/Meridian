"""Merge the two 2026-08-19 migration branches.

Two PRs merged the same day each added a migration off the same parent:
c1e4b7a90d33 (positions on account_balances, PR #29) and a9b4e6d13f75
(ESPN live signal tables, PR #34). Alembic then had two heads and every
container running `alembic upgrade head` on start crash-looped with
"Multiple head revisions" — the whole laptop stack went down for ~25
minutes on 2026-08-19 until this merge point.

No schema changes here; this revision only joins the branches.

Revision ID: 7fe2c9d40b18
Revises: c1e4b7a90d33, a9b4e6d13f75
"""
from collections.abc import Sequence

revision: str = "7fe2c9d40b18"
down_revision: str | Sequence[str] | None = ("c1e4b7a90d33", "a9b4e6d13f75")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
