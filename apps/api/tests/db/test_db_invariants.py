import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, DataError

from app.db.base import Base
from app.models import (
    User, RoleEnum, AccountStatus, TraceEvent, TraceEventType,
    Run, RunStatus, RunVerdict, CodingSession, CodeSnapshot, SessionStatus,
    Problem, ProblemVisibility, SupportedLanguage, Class, ClassMembership
)

# Connect to Postgres
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL environment variable must be set for PostgreSQL tests.")

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def db_session():
    session = TestingSessionLocal()
    # clean up all tables
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()

    yield session

    session.close()

def setup_basic_models(db_session):
    user_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    owner = User(
        id=owner_id, username=f"owner_{owner_id}", email=f"owner_{owner_id}@test.com",
        password_hash="hash", full_name="Owner", role=RoleEnum.TEACHER, status=AccountStatus.ACTIVE,
        force_password_change=False
    )
    user = User(
        id=user_id, username=f"user_{user_id}", email=f"user_{user_id}@test.com",
        password_hash="hash", full_name="User", role=RoleEnum.STUDENT, status=AccountStatus.ACTIVE,
        force_password_change=False
    )

    problem = Problem(
        id=uuid.uuid4(), title="Test Problem", description="Desc",
        owner_id=owner_id, visibility=ProblemVisibility.PUBLIC, time_limit_ms=1000,
        memory_limit_mb=256, supported_languages=[SupportedLanguage.PYTHON3]
    )

    from app.models import PracticeAttempt
    practice = PracticeAttempt(
        id=uuid.uuid4(), student_id=user_id, problem_id=problem.id,
        total_score=0, is_completed=False
    )

    coding_session = CodingSession(
        id=uuid.uuid4(), student_id=user_id, problem_id=problem.id,
        language=SupportedLanguage.PYTHON3, is_exam_context=False,
        practice_attempt_id=practice.id,
        status=SessionStatus.ACTIVE, opened_at=datetime.now(timezone.utc)
    )

    code_snapshot = CodeSnapshot(
        id=uuid.uuid4(), session_id=coding_session.id, reason="TEST",
        language=SupportedLanguage.PYTHON3, source_hash="hash",
        object_key="key", line_count=10
    )

    db_session.add_all([owner, user, problem, practice, coding_session, code_snapshot])
    db_session.commit()

    return coding_session.id, code_snapshot.id, user_id, problem.id

