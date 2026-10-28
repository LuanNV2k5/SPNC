import pytest
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, select, text, inspect
from sqlalchemy.orm import sessionmaker

from app.models.user import User, RoleEnum
from app.models.problem import Problem, SupportedLanguage
from app.models.session import CodingSession, PracticeAttempt, SessionStatus
from app.models.trace import TraceEvent, TraceEventType
# Model import under test - will fail before model is declared (RED)
from app.models.observation import TraceSignalOutbox

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set")

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(scope="function")
def setup_models(db_session):
    student = User(
        email=f"stu_{uuid.uuid4()}@test.com", 
        password_hash="hash", 
        role=RoleEnum.STUDENT, 
        username=f"stu_{uuid.uuid4()}", 
        full_name="Student"
    )
    db_session.add(student)
    db_session.flush()

    prob = Problem(title="Test", description="Test", owner_id=student.id)
    db_session.add(prob)
    db_session.flush()

    attempt = PracticeAttempt(student_id=student.id, problem_id=prob.id)
    db_session.add(attempt)
    db_session.flush()

    session = CodingSession(
        student_id=student.id,
        problem_id=prob.id,
        language=SupportedLanguage.PYTHON3,
        opened_at=datetime.now(timezone.utc),
        status=SessionStatus.ACTIVE,
        practice_attempt_id=attempt.id
    )
    db_session.add(session)
    db_session.commit()
    return student, prob, session

def test_trace_outbox_model_declaration():
    """Verify ORM model declaration attributes, table name, and constraints."""
    assert TraceSignalOutbox.__tablename__ == "trace_signal_outbox"
    columns = {c.name for c in TraceSignalOutbox.__table__.columns}
    expected_cols = {
        "id", "session_id", "event_id", "event_type", 
        "sequence_number", "server_timestamp", "created_at"
    }
    assert expected_cols.issubset(columns)

    # Verify foreign key ondelete is RESTRICT
    fks = {fk.target_fullname: fk.ondelete for fk in TraceSignalOutbox.__table__.foreign_keys}
    assert fks.get("coding_sessions.id") == "RESTRICT"
    assert fks.get("trace_events.id") == "RESTRICT"

