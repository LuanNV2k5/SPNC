import uuid
from typing import Optional, List, Tuple, Any
from datetime import datetime, timezone
import difflib
import re

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc, func

from app.core.config import settings
from app.models.session import CodingSession, SessionStatus
from app.models.observation import AttentionSignal, SignalType
from app.models.trace import TraceEvent, TraceEventType, CodeSnapshot
from app.models.run_submit import Run, RunVerdict
from app.models.class_org import ClassMembership, Class
from app.models.problem import Problem
from app.services.storage import StorageUnavailable, storage_adapter
from app.services.loc import count_loc

# Meaningful events for IDLE_DETECTED (strictly closed domain set)
MEANINGFUL_EVENT_TYPES = {
    TraceEventType.EDITOR_CHANGED,
    TraceEventType.RUN_REQUESTED,
    TraceEventType.SUBMISSION_CREATED,
}

def _get_stable_time(dt: datetime) -> int:
    return int(dt.timestamp())

def evaluate_idle_detected(session: CodingSession, db: Session, evaluated_at: Optional[datetime] = None) -> Optional[AttentionSignal]:
    if session.status != SessionStatus.ACTIVE:
        return None

    if evaluated_at is None:
        evaluated_at = datetime.now(timezone.utc)

    # Get latest meaningful event
    stmt = (
        select(TraceEvent)
        .where(
            and_(
                TraceEvent.session_id == session.id,
                TraceEvent.event_type.in_(MEANINGFUL_EVENT_TYPES)
            )
        )
        .order_by(desc(TraceEvent.server_timestamp))
        .limit(1)
    )
    latest_event = db.execute(stmt).scalar_one_or_none()
    
    last_meaningful_at = latest_event.server_timestamp if latest_event else session.opened_at
    idle_seconds = (evaluated_at - last_meaningful_at).total_seconds()
    
    if idle_seconds >= settings.SIGNAL_IDLE_THRESHOLD_SECONDS:
        window = int(idle_seconds // settings.SIGNAL_IDLE_THRESHOLD_SECONDS)
        dedup_key = f"IDLE:{session.id}:{_get_stable_time(last_meaningful_at)}:W{window}"
        
        evidence = {
            "session_id": str(session.id),
            "last_meaningful_event_at": last_meaningful_at.isoformat(),
            "evaluated_at": evaluated_at.isoformat(),
            "idle_duration_seconds": idle_seconds,
            "threshold_seconds": settings.SIGNAL_IDLE_THRESHOLD_SECONDS,
            "last_meaningful_event_type": getattr(latest_event.event_type, "value", latest_event.event_type) if latest_event else "SESSION_OPENED",
            # Authoritative REQ-IDLE-002 & docs/01_DOMAIN.md §1.8 fields
            "start_time": last_meaningful_at.isoformat(),
            "end_time": evaluated_at.isoformat(),
            "duration_seconds": idle_seconds,
            "meaningful_event_before_id": str(latest_event.id) if latest_event else None,
            "threshold_used": settings.SIGNAL_IDLE_THRESHOLD_SECONDS,
        }
        
        return AttentionSignal(
            student_id=session.student_id,
            session_id=session.id,
            signal_type=SignalType.IDLE_DETECTED,
            rule_version=settings.SIGNAL_RULE_VERSION,
            evidence=evidence,
            dedup_key=dedup_key
        )
    return None

def evaluate_historical_idle_gaps(session: CodingSession, target_events: List[Any], db: Session) -> List[AttentionSignal]:
    """
    Evaluates historical IDLE_DETECTED signals for intervals closed by target_events.
    target_events can be TraceSignalOutbox or TraceEvent items belonging to session.
    Enforces deterministic causal predecessor lookup and non-positive duration guards.
    """
    signals: List[AttentionSignal] = []
    if not target_events:
        return signals

    sorted_targets = sorted(target_events, key=lambda e: getattr(e, "sequence_number", 0))

    for event in sorted_targets:
        event_seq = getattr(event, "sequence_number", 0)
        event_ts = getattr(event, "server_timestamp", None)
        event_id = getattr(event, "event_id", None) or getattr(event, "id", None)
        event_type = getattr(event, "event_type", None)
        if hasattr(event_type, "value"):
            event_type = event_type.value

        # Predecessor query in trace_events: immediate preceding meaningful event in sequence
        stmt = (
            select(TraceEvent)
            .where(
                and_(
                    TraceEvent.session_id == session.id,
                    TraceEvent.event_type.in_(MEANINGFUL_EVENT_TYPES),
                    TraceEvent.sequence_number < event_seq
                )
            )
            .order_by(desc(TraceEvent.sequence_number))
            .limit(1)
        )
        prev_event = db.execute(stmt).scalar_one_or_none()

        if prev_event:
            start_time = prev_event.server_timestamp
            prev_id = str(prev_event.id)
            prev_type = getattr(prev_event.event_type, "value", prev_event.event_type)
        else:
            start_time = session.opened_at
            prev_id = None
            prev_type = "SESSION_OPENED"

        gap_seconds = (event_ts - start_time).total_seconds()

        # Guard against non-positive durations (e.g. inverted arrival timestamps)
        if gap_seconds <= 0:
            continue

        if gap_seconds >= settings.SIGNAL_IDLE_THRESHOLD_SECONDS:
            window = 1
            dedup_key = f"IDLE:{session.id}:{_get_stable_time(start_time)}:W{window}"

            evidence = {
                "session_id": str(session.id),
                "start_time": start_time.isoformat(),
                "end_time": event_ts.isoformat(),
                "duration_seconds": gap_seconds,
                "meaningful_event_before_id": prev_id,
                "threshold_used": settings.SIGNAL_IDLE_THRESHOLD_SECONDS,
                # Canonical & legacy compatibility fields
                "last_meaningful_event_at": start_time.isoformat(),
                "evaluated_at": event_ts.isoformat(),
                "idle_duration_seconds": gap_seconds,
                "threshold_seconds": settings.SIGNAL_IDLE_THRESHOLD_SECONDS,
                "last_meaningful_event_type": prev_type,
                "gap_closed": True,
                "closing_event_id": str(event_id) if event_id else None,
                "closing_event_type": event_type,
            }

            signals.append(
                AttentionSignal(
                    student_id=session.student_id,
                    session_id=session.id,
                    signal_type=SignalType.IDLE_DETECTED,
                    rule_version=settings.SIGNAL_RULE_VERSION,
                    evidence=evidence,
                    dedup_key=dedup_key
                )
            )

    return signals

def evaluate_fast_first_code(session: CodingSession, db: Session) -> Optional[AttentionSignal]:
    # First edit inside configured threshold
    stmt = (
        select(TraceEvent)
        .where(
            and_(
                TraceEvent.session_id == session.id,
                TraceEvent.event_type == TraceEventType.EDITOR_CHANGED
            )
        )
        .order_by(TraceEvent.sequence_number)
        .limit(1)
    )
    first_edit = db.execute(stmt).scalar_one_or_none()
    
    if not first_edit:
        return None
        
    elapsed = (first_edit.server_timestamp - session.opened_at).total_seconds()
    if elapsed <= settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS:
        dedup_key = f"FAST:{session.id}:{first_edit.id}"
        evidence = {
            # Authoritative canonical contract (docs/01_DOMAIN.md §1.8 / REQ-SIGNAL-003)
            "problem_open_time": session.opened_at.isoformat(),
            "first_code_event_time": first_edit.server_timestamp.isoformat(),
            "delta_seconds": elapsed,
            "threshold_seconds": settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS,
            # Preserved Phase 08 legacy fields for backward compatibility
            "session_id": str(session.id),
            "session_opened_at": session.opened_at.isoformat(),
            "first_code_event_at": first_edit.server_timestamp.isoformat(),
            "elapsed_seconds": elapsed,
            "configured_threshold_seconds": settings.SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS,
            "first_code_event_id": str(first_edit.id)
        }
        
        return AttentionSignal(
            student_id=session.student_id,
            session_id=session.id,
            signal_type=SignalType.FAST_FIRST_CODE,
            rule_version=settings.SIGNAL_RULE_VERSION,
            evidence=evidence,
            dedup_key=dedup_key
        )
    return None

def _normalize_error(run: Run) -> str:
    if run.verdict == RunVerdict.COMPILE_ERROR and run.testcase_results and "compile_error_message" in run.testcase_results:
        err = run.testcase_results["compile_error_message"] or ""
        first_line = err.splitlines()[0] if err else ""
        return re.sub(r"0x[0-9a-fA-F]+|\d+", "X", first_line).strip()
    elif run.verdict == RunVerdict.RUNTIME_ERROR and run.testcase_results and "runtime_error_message" in run.testcase_results:
        err = run.testcase_results["runtime_error_message"] or ""
        first_line = err.splitlines()[0] if err else ""
        return re.sub(r"0x[0-9a-fA-F]+|\d+", "X", first_line).strip()
    return getattr(run.verdict, "value", run.verdict) if run.verdict else "UNKNOWN"

def _code_change_ratio(code1: str, code2: str) -> float:
    lines1 = [line for line in code1.splitlines() if line.strip()]
    lines2 = [line for line in code2.splitlines() if line.strip()]
    if not lines1 and not lines2:
        return 0.0
    ratio = difflib.SequenceMatcher(None, lines1, lines2).ratio()
    return 1.0 - ratio

def evaluate_repeated_failure(session: CodingSession, db: Session) -> Optional[AttentionSignal]:
    min_attempts = settings.SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS
    max_change_ratio = settings.SIGNAL_REPEATED_FAILURE_MAX_CODE_CHANGE_RATIO
    
    # Get last N runs
    stmt = (
        select(Run)
        .where(Run.session_id == session.id)
        .order_by(desc(Run.created_at))
        .limit(min_attempts)
    )
    runs = list(db.execute(stmt).scalars())
    
    if len(runs) < min_attempts:
        return None
    
    runs.reverse() # Chronological order
    signatures = []
    snapshot_ids = []
    
    for run in runs:
        if run.verdict in (RunVerdict.ACCEPTED, None):
            return None # Breaks sequence
        signatures.append(_normalize_error(run))
        snapshot_ids.append(run.snapshot_id)
        
    if len(set(signatures)) > 1:
        return None # Different failures
        
    # Check code change metric
    stmt_snaps = select(CodeSnapshot).where(CodeSnapshot.id.in_(snapshot_ids))
    snaps_db = db.execute(stmt_snaps).scalars().all()
    snap_map = {s.id: s for s in snaps_db}
    
    max_change = 0.0
    for i in range(1, len(runs)):
        s1 = snap_map.get(runs[i-1].snapshot_id)
        s2 = snap_map.get(runs[i].snapshot_id)
        if s1 and s2:
            try:
                c1 = storage_adapter.download_code_snapshot(s1.object_key)
                c2 = storage_adapter.download_code_snapshot(s2.object_key)
            except StorageUnavailable:
                # Evidence cannot be verified without the code (REQ-SIGNAL-003): no signal
                return None
            change = _code_change_ratio(c1, c2)
            max_change = max(max_change, change)
            
    if max_change > max_change_ratio:
        return None

    last_run = runs[-1]
    dedup_key = f"RF:{session.id}:{last_run.id}"
    
    evidence = {
        # Authoritative canonical contract (DCR SPNC_RF_RUN_EVIDENCE_CONTRACT / docs/01_DOMAIN.md §1.8)
        "problem_id": str(session.problem_id),
        "target_entity": "RUN",
        "run_count": len(runs),
        "failed_count": len(runs),
        "verdicts": [getattr(r.verdict, "value", str(r.verdict)) for r in runs],
        "time_range_start": runs[0].created_at.isoformat(),
        "time_range_end": last_run.created_at.isoformat(),
        # Preserved Phase 08 legacy diagnostic fields for backward compatibility
        "session_id": str(session.id),
        "run_ids": [str(r.id) for r in runs],
        "snapshot_ids": [str(sid) for sid in snapshot_ids],
        "failure_signature": signatures[0],
        "attempt_count": min_attempts,
        "max_code_change_ratio": max_change,
        "configured_max_ratio": max_change_ratio,
        "last_run_at": last_run.created_at.isoformat()
    }
    
    return AttentionSignal(
        student_id=session.student_id,
        session_id=session.id,
        signal_type=SignalType.REPEATED_FAILURE,
        rule_version=settings.SIGNAL_RULE_VERSION,
        evidence=evidence,
        dedup_key=dedup_key
    )

_count_loc = count_loc

def evaluate_loc_anomaly(session: CodingSession, db: Session) -> Optional[AttentionSignal]:
    min_cohort = settings.SIGNAL_LOC_MIN_COHORT_SIZE
    dev_policy = settings.SIGNAL_LOC_DEVIATION_MULTIPLIER
    
    # 1. Identify active classes for the student
    stmt_classes = (
        select(ClassMembership.class_id)
        .where(
            and_(
                ClassMembership.student_id == session.student_id,
                ClassMembership.is_active == True
            )
        )
    )
    class_ids = list(db.execute(stmt_classes).scalars())
    if not class_ids:
        return None
        
    # 2. Get cohort students in these classes
    stmt_cohort_students = (
        select(ClassMembership.student_id)
        .where(
            and_(
                ClassMembership.class_id.in_(class_ids),
                ClassMembership.is_active == True,
                ClassMembership.student_id != session.student_id
            )
        )
    )
    cohort_student_ids = list(set(db.execute(stmt_cohort_students).scalars()))
    if not cohort_student_ids:
        return None
        
    # 3. Get their latest snapshots for the same problem
    # Subquery to get latest snapshot per session
    subq = (
        select(CodeSnapshot.session_id, func.max(CodeSnapshot.created_at).label("max_created_at"))
        .join(CodingSession, CodeSnapshot.session_id == CodingSession.id)
        .where(
            and_(
                CodingSession.student_id.in_(cohort_student_ids),
                CodingSession.problem_id == session.problem_id
            )
        )
        .group_by(CodeSnapshot.session_id)
        .subquery()
    )
    
    stmt_cohort_snaps = (
        select(CodeSnapshot)
        .join(subq, and_(
            CodeSnapshot.session_id == subq.c.session_id,
            CodeSnapshot.created_at == subq.c.max_created_at
        ))
    )
    
    cohort_snaps = db.execute(stmt_cohort_snaps).scalars().all()
    if len(cohort_snaps) < min_cohort:
        return None
        
    # 4. Calculate cohort median LOC
    cohort_locs = []
    try:
        for snap in cohort_snaps:
            content = storage_adapter.download_code_snapshot(snap.object_key)
            cohort_locs.append(_count_loc(content))
    except StorageUnavailable:
        return None
        
    cohort_locs.sort()
    n = len(cohort_locs)
    if n % 2 == 1:
        median_loc = float(cohort_locs[n//2])
    else:
        median_loc = (cohort_locs[n//2 - 1] + cohort_locs[n//2]) / 2.0
        
    # 5. Check student's LOC
    stmt_my_snap = (
        select(CodeSnapshot)
        .where(CodeSnapshot.session_id == session.id)
        .order_by(desc(CodeSnapshot.created_at))
        .limit(1)
    )
    my_snap = db.execute(stmt_my_snap).scalar_one_or_none()
    if not my_snap:
        return None
        
    try:
        my_content = storage_adapter.download_code_snapshot(my_snap.object_key)
    except StorageUnavailable:
        return None
    student_loc = _count_loc(my_content)
    
    if median_loc <= 0:
        return None

    relative_dev = student_loc / median_loc
        
    if relative_dev > dev_policy:
        dedup_key = f"LOC:{session.id}:{my_snap.id}"
        
        evidence = {
            # Canonical evidence contract (DCR SPNC_LOC_EVIDENCE_CONTRACT / docs/01_DOMAIN.md §1.8)
            "session_id": str(session.id),
            "observed_loc": student_loc,
            "context_median_loc": median_loc,
            "delta": round(float(student_loc) - float(median_loc), 2),
            "threshold_relative": float(dev_policy),
            # D7 (rule 1.1.0): null while ACTIVE; the server-computed Session.final_loc once finalized
            "final_loc": session.final_loc if session.status != SessionStatus.ACTIVE.value else None,
            # Preserved legacy diagnostic fields for backward compatibility
            "problem_id": str(session.problem_id),
            "student_loc": student_loc,
            "cohort_median_loc": median_loc,
            "cohort_size": n,
            "relative_deviation": relative_dev,
            "configured_threshold": dev_policy,
            "loc_counting_policy": "non-blank lines"
        }
        
        return AttentionSignal(
            student_id=session.student_id,
            session_id=session.id,
            signal_type=SignalType.LOC_ANOMALY,
            rule_version=settings.SIGNAL_RULE_VERSION,
            evidence=evidence,
            dedup_key=dedup_key
        )
        
    return None
