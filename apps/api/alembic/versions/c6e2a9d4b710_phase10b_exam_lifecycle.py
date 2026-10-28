"""phase10b exam lifecycle

Revision ID: c6e2a9d4b710
Revises: b8e4f2a91d03
Create Date: 2026-10-28 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6e2a9d4b710'
down_revision: Union[str, Sequence[str], None] = 'b8e4f2a91d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/36 §5: result visibility (D14) and cancellation metadata (REQ-EXAM-010)
    op.add_column('exams', sa.Column('allow_view_result_after', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('exams', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('exams', sa.Column('cancelled_by', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_exams_cancelled_by', 'exams', 'users', ['cancelled_by'], ['id'], ondelete='SET NULL')
    op.add_column('exams', sa.Column('cancel_reason', sa.Text(), nullable=True))
    op.add_column('exam_participations', sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True))

    # D8: align enum values with domain §1.5 (expected to touch 0 rows)
    op.execute(sa.text("UPDATE exams SET status = 'ENDED' WHERE status = 'COMPLETED'"))
    op.execute(sa.text("UPDATE exam_participations SET status = 'EXPIRED' WHERE status = 'ABANDONED'"))
    op.create_check_constraint(op.f('ck_exams_status_valid'), 'exams',
                               "status IN ('DRAFT', 'SCHEDULED', 'ONGOING', 'ENDED', 'CANCELLED')")
    op.create_check_constraint(op.f('ck_exam_participations_status_valid'), 'exam_participations',
                               "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'EXPIRED', 'CANCELLED')")

    # Scheduler sweeps (D10)
    op.create_index('ix_exams_status_start_time', 'exams', ['status', 'start_time'])
    op.create_index('ix_exams_status_end_time', 'exams', ['status', 'end_time'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_exams_status_end_time', table_name='exams')
    op.drop_index('ix_exams_status_start_time', table_name='exams')
    op.drop_constraint(op.f('ck_exam_participations_status_valid'), 'exam_participations', type_='check')
    op.drop_constraint(op.f('ck_exams_status_valid'), 'exams', type_='check')
    op.execute(sa.text("UPDATE exam_participations SET status = 'ABANDONED' WHERE status = 'EXPIRED'"))
    op.execute(sa.text("UPDATE exam_participations SET status = 'IN_PROGRESS' WHERE status = 'CANCELLED'"))
    op.execute(sa.text("UPDATE exams SET status = 'COMPLETED' WHERE status = 'ENDED'"))
    op.drop_column('exam_participations', 'expired_at')
    op.drop_column('exams', 'cancel_reason')
    op.drop_constraint('fk_exams_cancelled_by', 'exams', type_='foreignkey')
    op.drop_column('exams', 'cancelled_by')
    op.drop_column('exams', 'cancelled_at')
    op.drop_column('exams', 'allow_view_result_after')
