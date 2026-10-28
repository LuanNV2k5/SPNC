"""phase13b per-session idle threshold

Revision ID: a1c7e4f8b213
Revises: f9b5d3e6a012
Create Date: 2026-10-29 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e4f8b213'
down_revision: Union[str, Sequence[str], None] = 'f9b5d3e6a012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # REQ-USER-007, docs/39 D3: threshold captured at session creation; NULL = deployment default
    op.add_column('coding_sessions', sa.Column('idle_threshold_seconds', sa.Integer(), nullable=True))
    op.create_check_constraint(op.f('ck_coding_sessions_idle_threshold_range'), 'coding_sessions',
                               'idle_threshold_seconds IS NULL OR (idle_threshold_seconds BETWEEN 60 AND 3600)')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_coding_sessions_idle_threshold_range'), 'coding_sessions', type_='check')
    op.drop_column('coding_sessions', 'idle_threshold_seconds')
