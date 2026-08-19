"""add the signal side's five point-in-time tables (docs/infra/signal-side.md)

Every row is stamped first_seen_at — OUR poller's observation instant, the
only knowability stamp. ESPN's own wallclock is a data column beside it.
Plays and win-probability are append-only by ESPN play id; injury
observations are unique per (game, athlete, status) so on-change-only is
structural. Nothing derived is stored: signals are pure functions
(core/pulse/signals.py) over these rows.

Revision ID: a9b4e6d13f75
Revises: f7c3d9e04a62
Create Date: 2026-08-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = 'a9b4e6d13f75'
down_revision: str | None = 'f7c3d9e04a62'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'espn_live_plays',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('espn_game_id', sa.String(length=32), nullable=False),
        sa.Column('play_id', sa.String(length=32), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=True),
        sa.Column('period', sa.SmallInteger(), nullable=True),
        sa.Column('clock_seconds', sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column('wallclock', sa.DateTime(timezone=True), nullable=True),
        sa.Column('type_id', sa.String(length=16), nullable=True),
        sa.Column('type_text', sa.String(length=80), nullable=True),
        sa.Column('team_id', sa.String(length=16), nullable=True),
        sa.Column('athlete_id_1', sa.String(length=16), nullable=True),
        sa.Column('athlete_id_2', sa.String(length=16), nullable=True),
        sa.Column('shooting_play', sa.Boolean(), nullable=True),
        sa.Column('scoring_play', sa.Boolean(), nullable=True),
        sa.Column('points_attempted', sa.SmallInteger(), nullable=True),
        sa.Column('score_value', sa.SmallInteger(), nullable=True),
        sa.Column('home_score', sa.SmallInteger(), nullable=True),
        sa.Column('away_score', sa.SmallInteger(), nullable=True),
        sa.Column('text', sa.String(length=300), nullable=True),
        sa.Column('raw', JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('play_id', name='uq_elp_play_id'),
    )
    op.create_index('ix_elp_game', 'espn_live_plays', ['espn_game_id'])
    op.create_index('ix_elp_game_seq', 'espn_live_plays', ['espn_game_id', 'sequence'])
    op.create_index('ix_elp_first_seen', 'espn_live_plays', ['first_seen_at'])

    op.create_table(
        'espn_live_box_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('espn_game_id', sa.String(length=32), nullable=False),
        sa.Column('game_state', sa.String(length=8), nullable=True),
        sa.Column('season_type', sa.SmallInteger(), nullable=True),
        sa.Column('period', sa.SmallInteger(), nullable=True),
        sa.Column('clock_seconds', sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column('clock_source', sa.String(length=8), nullable=True),
        sa.Column('home_team_id', sa.String(length=16), nullable=True),
        sa.Column('away_team_id', sa.String(length=16), nullable=True),
        sa.Column('home_score', sa.SmallInteger(), nullable=True),
        sa.Column('away_score', sa.SmallInteger(), nullable=True),
        sa.Column('home_fgm', sa.SmallInteger(), nullable=True),
        sa.Column('home_fga', sa.SmallInteger(), nullable=True),
        sa.Column('home_tpm', sa.SmallInteger(), nullable=True),
        sa.Column('home_tpa', sa.SmallInteger(), nullable=True),
        sa.Column('home_ftm', sa.SmallInteger(), nullable=True),
        sa.Column('home_fta', sa.SmallInteger(), nullable=True),
        sa.Column('home_oreb', sa.SmallInteger(), nullable=True),
        sa.Column('home_turnovers', sa.SmallInteger(), nullable=True),
        sa.Column('away_fgm', sa.SmallInteger(), nullable=True),
        sa.Column('away_fga', sa.SmallInteger(), nullable=True),
        sa.Column('away_tpm', sa.SmallInteger(), nullable=True),
        sa.Column('away_tpa', sa.SmallInteger(), nullable=True),
        sa.Column('away_ftm', sa.SmallInteger(), nullable=True),
        sa.Column('away_fta', sa.SmallInteger(), nullable=True),
        sa.Column('away_oreb', sa.SmallInteger(), nullable=True),
        sa.Column('away_turnovers', sa.SmallInteger(), nullable=True),
        sa.Column('home_stats', JSONB(), nullable=True),
        sa.Column('away_stats', JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_elbs_game_seen', 'espn_live_box_snapshots',
                    ['espn_game_id', 'first_seen_at'])

    op.create_table(
        'espn_live_player_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('espn_game_id', sa.String(length=32), nullable=False),
        sa.Column('team_id', sa.String(length=16), nullable=True),
        sa.Column('athlete_id', sa.String(length=16), nullable=False),
        sa.Column('athlete_name', sa.String(length=80), nullable=True),
        sa.Column('minutes', sa.SmallInteger(), nullable=True),
        sa.Column('points', sa.SmallInteger(), nullable=True),
        sa.Column('fgm', sa.SmallInteger(), nullable=True),
        sa.Column('fga', sa.SmallInteger(), nullable=True),
        sa.Column('tpm', sa.SmallInteger(), nullable=True),
        sa.Column('tpa', sa.SmallInteger(), nullable=True),
        sa.Column('ftm', sa.SmallInteger(), nullable=True),
        sa.Column('fta', sa.SmallInteger(), nullable=True),
        sa.Column('rebounds', sa.SmallInteger(), nullable=True),
        sa.Column('assists', sa.SmallInteger(), nullable=True),
        sa.Column('turnovers', sa.SmallInteger(), nullable=True),
        sa.Column('fouls', sa.SmallInteger(), nullable=True),
        sa.Column('plus_minus', sa.SmallInteger(), nullable=True),
        sa.Column('starter', sa.Boolean(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('ejected', sa.Boolean(), nullable=True),
        sa.Column('did_not_play', sa.Boolean(), nullable=True),
        sa.Column('reason', sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_elps_game_seen', 'espn_live_player_snapshots',
                    ['espn_game_id', 'first_seen_at'])
    op.create_index('ix_elps_athlete', 'espn_live_player_snapshots', ['athlete_id'])

    op.create_table(
        'espn_live_win_probability',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('espn_game_id', sa.String(length=32), nullable=False),
        sa.Column('play_id', sa.String(length=32), nullable=False),
        sa.Column('home_win_pct', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('play_id', name='uq_elwp_play_id'),
    )
    op.create_index('ix_elwp_game', 'espn_live_win_probability', ['espn_game_id'])

    op.create_table(
        'espn_live_injury_observations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('espn_game_id', sa.String(length=32), nullable=False),
        sa.Column('team_id', sa.String(length=16), nullable=True),
        sa.Column('athlete_id', sa.String(length=16), nullable=False),
        sa.Column('athlete_name', sa.String(length=80), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('details', JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('espn_game_id', 'athlete_id', 'status',
                            name='uq_elio_game_athlete_status'),
    )
    op.create_index('ix_elio_game', 'espn_live_injury_observations', ['espn_game_id'])


def downgrade() -> None:
    op.drop_index('ix_elio_game', table_name='espn_live_injury_observations')
    op.drop_table('espn_live_injury_observations')
    op.drop_index('ix_elwp_game', table_name='espn_live_win_probability')
    op.drop_table('espn_live_win_probability')
    op.drop_index('ix_elps_athlete', table_name='espn_live_player_snapshots')
    op.drop_index('ix_elps_game_seen', table_name='espn_live_player_snapshots')
    op.drop_table('espn_live_player_snapshots')
    op.drop_index('ix_elbs_game_seen', table_name='espn_live_box_snapshots')
    op.drop_table('espn_live_box_snapshots')
    op.drop_index('ix_elp_first_seen', table_name='espn_live_plays')
    op.drop_index('ix_elp_game_seq', table_name='espn_live_plays')
    op.drop_index('ix_elp_game', table_name='espn_live_plays')
    op.drop_table('espn_live_plays')
