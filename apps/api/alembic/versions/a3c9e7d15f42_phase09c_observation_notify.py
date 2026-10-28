"""phase09c observation notify triggers

Revision ID: a3c9e7d15f42
Revises: f7b2d4e61c38
Create Date: 2026-10-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e7d15f42'
down_revision: Union[str, Sequence[str], None] = 'f7b2d4e61c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # docs/35 D4: id-only NOTIFY payloads, delivered by PostgreSQL only when the transaction commits.
    # Payloads never contain source code or evidence (NFR-REALTIME-002).
    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION trg_notify_signal_created() RETURNS TRIGGER AS $$
    BEGIN
        PERFORM pg_notify('spnc_observation', json_build_object(
            'type', 'signal.created', 'signal_id', NEW.id, 'session_id', NEW.session_id,
            'student_id', NEW.student_id, 'signal_type', NEW.signal_type)::text);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
    CREATE TRIGGER trg_attention_signals_notify AFTER INSERT ON attention_signals
    FOR EACH ROW EXECUTE FUNCTION trg_notify_signal_created();
    """))

    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION trg_notify_run_finished() RETURNS TRIGGER AS $$
    BEGIN
        PERFORM pg_notify('spnc_observation', json_build_object(
            'type', 'run.completed', 'run_id', NEW.id, 'session_id', NEW.session_id,
            'student_id', (SELECT student_id FROM coding_sessions WHERE id = NEW.session_id),
            'verdict', NEW.verdict, 'status', NEW.status)::text);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
    CREATE TRIGGER trg_runs_notify AFTER UPDATE OF status ON runs
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status IN ('COMPLETED', 'FAILED_INTERNAL'))
    EXECUTE FUNCTION trg_notify_run_finished();
    """))

    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION trg_notify_session_state() RETURNS TRIGGER AS $$
    BEGIN
        PERFORM pg_notify('spnc_observation', json_build_object(
            'type', 'session.state', 'session_id', NEW.id, 'student_id', NEW.student_id,
            'status', NEW.status)::text);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
    CREATE TRIGGER trg_coding_sessions_notify AFTER UPDATE OF status ON coding_sessions
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION trg_notify_session_state();
    """))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_coding_sessions_notify ON coding_sessions;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_notify_session_state();"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_runs_notify ON runs;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_notify_run_finished();"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_attention_signals_notify ON attention_signals;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_notify_signal_created();"))
