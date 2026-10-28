import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class TraceEventType(str, enum.Enum):
    PROBLEM_OPENED = "PROBLEM_OPENED"
    EDITOR_CHANGED = "EDITOR_CHANGED"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    RUN_REQUESTED = "RUN_REQUESTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    SUBMISSION_CREATED = "SUBMISSION_CREATED"
    SESSION_ENDED = "SESSION_ENDED"
    SESSION_CHECKPOINT = "SESSION_CHECKPOINT"

class SnapshotReason(str, enum.Enum):
    RUN = "RUN"
    SUBMIT = "SUBMIT"
    CHECKPOINT = "CHECKPOINT"

class TraceEvent(Base):
    __tablename__ = "trace_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="CASCADE"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[TraceEventType] = mapped_column(String(50), index=True)

    # Fingerprint for exact duplicate idempotency check
    canonical_fingerprint: Mapped[str] = mapped_column(String(255), index=True)

    client_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    payload: Mapped[dict] = mapped_column(JSONB)

    session: Mapped["CodingSession"] = relationship("CodingSession")

    __table_args__ = (
        UniqueConstraint('session_id', 'sequence_number', name='uq_trace_events_session_sequence'),
        CheckConstraint('sequence_number >= 1', name='ck_trace_events_sequence_positive'),
    )

class CodeSnapshot(Base, TimestampMixin):
    __tablename__ = "code_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="CASCADE"), index=True)

    reason: Mapped[SnapshotReason] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(50))

    source_hash: Mapped[str] = mapped_column(String(255))
    # Content-addressed; several rows may share one blob (docs/39 D1)
    object_key: Mapped[str] = mapped_column(String(1024), index=True)
    line_count: Mapped[int] = mapped_column(Integer)

    session: Mapped["CodingSession"] = relationship("CodingSession", foreign_keys=[session_id])

class ScratchpadRevision(Base):
    __tablename__ = "scratchpad_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="CASCADE"), index=True)
    revision_sequence: Mapped[int] = mapped_column(Integer)
    
    # Optional idempotency hash, used to reject exact duplicates seamlessly
    canonical_fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    
    content: Mapped[str] = mapped_column(String)
    
    client_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    session: Mapped["CodingSession"] = relationship("CodingSession")
    
    __table_args__ = (
        UniqueConstraint('session_id', 'revision_sequence', name='uq_scratchpad_session_revision'),
        CheckConstraint('revision_sequence >= 1', name='ck_scratchpad_sequence_positive'),
    )
