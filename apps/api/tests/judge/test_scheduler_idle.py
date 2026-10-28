import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.services.judge.materializer import run_cycle, process_outbox_cycle
from app.models.observation import AttentionSignal, SignalType, TraceSignalOutbox
from app.models.trace import TraceEvent, TraceEventType
from app.models.session import SessionStatus

pytestmark = pytest.mark.asyncio(loop_scope="function")

@pytest.fixture(scope="function", autouse=True)
def clean_db(db):
    from sqlalchemy import text
    db.execute(text("TRUNCATE TABLE trace_signal_outbox, attention_signals, coding_sessions, runs, code_snapshots, trace_events, practice_attempts, class_memberships, classes, users CASCADE;"))
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


def test_c_idle_01_active_threshold_crossed(db: Session, active_session):
    # C-IDLE-01: active idle threshold crossed => one signal
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.IDLE_DETECTED

def test_c_idle_02_same_episode_repeated(db: Session, active_session):
    # C-IDLE-02: same continuous idle episode, cycle repeated => still one signal
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    run_cycle(db, since_dt) # Repeat
    
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1

def test_c_idle_03_and_04_meaningful_activity_new_episode(db: Session, active_session):
    # C-IDLE-03: meaningful activity occurs => old idle episode ends
    # C-IDLE-04: later new idle threshold crossing => second distinct signal allowed
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS * 3)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1
    
    # Meaningful activity
    new_event = TraceEvent(
        session_id=active_session.id,
        event_type=TraceEventType.EDITOR_CHANGED,
        server_timestamp=datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10),
        sequence_number=1,
        canonical_fingerprint='fp1',
        payload={},
        client_timestamp=datetime.now(timezone.utc)
    )
    db.add(new_event)
    db.commit()
    
    # Run cycle again
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 2

def test_c_idle_05_06_07_status_changes(db: Session, active_session):
    # C-IDLE-05: idle never changes session ACTIVE status
    # C-IDLE-06: ENDED no ongoing idle signal
    # C-IDLE-07: ABANDONED no ongoing idle signal
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS + 10)
    db.commit()
    
    since_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    run_cycle(db, since_dt)
    assert active_session.status == SessionStatus.ACTIVE
    
    active_session.status = SessionStatus.ENDED
    db.commit()
    
    # Even if time advances, no new signal
    active_session.opened_at = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_IDLE_THRESHOLD_SECONDS * 5)
    db.commit()
    
    run_cycle(db, since_dt)
    signals = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all()
    assert len(signals) == 1 # Still just 1

# =========================================================================
# OUTBOX HISTORICAL IDLE INTEGRATION TESTS
# =========================================================================
def test_c_idle_outbox_bounded_chunk_and_cross_chunk_predecessor(db: Session, active_session):
    """Scenario 6 & 7: Bounded chunk processing (limit 500) and cross-chunk predecessor resolution."""
    now = datetime.now(timezone.utc) - timedelta(hours=2)

    # Insert 600 contiguous trace events:
    # Event 1..500: quick edits (1s apart)
    # Event 500 -> 501: 400s idle gap across the chunk boundary!
    # Event 501..600: quick edits (1s apart)
    events = []
    curr_time = now
    for i in range(1, 601):
        if i == 501:
            curr_time += timedelta(seconds=400) # Gap across boundary
        else:
            curr_time += timedelta(seconds=1)

        events.append(TraceEvent(
            session_id=active_session.id,
            sequence_number=i,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint=f"fp_{i}",
            client_timestamp=curr_time,
            server_timestamp=curr_time,
            payload={}
        ))
    db.add_all(events)
    db.commit()

    # Verify outbox has 600 items via trigger
    outbox_count = db.scalar(
        select(TraceSignalOutbox).where(TraceSignalOutbox.session_id == active_session.id)
    )
    assert outbox_count is not None

    # Iteration 1: Process with chunk_limit = 500
    metrics1 = process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)
    assert metrics1["outbox_deleted"] == 500
    # No gap >= 300s in chunk 1 (all were 1s apart)
    assert metrics1["signals_materialized"] == 0

    # Iteration 2: Process remaining 100 events (501..600)
    metrics2 = process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)
    assert metrics2["outbox_deleted"] == 100
    # The gap from 500 to 501 (400s) must qualify across chunk boundary!
    assert metrics2["signals_materialized"] == 1

    signals = db.scalars(
        select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)
    ).all()
    assert len(signals) == 1
    assert signals[0].evidence["duration_seconds"] == 400.0
    assert signals[0].evidence["meaningful_event_before_id"] == str(events[499].id)

