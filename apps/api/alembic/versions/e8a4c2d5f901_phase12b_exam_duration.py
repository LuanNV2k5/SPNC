"""phase12b exam duration

Revision ID: e8a4c2d5f901
Revises: d7f3b1c2e845
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8a4c2d5f901'
down_revision: Union[str, Sequence[str], None] = 'd7f3b1c2e845'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # REQ-EXAM-001; meaning per docs/38 D7 (OQ-27): optional per-student limit
    op.add_column('exams', sa.Column('duration_minutes', sa.Integer(), nullable=True))
    op.create_check_constraint(op.f('ck_exams_duration_positive'), 'exams', 'duration_minutes IS NULL OR duration_minutes > 0')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_exams_duration_positive'), 'exams', type_='check')
    op.drop_column('exams', 'duration_minutes')
