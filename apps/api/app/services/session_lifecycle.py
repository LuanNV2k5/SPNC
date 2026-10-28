import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.session import CodingSession, SessionStatus, TerminationSource
from app.models.trace import TraceEvent, TraceEventType
from app.repositories import academic as academic_repo
from app.repositories import trace as trace_repo
from app.services.loc import count_loc
from app.services.storage import StorageUnavailable, storage_adapter
from app.services.trace import _generate_fingerprint


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def finalize_session(
    db: Session,
    session_id: uuid.UUID,
    status: SessionStatus,
    actor: TerminationSource,
    last_sequence_number: Optional[int] = None,
) -> CodingSession:
    """
    The only path out of ACTIVE (docs/34 §3.1 S2). Computes final_loc and working time
    from server-side data, appends a server-authored SESSION_ENDED event and records the
    termination facts. Flushes only; the caller owns the commit.
    """
    session = academic_repo.lock_session_for_finalize(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))

    current_status = session.status if isinstance(session.status, str) else session.status.value
    if current_status != SessionStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail=_error("SESSION_ALREADY_ENDED", "Session is not active"))

    max_seq = trace_repo.get_max_sequence(db, session_id)
    if last_sequence_number is not None and max_seq < last_sequence_number:
        raise HTTPException(
            status_code=409,
            detail=_error("TRACE_NOT_FLUSHED", f"Server has trace up to sequence {max_seq}; flush up to {last_sequence_number} before ending"),
        )

    # D2/D3: server-computed non-blank LOC of the latest snapshot; null when no snapshot
    # exists or its content is unavailable (never fabricate code facts)
    snapshot = trace_repo.get_latest_snapshot(db, session_id)
    final_loc = None
    try:
        if snapshot and storage_adapter.exists_code_snapshot(snapshot.object_key):
            final_loc = count_loc(storage_adapter.download_code_snapshot(snapshot.object_key))
    except StorageUnavailable:
        # Content unreachable: same as unavailable, never a fabricated LOC (docs/37 §4)
        final_loc = None

    # D1: server wall clock (REQ-TRACE-006)
    ended_at = datetime.now(timezone.utc)
    working_time_seconds = max(0, int((ended_at - session.opened_at).total_seconds()))

    payload = {
        "source": "SERVER",
        "final_code_snapshot_id": str(snapshot.id) if snapshot else None,
        "final_loc": final_loc,
        "working_time_seconds": working_time_seconds,
        "termination_actor": actor.value,
    }
    trace_repo.append_server_event(db, TraceEvent(
        session_id=session_id,
        sequence_number=max_seq + 1,
        event_type=TraceEventType.SESSION_ENDED.value,
        canonical_fingerprint=_generate_fingerprint(TraceEventType.SESSION_ENDED.value, payload),
        client_timestamp=ended_at,
        server_timestamp=ended_at,
        payload=payload,
    ))

    return academic_repo.mark_session_terminated(
        db, session,
        status=status,
        termination_source=actor.value,
        ended_at=ended_at,
        final_loc=final_loc,
        working_time_seconds=working_time_seconds,
        final_code_snapshot_id=snapshot.id if snapshot else None,
    )


def abandon_session(db: Session, session_id: uuid.UUID) -> CodingSession:
    """Entry point for a future stale-session policy (out of 08E scope, docs/34 §3.2)."""
    return finalize_session(db, session_id, SessionStatus.ABANDONED, TerminationSource.SYSTEM_SESSION_POLICY)
