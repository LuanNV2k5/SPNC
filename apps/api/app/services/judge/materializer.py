import logging
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, delete
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.models.session import CodingSession, SessionStatus
from app.models.run_submit import Run
from app.models.trace import CodeSnapshot
from app.models.observation import AttentionSignal, TraceSignalOutbox
from app.repositories import trace as trace_repo
from app.services.judge.signals import (
    evaluate_idle_detected,
    evaluate_fast_first_code,
    evaluate_repeated_failure,
    evaluate_loc_anomaly,
    evaluate_historical_idle_gaps,
)

logger = logging.getLogger(__name__)

def materialize_signal(db: Session, signal: AttentionSignal, commit: bool = True) -> bool:
    """
    Idempotent insert into AttentionSignal using PostgreSQL ON CONFLICT DO NOTHING.
    Returns True if a new row was inserted, False if it was deduped.
    If commit is True, commits transaction; if False, flushes so caller controls atomicity.
    """
    from app.models.observation import SignalStatus
    import datetime
    
    stmt = insert(AttentionSignal).values(
        id=signal.id or __import__("uuid").uuid4(),
        session_id=signal.session_id,
        student_id=signal.student_id,
        signal_type=signal.signal_type,
        status=signal.status or SignalStatus.NEW,
        detected_at=signal.detected_at or datetime.datetime.now(datetime.timezone.utc),
        rule_version=signal.rule_version,
        evidence=signal.evidence,
        dedup_key=signal.dedup_key,
    ).on_conflict_do_nothing(index_elements=["dedup_key"])
    
    try:
        result = db.execute(stmt)
        if commit:
            db.commit()
        else:
            db.flush()
        return result.rowcount > 0
    except Exception as e:
        if commit:
            db.rollback()
        logger.error(f"Failed to materialize signal {signal.dedup_key}: {e}")
        if not commit:
            raise
        return False

def _process_active_sessions(db: Session, since_dt: datetime, batch_size: int, metrics: Dict[str, Any]):
    offset = 0
    while True:
        stmt = (
            select(CodingSession)
            .where(CodingSession.status == SessionStatus.ACTIVE)
            .order_by(CodingSession.id)
            .offset(offset)
            .limit(batch_size)
        )
        candidates = list(db.execute(stmt).scalars())
        if not candidates:
            break
            
        for session in candidates:
            metrics["candidates_evaluated"] += 1
            # Evaluate IDLE
            try:
                idle_signal = evaluate_idle_detected(session, db)
                if idle_signal:
                    inserted = materialize_signal(db, idle_signal)
                    if inserted:
                        metrics["signals_materialized"] += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Error evaluating IDLE for session {session.id}: {e}")

            # Evaluate FAST
            try:
                fast_signal = evaluate_fast_first_code(session, db)
                if fast_signal:
                    inserted = materialize_signal(db, fast_signal)
                    if inserted:
                        metrics["signals_materialized"] += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Error evaluating FAST for session {session.id}: {e}")

        offset += batch_size

def _process_rf_sessions(db: Session, since_dt: datetime, batch_size: int, metrics: Dict[str, Any]):
    offset = 0
    while True:
        stmt = (
            select(CodingSession)
            .join(Run)
            .where(Run.created_at >= since_dt)
            .distinct()
            .order_by(CodingSession.id)
            .offset(offset)
            .limit(batch_size)
        )
        candidates = list(db.execute(stmt).scalars())
        if not candidates:
            break
            
        for session in candidates:
            metrics["candidates_evaluated"] += 1
            try:
                rf_signal = evaluate_repeated_failure(session, db)
                if rf_signal:
                    inserted = materialize_signal(db, rf_signal)
                    if inserted:
                        metrics["signals_materialized"] += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Error evaluating RF for session {session.id}: {e}")
                
        offset += batch_size

