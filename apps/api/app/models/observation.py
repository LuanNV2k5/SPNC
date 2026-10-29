import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, ForeignKey, Integer, DateTime, BigInteger, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class SignalType(str, enum.Enum):
    IDLE_DETECTED = "IDLE_DETECTED"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    FAST_FIRST_CODE = "FAST_FIRST_CODE"
    LOC_ANOMALY = "LOC_ANOMALY"

class SignalStatus(str, enum.Enum):
    # Domain §1.8 / DCR SPNC_SIGNAL_STATUS_TRANSITIONS (docs/35 D1)
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"

class AttentionSignal(Base):
    __tablename__ = "attention_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    signal_type: Mapped[SignalType] = mapped_column(String(50), index=True)
    status: Mapped[SignalStatus] = mapped_column(String(20), default=SignalStatus.NEW, index=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    evidence: Mapped[dict] = mapped_column(JSONB) # MUST NOT contain opaque ML classification or judgment
    dedup_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)

    session: Mapped["CodingSession"] = relationship("CodingSession")
    student: Mapped["User"] = relationship("User")

class TeacherAnnotation(Base, TimestampMixin):
    __tablename__ = "teacher_annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coding_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("attention_signals.id", ondelete="SET NULL"), nullable=True, index=True)

    content: Mapped[str] = mapped_column(String)
    # docs/35 D7: soft delete; rows with deleted_at are excluded from every read
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    teacher: Mapped["User"] = relationship("User", foreign_keys=[teacher_id])
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    session: Mapped[Optional["CodingSession"]] = relationship("CodingSession")
    signal: Mapped[Optional["AttentionSignal"]] = relationship("AttentionSignal")

class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer) # Can be negative
    reason: Mapped[str] = mapped_column(String(255))
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Phase 14 (OQ-16): practice award links; UNIQUE(student, problem) WHERE reason = PRACTICE_ACCEPTED
    problem_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT", name="fk_point_transactions_problem_id"), nullable=True)
    submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("submissions.id", ondelete="RESTRICT", name="fk_point_transactions_submission_id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    student: Mapped["User"] = relationship("User")

class TraceSignalOutbox(Base):
    __tablename__ = "trace_signal_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="RESTRICT"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trace_events.id", ondelete="RESTRICT"), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    sequence_number: Mapped[int] = mapped_column(Integer)
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["CodingSession"] = relationship("CodingSession")
    event: Mapped["TraceEvent"] = relationship("TraceEvent")

    __table_args__ = (
        UniqueConstraint('event_id', name='uq_trace_signal_outbox_event_id'),
    )
