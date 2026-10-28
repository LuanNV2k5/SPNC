import pytest
import os
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.observation import AttentionSignal, SignalType
from app.models.user import User, RoleEnum
from app.models.session import CodingSession, SessionStatus
from app.models.trace import TraceEvent, TraceEventType, CodeSnapshot
from app.models.problem import Problem, SupportedLanguage
from app.models.class_org import Class, ClassMembership
from app.models.run_submit import Run, RunVerdict, Submission
from app.services.judge.signals import (
    evaluate_idle_detected,
    evaluate_fast_first_code,
    evaluate_repeated_failure,
    evaluate_loc_anomaly,
    evaluate_historical_idle_gaps,
)
from app.core.config import settings
from app.services.storage import storage_adapter

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
    
    opened_at = datetime.now(timezone.utc) - timedelta(hours=1)
    
    from app.models.session import PracticeAttempt
    attempt = PracticeAttempt(student_id=student.id, problem_id=problem.id)
    db_session.add(attempt)
    db_session.flush()
    
    session = CodingSession(
        student_id=student.id, 
        problem_id=problem.id, 
        language=SupportedLanguage.PYTHON3, 
        opened_at=opened_at,
        practice_attempt_id=attempt.id
    )
    db_session.add(session)
    db_session.commit()
    
    return student, problem, session

# =======================
# B-IDLE TESTS
# =======================
def test_idle_below_threshold(db_session, setup_user_and_session):
    # B-IDLE-01: idle below 300 sec => no signal
    _, _, session = setup_user_and_session
    
    event_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is None

def test_idle_exactly_threshold(db_session, setup_user_and_session):
    # B-IDLE-02: idle exactly 300 sec => qualifies
    _, _, session = setup_user_and_session
    
    event_time = datetime.now(timezone.utc) - timedelta(seconds=300)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.IDLE_DETECTED
    assert signal.rule_version == "1.1.0"
    # Authoritative REQ-IDLE-002 fields
    assert signal.evidence["start_time"] == event_time.isoformat()
    assert "end_time" in signal.evidence
    assert signal.evidence["duration_seconds"] >= 300
    assert signal.evidence["meaningful_event_before_id"] == str(event.id)
    assert signal.evidence["threshold_used"] == 300

def test_idle_no_prior_meaningful_event_boundary(db_session, setup_user_and_session):
    # Session opened 400s ago, zero trace events
    _, _, session = setup_user_and_session
    session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.IDLE_DETECTED
    assert signal.rule_version == "1.1.0"
    assert signal.evidence["start_time"] == session.opened_at.isoformat()
    assert "end_time" in signal.evidence
    assert signal.evidence["duration_seconds"] >= 400
    assert signal.evidence["meaningful_event_before_id"] is None
    assert signal.evidence["threshold_used"] == 300
    assert signal.evidence["last_meaningful_event_type"] == "SESSION_OPENED"

def test_idle_above_threshold(db_session, setup_user_and_session):
    # B-IDLE-03: idle above 300 sec => qualifies
    _, _, session = setup_user_and_session
    
    event_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is not None
    # B-IDLE-04: does not mutate status
    assert session.status == SessionStatus.ACTIVE
    # B-IDLE-05: remains active
    
    # B-IDLE-10: evidence values exact
    assert signal.evidence["idle_duration_seconds"] >= 600
    assert signal.evidence["last_meaningful_event_type"] == TraceEventType.EDITOR_CHANGED.value

def test_idle_not_active(db_session, setup_user_and_session):
    # B-IDLE-06, B-IDLE-07: ENDED or ABANDONED
    _, _, session = setup_user_and_session
    
    session.status = SessionStatus.ENDED
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is None

def test_idle_meaningful_reset(db_session, setup_user_and_session):
    # B-IDLE-08: meaningful edit resets
    # B-IDLE-09: irrelevant does not reset
    _, _, session = setup_user_and_session
    
    # Meaningful 400s ago
    event_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    
    # Irrelevant 10s ago
    irr_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    event2 = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.PROBLEM_OPENED, canonical_fingerprint="fp2", client_timestamp=irr_time, server_timestamp=irr_time, payload={})
    db_session.add(event2)
    db_session.commit()
    
    signal = evaluate_idle_detected(session, db_session)
    assert signal is not None

