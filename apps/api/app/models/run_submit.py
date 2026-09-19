import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, Integer, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class RunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED_INTERNAL = "FAILED_INTERNAL"

class RunVerdict(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    COMPILE_ERROR = "COMPILE_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("code_snapshots.id", ondelete="RESTRICT"), index=True)

    status: Mapped[RunStatus] = mapped_column(String(20), default=RunStatus.PENDING, index=True)
    verdict: Mapped[Optional[RunVerdict]] = mapped_column(String(30), nullable=True)

    # Fencing semantics (CRITICAL)
    execution_generation: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Judge info
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    execution_memory_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    testcase_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    session: Mapped["CodingSession"] = relationship("CodingSession")
    snapshot: Mapped["CodeSnapshot"] = relationship("CodeSnapshot")

    __table_args__ = (
        CheckConstraint('execution_generation >= 0', name='ck_runs_generation_positive'),
    )

class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coding_sessions.id", ondelete="RESTRICT"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("code_snapshots.id", ondelete="RESTRICT"), index=True)

    status: Mapped[RunStatus] = mapped_column(String(20), default=RunStatus.PENDING)
    verdict: Mapped[Optional[RunVerdict]] = mapped_column(String(30), nullable=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    student: Mapped["User"] = relationship("User")
    problem: Mapped["Problem"] = relationship("Problem")
    session: Mapped["CodingSession"] = relationship("CodingSession")
    snapshot: Mapped["CodeSnapshot"] = relationship("CodeSnapshot")

    __table_args__ = (
        CheckConstraint('score >= 0', name='ck_submissions_score_positive'),
    )
