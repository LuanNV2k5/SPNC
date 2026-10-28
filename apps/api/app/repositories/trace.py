import uuid
from typing import List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func, update
from sqlalchemy.exc import IntegrityError

from app.models.trace import TraceEvent, CodeSnapshot, ScratchpadRevision
from app.models.session import CodingSession

def _get_existing_events_dict(db: Session, session_id: uuid.UUID, seq_numbers: List[int]) -> dict:
    stmt = select(TraceEvent).where(
        and_(
            TraceEvent.session_id == session_id,
            TraceEvent.sequence_number.in_(seq_numbers)
        )
    )
    existing = db.scalars(stmt).all()
    return {e.sequence_number: e for e in existing}

class TraceConflictError(Exception):
    def __init__(self, message: str, request_id: str = ""):
        self.message = message
        self.request_id = request_id
        super().__init__(message)

def bulk_insert_events(db: Session, session_id: uuid.UUID, events_data: List[dict]) -> int:
    """
    Inserts a batch of trace events atomically.
    events_data should contain TraceEvent fields including 'canonical_fingerprint'.
    Returns number of new events accepted.
    Raises TraceConflictError if there is a conflict.
    """
    if not events_data:
        return 0
        
    seq_numbers = [e["sequence_number"] for e in events_data]
    
    # 1. Check for existing rows (idempotency vs conflict)
    existing_dict = _get_existing_events_dict(db, session_id, seq_numbers)
    
    to_insert = []
    
    for incoming in events_data:
        seq = incoming["sequence_number"]
        fingerprint = incoming["canonical_fingerprint"]
        
        if seq in existing_dict:
            existing_row = existing_dict[seq]
            if existing_row.canonical_fingerprint != fingerprint:
                raise TraceConflictError(f"Sequence {seq} conflict. Different content.")
            # Exact duplicate, safely ignore
        else:
            # Need to insert
            event_obj = TraceEvent(**incoming)
            to_insert.append(event_obj)
            # Add to existing_dict to prevent intra-batch duplicates (should be caught by input validation, but just in case)
            existing_dict[seq] = event_obj
            
    if to_insert:
        try:
            db.add_all(to_insert)
            db.flush()
        except IntegrityError:
            db.rollback()
            raise TraceConflictError("Database integrity error during trace batch ingest.")
            
    return len(to_insert)

def get_trace_state(db: Session, session_id: uuid.UUID) -> Tuple[int, int]:
    """
    Returns (highest_contiguous_sequence, next_expected_sequence).
    Uses a query to find the first sequence gap.
    """
    # Optimized query to find highest contiguous
    # Select max(sequence_number) where sequence_number = row_number()
    # Or simply:
    # SELECT sequence_number FROM trace_events WHERE session_id = ? ORDER BY sequence_number ASC
    # In python we can just fetch and count if it's contiguous, but for 20k events this is O(N) fetch.
    # To do it in DB:
    # SELECT sequence_number, row_number() OVER (ORDER BY sequence_number) as rn
    # FROM trace_events WHERE session_id = ?
    # Then find the max sequence_number where sequence_number == rn
    
    stmt = """
    WITH numbered AS (
        SELECT sequence_number, row_number() OVER (ORDER BY sequence_number) as rn
        FROM trace_events
        WHERE session_id = :session_id
    )
    SELECT MAX(sequence_number)
    FROM numbered
    WHERE sequence_number = rn;
    """
    
    from sqlalchemy import text
    result = db.execute(text(stmt), {"session_id": str(session_id)}).scalar()
    highest_contiguous = result if result else 0
    return highest_contiguous, highest_contiguous + 1

