import pytest
import os
import uuid
import threading
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.observation import AttentionSignal, SignalType
from app.models.user import User, RoleEnum
from app.models.session import CodingSession, PracticeAttempt
from app.models.problem import SupportedLanguage, Problem, ProblemVisibility

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

def test_signal_types_exact():
    expected = {"IDLE_DETECTED", "REPEATED_FAILURE", "FAST_FIRST_CODE", "LOC_ANOMALY"}
    actual = {e.value for e in SignalType}
    assert actual == expected

def test_signal_domain_persistence_and_dedup(db_session):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db_session.add(student)
    db_session.commit()
    
    problem = Problem(title="Test", description="Test", owner_id=student.id, visibility=ProblemVisibility.PUBLIC)
    db_session.add(problem)
    db_session.flush()
    problem_id = problem.id

    practice_attempt = PracticeAttempt(student_id=student.id, problem_id=problem_id)
    db_session.add(practice_attempt)
    db_session.flush()

    session = CodingSession(student_id=student.id, problem_id=problem_id, language=SupportedLanguage.PYTHON3, practice_attempt_id=practice_attempt.id)
    db_session.add(session)
    db_session.commit()
    
    signal1 = AttentionSignal(
        student_id=student.id,
        session_id=session.id,
        signal_type=SignalType.IDLE_DETECTED,
        evidence={"idle_seconds": 300},
        dedup_key=f"IDLE_DETECTED:{session.id}:1"
    )
    db_session.add(signal1)
    db_session.commit()
    
    assert signal1.id is not None
    assert signal1.detected_at.tzinfo == timezone.utc
    assert not hasattr(signal1, "teacher_note")
    
    signal2 = AttentionSignal(
        student_id=student.id,
        session_id=session.id,
        signal_type=SignalType.IDLE_DETECTED,
        evidence={"idle_seconds": 300},
        dedup_key=f"IDLE_DETECTED:{session.id}:1"
    )
    db_session.add(signal2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    
    db_session.rollback()
    
    signal3 = AttentionSignal(
        student_id=student.id,
        session_id=session.id,
        signal_type=SignalType.IDLE_DETECTED,
        evidence={"idle_seconds": 350},
        dedup_key=f"IDLE_DETECTED:{session.id}:2"
    )
    db_session.add(signal3)
    db_session.commit()
    
    assert signal3.id is not None

def test_concurrent_insertion(db_session):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db_session.add(student)
    db_session.commit()
    
    problem = Problem(title="Test", description="Test", owner_id=student.id, visibility=ProblemVisibility.PUBLIC)
    db_session.add(problem)
    db_session.flush()
    problem_id = problem.id

    practice_attempt = PracticeAttempt(student_id=student.id, problem_id=problem_id)
    db_session.add(practice_attempt)
    db_session.flush()

    session = CodingSession(student_id=student.id, problem_id=problem_id, language=SupportedLanguage.PYTHON3, practice_attempt_id=practice_attempt.id)
    db_session.add(session)
    db_session.commit()
    
    dedup = f"CONCURRENT:{session.id}"
    barrier = threading.Barrier(10)
    results = []

    def insert_signal():
        sess = TestingSessionLocal()
        barrier.wait(timeout=5)
        sig = AttentionSignal(
            student_id=student.id,
            session_id=session.id,
            signal_type=SignalType.FAST_FIRST_CODE,
            evidence={},
            dedup_key=dedup
        )
        sess.add(sig)
        try:
            sess.commit()
            results.append(True)
        except IntegrityError:
            sess.rollback()
            results.append(False)
        finally:
            sess.close()

    threads = []
    for _ in range(10):
        t = threading.Thread(target=insert_signal)
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
        
    successes = sum(results)
    assert successes == 1

def test_req_signal_005_rule_version_persistence(db_session):
    student = User(email=f"stu_{uuid.uuid4()}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"stu_{uuid.uuid4()}", full_name="Student")
    db_session.add(student)
    db_session.commit()

    problem = Problem(title="Test", description="Test", owner_id=student.id, visibility=ProblemVisibility.PUBLIC)
    db_session.add(problem)
    db_session.flush()

    attempt = PracticeAttempt(student_id=student.id, problem_id=problem.id)
    db_session.add(attempt)
    db_session.flush()

    session = CodingSession(student_id=student.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
    db_session.add(session)
    db_session.commit()

    sig = AttentionSignal(
        student_id=student.id,
        session_id=session.id,
        signal_type=SignalType.IDLE_DETECTED,
        evidence={"idle_seconds": 300},
        rule_version="1.0.0",
        dedup_key=f"RULE_VER_PERSIST:{session.id}"
    )
    db_session.add(sig)
    db_session.commit()

    reloaded = db_session.get(AttentionSignal, sig.id)
    assert reloaded.rule_version is not None
    assert reloaded.rule_version == "1.0.0"