# =======================
# B-FAST TESTS
# =======================
def test_fast_first_code_inside(db_session, setup_user_and_session):
    # B-FAST-01, B-FAST-03, B-FAST-07, B-FAST-08
    _, _, session = setup_user_and_session
    
    event_time = session.opened_at + timedelta(seconds=10)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.FAST_FIRST_CODE
    assert signal.rule_version is not None
    assert signal.rule_version == "1.1.0"

    # Authoritative canonical evidence fields (01_DOMAIN.md §1.8 / REQ-SIGNAL-003)
    assert "problem_open_time" in signal.evidence
    assert isinstance(signal.evidence["problem_open_time"], str)
    assert signal.evidence["problem_open_time"] == session.opened_at.isoformat()

    assert "first_code_event_time" in signal.evidence
    assert isinstance(signal.evidence["first_code_event_time"], str)
    assert signal.evidence["first_code_event_time"] == event_time.isoformat()

    assert "delta_seconds" in signal.evidence
    assert isinstance(signal.evidence["delta_seconds"], (int, float))
    assert signal.evidence["delta_seconds"] == 10.0

    assert "threshold_seconds" in signal.evidence
    assert isinstance(signal.evidence["threshold_seconds"], (int, float))
    assert signal.evidence["threshold_seconds"] == settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS

    # Backward compatibility with pre-existing Phase 08 fields
    assert signal.evidence["elapsed_seconds"] == 10.0
    assert signal.evidence["configured_threshold_seconds"] == settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS
    assert signal.evidence["session_opened_at"] == signal.evidence["problem_open_time"]
    assert signal.evidence["first_code_event_at"] == signal.evidence["first_code_event_time"]
    assert signal.evidence["delta_seconds"] == signal.evidence["elapsed_seconds"]
    assert signal.evidence["threshold_seconds"] == signal.evidence["configured_threshold_seconds"]
    assert signal.evidence["session_id"] == str(session.id)
    assert signal.evidence["first_code_event_id"] == str(event.id)

def test_fast_first_code_outside(db_session, setup_user_and_session):
    # B-FAST-02
    _, _, session = setup_user_and_session
    
    event_time = session.opened_at + timedelta(seconds=100)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is None

def test_fast_first_code_none(db_session, setup_user_and_session):
    # B-FAST-04, B-FAST-05, B-FAST-06
    _, _, session = setup_user_and_session
    
    event_time = session.opened_at + timedelta(seconds=10)
    # Just run requested, no code event
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.RUN_REQUESTED, canonical_fingerprint="fp1", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is None

def test_fast_first_code_exact_threshold_boundary(db_session, setup_user_and_session):
    # Tests exact boundary: elapsed == threshold_seconds qualifies
    _, _, session = setup_user_and_session
    threshold = settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS
    
    event_time = session.opened_at + timedelta(seconds=threshold)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp_exact", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.FAST_FIRST_CODE
    assert signal.evidence["delta_seconds"] == float(threshold)
    assert signal.evidence["threshold_seconds"] == threshold
    assert signal.evidence["problem_open_time"] == session.opened_at.isoformat()
    assert signal.evidence["first_code_event_time"] == event_time.isoformat()
    assert signal.rule_version == "1.1.0"

def test_fast_first_code_just_above_threshold(db_session, setup_user_and_session):
    # Tests just above boundary: elapsed > threshold_seconds returns None
    _, _, session = setup_user_and_session
    threshold = settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS
    
    event_time = session.opened_at + timedelta(seconds=threshold + 0.1)
    event = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp_above", client_timestamp=event_time, server_timestamp=event_time, payload={})
    db_session.add(event)
    db_session.commit()
    
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is None

def test_fast_first_code_empty_session_boundary(db_session, setup_user_and_session):
    # Tests missing first code boundary: session with zero trace events returns None
    _, _, session = setup_user_and_session
    signal = evaluate_fast_first_code(session, db_session)
    assert signal is None

# =======================
# B-RF TESTS
# =======================
def _create_snapshot(db_session, session, code, seq):
    _, obj_key = storage_adapter.upload_code_snapshot(str(session.id), seq, code)
    snap = CodeSnapshot(session_id=session.id, reason="RUN", language="PYTHON3", source_hash="hash", object_key=obj_key, line_count=len(code.split("\n")))
    db_session.add(snap)
    db_session.commit()
    return snap