def test_trace_outbox_table_and_indexes_exist(db_session):
    """Verify table schema and indexes created by Alembic migration."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "trace_signal_outbox" in tables

    # Check unique constraint / index on event_id
    unique_constraints = inspector.get_unique_constraints("trace_signal_outbox")
    uq_names = [uc["name"] for uc in unique_constraints]
    assert "uq_trace_signal_outbox_event_id" in uq_names or any("event_id" in uc["column_names"] for uc in unique_constraints)

def test_trace_events_trigger_enqueues_meaningful(db_session, setup_models):
    """Verify database trigger automatically enqueues meaningful events."""
    _, _, session = setup_models
    now = datetime.now(timezone.utc)

    # 1. Insert meaningful events
    e1 = TraceEvent(
        session_id=session.id,
        sequence_number=1,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp1",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    e2 = TraceEvent(
        session_id=session.id,
        sequence_number=2,
        event_type=TraceEventType.RUN_REQUESTED,
        canonical_fingerprint="fp2",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    e3 = TraceEvent(
        session_id=session.id,
        sequence_number=3,
        event_type=TraceEventType.SUBMISSION_CREATED,
        canonical_fingerprint="fp3",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add_all([e1, e2, e3])
    db_session.commit()

    # Query outbox
    outbox_items = db_session.scalars(
        select(TraceSignalOutbox)
        .where(TraceSignalOutbox.session_id == session.id)
        .order_by(TraceSignalOutbox.sequence_number.asc())
    ).all()

    assert len(outbox_items) == 3
    assert outbox_items[0].event_type == TraceEventType.EDITOR_CHANGED.value
    assert outbox_items[0].event_id == e1.id
    assert outbox_items[1].event_type == TraceEventType.RUN_REQUESTED.value
    assert outbox_items[1].event_id == e2.id
    assert outbox_items[2].event_type == TraceEventType.SUBMISSION_CREATED.value
    assert outbox_items[2].event_id == e3.id

def test_trace_events_trigger_ignores_non_meaningful(db_session, setup_models):
    """Verify trigger ignores non-meaningful events (PROBLEM_OPENED, SESSION_CHECKPOINT, SNAPSHOT_CREATED)."""
    _, _, session = setup_models
    now = datetime.now(timezone.utc)

    e_po = TraceEvent(
        session_id=session.id,
        sequence_number=10,
        event_type=TraceEventType.PROBLEM_OPENED,
        canonical_fingerprint="fp_po",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    e_cp = TraceEvent(
        session_id=session.id,
        sequence_number=11,
        event_type=TraceEventType.SESSION_CHECKPOINT,
        canonical_fingerprint="fp_cp",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    e_sc = TraceEvent(
        session_id=session.id,
        sequence_number=12,
        event_type=TraceEventType.SNAPSHOT_CREATED,
        canonical_fingerprint="fp_sc",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add_all([e_po, e_cp, e_sc])
    db_session.commit()

    outbox_non_meaningful = db_session.scalars(
        select(TraceSignalOutbox).where(
            TraceSignalOutbox.session_id == session.id,
            TraceSignalOutbox.sequence_number.in_([10, 11, 12])
        )
    ).all()
    assert len(outbox_non_meaningful) == 0

def test_trace_outbox_unique_event_constraint(db_session, setup_models):
    """Verify UNIQUE(event_id) constraint prevents duplicate outbox entries."""
    _, _, session = setup_models
    now = datetime.now(timezone.utc)

    # Insert a meaningful event (trigger enqueues row 1)
    e = TraceEvent(
        session_id=session.id,
        sequence_number=20,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp20",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add(e)
    db_session.commit()

    # Attempt manual duplicate insertion of same event_id
    dup = TraceSignalOutbox(
        session_id=session.id,
        event_id=e.id,
        event_type=TraceEventType.EDITOR_CHANGED.value,
        sequence_number=20,
        server_timestamp=now
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_trace_outbox_foreign_key_restrict(db_session, setup_models):
    """Verify ON DELETE RESTRICT prevents deleting CodingSession or TraceEvent while outbox row exists."""
    _, _, session = setup_models
    now = datetime.now(timezone.utc)

    e = TraceEvent(
        session_id=session.id,
        sequence_number=30,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp30",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add(e)
    db_session.commit()

    # Attempt to delete TraceEvent directly while referenced by outbox
    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM trace_events WHERE id = :id"), {"id": e.id})
        db_session.commit()
    db_session.rollback()

def test_trace_outbox_bootstrap_idempotency(db_session, setup_models):
    """Verify bootstrap query safely populates historical events and is idempotent."""
    _, _, session = setup_models
    now = datetime.now(timezone.utc)

    # Disable trigger temporarily to simulate pre-existing historical events not in outbox
    db_session.execute(text("ALTER TABLE trace_events DISABLE TRIGGER trg_enqueue_trace_signal_outbox;"))
    db_session.commit()

    try:
        e_hist = TraceEvent(
            session_id=session.id,
            sequence_number=40,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint="fp40",
            client_timestamp=now,
            server_timestamp=now,
            payload={}
        )
        db_session.add(e_hist)
        db_session.commit()

        # Check outbox has 0 rows for sequence 40
        outbox_count = db_session.scalar(
            select(text("COUNT(*)")).select_from(text("trace_signal_outbox")).where(text("event_id = :id")),
            {"id": e_hist.id}
        )
        assert outbox_count == 0
    finally:
        db_session.execute(text("ALTER TABLE trace_events ENABLE TRIGGER trg_enqueue_trace_signal_outbox;"))
        db_session.commit()

    # Run the bootstrap query
    bootstrap_sql = """
    INSERT INTO trace_signal_outbox (
        session_id, event_id, event_type, sequence_number, server_timestamp
    )
    SELECT session_id, id, event_type, sequence_number, server_timestamp
    FROM trace_events
    WHERE event_type IN ('EDITOR_CHANGED', 'RUN_REQUESTED', 'SUBMISSION_CREATED')
      AND id = :target_id
    ON CONFLICT (event_id) DO NOTHING;
    """
    db_session.execute(text(bootstrap_sql), {"target_id": e_hist.id})
    db_session.commit()

    # Verify event is now in outbox
    item = db_session.scalar(
        select(TraceSignalOutbox).where(TraceSignalOutbox.event_id == e_hist.id)
    )
    assert item is not None
    assert item.sequence_number == 40

    # Run bootstrap query a second time (idempotency check)
    db_session.execute(text(bootstrap_sql), {"target_id": e_hist.id})
    db_session.commit()

    count_after = db_session.scalar(
        select(text("COUNT(*)")).select_from(text("trace_signal_outbox")).where(text("event_id = :id")),
        {"id": e_hist.id}
    )
    assert count_after == 1

def test_trace_outbox_concurrent_session_locking(db_session, setup_models):
    """Verify session-level locking with FOR UPDATE SKIP LOCKED serializes session access."""
    _, _, session1 = setup_models
    now = datetime.now(timezone.utc)

    # Insert event for session 1
    e1 = TraceEvent(
        session_id=session1.id,
        sequence_number=50,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp50",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add(e1)
    db_session.commit()

    # Session 2 setup
    attempt2 = PracticeAttempt(student_id=session1.student_id, problem_id=session1.problem_id)
    db_session.add(attempt2)
    db_session.flush()
    session2 = CodingSession(
        student_id=session1.student_id,
        problem_id=session1.problem_id,
        language=SupportedLanguage.PYTHON3,
        opened_at=now,
        status=SessionStatus.ACTIVE,
        practice_attempt_id=attempt2.id
    )
    db_session.add(session2)
    db_session.flush()
    e2 = TraceEvent(
        session_id=session2.id,
        sequence_number=1,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp51",
        client_timestamp=now,
        server_timestamp=now,
        payload={}
    )
    db_session.add(e2)
    db_session.commit()

    # Open secondary DB connection to simulate concurrent worker
    sess2 = TestingSessionLocal()
    try:
        # Worker 1 locks session 1
        claim_stmt = (
            select(CodingSession.id)
            .where(CodingSession.id.in_(select(TraceSignalOutbox.session_id)))
            .order_by(CodingSession.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        locked_s1 = db_session.scalar(claim_stmt)
        assert locked_s1 is not None

        # Worker 2 attempts claiming with SKIP LOCKED
        locked_s2 = sess2.scalar(claim_stmt)
        assert locked_s2 is not None
        # Must be partitioned to different sessions
        assert locked_s1 != locked_s2
    finally:
        sess2.rollback()
        sess2.close()
