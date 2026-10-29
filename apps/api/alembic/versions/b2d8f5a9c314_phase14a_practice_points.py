"""phase14a practice points on the point_transactions ledger

Revision ID: b2d8f5a9c314
Revises: a1c7e4f8b213
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d8f5a9c314'
down_revision: Union[str, Sequence[str], None] = 'a1c7e4f8b213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # OQ-16 / docs/40 Q1: reuse the Phase 02 ledger; link awards to their problem and submission
    op.add_column('point_transactions', sa.Column('problem_id', sa.UUID(), nullable=True))
    op.add_column('point_transactions', sa.Column('submission_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_point_transactions_problem_id', 'point_transactions', 'problems', ['problem_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_point_transactions_submission_id', 'point_transactions', 'submissions', ['submission_id'], ['id'], ondelete='RESTRICT')
    # Once per student and problem for practice awards
    op.create_index('uq_point_transactions_practice_award', 'point_transactions', ['student_id', 'problem_id'], unique=True,
                    postgresql_where=sa.text("reason = 'PRACTICE_ACCEPTED'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_point_transactions_practice_award', table_name='point_transactions')
    op.drop_constraint('fk_point_transactions_submission_id', 'point_transactions', type_='foreignkey')
    op.drop_constraint('fk_point_transactions_problem_id', 'point_transactions', type_='foreignkey')
    op.drop_column('point_transactions', 'submission_id')
    op.drop_column('point_transactions', 'problem_id')