def test_rf_single_failure(db_session, setup_user_and_session):
    # B-RF-01
    _, _, session = setup_user_and_session
    snap = _create_snapshot(db_session, session, "code", 1)
    
    run = Run(session_id=session.id, snapshot_id=snap.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1)
    db_session.add(run)
    db_session.commit()
    
    signal = evaluate_repeated_failure(session, db_session)
    assert signal is None

def test_rf_qualifies(db_session, setup_user_and_session):
    # B-RF-02, B-RF-06, B-RF-07, B-RF-08, B-RF-09, B-RF-10, B-RF-11
    _, _, session = setup_user_and_session
    
    # 3 failures, little code change
    s1 = _create_snapshot(db_session, session, "def x():\n  pass\n", 1)
    r1 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1)
    r1.testcase_results = {"compile_error_message": "Error on line 1"}
    
    s2 = _create_snapshot(db_session, session, "def x():\n  pass\n  ", 2)
    r2 = Run(session_id=session.id, snapshot_id=s2.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=2)
    r2.testcase_results = {"compile_error_message": "Error on line 1"}
    
    s3 = _create_snapshot(db_session, session, "def x():\n  pass\n   ", 3)
    r3 = Run(session_id=session.id, snapshot_id=s3.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=3)
    r3.testcase_results = {"compile_error_message": "Error on line 1"}
    
    db_session.add_all([r1, r2, r3])
    db_session.commit()
    
    signal = evaluate_repeated_failure(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.REPEATED_FAILURE
    assert signal.rule_version == "1.1.0"

    # Canonical evidence contract (DCR SPNC_RF_RUN_EVIDENCE_CONTRACT / docs/01_DOMAIN.md §1.8)
    assert "problem_id" in signal.evidence
    assert signal.evidence["problem_id"] == str(session.problem_id)
    assert "target_entity" in signal.evidence
    assert signal.evidence["target_entity"] == "RUN"
    assert "run_count" in signal.evidence
    assert signal.evidence["run_count"] == 3
    assert "failed_count" in signal.evidence
    assert signal.evidence["failed_count"] == 3
    assert "verdicts" in signal.evidence
    assert signal.evidence["verdicts"] == [RunVerdict.COMPILE_ERROR.value, RunVerdict.COMPILE_ERROR.value, RunVerdict.COMPILE_ERROR.value]
    assert "time_range_start" in signal.evidence
    assert signal.evidence["time_range_start"] == r1.created_at.isoformat()
    assert "time_range_end" in signal.evidence
    assert signal.evidence["time_range_end"] == r3.created_at.isoformat()
    assert signal.evidence["time_range_start"] <= signal.evidence["time_range_end"]

    # Invariant: zero submission_count fabrication
    assert "submission_count" not in signal.evidence

    # Legacy diagnostic fields preserved for backward compatibility
    assert len(signal.evidence["run_ids"]) == 3
    assert len(signal.evidence["snapshot_ids"]) == 3
    assert signal.evidence["failure_signature"] == "Error on line X"
    assert signal.evidence["session_id"] == str(session.id)
    assert signal.evidence["attempt_count"] == 3
    assert signal.evidence["last_run_at"] == signal.evidence["time_range_end"]
    assert signal.evidence["configured_max_ratio"] == settings.SIGNAL_REPEATED_FAILURE_MAX_CODE_CHANGE_RATIO
    assert signal.evidence["max_code_change_ratio"] <= settings.SIGNAL_REPEATED_FAILURE_MAX_CODE_CHANGE_RATIO

def test_rf_submission_entity_isolation(db_session, setup_user_and_session):
    # Verifies that evaluating repeated failure never queries, modifies, or creates Submission records
    _, _, session = setup_user_and_session
    snap = _create_snapshot(db_session, session, "def x():\n  pass\n", 1)
    
    # Pre-existing formal submission in DB
    existing_sub = Submission(
        student_id=session.student_id,
        problem_id=session.problem_id,
        session_id=session.id,
        snapshot_id=snap.id,
        verdict=RunVerdict.WRONG_ANSWER,
        score=0
    )
    db_session.add(existing_sub)
    db_session.commit()
    sub_count_before = db_session.query(Submission).filter(Submission.session_id == session.id).count()
    assert sub_count_before == 1

    now = datetime.now(timezone.utc)
    s1 = _create_snapshot(db_session, session, "def x():\n  pass\n", 2)
    r1 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1, created_at=now - timedelta(seconds=20))
    r1.testcase_results = {"compile_error_message": "Error on line 1"}
    
    s2 = _create_snapshot(db_session, session, "def x():\n  pass\n  ", 3)
    r2 = Run(session_id=session.id, snapshot_id=s2.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=2, created_at=now - timedelta(seconds=10))
    r2.testcase_results = {"compile_error_message": "Error on line 1"}
    
    s3 = _create_snapshot(db_session, session, "def x():\n  pass\n   ", 4)
    r3 = Run(session_id=session.id, snapshot_id=s3.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=3, created_at=now)
    r3.testcase_results = {"compile_error_message": "Error on line 1"}
    
    db_session.add_all([r1, r2, r3])
    db_session.commit()

    signal = evaluate_repeated_failure(session, db_session)
    assert signal is not None
    assert signal.evidence["target_entity"] == "RUN"
    assert signal.evidence["run_count"] == 3
    assert "submission_count" not in signal.evidence

    # Verify submissions in DB remain untouched
    sub_count_after = db_session.query(Submission).filter(Submission.session_id == session.id).count()
    assert sub_count_after == sub_count_before
    persisted_sub = db_session.query(Submission).filter(Submission.id == existing_sub.id).one()
    assert persisted_sub.verdict == RunVerdict.WRONG_ANSWER
    assert persisted_sub.score == 0

