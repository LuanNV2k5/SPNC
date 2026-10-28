import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Boolean, ForeignKey, Integer, UniqueConstraint, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base, TimestampMixin

class ProblemVisibility(str, enum.Enum):
    PRIVATE = "PRIVATE"
    CLASS = "CLASS"
    PUBLIC = "PUBLIC"

class ProblemDifficulty(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"

class SupportedLanguage(str, enum.Enum):
    CPP17 = "CPP17"
    PYTHON3 = "PYTHON3"

class Problem(Base, TimestampMixin):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String)
    # REQ-PROB-001 statement fields (docs/38 12A)
    constraints: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[Optional[ProblemDifficulty]] = mapped_column(String(10), nullable=True)
    # docs/38 D5: soft delete keeps history (sessions, submissions reference problems)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    visibility: Mapped[ProblemVisibility] = mapped_column(String(20), default=ProblemVisibility.PRIVATE, index=True)

    time_limit_ms: Mapped[int] = mapped_column(Integer, default=1000)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=256)

    # Supported languages JSON list, e.g. ["CPP17", "PYTHON3"]
    supported_languages: Mapped[list] = mapped_column(JSONB, default=["CPP17", "PYTHON3"])

    owner: Mapped["User"] = relationship("User")
    test_cases: Mapped[List["ProblemTestCase"]] = relationship("ProblemTestCase", back_populates="problem", cascade="all, delete-orphan")
    class_publications: Mapped[List["ProblemClassPublication"]] = relationship("ProblemClassPublication", back_populates="problem", cascade="all, delete-orphan")

class ProblemTestCase(Base):
    __tablename__ = "problem_test_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    input_data: Mapped[str] = mapped_column(String)
    expected_output: Mapped[str] = mapped_column(String)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=True)
    score_weight: Mapped[int] = mapped_column(Integer, default=10)

    problem: Mapped["Problem"] = relationship("Problem", back_populates="test_cases")

    __table_args__ = (
        UniqueConstraint('problem_id', 'order_index', name='uq_problem_test_cases_order'),
        CheckConstraint('score_weight >= 0', name='ck_problem_test_cases_weight_positive'),
    )

class ProblemClassPublication(Base, TimestampMixin):
    __tablename__ = "problem_class_publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)

    problem: Mapped["Problem"] = relationship("Problem", back_populates="class_publications")
    class_org: Mapped["Class"] = relationship("Class")

    __table_args__ = (
        UniqueConstraint('problem_id', 'class_id', name='uq_problem_class_publications_problem_class'),
    )