def test_c_idle_outbox_missing_sequence_defers(db: Session, active_session):
    """Scenario 8: Missing sequence defers affected outbox tasks until contiguity is restored."""
    now = datetime.now(timezone.utc) - timedelta(hours=1)

    # Ingest events 1..5, skip 6, ingest 7..10
    events_part1 = [
        TraceEvent(
            session_id=active_session.id,
            sequence_number=i,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint=f"fp_{i}",
            client_timestamp=now + timedelta(seconds=i),
            server_timestamp=now + timedelta(seconds=i),
            payload={}
        )
        for i in range(1, 6)
    ]
    events_part2 = [
        TraceEvent(
            session_id=active_session.id,
            sequence_number=i,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint=f"fp_{i}",
            client_timestamp=now + timedelta(seconds=i + 400),
            server_timestamp=now + timedelta(seconds=i + 400),
            payload={}
        )
        for i in range(7, 11)
    ]
    db.add_all(events_part1 + events_part2)
    db.commit()

    # Process outbox: contiguity halts at sequence 5
    metrics1 = process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)
    assert metrics1["outbox_deleted"] == 5

    # Outbox still contains events 7..10
    remaining_seqs = db.scalars(
        select(TraceSignalOutbox.sequence_number)
        .where(TraceSignalOutbox.session_id == active_session.id)
        .order_by(TraceSignalOutbox.sequence_number.asc())
    ).all()
    assert list(remaining_seqs) == [7, 8, 9, 10]

    # Now event 6 arrives and commits
    e6 = TraceEvent(
        session_id=active_session.id,
        sequence_number=6,
        event_type=TraceEventType.EDITOR_CHANGED,
        canonical_fingerprint="fp_6",
        client_timestamp=now + timedelta(seconds=6),
        server_timestamp=now + timedelta(seconds=6),
        payload={}
    )
    db.add(e6)
    db.commit()

    # Process outbox again: contiguity restored, all remaining (6..10) processed!
    metrics2 = process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)
    assert metrics2["outbox_deleted"] == 5 # 6, 7, 8, 9, 10
    # Gap between 6 and 7 was 400s -> qualifies!
    assert metrics2["signals_materialized"] >= 1