def test_rf_below_minimum_attempts_boundary(db_session, setup_user_and_session):
    # Verifies that fewer than min_attempts (e.g. 2 runs) returns None
    _, _, session = setup_user_and_session
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS - 1):
        s = _create_snapshot(db_session, session, f"def x():\n  pass\n{' ' * i}", i + 1)
        r = Run(session_id=session.id, snapshot_id=s.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=i + 1)
        r.testcase_results = {"compile_error_message": "Same error"}
        db_session.add(r)
    db_session.commit()

    signal = evaluate_repeated_failure(session, db_session)
    assert signal is None

def test_rf_substantial_change(db_session, setup_user_and_session):
    # B-RF-03
    _, _, session = setup_user_and_session
    
    s1 = _create_snapshot(db_session, session, "def x():\n  pass\n", 1)
    r1 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1)
    
    # huge change
    s2 = _create_snapshot(db_session, session, "def y():\n  return 1\ndef z():\n  pass\n", 2)
    r2 = Run(session_id=session.id, snapshot_id=s2.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=2)
    
    s3 = _create_snapshot(db_session, session, "def y():\n  return 1\ndef z():\n  pass\n", 3)
    r3 = Run(session_id=session.id, snapshot_id=s3.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=3)
    
    db_session.add_all([r1, r2, r3])
    db_session.commit()
    
    signal = evaluate_repeated_failure(session, db_session)
    assert signal is None # Change is too big

def test_rf_different_failures(db_session, setup_user_and_session):
    # B-RF-04
    _, _, session = setup_user_and_session
    
    s1 = _create_snapshot(db_session, session, "def x():\n  pass\n", 1)
    r1 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1)
    r1.testcase_results = {"compile_error_message": "A"}
    r2 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.RUNTIME_ERROR, execution_generation=2)
    r2.testcase_results = {"runtime_error_message": "B"}
    r3 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.TIME_LIMIT_EXCEEDED, execution_generation=3)
    
    db_session.add_all([r1, r2, r3])
    db_session.commit()
    
    signal = evaluate_repeated_failure(session, db_session)
    assert signal is None

def test_rf_success_breaks(db_session, setup_user_and_session):
    # B-RF-05
    _, _, session = setup_user_and_session
    
    s1 = _create_snapshot(db_session, session, "def x():\n  pass\n", 1)
    r1 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=1)
    r2 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.ACCEPTED, execution_generation=2)
    r3 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=3)
    r4 = Run(session_id=session.id, snapshot_id=s1.id, verdict=RunVerdict.COMPILE_ERROR, execution_generation=4)
    
    db_session.add_all([r1, r2, r3, r4])
    db_session.commit()
    
    signal = evaluate_repeated_failure(session, db_session)
    assert signal is None # Only 2 consecutive

