"""phase08d trace signal outbox

Revision ID: c4819d7a2e10
Revises: 51377aaa532a
Create Date: 2026-10-24 20:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4819d7a2e10'
down_revision: Union[str, Sequence[str], None] = '51377aaa532a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table trace_signal_outbox with ON DELETE RESTRICT and CURRENT_TIMESTAMP default
    op.create_table(
        'trace_signal_outbox',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('server_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['coding_sessions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['event_id'], ['trace_events.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_trace_signal_outbox_event_id')
    )
    op.create_index('ix_trace_signal_outbox_session_id', 'trace_signal_outbox', ['session_id'])
    op.create_index('ix_trace_signal_outbox_session_seq', 'trace_signal_outbox', ['session_id', 'sequence_number'])

    # 2. Create trigger function to enqueue meaningful events atomically upon ingestion
    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION trg_trace_events_enqueue_outbox()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.event_type IN ('EDITOR_CHANGED', 'RUN_REQUESTED', 'SUBMISSION_CREATED') THEN
            INSERT INTO trace_signal_outbox (
                session_id, event_id, event_type, sequence_number, server_timestamp
            ) VALUES (
                NEW.session_id, NEW.id, NEW.event_type, NEW.sequence_number, NEW.server_timestamp
            )
            ON CONFLICT (event_id) DO NOTHING;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """))

    # 3. Attach trigger to trace_events BEFORE historical bootstrap
    op.execute(sa.text("""
    CREATE TRIGGER trg_enqueue_trace_signal_outbox
    AFTER INSERT ON trace_events
    FOR EACH ROW EXECUTE FUNCTION trg_trace_events_enqueue_outbox();
    """))

    # 4. Safe historical bootstrap with ON CONFLICT DO NOTHING
    op.execute(sa.text("""
    INSERT INTO trace_signal_outbox (
        session_id, event_id, event_type, sequence_number, server_timestamp
    )
    SELECT session_id, id, event_type, sequence_number, server_timestamp
    FROM trace_events
    WHERE event_type IN ('EDITOR_CHANGED', 'RUN_REQUESTED', 'SUBMISSION_CREATED')
    ORDER BY server_timestamp ASC, sequence_number ASC
    ON CONFLICT (event_id) DO NOTHING;
    """))


def downgrade() -> None:
    # Drop trigger and function
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_enqueue_trace_signal_outbox ON trace_events;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_trace_events_enqueue_outbox();"))

    # Drop indexes and table
    op.drop_index('ix_trace_signal_outbox_session_seq', table_name='trace_signal_outbox')
    op.drop_index('ix_trace_signal_outbox_session_id', table_name='trace_signal_outbox')
    op.drop_table('trace_signal_outbox')
