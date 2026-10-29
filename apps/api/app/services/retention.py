"""Phase 19 — Retention purge of raw trace data (docs/45, OQ-21 / NFR-DATA-008).

A session that ended more than `retention_days` ago loses its trace events, scratchpad
revisions and the snapshots no run, submission or final code references (D1). The session
row and every academic record stay; `trace_purged_at` marks the purge (D2).

Rows are deleted and committed first; only then are blobs that no remaining row references
deleted. A failed blob delete leaves an orphan for the existing sweep, never a row pointing
at a missing blob (D6). Each applied batch writes one RETENTION_PURGE audit row (D5).
This module commits its own transactions (one per batch), like the daemons that call it.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import settings
from app.models.exam import Exam, ExamParticipation, ExamStatus
from app.models.observation import TraceSignalOutbox
from app.models.run_submit import Run, Submission
from app.models.session import CodingSession, SessionStatus
from app.models.trace import CodeSnapshot, ScratchpadRevision, TraceEvent
from app.models.user import AuditLog, RefreshSession, User
from app.services import system_settings
from app.services.storage import StorageUnavailable, storage_adapter

logger = logging.getLogger(__name__)

# Fixed key so a CLI run and the reconciler hook never purge at the same time (docs/45 §3.4)
ADVISORY_LOCK_KEY = 45190001

FINISHED_EXAM = (ExamStatus.ENDED.value, ExamStatus.CANCELLED.value)
ENDED_SESSION = (SessionStatus.ENDED.value, SessionStatus.ABANDONED.value)


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def retention_days(db: Session) -> int:
    """Admin setting (D7), unset → RETENTION_DEFAULT_DAYS, never below RETENTION_MIN_DAYS."""
    days = system_settings.retention_days(db)
    if days < settings.RETENTION_MIN_DAYS:
        logger.warning(f"retention_days={days} is below the floor; using {settings.RETENTION_MIN_DAYS}")
        return settings.RETENTION_MIN_DAYS
    return days


def _eligible(cutoff: datetime):
    """docs/45 §3.1: ended before the cutoff, not purged, no pending outbox row, and for an
    exam session a finished exam that ended before the cutoff and is not on hold."""
    exam_ok = exists().where(and_(
        ExamParticipation.id == CodingSession.exam_participation_id,
        Exam.id == ExamParticipation.exam_id,
        Exam.status.in_(FINISHED_EXAM),
        Exam.end_time < cutoff,
        Exam.retention_hold.is_(False),
    ))
    return and_(
        CodingSession.status.in_(ENDED_SESSION),
        CodingSession.ended_at < cutoff,
        CodingSession.trace_purged_at.is_(None),
        ~exists().where(TraceSignalOutbox.session_id == CodingSession.id),
        or_(CodingSession.is_exam_context.is_(False), exam_ok),
    )


def _purgeable_snapshots(session_ids):
    """Snapshots of these sessions that no run, submission or final code references (F5)."""
    final_ids = select(CodingSession.final_code_snapshot_id).where(CodingSession.final_code_snapshot_id.isnot(None))
    return and_(
        CodeSnapshot.session_id.in_(session_ids),
        ~exists().where(Run.snapshot_id == CodeSnapshot.id),
        ~exists().where(Submission.snapshot_id == CodeSnapshot.id),
        CodeSnapshot.id.notin_(final_ids),
    )


def _expired_tokens(now: datetime):
    # refresh_sessions.expires_at is a naive UTC timestamp
    limit = (now - timedelta(days=settings.REFRESH_TOKEN_PURGE_GRACE_DAYS)).replace(tzinfo=None)
    return RefreshSession.expires_at < limit


def _count(db: Session, model, condition) -> int:
    return db.scalar(select(func.count()).select_from(model).where(condition)) or 0


def _new_result(apply: bool, days: int, cutoff: datetime) -> Dict:
    return {
        "mode": "apply" if apply else "dry_run",
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "eligible_sessions": 0,
        "sessions_purged": 0,
        "trace_events": 0,
        "scratchpad_revisions": 0,
        "code_snapshots": 0,
        "blobs_deleted": 0,
        "blob_delete_failures": 0,
        "refresh_sessions": 0,
        "batches": 0,
    }


def _purge_batch(db: Session, cutoff: datetime, days: int, now: datetime, batch_size: int) -> Optional[dict]:
    """One transaction: delete one batch of sessions' raw trace, audit it, commit.
    Returns None (nothing changed) when another purge holds the lock or nothing is left."""
    if not db.scalar(select(func.pg_try_advisory_xact_lock(ADVISORY_LOCK_KEY))):
        db.rollback()
        logger.info("Retention purge skipped: another purge is running")
        return None
    session_ids: List[uuid.UUID] = list(db.scalars(
        select(CodingSession.id).where(_eligible(cutoff)).order_by(CodingSession.ended_at)
        .limit(batch_size).with_for_update(skip_locked=True)
    ).all())
    if not session_ids:
        db.rollback()
        return None
    counts = {
        "trace_events": db.execute(delete(TraceEvent).where(TraceEvent.session_id.in_(session_ids))
                                   .execution_options(synchronize_session=False)).rowcount,
        "scratchpad_revisions": db.execute(delete(ScratchpadRevision).where(ScratchpadRevision.session_id.in_(session_ids))
                                           .execution_options(synchronize_session=False)).rowcount,
    }
    keys = list(db.scalars(
        delete(CodeSnapshot).where(_purgeable_snapshots(session_ids))
        .returning(CodeSnapshot.object_key).execution_options(synchronize_session=False)
    ).all())
    counts["code_snapshots"] = len(keys)
    db.execute(update(CodingSession).where(CodingSession.id.in_(session_ids))
               .values(trace_purged_at=now).execution_options(synchronize_session=False))
    db.add(AuditLog(actor_id=None, action="RETENTION_PURGE", target_type="CODING_SESSION_BATCH",
                    target_id=str(len(session_ids)),
                    metadata_payload={"retention_days": days, "cutoff": cutoff.isoformat(), **counts,
                                      "session_ids": [str(s) for s in session_ids]}))
    db.commit()
    return {"sessions": len(session_ids), "keys": set(keys), **counts}


def _delete_blobs(db: Session, keys, storage, result: Dict) -> None:
    """After the commit (D6): delete only blobs no remaining row references."""
    if not keys:
        return
    still_used = set(db.scalars(select(CodeSnapshot.object_key).where(CodeSnapshot.object_key.in_(keys))).all())
    db.rollback()
    for key in sorted(keys - still_used):
        try:
            storage.delete_code_snapshot(key)
            result["blobs_deleted"] += 1
            metrics.RETENTION_BLOB_DELETES.labels(outcome="deleted").inc()
        except StorageUnavailable as e:
            # Left as an orphan; sweep_orphans removes it later (docs/39 D2)
            logger.warning(f"Retention blob delete failed for {key}: {e}")
            result["blob_delete_failures"] += 1
            metrics.RETENTION_BLOB_DELETES.labels(outcome="failed").inc()


def _purge_tokens(db: Session, now: datetime, batch_size: int, max_batches: int) -> int:
    deleted = 0
    for _ in range(max_batches):
        ids = select(RefreshSession.id).where(_expired_tokens(now)).limit(batch_size * 10).scalar_subquery()
        n = db.execute(delete(RefreshSession).where(RefreshSession.id.in_(ids))
                       .execution_options(synchronize_session=False)).rowcount
        if not n:
            db.rollback()
            break
        db.add(AuditLog(actor_id=None, action="RETENTION_PURGE", target_type="REFRESH_SESSIONS",
                        target_id=str(n), metadata_payload={"refresh_sessions": n}))
        db.commit()
        deleted += n
    return deleted


def purge(db: Session, *, apply: bool, now: Optional[datetime] = None, batch_size: Optional[int] = None,
          max_batches: Optional[int] = None, storage=storage_adapter) -> Dict:
    """Dry run (apply=False) counts what would go and changes nothing (D5)."""
    now = now or datetime.now(timezone.utc)
    batch_size = batch_size or settings.RETENTION_PURGE_BATCH_SIZE
    max_batches = max_batches or settings.RETENTION_PURGE_MAX_BATCHES
    days = retention_days(db)
    cutoff = now - timedelta(days=days)
    result = _new_result(apply, days, cutoff)
    result["eligible_sessions"] = _count(db, CodingSession, _eligible(cutoff))
    metrics.RETENTION_ELIGIBLE.set(result["eligible_sessions"])

    if not apply:
        ids = select(CodingSession.id).where(_eligible(cutoff))
        result["sessions_purged"] = result["eligible_sessions"]
        result["trace_events"] = _count(db, TraceEvent, TraceEvent.session_id.in_(ids))
        result["scratchpad_revisions"] = _count(db, ScratchpadRevision, ScratchpadRevision.session_id.in_(ids))
        result["code_snapshots"] = _count(db, CodeSnapshot, _purgeable_snapshots(ids))
        result["refresh_sessions"] = _count(db, RefreshSession, _expired_tokens(now))
        db.rollback()
        return result

    db.rollback()
    for _ in range(max_batches):
        batch = _purge_batch(db, cutoff, days, now, batch_size)
        if batch is None:
            break
        result["batches"] += 1
        result["sessions_purged"] += batch["sessions"]
        metrics.RETENTION_SESSIONS.labels(outcome="purged").inc(batch["sessions"])
        for data_class, key in (("trace_event", "trace_events"), ("scratchpad_revision", "scratchpad_revisions"),
                                ("code_snapshot", "code_snapshots")):
            result[key] += batch[key]
            metrics.RETENTION_ROWS.labels(data_class=data_class).inc(batch[key])
        _delete_blobs(db, batch["keys"], storage, result)

    result["refresh_sessions"] = _purge_tokens(db, now, batch_size, max_batches)
    metrics.RETENTION_ROWS.labels(data_class="refresh_session").inc(result["refresh_sessions"])
    if result["sessions_purged"] or result["refresh_sessions"] or result["blob_delete_failures"]:
        logger.info(f"Retention purge: {result}")
    return result


def set_retention_hold(db: Session, admin: User, exam_id: uuid.UUID, hold: bool, reason: str) -> Exam:
    """docs/45 D4: ADMIN hold keeps an exam's raw trace from the purge; audited."""
    exam = db.query(Exam).filter(Exam.id == exam_id).with_for_update().first()
    if not exam:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    old = bool(exam.retention_hold)
    exam.retention_hold = hold
    db.add(AuditLog(actor_id=admin.id, action="RETENTION_HOLD_CHANGED", target_type="EXAM", target_id=str(exam.id),
                    metadata_payload={"old": old, "new": hold, "reason": reason}))
    db.flush()
    return exam