# =======================
# B-LOC TESTS
# =======================
def test_loc_anomaly(db_session, setup_user_and_session):
    # B-LOC-03, B-LOC-04, B-LOC-05, B-LOC-08, B-LOC-10
    student, problem, session = setup_user_and_session
    
    cls = Class(name="C1", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))
    
    # 3 other students in cohort
    for i in range(3):
        u_id = uuid.uuid4()
        u = User(email=f"u_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        
        # Give them LOC = 10
        code = "\n".join([f"line {j}" for j in range(10)])
        _create_snapshot(db_session, sess, code, 1)
        
    db_session.commit()
    
    # Our student LOC = 50
    code = "\n".join([f"line {j}" for j in range(50)])
    _create_snapshot(db_session, session, code, 1)
    
    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is not None
    assert signal.signal_type == SignalType.LOC_ANOMALY
    assert signal.rule_version == "1.1.0"
    
    # Canonical evidence contract (DCR SPNC_LOC_EVIDENCE_CONTRACT / docs/01_DOMAIN.md §1.8)
    assert signal.evidence["session_id"] == str(session.id)
    assert signal.evidence["observed_loc"] == 50
    assert isinstance(signal.evidence["observed_loc"], int)
    assert signal.evidence["context_median_loc"] == 10.0
    assert isinstance(signal.evidence["context_median_loc"], (int, float))
    assert signal.evidence["delta"] == 40.0
    assert isinstance(signal.evidence["delta"], (int, float))
    assert signal.evidence["threshold_relative"] == 2.0
    assert isinstance(signal.evidence["threshold_relative"], (int, float))
    assert signal.evidence["final_loc"] is None

    # Preserved legacy diagnostic fields for backward compatibility
    assert signal.evidence["student_loc"] == 50
    assert signal.evidence["cohort_median_loc"] == 10.0
    assert signal.evidence["cohort_size"] == 3
    assert signal.evidence["relative_deviation"] == 5.0
    assert signal.evidence["configured_threshold"] == 2.0
    assert signal.evidence["loc_counting_policy"] == "non-blank lines"
    assert signal.evidence["problem_id"] == str(session.problem_id)

def test_loc_below_cohort(db_session, setup_user_and_session):
    # B-LOC-01
    student, problem, session = setup_user_and_session
    
    cls = Class(name="C1", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))
    
    # 1 other student (min cohort is 3)
    u_id = uuid.uuid4()
    u = User(email=f"u_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_{u_id}", full_name="U")
    db_session.add(u)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
    
    from app.models.session import PracticeAttempt
    attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
    db_session.add(attempt)
    db_session.flush()
    
    sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
    db_session.add(sess)
    db_session.flush()
    _create_snapshot(db_session, sess, "line\n", 1)
    
    db_session.commit()
    _create_snapshot(db_session, session, "line\n" * 50, 1)
    
    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is None # Cohort size 1 < 3