def get_paginated_history(db: Session, session_id: uuid.UUID, skip: int, limit: int) -> Tuple[List[TraceEvent], int]:
    """
    Returns paginated trace history ordered by sequence_number ASC.
    """
    stmt = select(TraceEvent).where(TraceEvent.session_id == session_id).order_by(TraceEvent.sequence_number.asc()).offset(skip).limit(limit)
    items = db.scalars(stmt).all()
    
    count_stmt = select(func.count(TraceEvent.id)).where(TraceEvent.session_id == session_id)
    total = db.scalar(count_stmt) or 0
    
    return items, total

def create_snapshot_metadata(db: Session, snapshot: CodeSnapshot) -> CodeSnapshot:
    """
    Saves snapshot metadata to DB.
    """
    db.add(snapshot)
    db.flush()
    return snapshot

from typing import Optional
from datetime import datetime

def save_scratchpad_revision(db: Session, session_id: uuid.UUID, content: str, client_timestamp: datetime, fingerprint: str) -> Optional[ScratchpadRevision]:
    stmt = select(func.max(ScratchpadRevision.revision_sequence)).where(ScratchpadRevision.session_id == session_id)
    max_seq = db.scalar(stmt) or 0
    next_seq = max_seq + 1
    
    if max_seq > 0:
        latest = db.scalar(select(ScratchpadRevision).where(
            and_(ScratchpadRevision.session_id == session_id,
                 ScratchpadRevision.revision_sequence == max_seq)
        ))
        if latest and latest.canonical_fingerprint == fingerprint:
            return None # exact duplicate, ignore
            
    rev = ScratchpadRevision(
        session_id=session_id,
        revision_sequence=next_seq,
        canonical_fingerprint=fingerprint,
        content=content,
        client_timestamp=client_timestamp
    )
    db.add(rev)
    db.flush()
    return rev

def get_current_scratchpad(db: Session, session_id: uuid.UUID) -> Optional[ScratchpadRevision]:
    stmt = select(ScratchpadRevision).where(ScratchpadRevision.session_id == session_id).order_by(ScratchpadRevision.revision_sequence.desc()).limit(1)
    return db.scalar(stmt)

def get_scratchpad_history(db: Session, session_id: uuid.UUID, skip: int, limit: int) -> Tuple[List[ScratchpadRevision], int]:
    stmt = select(ScratchpadRevision).where(ScratchpadRevision.session_id == session_id).order_by(ScratchpadRevision.revision_sequence.asc()).offset(skip).limit(limit)
    items = db.scalars(stmt).all()
    count_stmt = select(func.count(ScratchpadRevision.id)).where(ScratchpadRevision.session_id == session_id)
    total = db.scalar(count_stmt) or 0
    return items, total

def lock_session_for_ingest(db: Session, session_id: uuid.UUID) -> Optional[CodingSession]:
    """
    SELECT ... FOR KEY SHARE: conflicts with finalization (FOR UPDATE) so no event lands
    after SESSION_ENDED, but not with the signal outbox claim (FOR NO KEY UPDATE).
    """
    stmt = (
        select(CodingSession)
        .where(CodingSession.id == session_id)
        .with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)

def mark_first_code(db: Session, session_id: uuid.UUID, at: datetime) -> None:
    """Sets coding_sessions.first_code_at once (atomic: only while still NULL)."""
    db.execute(update(CodingSession).where(and_(CodingSession.id == session_id, CodingSession.first_code_at.is_(None)))
               .values(first_code_at=at))


def get_max_sequence(db: Session, session_id: uuid.UUID) -> int:
    return db.scalar(select(func.max(TraceEvent.sequence_number)).where(TraceEvent.session_id == session_id)) or 0

def get_latest_snapshot(db: Session, session_id: uuid.UUID) -> Optional[CodeSnapshot]:
    stmt = (
        select(CodeSnapshot)
        .where(CodeSnapshot.session_id == session_id)
        .order_by(CodeSnapshot.created_at.desc(), CodeSnapshot.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)

def append_server_event(db: Session, event: TraceEvent) -> TraceEvent:
    db.add(event)
    db.flush()
    return event
