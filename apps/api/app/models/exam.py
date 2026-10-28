import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Boolean, ForeignKey, Integer, UniqueConstraint, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin

# Domain §1.5 (docs/36 D8)
class ExamStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ONGOING = "ONGOING"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"

class ParticipationStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"

class Exam(Base, TimestampMixin):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    # Server Authoritative Times
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Materialized status for quick query, but Authorization must use start_time/end_time
    status: Mapped[ExamStatus] = mapped_column(String(20), default=ExamStatus.DRAFT, index=True)

    # REQ-EXAM-001; docs/38 D7: per-student limit, deadline = min(started_at + duration, end_time)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # D14: students see exam results only after ENDED and when this is set
    allow_view_result_after: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # REQ-EXAM-010 cancellation metadata
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL", name="fk_exams_cancelled_by"), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])
    exam_problems: Mapped[List["ExamProblem"]] = relationship("ExamProblem", back_populates="exam", cascade="all, delete-orphan", order_by="ExamProblem.order_index")
    exam_assignments: Mapped[List["ExamAssignment"]] = relationship("ExamAssignment", back_populates="exam", cascade="all, delete-orphan")
    participations: Mapped[List["ExamParticipation"]] = relationship("ExamParticipation", back_populates="exam", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('end_time > start_time', name='ck_exam_time_valid'),
        CheckConstraint("status IN ('DRAFT', 'SCHEDULED', 'ONGOING', 'ENDED', 'CANCELLED')", name='status_valid'),
    )

class ExamProblem(Base):
    __tablename__ = "exam_problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer, default=100)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="exam_problems")
    problem: Mapped["Problem"] = relationship("Problem")

    __table_args__ = (
        UniqueConstraint('exam_id', 'problem_id', name='uq_exam_problems_exam_problem'),
        UniqueConstraint('exam_id', 'order_index', name='uq_exam_problems_order'),
        CheckConstraint('max_score >= 0', name='ck_exam_problems_score_positive'),
    )

class ExamAssignment(Base, TimestampMixin):
    __tablename__ = "exam_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="exam_assignments")
    class_org: Mapped["Class"] = relationship("Class")

    __table_args__ = (
        UniqueConstraint('exam_id', 'class_id', name='uq_exam_assignments_exam_class'),
    )

class ExamParticipation(Base, TimestampMixin):
    __tablename__ = "exam_participations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    status: Mapped[ParticipationStatus] = mapped_column(String(20), default=ParticipationStatus.NOT_STARTED, index=True)
    total_score: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="participations")
    student: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint('exam_id', 'student_id', name='uq_exam_participations_exam_student'),
        CheckConstraint('total_score >= 0', name='ck_exam_participations_score_positive'),
        CheckConstraint("status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'EXPIRED', 'CANCELLED')", name='status_valid'),
    )