def test_loc_normal(db_session, setup_user_and_session):
    # B-LOC-02
    student, problem, session = setup_user_and_session
    
    cls = Class(name="C1", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))
    
    for i in range(3):
        u_id = uuid.uuid4()
        u = User(email=f"u_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        _create_snapshot(db_session, sess, "line\n" * 10, 1)
        
    db_session.commit()
    _create_snapshot(db_session, session, "line\n" * 15, 1)
    
    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is None # 15/10 = 1.5 <= 2.0

def test_loc_anomaly_zero_median_no_signal(db_session, setup_user_and_session):
    # Verifies that when cohort median is <= 0 (e.g. empty files), no signal is generated
    student, problem, session = setup_user_and_session
    cls = Class(name="C_Zero", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))

    for i in range(3):
        u_id = uuid.uuid4()
        u = User(email=f"u_zero_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_zero_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        # Empty code (0 lines)
        _create_snapshot(db_session, sess, "   \n   ", 1)

    db_session.commit()
    _create_snapshot(db_session, session, "def solution():\n  return 1\n", 1)

    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is None # Zero-median must not generate LOC_ANOMALY

def test_loc_anomaly_even_cohort_median(db_session, setup_user_and_session):
    # Verifies even cohort median calculation: (20 + 30) / 2 = 25.0
    student, problem, session = setup_user_and_session
    cls = Class(name="C_Even", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))

    # 4 peers with 10, 20, 30, 40 lines
    for line_target in [10, 20, 30, 40]:
        u_id = uuid.uuid4()
        u = User(email=f"u_even_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_even_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        code = "\n".join([f"line {j}" for j in range(line_target)])
        _create_snapshot(db_session, sess, code, 1)

    db_session.commit()

    # Student has 60 lines -> relative_dev = 60 / 25.0 = 2.4 > 2.0
    code = "\n".join([f"line {j}" for j in range(60)])
    _create_snapshot(db_session, session, code, 1)

    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is not None
    assert signal.evidence["observed_loc"] == 60
    assert signal.evidence["context_median_loc"] == 25.0
    assert signal.evidence["delta"] == 35.0 # 60 - 25.0
    assert signal.evidence["threshold_relative"] == 2.0
    assert signal.evidence["final_loc"] is None
    assert signal.evidence["cohort_size"] == 4
    assert signal.evidence["relative_deviation"] == 2.4

def test_loc_anomaly_threshold_equality_does_not_trigger(db_session, setup_user_and_session):
    # Verifies that exactly at threshold (e.g. 20 / 10 = 2.0) does NOT trigger (strictly > threshold)
    student, problem, session = setup_user_and_session
    cls = Class(name="C_Eq", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))

    for i in range(3):
        u_id = uuid.uuid4()
        u = User(email=f"u_eq_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_eq_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        _create_snapshot(db_session, sess, "\n".join([f"line {j}" for j in range(10)]), 1)

    db_session.commit()

    # Exactly 20 lines -> 20 / 10 = 2.0 <= 2.0 -> returns None
    _create_snapshot(db_session, session, "\n".join([f"line {j}" for j in range(20)]), 1)

    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is None

def test_loc_anomaly_peer_privacy_invariant(db_session, setup_user_and_session):
    # Verifies that peer user IDs, usernames, snapshot IDs, and peer code are never present in evidence
    student, problem, session = setup_user_and_session
    cls = Class(name="C_Priv", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))

    peer_ids = []
    peer_usernames = []
    for i in range(3):
        u_id = uuid.uuid4()
        username = f"secret_peer_{u_id}"
        u = User(email=f"u_priv_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=username, full_name="Secret Peer")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        peer_ids.append(str(u.id))
        peer_usernames.append(username)
        from app.models.session import PracticeAttempt
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        sess = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(sess)
        db_session.flush()
        _create_snapshot(db_session, sess, "\n".join([f"peer_secret_line_{j}" for j in range(10)]), 1)

    db_session.commit()
    _create_snapshot(db_session, session, "\n".join([f"my_line_{j}" for j in range(50)]), 1)

    signal = evaluate_loc_anomaly(session, db_session)
    assert signal is not None

    evidence_str = str(signal.evidence)
    for pid in peer_ids:
        assert pid not in evidence_str
    for uname in peer_usernames:
        assert uname not in evidence_str
    assert "peer_secret_line" not in evidence_str

# =======================
# HISTORICAL IDLE TESTS
# =======================
def test_historical_idle_two_consecutive_meaningful_events(db_session, setup_user_and_session):
    """Scenario 1: Two consecutive meaningful events with gap >= 300s qualify."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=10)
    t2 = t1 + timedelta(seconds=400) # 400s gap

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.RUN_REQUESTED, canonical_fingerprint="fp2", client_timestamp=t2, server_timestamp=t2, payload={})
    db_session.add_all([e1, e2])
    db_session.commit()

    signals = evaluate_historical_idle_gaps(session, [e2], db_session)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_type == SignalType.IDLE_DETECTED
    assert sig.rule_version == "1.1.0"
    assert sig.evidence["duration_seconds"] == 400.0
    assert sig.evidence["start_time"] == t1.isoformat()
    assert sig.evidence["end_time"] == t2.isoformat()
    assert sig.evidence["meaningful_event_before_id"] == str(e1.id)
    assert sig.evidence["threshold_used"] == settings.SIGNAL_IDLE_THRESHOLD_SECONDS

def test_historical_idle_session_open_to_first_meaningful(db_session, setup_user_and_session):
    """Scenario 2: Initial gap from session.opened_at to first meaningful event >= 300s qualifies."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=400) # 400s after open

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    db_session.add(e1)
    db_session.commit()

    signals = evaluate_historical_idle_gaps(session, [e1], db_session)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.evidence["duration_seconds"] == 400.0
    assert sig.evidence["start_time"] == session.opened_at.isoformat()
    assert sig.evidence["end_time"] == t1.isoformat()
    assert sig.evidence["meaningful_event_before_id"] is None
    assert sig.evidence["threshold_used"] == settings.SIGNAL_IDLE_THRESHOLD_SECONDS

def test_historical_idle_threshold_equality_and_shorter_gaps(db_session, setup_user_and_session):
    """Scenario 3: Gap exactly equal to 300s qualifies; shorter gap (299s) does not."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=10)
    t_exact = t1 + timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS) # 300s
    t_short = t_exact + timedelta(seconds=299) # 299s gap

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=t_exact, server_timestamp=t_exact, payload={})
    e3 = TraceEvent(session_id=session.id, sequence_number=3, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp3", client_timestamp=t_short, server_timestamp=t_short, payload={})
    db_session.add_all([e1, e2, e3])
    db_session.commit()

    # Exact threshold gap qualifies
    signals_exact = evaluate_historical_idle_gaps(session, [e2], db_session)
    assert len(signals_exact) == 1
    assert signals_exact[0].evidence["duration_seconds"] == 300.0

    # Shorter gap (299s) does not qualify
    signals_short = evaluate_historical_idle_gaps(session, [e3], db_session)
    assert len(signals_short) == 0

def test_historical_idle_session_checkpoint_does_not_reset_inactivity(db_session, setup_user_and_session):
    """Scenario 4: Automated SESSION_CHECKPOINT does not reset inactivity timer."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=10)
    t_cp = t1 + timedelta(seconds=200) # Automated checkpoint at 200s
    t2 = t1 + timedelta(seconds=450) # Real edit at 450s

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    e_cp = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.SESSION_CHECKPOINT, canonical_fingerprint="fp_cp", client_timestamp=t_cp, server_timestamp=t_cp, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=3, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=t2, server_timestamp=t2, payload={})
    db_session.add_all([e1, e_cp, e2])
    db_session.commit()

    signals = evaluate_historical_idle_gaps(session, [e2], db_session)
    assert len(signals) == 1
    sig = signals[0]
    # Checkpoint ignored as non-meaningful: predecessor is e1, gap is 450s
    assert sig.evidence["meaningful_event_before_id"] == str(e1.id)
    assert sig.evidence["duration_seconds"] == 450.0

