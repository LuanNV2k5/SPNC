import pytest
import os
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.observation import SignalType
from app.models.user import User, RoleEnum
from app.models.session import CodingSession, SessionStatus, PracticeAttempt
from app.models.trace import ScratchpadRevision
from app.models.problem import Problem, SupportedLanguage
from app.services.judge.signals import (
    evaluate_idle_detected,
    evaluate_fast_first_code,
    evaluate_repeated_failure,
    evaluate_loc_anomaly
)

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
def setup_user_and_session(db_session):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db_session.add(student)
    db_session.flush()
    
    problem = Problem(title="Test", description="Test", owner_id=student.id)
    db_session.add(problem)
    db_session.flush()
    
    attempt = PracticeAttempt(student_id=student.id, problem_id=problem.id)
    db_session.add(attempt)
    db_session.flush()
    
    opened_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session = CodingSession(student_id=student.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, opened_at=opened_at, practice_attempt_id=attempt.id)
    db_session.add(session)
    db_session.commit()
    
    return student, problem, session

def test_bx_scratchpad_exclusion(db_session, setup_user_and_session):
    student, problem, session = setup_user_and_session
    session.opened_at = datetime.now(timezone.utc)
    db_session.commit()
    
    fp = "fp1"
    rev = ScratchpadRevision(session_id=session.id, revision_sequence=1, canonical_fingerprint=fp, content="def x():\\n  pass\\n", client_timestamp=datetime.now(timezone.utc), server_timestamp=datetime.now(timezone.utc))
    db_session.add(rev)
    db_session.commit()
    
    assert evaluate_idle_detected(session, db_session) is None
    assert evaluate_fast_first_code(session, db_session) is None
    assert evaluate_repeated_failure(session, db_session) is None
    assert evaluate_loc_anomaly(session, db_session) is None

def test_bx_four_signal_types():
    actual = {e.value for e in SignalType}
    assert actual == {"IDLE_DETECTED", "REPEATED_FAILURE", "FAST_FIRST_CODE", "LOC_ANOMALY"}
