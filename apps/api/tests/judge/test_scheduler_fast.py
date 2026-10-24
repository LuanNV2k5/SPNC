import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle
from app.models.observation import AttentionSignal, SignalType
from app.models.trace import TraceEvent, TraceEventType

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


def test_c_fast_01_qualifying_first_edit(db: Session, active_session):
    # C-FAST-01: qualifying first edit => one signal
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    
    # Edit within threshold
    edit = TraceEvent(
        session_id=active_session.id,
        event_type=TraceEventType.EDITOR_CHANGED,
        server_timestamp=active_session.opened_at + timedelta(seconds=settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS - 5),
        sequence_number=1,
        canonical_fingerprint='fp1',
        payload={},
        client_timestamp=datetime.now(timezone.utc)
    )
    db.add(edit)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id, AttentionSignal.signal_type == SignalType.FAST_FIRST_CODE)).all()
    assert len(signals) == 1

def test_c_fast_02_repeat_cycle(db: Session, active_session):
    # C-FAST-02: repeat cycle => no duplicate
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    
    edit = TraceEvent(
        session_id=active_session.id,
        event_type=TraceEventType.EDITOR_CHANGED,
        server_timestamp=active_session.opened_at + timedelta(seconds=10),
        sequence_number=1,
        canonical_fingerprint='fp1',
        payload={},
        client_timestamp=datetime.now(timezone.utc)
    )
    db.add(edit)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id, AttentionSignal.signal_type == SignalType.FAST_FIRST_CODE)).all()
    assert len(signals) == 1

def test_c_fast_03_non_qualifying(db: Session, active_session):
    # C-FAST-03: non-qualifying first edit => none
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    
    edit = TraceEvent(
        session_id=active_session.id,
        event_type=TraceEventType.EDITOR_CHANGED,
        server_timestamp=active_session.opened_at + timedelta(seconds=settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS + 10),
        sequence_number=1,
        canonical_fingerprint='fp1',
        payload={},
        client_timestamp=datetime.now(timezone.utc)
    )
    db.add(edit)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id, AttentionSignal.signal_type == SignalType.FAST_FIRST_CODE)).all()
    assert len(signals) == 0

def test_c_fast_04_no_edit(db: Session, active_session):
    # C-FAST-04: no edit => none
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id, AttentionSignal.signal_type == SignalType.FAST_FIRST_CODE)).all()
    assert len(signals) == 0
