"""Phase 05 — Academic domain schemas (Class, Problem, Exam, Practice, Session, Submission)."""
import uuid
from datetime import datetime
from typing import List, Optional, Any

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Shared / Pagination
# ---------------------------------------------------------------------------
class PaginatedResponse(BaseModel):
    total: int
    page: int
    size: int


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------
class ClassCreateRequest(BaseModel):
    name: str
    academic_year: str


class ClassUpdateRequest(BaseModel):
    name: Optional[str] = None
    academic_year: Optional[str] = None
    is_active: Optional[bool] = None


class ClassResponse(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str
    is_active: bool
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClassListResponse(PaginatedResponse):
    items: List[ClassResponse]


# ---------------------------------------------------------------------------
# ClassMembership
# ---------------------------------------------------------------------------
class EnrollRequest(BaseModel):
    student_id: uuid.UUID


class MemberResponse(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    student_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberListResponse(PaginatedResponse):
    items: List[MemberResponse]


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
class ProblemCreateRequest(BaseModel):
    title: str
    description: str
    visibility: str = "PRIVATE"
    time_limit_ms: int = 1000
    memory_limit_mb: int = 256
    supported_languages: List[str] = ["CPP17", "PYTHON3"]

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in ("PRIVATE", "CLASS", "PUBLIC"):
            raise ValueError("visibility must be PRIVATE, CLASS, or PUBLIC")
        return v

    @field_validator("supported_languages")
    @classmethod
    def validate_languages(cls, v: List[str]) -> List[str]:
        for lang in v:
            if lang not in ("CPP17", "PYTHON3"):
                raise ValueError(f"Unsupported language: {lang}")
        return v


class ProblemUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = None
    time_limit_ms: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    supported_languages: Optional[List[str]] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("PRIVATE", "CLASS", "PUBLIC"):
            raise ValueError("visibility must be PRIVATE, CLASS, or PUBLIC")
        return v


class ProblemResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    visibility: str
    owner_id: uuid.UUID
    time_limit_ms: int
    memory_limit_mb: int
    supported_languages: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProblemListResponse(PaginatedResponse):
    items: List[ProblemResponse]


# ---------------------------------------------------------------------------
# ProblemClassPublication
# ---------------------------------------------------------------------------
class PublishToCLassRequest(BaseModel):
    class_id: uuid.UUID


class PublicationResponse(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    class_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Exam
# ---------------------------------------------------------------------------
class ExamCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime

    @field_validator("end_time")
    @classmethod
    def validate_end_after_start(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class ExamUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class ExamResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    owner_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamListResponse(PaginatedResponse):
    items: List[ExamResponse]


class AttachProblemRequest(BaseModel):
    problem_id: uuid.UUID
    order_index: int
    max_score: int = 100


class ExamProblemResponse(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    problem_id: uuid.UUID
    order_index: int
    max_score: int

    model_config = ConfigDict(from_attributes=True)


class AssignClassRequest(BaseModel):
    class_id: uuid.UUID


class ExamAssignmentResponse(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    class_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# ExamParticipation
# ---------------------------------------------------------------------------
class ParticipationResponse(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    student_id: uuid.UUID
    status: str
    total_score: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# CodingSession
# ---------------------------------------------------------------------------
class StartPracticeSessionRequest(BaseModel):
    problem_id: uuid.UUID
    language: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ("CPP17", "PYTHON3"):
            raise ValueError("language must be CPP17 or PYTHON3")
        return v


class StartExamSessionRequest(BaseModel):
    problem_id: uuid.UUID
    language: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ("CPP17", "PYTHON3"):
            raise ValueError("language must be CPP17 or PYTHON3")
        return v


class EndSessionRequest(BaseModel):
    termination_source: str = "STUDENT"


class SessionResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    problem_id: uuid.UUID
    language: str
    is_exam_context: bool
    exam_participation_id: Optional[uuid.UUID]
    practice_attempt_id: Optional[uuid.UUID]
    status: str
    termination_source: Optional[str]
    opened_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(PaginatedResponse):
    items: List[SessionResponse]


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
class SubmissionResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    problem_id: uuid.UUID
    session_id: uuid.UUID
    snapshot_id: uuid.UUID
    status: str
    verdict: Optional[str]
    score: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionListResponse(PaginatedResponse):
    items: List[SubmissionResponse]
