import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.services.judge.materializer import run_cycle, process_outbox_cycle
from app.models.observation import AttentionSignal, SignalType, TraceSignalOutbox
from app.models.trace import TraceEvent, TraceEventType, CodeSnapshot
from app.models.session import CodingSession, SessionStatus, PracticeAttempt
from app.models.user import User, RoleEnum
from app.models.problem import Problem, SupportedLanguage
from app.models.class_org import Class, ClassMembership
from app.models.run_submit import Run, RunVerdict
from app.services.storage import storage_adapter

pytestmark = pytest.mark.asyncio(loop_scope="function")

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

@pytest.fixture(scope="function", autouse=True)
def clean_db(db):
    db.execute(text("TRUNCATE TABLE trace_signal_outbox, attention_signals, coding_sessions, runs, code_snapshots, trace_events, practice_attempts, class_memberships, classes, users CASCADE;"))
    db.commit()

@pytest.fixture(scope="function")
def student_user(db):
    student = User(
        email=f"stu_e2e_{uuid.uuid4()}@test.com",
        password_hash="hash",
        role=RoleEnum.STUDENT,
        username=f"stu_e2e_{uuid.uuid4()}",
        full_name="E2E Student"
    )
    db.add(student)
    db.commit()
    return student

@pytest.fixture(scope="function")
def problem(db, student_user):
    prob = Problem(title="E2E Problem", description="E2E Problem Description", owner_id=student_user.id)
    db.add(prob)
    db.commit()
    return prob

@pytest.fixture(scope="function")
def active_session(db, student_user, problem):
    attempt = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add(attempt)
    db.commit()
    
    sess = CodingSession(
        student_id=student_user.id,
        problem_id=problem.id,
        language=SupportedLanguage.PYTHON3,
        opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        status=SessionStatus.ACTIVE,
        practice_attempt_id=attempt.id
    )
    db.add(sess)
    db.commit()
    return sess

def _setup_cohort(db: Session, student_user: User, problem: Problem):
    """Sets up a class and peer students with snapshots for LOC anomaly evaluation."""
    cls = Class(name="CS-E2E", owner_id=student_user.id, academic_year="2026")
    db.add(cls)
    db.commit()

    db.add(ClassMembership(student_id=student_user.id, class_id=cls.id, is_active=True))
    db.commit()

    for i in range(settings.SIGNAL_LOC_MIN_COHORT_SIZE):
        peer = User(
            username=f"peer_e2e_{i}_{uuid.uuid4()}",
            email=f"peer_e2e_{i}_{uuid.uuid4()}@test.com",
            password_hash="hash",
            role=RoleEnum.STUDENT,
            full_name=f"Peer {i}"
        )
        db.add(peer)
        db.commit()

        db.add(ClassMembership(student_id=peer.id, class_id=cls.id, is_active=True))
        attempt = PracticeAttempt(student_id=peer.id, problem_id=problem.id)
        db.add(attempt)
        db.flush()

        peer_sess = CodingSession(
            student_id=peer.id,
            problem_id=problem.id,
            language=SupportedLanguage.PYTHON3,
            status=SessionStatus.ACTIVE,
            practice_attempt_id=attempt.id
        )
        db.add(peer_sess)
        db.commit()

        # Peer snapshots: 10 lines each -> median LOC = 10.0
        shash, obj_key = storage_adapter.upload_code_snapshot(str(peer_sess.id), 1, "print('peer')\n" * 10)
        snap = CodeSnapshot(
            reason="RUN",
            language="PYTHON3",
            source_hash=shash,
            line_count=10,
            session_id=peer_sess.id,
            object_key=obj_key,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=30)
        )
        db.add(snap)
        db.commit()