def _process_loc_sessions(db: Session, since_dt: datetime, batch_size: int, metrics: Dict[str, Any]):
    offset = 0
    while True:
        stmt = (
            select(CodingSession)
            .join(CodeSnapshot)
            .where(CodeSnapshot.created_at >= since_dt)
            .distinct()
            .order_by(CodingSession.id)
            .offset(offset)
            .limit(batch_size)
        )
        candidates = list(db.execute(stmt).scalars())
        if not candidates:
            break
            
        for session in candidates:
            metrics["candidates_evaluated"] += 1
            try:
                loc_signal = evaluate_loc_anomaly(session, db)
                if loc_signal:
                    inserted = materialize_signal(db, loc_signal)
                    if inserted:
                        metrics["signals_materialized"] += 1
            except Exception as e:
                db.rollback()
                logger.error(f"Error evaluating LOC for session {session.id}: {e}")
                
        offset += batch_size

def process_outbox_cycle(db: Session, batch_sessions: int = 10, chunk_limit: int = 500) -> Dict[str, Any]:
    """
    Processes pending items from trace_signal_outbox in bounded chunks per session.
    Enforces per-session locking (FOR NO KEY UPDATE SKIP LOCKED), causal contiguity,
    atomic materialization, and outbox deletion within a single transaction per cycle.
    """
    metrics = {
        "sessions_claimed": 0,
        "outbox_processed": 0,
        "outbox_deleted": 0,
        "signals_materialized": 0,
    }

    try:
        # 1. Claim sessions that have pending outbox rows
        # FOR NO KEY UPDATE SKIP LOCKED prevents concurrent worker overlap without blocking live student trace ingestion
        claim_stmt = (
            select(CodingSession)
            .where(CodingSession.id.in_(select(TraceSignalOutbox.session_id)))
            .order_by(CodingSession.id.asc())
            .with_for_update(key_share=True, skip_locked=True)
            .limit(batch_sessions)
        )
        sessions = list(db.execute(claim_stmt).scalars().all())
        if not sessions:
            return metrics

        metrics["sessions_claimed"] = len(sessions)

        for session in sessions:
            # 2. Check causal contiguity on full TraceEvent sequence
            highest_contiguous, _ = trace_repo.get_trace_state(db, session.id)
            if highest_contiguous < 1:
                # Contiguity not established or sequence 1 missing; defer this session
                continue

            # 3. Fetch bounded chunk of outbox items up to highest_contiguous
            outbox_stmt = (
                select(TraceSignalOutbox)
                .where(
                    and_(
                        TraceSignalOutbox.session_id == session.id,
                        TraceSignalOutbox.sequence_number <= highest_contiguous
                    )
                )
                .order_by(TraceSignalOutbox.sequence_number.asc())
                .limit(chunk_limit)
            )
            outbox_chunk = list(db.execute(outbox_stmt).scalars().all())
            if not outbox_chunk:
                continue

            metrics["outbox_processed"] += len(outbox_chunk)

            # 4. Evaluate historical IDLE gaps for chunk items
            signals = evaluate_historical_idle_gaps(session, outbox_chunk, db)

            # 5. Materialize signals atomically (without committing transaction yet)
            for sig in signals:
                inserted = materialize_signal(db, sig, commit=False)
                if inserted:
                    metrics["signals_materialized"] += 1

            # 6. Delete processed outbox items atomically
            processed_ids = [item.id for item in outbox_chunk]
            delete_stmt = delete(TraceSignalOutbox).where(TraceSignalOutbox.id.in_(processed_ids))
            db.execute(delete_stmt)
            metrics["outbox_deleted"] += len(processed_ids)

        # 7. Commit transaction atomically
        db.commit()
        return metrics
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing outbox cycle: {e}")
        raise

def run_cycle(db: Session, since_dt: datetime) -> Dict[str, Any]:
    """
    Run one full materialization cycle.
    """
    metrics = {
        "cycle_start": datetime.now().isoformat(),
        "candidates_evaluated": 0,
        "signals_materialized": 0
    }
    
    batch_size = settings.SIGNAL_SCHEDULER_BATCH_SIZE
    
    _process_active_sessions(db, since_dt, batch_size, metrics)
    _process_rf_sessions(db, since_dt, batch_size, metrics)
    _process_loc_sessions(db, since_dt, batch_size, metrics)
    
    metrics["cycle_end"] = datetime.now().isoformat()
    logger.info(f"Cycle complete: evaluated {metrics['candidates_evaluated']} candidates, materialized {metrics['signals_materialized']} signals.")
    return metrics