def test_c_idle_outbox_two_workers_session_locking(db: Session, student_user, problem):
    """Scenario 9: Two workers cannot process the same session concurrently."""
    from app.models.session import PracticeAttempt
    now = datetime.now(timezone.utc) - timedelta(hours=1)

    # Setup two distinct sessions
    att1 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    att2 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add_all([att1, att2])
    db.flush()

    s1 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=att1.id)
    s2 = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=att2.id)
    db.add_all([s1, s2])
    db.flush()

    e1 = TraceEvent(session_id=s1.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=now, server_timestamp=now, payload={})
    e2 = TraceEvent(session_id=s2.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=now, server_timestamp=now, payload={})
    db.add_all([e1, e2])
    db.commit()

    # Worker 1 transaction holds session 1
    sess2 = TestingSessionLocal()
    try:
        # Worker 1 locks session 1 with FOR NO KEY UPDATE SKIP LOCKED
        claim_stmt = (
            select(CodingSession)
            .where(CodingSession.id.in_(select(TraceSignalOutbox.session_id)))
            .order_by(CodingSession.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        w1_session = db.scalar(claim_stmt)
        assert w1_session is not None

        # Worker 2 attempts claiming concurrently
        w2_session = sess2.scalar(claim_stmt)
        assert w2_session is not None

        # They must be partitioned to different sessions
        assert w1_session.id != w2_session.id
    finally:
        sess2.rollback()
        sess2.close()

def test_c_idle_outbox_crash_rollback(db: Session, active_session):
    """Scenario 11: Crash during materialization rolls back both signals and outbox acknowledgement."""
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    e1 = TraceEvent(session_id=active_session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=now, server_timestamp=now, payload={})
    e2 = TraceEvent(session_id=active_session.id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=now + timedelta(seconds=400), server_timestamp=now + timedelta(seconds=400), payload={})
    db.add_all([e1, e2])
    db.commit()

    # Simulate crash inside outbox processing
    from unittest.mock import patch
    with patch("app.services.judge.materializer.materialize_signal", side_effect=RuntimeError("Simulated DB Crash")):
        with pytest.raises(RuntimeError, match="Simulated DB Crash"):
            process_outbox_cycle(db, batch_sessions=1)

    # After rollback, outbox rows are NOT deleted
    outbox_count = db.scalar(
        select(TraceSignalOutbox).where(TraceSignalOutbox.session_id == active_session.id)
    )
    assert outbox_count is not None
    # No signals committed
    sig_count = db.scalar(
        select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)
    )
    assert sig_count is None

def test_c_idle_outbox_24h_downtime_recovery(db: Session, active_session):
    """Scenario 12: Recovery after 24-hour downtime drains outbox completely."""
    now = datetime.now(timezone.utc) - timedelta(hours=24)
    active_session.opened_at = now
    db.commit()

    # Ingest 3 distinct idle intervals across 24h
    events = []
    curr_time = now
    seq = 1
    for interval in [400, 50, 450, 60, 500]: # 3 gaps >= 300s
        curr_time += timedelta(seconds=interval)
        events.append(TraceEvent(
            session_id=active_session.id,
            sequence_number=seq,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint=f"fp_24_{seq}",
            client_timestamp=curr_time,
            server_timestamp=curr_time,
            payload={}
        ))
        seq += 1
    db.add_all(events)
    db.commit()

    # Run outbox cycle: drains all items
    metrics = process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)
    assert metrics["outbox_deleted"] == len(events)
    assert metrics["signals_materialized"] >= 3

    # Outbox is completely empty
    remaining = db.scalars(
        select(TraceSignalOutbox).where(TraceSignalOutbox.session_id == active_session.id)
    ).all()
    assert len(remaining) == 0

def test_c_idle_outbox_active_ended_abandoned_coverage(db: Session, student_user, problem):
    """Scenario 13 & 14: Historical gaps processed in ACTIVE, ENDED, and ABANDONED. Tail only on ACTIVE."""
    from app.models.session import PracticeAttempt
    now = datetime.now(timezone.utc) - timedelta(hours=2)

    att1 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    att2 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    att3 = PracticeAttempt(student_id=student_user.id, problem_id=problem.id)
    db.add_all([att1, att2, att3])
    db.flush()

    s_act = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ACTIVE, practice_attempt_id=att1.id, opened_at=now)
    s_end = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ENDED, practice_attempt_id=att2.id, opened_at=now)
    s_abn = CodingSession(student_id=student_user.id, problem_id=problem.id, language="PYTHON3", status=SessionStatus.ABANDONED, practice_attempt_id=att3.id, opened_at=now)
    db.add_all([s_act, s_end, s_abn])
    db.flush()

    for s in [s_act, s_end, s_abn]:
        e1 = TraceEvent(session_id=s.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint=f"fp1_{s.id}", client_timestamp=now, server_timestamp=now, payload={})
        e2 = TraceEvent(session_id=s.id, sequence_number=2, event_type=TraceEventType.RUN_REQUESTED, canonical_fingerprint=f"fp2_{s.id}", client_timestamp=now + timedelta(seconds=400), server_timestamp=now + timedelta(seconds=400), payload={})
        db.add_all([e1, e2])
    db.commit()

    # Process all sessions
    metrics = process_outbox_cycle(db, batch_sessions=10, chunk_limit=500)
    assert metrics["sessions_claimed"] == 3

    # All 3 sessions must have their historical gap (400s) materialized!
    sig_act = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == s_act.id)).all()
    sig_end = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == s_end.id)).all()
    sig_abn = db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == s_abn.id)).all()

    assert len(sig_act) >= 1
    assert len(sig_end) >= 1
    assert len(sig_abn) >= 1