def test_complete_session_lifecycle_all_four_signals_e2e(db: Session, student_user, problem, active_session):
    """
    AC-08D-12: Unified End-to-End Integration Test
    Validates that a complete student practice session lifecycle triggers all 4 authorized
    attention signals (FAST_FIRST_CODE, IDLE_DETECTED, REPEATED_FAILURE, LOC_ANOMALY),
    verifying non-null rule_version, exact evidence schemas, objectivity, privacy, and idempotency.
    """
    session_open = active_session.opened_at

    # -------------------------------------------------------------------------
    # 1. FAST_FIRST_CODE: First edit arrives 10s after session open (<= 30s)
    # -------------------------------------------------------------------------
    t_first_edit = session_open + timedelta(seconds=10)
    event_first_edit = TraceEvent(
        session_id=active_session.id,
        sequence_number=1,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp_first_edit",
        client_timestamp=t_first_edit,
        server_timestamp=t_first_edit,
        payload={"change": "initial code"}
    )
    db.add(event_first_edit)
    db.commit()

    # -------------------------------------------------------------------------
    # 2. IDLE_DETECTED: A 400s gap of inactivity before next meaningful event
    # -------------------------------------------------------------------------
    t_second_edit = t_first_edit + timedelta(seconds=400)
    event_second_edit = TraceEvent(
        session_id=active_session.id,
        sequence_number=2,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp_second_edit",
        client_timestamp=t_second_edit,
        server_timestamp=t_second_edit,
        payload={"change": "resumed code"}
    )
    db.add(event_second_edit)
    db.commit()

    # -------------------------------------------------------------------------
    # 3. REPEATED_FAILURE: 3 consecutive runs with identical normalized error
    # -------------------------------------------------------------------------
    run_code = "def solution():\n    raise ValueError('index out of bounds 0x7ffd98b0')\n"
    for i in range(settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS):
        t_run = t_second_edit + timedelta(seconds=30 * (i + 1))
        shash, obj_key = storage_adapter.upload_code_snapshot(str(active_session.id), i + 1, run_code)
        snap = CodeSnapshot(
            reason="RUN",
            language="PYTHON3",
            source_hash=shash,
            line_count=2,
            session_id=active_session.id,
            object_key=obj_key,
            created_at=t_run
        )
        db.add(snap)
        db.flush()

        run = Run(
            session_id=active_session.id,
            snapshot_id=snap.id,
            verdict=RunVerdict.RUNTIME_ERROR,
            created_at=t_run,
            testcase_results={"runtime_error_message": "ValueError: index out of bounds 0x7ffd98b0"}
        )
        db.add(run)
        db.commit()

    # -------------------------------------------------------------------------
    # 4. LOC_ANOMALY: Cohort median is 10 lines; student submits snapshot of 30 lines (> 2.0x)
    # -------------------------------------------------------------------------
    _setup_cohort(db, student_user, problem)
    student_loc_code = "x = 1\n" * 30
    shash_loc, obj_key_loc = storage_adapter.upload_code_snapshot(str(active_session.id), 99, student_loc_code)
    student_loc_snap = CodeSnapshot(
        reason="RUN",
        language="PYTHON3",
        source_hash=shash_loc,
        line_count=30,
        session_id=active_session.id,
        object_key=obj_key_loc,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10)
    )
    db.add(student_loc_snap)
    db.commit()

    # -------------------------------------------------------------------------
    # 5. EXECUTION: Run Outbox Cycle + Scheduled Cycle
    # -------------------------------------------------------------------------
    # Outbox processes historical events & idle gaps
    process_outbox_cycle(db)

    # Materializer run_cycle processes active-tail heuristics
    since_dt = datetime.now(timezone.utc) - timedelta(hours=3)
    metrics = run_cycle(db, since_dt)
    assert metrics["candidates_evaluated"] >= 1

    # -------------------------------------------------------------------------
    # 6. VERIFICATION: Assert all 4 distinct signal types are materialized
    # -------------------------------------------------------------------------
    signals = db.scalars(
        select(AttentionSignal)
        .where(AttentionSignal.session_id == active_session.id)
        .order_by(AttentionSignal.detected_at.asc())
    ).all()

    signal_types_found = {s.signal_type for s in signals}
    expected_types = {
        SignalType.FAST_FIRST_CODE,
        SignalType.IDLE_DETECTED,
        SignalType.REPEATED_FAILURE,
        SignalType.LOC_ANOMALY
    }
    assert signal_types_found == expected_types, f"Expected {expected_types}, found {signal_types_found}"
    # Two distinct IDLE episodes: the closed 400s gap (historical outbox mode) and the
    # still-open tail since the second edit (session opened 2h ago, active-tail mode)
    idle_signals = [s for s in signals if s.signal_type == SignalType.IDLE_DETECTED]
    assert len(idle_signals) == 2, f"Expected 2 IDLE episodes, found {len(idle_signals)}"
    assert len(signals) == 5, f"Expected exactly 5 signals, found {len(signals)}"
    tail_idle = next(s for s in idle_signals if not s.evidence.get("gap_closed"))
    assert tail_idle.evidence["meaningful_event_before_id"] == str(event_second_edit.id)

    # Specific assertions per signal
    for sig in signals:
        assert sig.student_id == student_user.id
        assert sig.rule_version == settings.SIGNAL_RULE_VERSION
        assert sig.rule_version == "1.1.0"
        assert isinstance(sig.evidence, dict)
        assert len(sig.evidence) > 0

        # Objectivity audit: no judgmental or cognitive words in evidence
        evidence_str = str(sig.evidence).lower()
        forbidden_words = ["cheat", "gian lận", "yếu", "không hiểu", "struggling", "suspicious", "vấn đề"]
        for word in forbidden_words:
            assert word not in evidence_str, f"Forbidden word '{word}' found in evidence: {evidence_str}"

    # Detailed schema checks
    fast_sig = next(s for s in signals if s.signal_type == SignalType.FAST_FIRST_CODE)
    assert fast_sig.evidence["delta_seconds"] == 10.0
    assert fast_sig.evidence["threshold_seconds"] == settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS

    idle_sig = next(s for s in idle_signals if s.evidence.get("gap_closed"))
    assert idle_sig.evidence["duration_seconds"] == 400.0
    assert idle_sig.evidence["meaningful_event_before_id"] == str(event_first_edit.id)

    rf_sig = next(s for s in signals if s.signal_type == SignalType.REPEATED_FAILURE)
    assert rf_sig.evidence["target_entity"] == "RUN"
    assert rf_sig.evidence["run_count"] == settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS
    assert rf_sig.evidence["failed_count"] == settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS

    loc_sig = next(s for s in signals if s.signal_type == SignalType.LOC_ANOMALY)
    assert loc_sig.evidence["observed_loc"] == 30
    assert loc_sig.evidence["context_median_loc"] == 10.0
    assert loc_sig.evidence["threshold_relative"] == settings.SIGNAL_LOC_DEVIATION_MULTIPLIER
    assert loc_sig.evidence["final_loc"] is None
    # Peer privacy: no peer student IDs or codes in evidence
    assert "peer" not in str(loc_sig.evidence).lower()

    # -------------------------------------------------------------------------
    # 7. IDEMPOTENCY: Re-running cycles produces zero duplicates
    # -------------------------------------------------------------------------
    process_outbox_cycle(db)
    run_cycle(db, since_dt)

    signals_after = db.scalars(
        select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)
    ).all()
    assert len(signals_after) == len(signals)
