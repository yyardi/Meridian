"""service_heartbeats.markets_seen: what the sweep SAW, not what it wrote

`rows_written` already distinguishes "the process is alive" from "the process
produced nothing". It cannot distinguish the two reasons for producing nothing:
the venue's board was empty, or the board was full and no price changed. Both
write zero rows, and on 2026-09-14 the whole venue board emptied at 09:35Z while
every container stayed up and every log stayed clean.

Nothing we own could tell those apart, because the count of markets the sweep
observed is logged and never stored. This column stores it.

The model's own docstring already makes this argument one level up: "Every
writer's silence is ambiguous from its data alone ... 'no rows' read as 'no
game'." It removed the ambiguity for LIVENESS and stopped short of board
CONTENT. Credit to meridian-7f for noticing that the same argument had not been
carried down. Nullable, because a writer with no board (the scheduler) has no
honest value to put here and NULL means "not measured", which is exactly what
rows_written already means by the same convention.

Revision ID: a1c7e35b9d20
Revises: c2d9a7e51f83
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c7e35b9d20"
down_revision = "c2d9a7e51f83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_heartbeats", sa.Column("markets_seen", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_heartbeats", "markets_seen")
