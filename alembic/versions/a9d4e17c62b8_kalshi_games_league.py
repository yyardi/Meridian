"""kalshi_games.league — identity becomes (league, game_key) for GRIDIRON

Seven Kalshi team codes exist in both the WNBA and NFL tables (ATL, CHI,
DAL, IND, LV, MIN, SEA), so a game_key alone cannot identify a game once
NFL series record: a same-date cross-league pair (SEA/ATL on one Sunday)
would silently merge two different games into one row and corrupt the
Polymarket link. Existing rows are all WNBA (server_default backfills
them); child tables (kalshi_contracts / kalshi_snapshots) stay keyed by
game_key and disambiguate via their series_ticker column.

Revision ID: a9d4e17c62b8
Revises: e1a7c3f60d94
Create Date: 2026-09-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a9d4e17c62b8'
down_revision: str | None = 'e1a7c3f60d94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('kalshi_games', sa.Column(
        'league', sa.String(length=8), nullable=False,
        server_default='wnba'))
    op.drop_constraint('kalshi_games_game_key_key', 'kalshi_games',
                       type_='unique')
    op.create_unique_constraint('uq_kalshi_games_league_game_key',
                                'kalshi_games', ['league', 'game_key'])


def downgrade() -> None:
    op.drop_constraint('uq_kalshi_games_league_game_key', 'kalshi_games',
                       type_='unique')
    op.create_unique_constraint('kalshi_games_game_key_key',
                                'kalshi_games', ['game_key'])
    op.drop_column('kalshi_games', 'league')
