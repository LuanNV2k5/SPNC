import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle
from app.models.observation import AttentionSignal, SignalType
from app.db.session import SessionLocal

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


def test_c_restart_safe(db: Session, active_session):
    # C-RESTART-01 to C-RESTART-04
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    
    # 1. Cycle materializes signal
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len([s for s in signals if s.signal_type == 'IDLE_DETECTED' or s.signal_type == __import__('app.models.observation', fromlist=['SignalType']).SignalType.IDLE_DETECTED]) == 1
    
    # 2 & 3. Dispose state, new DB session
    db.close() # simulate restart
    
    with SessionLocal() as new_db:
        # 4. Same DB state reevaluated => no duplicate
        run_cycle(new_db, since_dt)
        signals = new_db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
        assert len([s for s in signals if s.signal_type == 'IDLE_DETECTED' or s.signal_type == __import__('app.models.observation', fromlist=['SignalType']).SignalType.IDLE_DETECTED]) == 1
        
        # New distinct qualifying evidence
        # (e.g. fast first code event)
        from app.models.trace import TraceEvent, TraceEventType
        edit = TraceEvent(
            session_id=active_session.id,
            event_type=TraceEventType.EDITOR_CHANGED,
            server_timestamp=active_session.opened_at + timedelta(seconds=10),
            sequence_number=1,
        canonical_fingerprint='fp1',
        payload={},
            client_timestamp=datetime.now(timezone.utc)
        )
        new_db.add(edit)
        new_db.commit()
        
        run_cycle(new_db, since_dt)
        signals = new_db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
        assert len([s for s in signals if s.signal_type == 'IDLE_DETECTED' or s.signal_type == __import__('app.models.observation', fromlist=['SignalType']).SignalType.IDLE_DETECTED]) == 2 # 1 IDLE, 1 FAST

async def test_concurrent_scheduler_race(db: Session, student_user, problem):
    # Run 10 iterations
    from app.models.session import CodingSession, SessionStatus
    
    for i in range(10):
        # Create a new session for each iteration
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
        db.add(attempt)
        db.commit()
        s = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=attempt.id)
        s.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10)
        db.add(s)
        db.commit()
        session_id = s.id
        
        barrier = asyncio.Barrier(2)
        
        async def racer(worker_id):
            await barrier.wait()
            # New independent session for true race
            with SessionLocal() as db2:
                since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
                # Instead of full cycle, specifically evaluate this candidate to force the race
                from app.services.judge.signals import evaluate_idle_detected
                from app.services.judge.materializer import materialize_signal
                
                # Fetch fresh
                s2 = db2.get(CodingSession, session_id)
                idle_signal = evaluate_idle_detected(s2, db2)
                print('IDLE SIGNAL IS:', idle_signal)
                inserted = materialize_signal(db2, idle_signal)
                return inserted
                
        # Run two racers concurrently
        results = await asyncio.gather(racer(1), racer(2))
        
        # EXACTLY ONE should return True (inserted), the other False (deduped/on conflict do nothing)
        assert results.count(True) == 1
        assert results.count(False) == 1
        
        # Check DB has exactly 1
        from sqlalchemy import func
        count = db.scalar(select(func.count()).select_from(AttentionSignal).where(AttentionSignal.session_id == session_id))
        assert count == 1
