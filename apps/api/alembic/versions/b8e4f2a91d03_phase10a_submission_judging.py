"""phase10a submission judging

Revision ID: b8e4f2a91d03
Revises: a3c9e7d15f42
Create Date: 2026-10-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8e4f2a91d03'
down_revision: Union[str, Sequence[str], None] = 'a3c9e7d15f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/36 §5: judging fields and exam linkage on submissions
    op.add_column('submissions', sa.Column('exam_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_submissions_exam_id', 'submissions', 'exams', ['exam_id'], ['id'], ondelete='RESTRICT')
    op.add_column('submissions', sa.Column('source', sa.String(length=30), server_default='STUDENT', nullable=False))
    op.add_column('submissions', sa.Column('judge_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('submissions', sa.Column('execution_generation', sa.Integer(), server_default='0', nullable=False))
    op.add_column('submissions', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_submissions_source_valid', 'submissions', "source IN ('STUDENT', 'SYSTEM_EXAM_TIMEOUT')")
    op.create_check_constraint('ck_submissions_generation_non_negative', 'submissions', 'execution_generation >= 0')
    op.create_index('ix_submissions_exam_student_problem', 'submissions', ['exam_id', 'student_id', 'problem_id'])
    op.create_index('ix_submissions_status', 'submissions', ['status'])

    # docs/36 10A realtime: id-only notification when judging finishes (docs/35 D4 channel)
    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION trg_notify_submission_judged() RETURNS TRIGGER AS $$
    BEGIN
        PERFORM pg_notify('spnc_observation', json_build_object(
            'type', 'submission.judged', 'submission_id', NEW.id, 'session_id', NEW.session_id,
            'student_id', NEW.student_id, 'verdict', NEW.verdict)::text);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
    CREATE TRIGGER trg_submissions_notify AFTER UPDATE OF status ON submissions
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status IN ('COMPLETED', 'FAILED_INTERNAL'))
    EXECUTE FUNCTION trg_notify_submission_judged();
    """))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_submissions_notify ON submissions;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_notify_submission_judged();"))
    op.drop_index('ix_submissions_status', table_name='submissions')
    op.drop_index('ix_submissions_exam_student_problem', table_name='submissions')
    op.drop_constraint('ck_submissions_generation_non_negative', 'submissions', type_='check')
    op.drop_constraint('ck_submissions_source_valid', 'submissions', type_='check')
    op.drop_column('submissions', 'lease_expires_at')
    op.drop_column('submissions', 'execution_generation')
    op.drop_column('submissions', 'judge_result')
    op.drop_column('submissions', 'source')
    op.drop_constraint('fk_submissions_exam_id', 'submissions', type_='foreignkey')
    op.drop_column('submissions', 'exam_id')
