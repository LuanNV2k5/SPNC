import pytest
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle
from app.models.observation import AttentionSignal, SignalType
from app.models.trace import CodeSnapshot
from app.models.session import CodingSession, SessionStatus
from app.models.class_org import ClassMembership, Class
from app.models.problem import Problem
from app.services.storage import storage_adapter

pytestmark = pytest.mark.asyncio(loop_scope="function")

@pytest.fixture(scope="function", autouse=True)
def clean_db(db):
    from sqlalchemy import text
    db.execute(text("TRUNCATE TABLE attention_signals, coding_sessions, runs, code_snapshots, trace_events, practice_attempts, class_memberships, classes, users CASCADE;"))
    db.commit()
    # Also clean memory store
    storage_adapter._memory_store = {}


import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, RoleEnum
from app.models.problem import SupportedLanguage

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


def _setup_cohort(db, student_user, active_session):
    # Create class and memberships
    cls = Class(name="CS101", owner_id=student_user.id, academic_year="2026")
    db.add(cls)
    db.commit()
    
    db.add(ClassMembership(student_id=student_user.id, class_id=cls.id, is_active=True))
    db.commit()
    
    from app.models.user import User, RoleEnum
    from app.models.session import PracticeAttempt
    for i in range(settings.SIGNAL_LOC_MIN_COHORT_SIZE):
        u = User(username=f"student_{i}", email=f"student_{i}@test.com", password_hash="hash", role=RoleEnum.STUDENT, full_name="U")
        db.add(u)
        db.commit()
        db.add(ClassMembership(student_id=u.id, class_id=cls.id, is_active=True))
        
        attempt = PracticeAttempt(student_id=u.id, problem_id=active_session.problem_id)
        db.add(attempt)
        db.flush()
        
        s = CodingSession(student_id=u.id, problem_id=active_session.problem_id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)
        db.add(s)
        db.commit()
        
        # Cohort has median 10 lines
        shash, obj_key = storage_adapter.upload_code_snapshot(str(s.id), 1, "line\\n" * 10)
        
        snap = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash, line_count=10, 
            session_id=s.id,
            object_key=obj_key,
            created_at=datetime.now(timezone.utc)
        )
        db.add(snap)
        db.commit()

def test_c_loc_01_02_qualifying_and_repeat(db: Session, student_user, active_session):
    _setup_cohort(db, student_user, active_session)
    
    # Student has 30 lines > 10 * 2.0 (dev_policy)
    shash, obj_key = storage_adapter.upload_code_snapshot(str(active_session.id), 1, "line\\n" * 30)
    snap = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash, line_count=30, 
        session_id=active_session.id,
        object_key=obj_key,
        created_at=datetime.now(timezone.utc)
    )
    db.add(snap)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    
    # Repeat
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1

def test_c_loc_03_small_cohort(db: Session, student_user, active_session):
    # Don't add enough cohort members
    cls = Class(name="CS101", owner_id=student_user.id, academic_year="2026")
    db.add(cls)
    db.flush()
    db.add(ClassMembership(student_id=student_user.id, class_id=cls.id, is_active=True))
    db.commit()
    
    shash, obj_key = storage_adapter.upload_code_snapshot(str(active_session.id), 1, "line\\n" * 30)
    snap = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash, line_count=30, 
        session_id=active_session.id,
        object_key=obj_key,
        created_at=datetime.now(timezone.utc)
    )
    db.add(snap)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 0

def test_c_loc_04_non_outlier(db: Session, student_user, active_session):
    _setup_cohort(db, student_user, active_session)
    
    # Student has 15 lines <= 10 * 2.0
    shash, obj_key = storage_adapter.upload_code_snapshot(str(active_session.id), 1, "line\\n" * 15)
    snap = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash, line_count=15, 
        session_id=active_session.id,
        object_key=obj_key,
        created_at=datetime.now(timezone.utc)
    )
    db.add(snap)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 0

def test_c_loc_05_06_changed_evidence_and_aggregate_only(db: Session, student_user, active_session):
    _setup_cohort(db, student_user, active_session)
    
    shash, obj_key = storage_adapter.upload_code_snapshot(str(active_session.id), 1, "line\\n" * 30)
    snap1 = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash, line_count=30, 
        session_id=active_session.id,
        object_key=obj_key,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10)
    )
    db.add(snap1)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    assert "cohort_median_loc" in signals[0].evidence
    
    # Genuine new evidence (new snapshot)
    shash2, obj_key2 = storage_adapter.upload_code_snapshot(str(active_session.id), 2, "line\\n" * 35)
    snap2 = CodeSnapshot(reason='RUN', language='PYTHON3', source_hash=shash2, line_count=35, 
        session_id=active_session.id,
        object_key=obj_key2,
        created_at=datetime.now(timezone.utc)
    )
    db.add(snap2)
    db.commit()
    
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 2