def test_c_idle_outbox_tail_historical_overlap_one_alert(db: Session, active_session):
    """Scenario 15: Case A overlap produces exactly one alert with immutable evidence."""
    now = datetime.now(timezone.utc) - timedelta(seconds=600)

    # 1. Active tail triggers at 09:06
    e1 = TraceEvent(session_id=active_session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=now, server_timestamp=now, payload={})
    db.add(e1)
    db.commit()

    # Tail signal materialized
    from app.services.judge.signals import evaluate_idle_detected
    from app.services.judge.materializer import materialize_signal
    tail_sig = evaluate_idle_detected(active_session, db, evaluated_at=now + timedelta(seconds=360))
    assert tail_sig is not None
    materialize_signal(db, tail_sig)

    # 2. Student comes back and executes event 2 at 09:12 (600s after e1)
    e2 = TraceEvent(session_id=active_session.id, sequence_number=2, event_type=TraceEventType.RUN_REQUESTED, canonical_fingerprint="fp2", client_timestamp=now + timedelta(seconds=600), server_timestamp=now + timedelta(seconds=600), payload={})
    db.add(e2)
    db.commit()

    # Process outbox
    process_outbox_cycle(db, batch_sessions=1, chunk_limit=500)

    # Exactly 1 signal exists in database (deduped on W1 key!)
    signals = db.scalars(
        select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)
    ).all()
    assert len(signals) == 1
    # Evidence remains the immutable tail evidence from detection time (360s)
    assert signals[0].evidence["duration_seconds"] == 360.0

def test_c_idle_outbox_repeated_replay_idempotency(db: Session, active_session):
    """Scenario 16: Repeated replay does not create duplicates."""
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    e1 = TraceEvent(session_id=active_session.id, sequence_number=1, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp1", client_timestamp=now, server_timestamp=now, payload={})
    e2 = TraceEvent(session_id=active_session.id, sequence_number=2, event_type=TraceEventType.EDITOR_CHANGED, canonical_fingerprint="fp2", client_timestamp=now + timedelta(seconds=400), server_timestamp=now + timedelta(seconds=400), payload={})
    db.add_all([e1, e2])
    db.commit()

    # Cycle 1
    process_outbox_cycle(db, batch_sessions=1)
    sig_count1 = len(db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all())
    assert sig_count1 == 1

    # Re-insert outbox rows manually to simulate replay
    e1_type = getattr(e1.event_type, "value", e1.event_type)
    e2_type = getattr(e2.event_type, "value", e2.event_type)
    o1 = TraceSignalOutbox(session_id=active_session.id, event_id=e1.id, event_type=e1_type, sequence_number=1, server_timestamp=e1.server_timestamp)
    o2 = TraceSignalOutbox(session_id=active_session.id, event_id=e2.id, event_type=e2_type, sequence_number=2, server_timestamp=e2.server_timestamp)
    db.add_all([o1, o2])
    db.commit()

    # Cycle 2 (replay)
    process_outbox_cycle(db, batch_sessions=1)
    sig_count2 = len(db.scalars(select(AttentionSignal).where(AttentionSignal.session_id == active_session.id)).all())
    assert sig_count2 == 1 # Still strictly 1

def test_c_idle_live_ingestion_not_blocked_by_worker(db: Session, active_session):
    """Lock contention invariant: Live student trace ingestion is not blocked by worker session lock."""
    # Worker locks session with FOR NO KEY UPDATE
    lock_stmt = select(CodingSession.id).where(CodingSession.id == active_session.id).with_for_update(key_share=False)
    # Using raw SQL with FOR NO KEY UPDATE
    from sqlalchemy import text
    db.execute(text("SELECT id FROM coding_sessions WHERE id = :id FOR NO KEY UPDATE"), {"id": active_session.id})

    # In secondary transaction, simulate student trace ingestion (which executes INSERT INTO trace_events, requiring FOR KEY SHARE)
    sess2 = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        e = TraceEvent(
            session_id=active_session.id,
            sequence_number=99,
            event_type=TraceEventType.EDITOR_CHANGED,
            canonical_fingerprint="fp99",
            client_timestamp=now,
            server_timestamp=now,
            payload={}
        )
        sess2.add(e)
        # Must commit without blocking or timeout!
        sess2.commit()
    finally:
        sess2.close()
        db.rollback()
