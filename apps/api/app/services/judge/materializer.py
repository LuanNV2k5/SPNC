import logging
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.models.session import CodingSession, SessionStatus
from app.models.run_submit import Run
from app.models.trace import CodeSnapshot
from app.models.observation import AttentionSignal
from app.services.judge.signals import (
    evaluate_idle_detected,
    evaluate_fast_first_code,
    evaluate_repeated_failure,
    evaluate_loc_anomaly,
)

logger = logging.getLogger(__name__)

def materialize_signal(db: Session, signal: AttentionSignal) -> bool:
    """
    Idempotent insert into AttentionSignal using PostgreSQL ON CONFLICT DO NOTHING.
    Returns True if a new row was inserted, False if it was deduped.
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
        db.commit()
        return result.rowcount > 0
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to materialize signal {signal.dedup_key}: {e}")
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
