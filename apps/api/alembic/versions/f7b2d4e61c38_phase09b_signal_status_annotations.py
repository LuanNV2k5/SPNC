"""phase09b signal status and annotations

Revision ID: f7b2d4e61c38
Revises: e5a1c3f09b27
Create Date: 2026-10-28 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2d4e61c38'
down_revision: Union[str, Sequence[str], None] = 'e5a1c3f09b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/35 §5: attention query (REQ-OBS-001) filters by student and NEW status
    op.create_index('ix_attention_signals_student_status', 'attention_signals', ['student_id', 'status'])
    # docs/35 D7: annotation soft delete
    op.add_column('teacher_annotations', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('teacher_annotations', 'deleted_at')
    op.drop_index('ix_attention_signals_student_status', table_name='attention_signals')
