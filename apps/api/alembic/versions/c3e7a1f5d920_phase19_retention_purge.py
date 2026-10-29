"""phase19 retention purge

Revision ID: c3e7a1f5d920
Revises: b2d8f5a9c314
Create Date: 2026-10-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e7a1f5d920'
down_revision: Union[str, Sequence[str], None] = 'b2d8f5a9c314'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/45 §3.5: raw trace purged marker and exam retention hold (D4)
    op.add_column('coding_sessions', sa.Column('trace_purged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('exams', sa.Column('retention_hold', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_coding_sessions_purge_candidates', 'coding_sessions', ['ended_at'],
                    postgresql_where=sa.text('trace_purged_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_coding_sessions_purge_candidates', table_name='coding_sessions')
    op.drop_column('exams', 'retention_hold')
    op.drop_column('coding_sessions', 'trace_purged_at')
