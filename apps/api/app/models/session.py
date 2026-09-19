import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Boolean, ForeignKey, Integer, UniqueConstraint, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin

class SessionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    ABANDONED = "ABANDONED"

class TerminationSource(str, enum.Enum):
    STUDENT = "STUDENT"
    SYSTEM_EXAM_TIMEOUT = "SYSTEM_EXAM_TIMEOUT"
    SYSTEM_SESSION_POLICY = "SYSTEM_SESSION_POLICY"

class CodingSession(Base, TimestampMixin):
    __tablename__ = "coding_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT"), index=True)
    language: Mapped[str] = mapped_column(String(50)) # Must be CPP17 or PYTHON3 based on domain enforcement

    # Context
    is_exam_context: Mapped[bool] = mapped_column(Boolean, default=False)
    exam_participation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("exam_participations.id", ondelete="RESTRICT"), nullable=True, index=True)
    practice_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("practice_attempts.id", ondelete="RESTRICT"), nullable=True, index=True)

    status: Mapped[SessionStatus] = mapped_column(String(20), default=SessionStatus.ACTIVE, index=True)
    termination_source: Mapped[Optional[TerminationSource]] = mapped_column(String(50), nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    first_code_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped["User"] = relationship("User")
    problem: Mapped["Problem"] = relationship("Problem")
    exam_participation: Mapped[Optional["ExamParticipation"]] = relationship("ExamParticipation")
    practice_attempt: Mapped[Optional["PracticeAttempt"]] = relationship("PracticeAttempt", back_populates="sessions")

    __table_args__ = (
        CheckConstraint(
            "(is_exam_context = true AND exam_participation_id IS NOT NULL AND practice_attempt_id IS NULL) OR "
            "(is_exam_context = false AND exam_participation_id IS NULL AND practice_attempt_id IS NOT NULL)",
            name="ck_coding_sessions_context_exclusive"
        ),
        CheckConstraint(
            "language IN ('CPP17', 'PYTHON3')",
            name="ck_coding_sessions_language_canonical"
        ),
    )

class PracticeAttempt(Base, TimestampMixin):
    __tablename__ = "practice_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)

    total_score: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["User"] = relationship("User")
    problem: Mapped["Problem"] = relationship("Problem")
    sessions: Mapped[List["CodingSession"]] = relationship("CodingSession", back_populates="practice_attempt")

    __table_args__ = (
        CheckConstraint('total_score >= 0', name='ck_practice_attempts_score_positive'),
    )
