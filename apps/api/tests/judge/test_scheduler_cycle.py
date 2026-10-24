import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle
from app.models.observation import AttentionSignal, SignalType
from app.models.session import SessionStatus

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


@pytest.fixture
def mock_idle():
    with patch("app.services.judge.materializer.evaluate_idle_detected") as m:
        yield m

def test_c_cycle_01_empty_candidate_set(db: Session):
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = run_cycle(db, since_dt)
    assert metrics["candidates_evaluated"] == 0
    assert metrics["signals_materialized"] == 0

def test_c_cycle_02_and_03_one_qualifying_non_qualifying(db: Session, student_user, active_session, mock_idle):
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    
    # C-CYCLE-03: Non-qualifying returns None
    mock_idle.return_value = None
    metrics = run_cycle(db, since_dt)
    assert metrics["candidates_evaluated"] >= 1
    assert metrics["signals_materialized"] == 0
    
    # C-CYCLE-02: Qualifying returns signal
    signal = AttentionSignal(
        student_id=student_user.id,
        session_id=active_session.id,
        signal_type=SignalType.IDLE_DETECTED,
        evidence={},
        dedup_key="TEST:DEDUP:1"
    )
    mock_idle.return_value = signal
    metrics = run_cycle(db, since_dt)
    assert metrics["signals_materialized"] == 1
    
    # Check DB
    assert db.scalar(select(AttentionSignal).where(AttentionSignal.dedup_key == "TEST:DEDUP:1")) is not None

def test_c_cycle_04_and_05_mixed_and_failure_isolation(db: Session, student_user, problem, mock_idle):
    # Create two sessions
    from app.models.session import CodingSession, PracticeAttempt
    attempt1 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    attempt2 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add_all([attempt1, attempt2])
    db.flush()
    s1 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt1.id)
    s2 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt2.id)
    db.add_all([s1, s2])
    db.commit()
    
    # s1 raises exception, s2 succeeds
    def side_effect(session, db_session):
        if session.id == s1.id:
            raise ValueError("Intentional failure")
        elif session.id == s2.id:
            return AttentionSignal(
                student_id=session.student_id,
                session_id=session.id,
                signal_type=SignalType.IDLE_DETECTED,
                evidence={},
                dedup_key=f"TEST:DEDUP:{session.id}"
            )
        return None
        
    mock_idle.side_effect = side_effect
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = run_cycle(db, since_dt)
    
    # C-CYCLE-05: one candidate failure does not corrupt unrelated candidate transaction
    # s2 should be materialized
    assert db.scalar(select(AttentionSignal).where(AttentionSignal.session_id == s2.id)) is not None
    assert db.scalar(select(AttentionSignal).where(AttentionSignal.session_id == s1.id)) is None

def test_c_cycle_06_returns_bounded_factual_statistics(db: Session, student_user, active_session):
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = run_cycle(db, since_dt)
    
    assert "cycle_start" in metrics
    assert "cycle_end" in metrics
    assert "candidates_evaluated" in metrics
    assert "signals_materialized" in metrics
    assert isinstance(metrics["candidates_evaluated"], int)
    
def test_batching_starvation(db: Session, student_user, problem, mock_idle):
    from app.models.session import CodingSession
    # Create N sessions where N > batch size
    batch_size = 5
    settings.SIGNAL_SCHEDULER_BATCH_SIZE = batch_size
    
    from app.models.session import PracticeAttempt
    sessions = []
    for _ in range(batch_size * 2 + 2): # 12 sessions
        attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
        db.add(attempt)
        db.flush()
        sessions.append(CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id))
    
    db.add_all(sessions)
    db.commit()
    
    mock_idle.return_value = None
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = run_cycle(db, since_dt)
    
    # Should evaluate all of them
    assert metrics["candidates_evaluated"] >= batch_size * 2 + 2
    
    # Restore config
    settings.SIGNAL_SCHEDULER_BATCH_SIZE = 100
