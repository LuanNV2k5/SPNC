import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, ForeignKey, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class SignalType(str, enum.Enum):
    IDLE_DETECTED = "IDLE_DETECTED"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    FAST_FIRST_CODE = "FAST_FIRST_CODE"
    LOC_ANOMALY = "LOC_ANOMALY"

class SignalStatus(str, enum.Enum):
    NEW = "NEW"
    VIEWED = "VIEWED"
    ACK = "ACK"
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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    student: Mapped["User"] = relationship("User")