def test_R07_R08_R09_trace_sequence(db_session):
    """R07 sequence 0 rejected, R08 sequence -1 rejected, R09 out-of-order accepted"""
    session_id, _, _, _ = setup_basic_models(db_session)

    # R07: Sequence 0 rejected
    event0 = TraceEvent(
        session_id=session_id, sequence_number=0, event_type=TraceEventType.PROBLEM_OPENED,
        canonical_fingerprint="fp0", client_timestamp=datetime.now(timezone.utc),
        server_timestamp=datetime.now(timezone.utc), payload={}
    )
    db_session.add(event0)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # R08: Sequence -1 rejected
    event_minus1 = TraceEvent(
        session_id=session_id, sequence_number=-1, event_type=TraceEventType.PROBLEM_OPENED,
        canonical_fingerprint="fp_minus1", client_timestamp=datetime.now(timezone.utc),
        server_timestamp=datetime.now(timezone.utc), payload={}
    )
    db_session.add(event_minus1)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # R09: Out-of-order sequence 1,3,2 accepted
    e1 = TraceEvent(session_id=session_id, sequence_number=1, event_type=TraceEventType.PROBLEM_OPENED, canonical_fingerprint="fp1", client_timestamp=datetime.now(timezone.utc), server_timestamp=datetime.now(timezone.utc), payload={})
    e3 = TraceEvent(session_id=session_id, sequence_number=3, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp3", client_timestamp=datetime.now(timezone.utc), server_timestamp=datetime.now(timezone.utc), payload={})

    db_session.add_all([e1, e3])
    db_session.commit()

    e2 = TraceEvent(session_id=session_id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=datetime.now(timezone.utc), server_timestamp=datetime.now(timezone.utc), payload={})
    db_session.add(e2)
    db_session.commit()

    count = db_session.query(TraceEvent).filter_by(session_id=session_id).count()
    assert count == 3

def test_R10_trace_exact_duplicate_batch_commits(db_session):
    """R10 exact duplicate batch commits correctly using INSERT ON CONFLICT DO NOTHING"""
    session_id, _, _, _ = setup_basic_models(db_session)

    # Existing 100/A
    db_session.execute(text(
        "INSERT INTO trace_events (id, session_id, sequence_number, event_type, canonical_fingerprint, client_timestamp, server_timestamp, payload) "
        "VALUES (:id, :session_id, 100, 'PROBLEM_OPENED', 'A', :ts, :ts, '{}')"
    ), {"id": uuid.uuid4(), "session_id": session_id, "ts": datetime.now(timezone.utc)})
    db_session.commit()

    # Incoming batch 100/A, 101/B, 102/C
    # PostgreSQL INSERT ON CONFLICT DO NOTHING handles exact duplicate inserts gracefully per row
    stmt = text("""
    INSERT INTO trace_events (id, session_id, sequence_number, event_type, canonical_fingerprint, client_timestamp, server_timestamp, payload)
    VALUES
    (:id1, :session_id, 100, 'PROBLEM_OPENED', 'A', :ts, :ts, '{}'),
    (:id2, :session_id, 101, 'PROBLEM_OPENED', 'B', :ts, :ts, '{}'),
    (:id3, :session_id, 102, 'PROBLEM_OPENED', 'C', :ts, :ts, '{}')
    ON CONFLICT (session_id, sequence_number) DO NOTHING
    """)
    db_session.execute(stmt, {
        "id1": uuid.uuid4(), "id2": uuid.uuid4(), "id3": uuid.uuid4(),
        "session_id": session_id, "ts": datetime.now(timezone.utc)
    })
    db_session.commit()

    count = db_session.query(TraceEvent).filter_by(session_id=session_id).count()
    assert count == 3

def test_R11_trace_conflicting_duplicate_batch_rolls_back(db_session):
    """R11 conflicting duplicate batch rolls back fully"""
    session_id, _, _, _ = setup_basic_models(db_session)

    # Existing 100/A
    db_session.execute(text(
        "INSERT INTO trace_events (id, session_id, sequence_number, event_type, canonical_fingerprint, client_timestamp, server_timestamp, payload) "
        "VALUES (:id, :session_id, 100, 'PROBLEM_OPENED', 'A', :ts, :ts, '{}')"
    ), {"id": uuid.uuid4(), "session_id": session_id, "ts": datetime.now(timezone.utc)})
    db_session.commit()

    # Incoming batch 100/X, 101/B
    # This must cause IntegrityError since we check canonical_fingerprint equality or just let basic UNIQUE constraint fire
    # Since ON CONFLICT DOES NOTHING masks conflict, we need a way to detect conflict, or if we don't use DO NOTHING on batch ingestion.
    # The requirement says "conflicting duplicate batch rolls back fully", which means we try to insert without DO NOTHING and catch IntegrityError,
    # or we handle it in app code. Since we test DB invariants, we test that simple INSERT of conflict fails.

    stmt = text("""
    INSERT INTO trace_events (id, session_id, sequence_number, event_type, canonical_fingerprint, client_timestamp, server_timestamp, payload)
    VALUES
    (:id1, :session_id, 100, 'PROBLEM_OPENED', 'X', :ts, :ts, '{}'),
    (:id2, :session_id, 101, 'PROBLEM_OPENED', 'B', :ts, :ts, '{}')
    """)
    with pytest.raises(IntegrityError):
        db_session.execute(stmt, {
            "id1": uuid.uuid4(), "id2": uuid.uuid4(),
            "session_id": session_id, "ts": datetime.now(timezone.utc)
        })
        db_session.commit()
    db_session.rollback()

    count = db_session.query(TraceEvent).filter_by(session_id=session_id).count()
    assert count == 1 # Only 100/A remains, 101/B did not commit

def test_R12_R13_R14_R15_run_fencing(db_session):
    """R12 normal claim, R13 healthy not stolen, R14 stale recovery, R15 new generation"""
    session_id, snapshot_id, _, _ = setup_basic_models(db_session)
    run_id = uuid.uuid4()

    run = Run(
        id=run_id, session_id=session_id, snapshot_id=snapshot_id,
        status=RunStatus.PENDING, execution_generation=0
    )
    db_session.add(run)
    db_session.commit()

    # R12 W1 normal PENDING claim succeeds
    stmt = text("""
    UPDATE runs SET status = 'RUNNING', execution_generation = execution_generation + 1, lease_expires_at = :lease
    WHERE id = :id AND status = 'PENDING'
    """)
    res = db_session.execute(stmt, {"id": run_id, "lease": datetime.now(timezone.utc) + timedelta(minutes=5)})
    db_session.commit()
    assert res.rowcount == 1

    # R13 W2 cannot steal healthy RUNNING
    res2 = db_session.execute(stmt, {"id": run_id, "lease": datetime.now(timezone.utc) + timedelta(minutes=5)})
    db_session.commit()
    assert res2.rowcount == 0 # Cannot steal

    # R14 stale recovery works & R15 new generation
    # Expire lease
    db_session.execute(text("UPDATE runs SET lease_expires_at = :lease WHERE id = :id"), {"id": run_id, "lease": datetime.now(timezone.utc) - timedelta(minutes=1)})
    db_session.commit()

    stmt_reconcile = text("""
    UPDATE runs SET status = 'RUNNING', execution_generation = execution_generation + 1, lease_expires_at = :new_lease
    WHERE id = :id AND status = 'RUNNING' AND lease_expires_at < :now
    """)
    res_rec = db_session.execute(stmt_reconcile, {"id": run_id, "new_lease": datetime.now(timezone.utc) + timedelta(minutes=5), "now": datetime.now(timezone.utc)})
    db_session.commit()
    assert res_rec.rowcount == 1

    # Verify generation is 2 (R15)
    gen = db_session.execute(text("SELECT execution_generation FROM runs WHERE id = :id"), {"id": run_id}).scalar()
    assert gen == 2

def test_R16_R17_authoritative_result_CAS(db_session):
    """R16 W2 CAS succeeds, R17 stale W1 updates 0 rows"""
    session_id, snapshot_id, _, _ = setup_basic_models(db_session)
    run_id = uuid.uuid4()

    run = Run(
        id=run_id, session_id=session_id, snapshot_id=snapshot_id,
        status=RunStatus.RUNNING, execution_generation=2, lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db_session.add(run)
    db_session.commit()

    # R16 W2 CAS succeeds
    stmt_w2 = text("""
    UPDATE runs SET status = 'COMPLETED', verdict = 'ACCEPTED'
    WHERE id = :id AND status = 'RUNNING' AND execution_generation = 2
    """)
    res_w2 = db_session.execute(stmt_w2, {"id": run_id})
    db_session.commit()
    assert res_w2.rowcount == 1

    # R17 stale W1 tries to update with generation 1
    stmt_w1 = text("""
    UPDATE runs SET status = 'COMPLETED', verdict = 'WRONG_ANSWER'
    WHERE id = :id AND status = 'RUNNING' AND execution_generation = 1
    """)
    res_w1 = db_session.execute(stmt_w1, {"id": run_id})
    db_session.commit()
    assert res_w1.rowcount == 0

    verdict = db_session.execute(text("SELECT verdict FROM runs WHERE id = :id"), {"id": run_id}).scalar()
    assert verdict == 'ACCEPTED'

def test_R18_multi_reconciler_CAS(db_session):
    """R18 multi-reconciler CAS protected"""
    session_id, snapshot_id, _, _ = setup_basic_models(db_session)
    run_id = uuid.uuid4()

    run = Run(
        id=run_id, session_id=session_id, snapshot_id=snapshot_id,
        status=RunStatus.RUNNING, execution_generation=1, lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    db_session.add(run)
    db_session.commit()

    stmt = text("""
    UPDATE runs SET status = 'RUNNING', execution_generation = execution_generation + 1, lease_expires_at = :new_lease
    WHERE id = :id AND status = 'RUNNING' AND execution_generation = 1 AND lease_expires_at < :now
    """)

    res1 = db_session.execute(stmt, {"id": run_id, "new_lease": datetime.now(timezone.utc) + timedelta(minutes=5), "now": datetime.now(timezone.utc)})
    db_session.commit()
    assert res1.rowcount == 1

    # Second reconciler using SAME expected generation 1
    res2 = db_session.execute(stmt, {"id": run_id, "new_lease": datetime.now(timezone.utc) + timedelta(minutes=5), "now": datetime.now(timezone.utc)})
    db_session.commit()
    assert res2.rowcount == 0 # Protected by expected execution_generation = 1

def test_R19_snapshot_FK_delete_safety(db_session):
    """R19 CodeSnapshot -> nonexistent CodingSession rejected. FK delete safety."""
    session_id, snapshot_id, user_id, problem_id = setup_basic_models(db_session)

    bad_snapshot = CodeSnapshot(
        id=uuid.uuid4(), session_id=uuid.uuid4(), reason="TEST",
        language=SupportedLanguage.PYTHON3, source_hash="hash2",
        object_key="key2", line_count=10
    )
    db_session.add(bad_snapshot)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Delete safety: Try deleting User (which is a student). It shouldn't cascade and delete coding sessions if restricted.
    # Wait, student_id on CodingSession is RESTRICT on delete.
    user = db_session.query(User).filter_by(id=user_id).first()
    db_session.delete(user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
