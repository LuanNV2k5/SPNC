"""phase08e session finalization

Revision ID: e5a1c3f09b27
Revises: c4819d7a2e10
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1c3f09b27'
down_revision: Union[str, Sequence[str], None] = 'c4819d7a2e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # REQ-SIGNAL-001 / REQ-TRACE-015: server-computed session termination facts.
    # Sessions ended before Phase 08E keep NULLs (D9: no backfill).
    op.add_column('coding_sessions', sa.Column('final_loc', sa.Integer(), nullable=True))
    op.add_column('coding_sessions', sa.Column('working_time_seconds', sa.Integer(), nullable=True))
    op.add_column('coding_sessions', sa.Column('final_code_snapshot_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_coding_sessions_final_code_snapshot_id', 'coding_sessions', 'code_snapshots',
        ['final_code_snapshot_id'], ['id'], ondelete='RESTRICT'
    )
    op.create_check_constraint('ck_coding_sessions_final_loc_non_negative', 'coding_sessions', 'final_loc >= 0')
    op.create_check_constraint('ck_coding_sessions_working_time_non_negative', 'coding_sessions', 'working_time_seconds >= 0')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_coding_sessions_working_time_non_negative', 'coding_sessions', type_='check')
    op.drop_constraint('ck_coding_sessions_final_loc_non_negative', 'coding_sessions', type_='check')
    op.drop_constraint('fk_coding_sessions_final_code_snapshot_id', 'coding_sessions', type_='foreignkey')
    op.drop_column('coding_sessions', 'final_code_snapshot_id')
    op.drop_column('coding_sessions', 'working_time_seconds')
    op.drop_column('coding_sessions', 'final_loc')
