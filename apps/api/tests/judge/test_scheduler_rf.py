import pytest
from datetime import datetime, timezone, timedelta
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle
from app.models.observation import AttentionSignal, SignalType
from app.models.run_submit import Run, RunVerdict
from app.models.trace import CodeSnapshot

pytestmark = pytest.mark.asyncio(loop_scope="function")

@pytest.fixture(scope="function", autouse=True)
def clean_db(db):
    from sqlalchemy import text
    db.execute(text("TRUNCATE TABLE attention_signals, coding_sessions, runs, code_snapshots, trace_events, practice_attempts, class_memberships, classes, users CASCADE;"))
    db.commit()


import os
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, RoleEnum
from app.models.problem import Problem, SupportedLanguage
from app.models.session import CodingSession, SessionStatus

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must be set")
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(scope="function")
def student_user(db):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db.add(student)
    db.commit()
    return student

@pytest.fixture(scope="function")
def problem(db, student_user):
    prob = Problem(title="Test", description="Test", owner_id=student_user.id)
    db.add(prob)
    db.commit()
    return prob

@pytest.fixture(scope="function")
def active_session(db, student_user, problem):
    from datetime import datetime, timezone, timedelta
    from app.models.session import PracticeAttempt
    attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add(attempt)
    db.commit()
    
    sess = CodingSession(
        student_id=student_user.id, 
        problem_id=problem.id, 
        language=SupportedLanguage.PYTHON3, 
        opened_at=datetime.now(timezone.utc),
        status=SessionStatus.ACTIVE,
        practice_attempt_id=attempt.id
    )
    db.add(sess)
    db.commit()
    return sess


def _create_run(db, session_id, verdict, error_msg, offset_sec=0):
    snap = CodeSnapshot(
        session_id=session_id,
        object_key=f"test/{uuid.uuid4()}",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=offset_sec),
        reason="RUN",
        language="PYTHON3",
        source_hash="hash",
        line_count=10
    )
    db.add(snap)
    db.commit()
    
    # Needs actual code in storage for evaluate_repeated_failure to compute diff
    from app.services.storage import storage_adapter
    storage_adapter.upload_code_snapshot(str(session_id), 1, "print('hello')\n" * (1 + offset_sec % 3))
    
    run = Run(
        session_id=session_id,
        snapshot_id=snap.id,
        verdict=verdict,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=offset_sec),
        testcase_results={"compile_error_message": error_msg} if verdict == RunVerdict.COMPILE_ERROR else {}
    )
    db.add(run)
    db.commit()
    return run

def test_c_rf_01_single_failure(db: Session, active_session):
    _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "error1")
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 0

def test_c_rf_02_and_03_qualifying_and_repeat(db: Session, active_session):
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS):
        _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "same_error")
        
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    
    # Repeat cycle
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1

def test_c_rf_04_later_distinct_sequence(db: Session, active_session):
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS):
        _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "same_error")
        
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    
    # Success break
    _create_run(db, active_session.id, RunVerdict.ACCEPTED, "")
    
    # New distinct failure sequence
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS):
        _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "new_error")
        
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 2

def test_c_rf_05_success_break(db: Session, active_session):
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS - 1):
        _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "same_error")
    _create_run(db, active_session.id, RunVerdict.ACCEPTED, "")
    _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "same_error")
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 0

def test_c_rf_06_stale_ignored(db: Session, active_session):
    # If the evaluator ignores them, the cycle ignores them. The evaluator currently checks verdict in (ACCEPTED, None)
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS - 1):
        _create_run(db, active_session.id, RunVerdict.COMPILE_ERROR, "same_error")
    _create_run(db, active_session.id, None, "") # In-progress or stale
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 0
