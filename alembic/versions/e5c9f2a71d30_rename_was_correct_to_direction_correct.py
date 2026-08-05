"""rename predictions.was_correct to direction_correct

The column answers "was the model probability on the right side of 0.50?",
which is not "did the bet win?" — most contracts are lopsided, so the old name
read as performance while measuring something nearly free (84% vs an actual
38.5% bet win rate on the same rows; findings C5). The new name says what it
is: a direction diagnostic, never a money metric, and it must not appear in
any aggregate presented as performance.

A pure rename — no data changes, no type changes.

Revision ID: e5c9f2a71d30
Revises: b7e2c9d41f80
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e5c9f2a71d30'
down_revision: Union[str, None] = 'b7e2c9d41f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('predictions', 'was_correct', new_column_name='direction_correct')


def downgrade() -> None:
    op.alter_column('predictions', 'direction_correct', new_column_name='was_correct')