def test_historical_idle_non_meaningful_events_transparent(db_session, setup_user_and_session):
    """Scenario 5: Non-meaningful events (PROBLEM_OPENED, SNAPSHOT_CREATED) do not fragment a gap."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=10)
    t_po = t1 + timedelta(seconds=100)
    t_sc = t1 + timedelta(seconds=250)
    t2 = t1 + timedelta(seconds=500)

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    e_po = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.PROBLEM_OPENED, canonical_fingerprint="fp_po", client_timestamp=t_po, server_timestamp=t_po, payload={})
    e_sc = TraceEvent(session_id=session.id, sequence_number=3, event_type=TraceEventType.SNAPSHOT_CREATED, canonical_fingerprint="fp_sc", client_timestamp=t_sc, server_timestamp=t_sc, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=4, event_type=TraceEventType.SUBMISSION_CREATED, canonical_fingerprint="fp2", client_timestamp=t2, server_timestamp=t2, payload={})
    db_session.add_all([e1, e_po, e_sc, e2])
    db_session.commit()

    signals = evaluate_historical_idle_gaps(session, [e2], db_session)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.evidence["meaningful_event_before_id"] == str(e1.id)
    assert sig.evidence["duration_seconds"] == 500.0

def test_historical_idle_inverted_server_timestamp_non_qualifying(db_session, setup_user_and_session):
    """Scenario 10: Inverted server timestamps resulting in negative/zero duration do not qualify."""
    _, _, session = setup_user_and_session
    t_base = session.opened_at + timedelta(seconds=10)
    t_late = t_base + timedelta(seconds=400) # Arrival inversion: seq 2 has later ts than seq 3
    t_early = t_base + timedelta(seconds=350)

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t_base, server_timestamp=t_base, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=t_late, server_timestamp=t_late, payload={})
    e3 = TraceEvent(session_id=session.id, sequence_number=3, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp3", client_timestamp=t_early, server_timestamp=t_early, payload={})
    db_session.add_all([e1, e2, e3])
    db_session.commit()

    # e3 evaluated against causal predecessor e2 has duration = 350 - 400 = -50s <= 0 => does not qualify
    signals = evaluate_historical_idle_gaps(session, [e3], db_session)
    assert len(signals) == 0

def test_historical_idle_distinct_episodes_remain_distinct(db_session, setup_user_and_session):
    """Scenario 17: Distinct idle episodes within same session remain distinct with separate dedup keys."""
    _, _, session = setup_user_and_session
    t1 = session.opened_at + timedelta(seconds=400) # Episode 1: opened_at -> e1 (400s)
    t2 = t1 + timedelta(seconds=500) # Episode 2: e1 -> e2 (500s)

    e1 = TraceEvent(session_id=session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=t1, server_timestamp=t1, payload={})
    e2 = TraceEvent(session_id=session.id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=t2, server_timestamp=t2, payload={})
    db_session.add_all([e1, e2])
    db_session.commit()

    signals = evaluate_historical_idle_gaps(session, [e1, e2], db_session)
    assert len(signals) == 2
    assert signals[0].dedup_key != signals[1].dedup_key
    assert signals[0].evidence["meaningful_event_before_id"] is None
    assert signals[1].evidence["meaningful_event_before_id"] == str(e1.id)

def test_loc_and_change_ratio_use_real_line_breaks():
    # Regression: snapshot content uses real line breaks (LF or CRLF), not the literal two-character "\n"
    from app.services.judge.signals import _count_loc, _code_change_ratio
    code_lf = "def solve():\n    x = 1\n\n    return x\n"
    code_crlf = code_lf.replace("\n", "\r\n")
    assert _count_loc(code_lf) == 3
    assert _count_loc(code_crlf) == 3
    assert _code_change_ratio(code_lf, code_crlf) == 0.0
    assert _code_change_ratio(code_lf, "def solve():\n    x = 2\n\n    return x\n") > 0.0

def test_loc_anomaly_final_loc_after_finalization(db_session, setup_user_and_session):
    # docs/34 D7 (rule 1.1.0): null while ACTIVE, Session.final_loc once the session is finalized
    from app.models.session import PracticeAttempt
    student, problem, session = setup_user_and_session
    cls = Class(name="C-D7", academic_year="2026", owner_id=student.id)
    db_session.add(cls)
    db_session.flush()
    db_session.add(ClassMembership(class_id=cls.id, student_id=student.id))
    for _ in range(3):
        u_id = uuid.uuid4()
        u = User(email=f"u_{u_id}@test.com", password_hash="hash", role=RoleEnum.STUDENT, username=f"u_{u_id}", full_name="U")
        db_session.add(u)
        db_session.flush()
        db_session.add(ClassMembership(class_id=cls.id, student_id=u.id))
        attempt = PracticeAttempt(student_id=u.id, problem_id=problem.id)
        db_session.add(attempt)
        db_session.flush()
        peer = CodingSession(student_id=u.id, problem_id=problem.id, language=SupportedLanguage.PYTHON3, practice_attempt_id=attempt.id)
        db_session.add(peer)
        db_session.flush()
        _create_snapshot(db_session, peer, "\n".join(f"line {j}" for j in range(10)), 1)
    _create_snapshot(db_session, session, "\n".join(f"line {j}" for j in range(50)), 1)

    active_signal = evaluate_loc_anomaly(session, db_session)
    assert active_signal.evidence["final_loc"] is None

    session.status = SessionStatus.ENDED.value
    session.final_loc = 50
    db_session.commit()

    ended_signal = evaluate_loc_anomaly(session, db_session)
    assert ended_signal.evidence["final_loc"] == 50
    assert ended_signal.evidence["observed_loc"] == 50
    assert ended_signal.rule_version == "1.1.0"
