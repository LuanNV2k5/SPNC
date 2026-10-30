"""Phase 05 — Academic domain schemas (Class, Problem, Exam, Practice, Session, Submission)."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class StudentClassResponse(BaseModel):
    """Class as a student sees it: never carries the invite code (docs/38 §5)."""
    id: uuid.UUID
    name: str
    academic_year: str
    is_active: bool
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClassResponse(StudentClassResponse):
    invite_code: str   # owner only (REQ-CLASS-001)


class ClassListResponse(PaginatedResponse):
    items: List[ClassResponse]


class StudentClassListResponse(PaginatedResponse):
    items: List[StudentClassResponse]


class JoinClassRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=16)

    model_config = ConfigDict(extra="forbid")


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
    # docs/47 D2: the owner teacher's roster shows who each member is
    username: Optional[str] = None
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _student_names(cls, v):
        student = getattr(v, "student", None)
        if student is None:
            return v
        return {"id": v.id, "class_id": v.class_id, "student_id": v.student_id, "is_active": v.is_active,
                "created_at": v.created_at, "username": student.username, "full_name": student.full_name}


class MemberListResponse(PaginatedResponse):
    items: List[MemberResponse]


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------
DIFFICULTIES = ("EASY", "MEDIUM", "HARD")


def _check_difficulty(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in DIFFICULTIES:
        raise ValueError("difficulty must be EASY, MEDIUM, or HARD")
    return v


class ProblemCreateRequest(BaseModel):
    title: str
    description: str
    constraints: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    difficulty: Optional[str] = None
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

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: Optional[str]) -> Optional[str]:
        return _check_difficulty(v)


class ProblemUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    constraints: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    difficulty: Optional[str] = None
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

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: Optional[str]) -> Optional[str]:
        return _check_difficulty(v)


class ProblemResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    constraints: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    difficulty: Optional[str] = None
    deleted_at: Optional[datetime] = None
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


class PublicationListResponse(BaseModel):
    items: List[PublicationResponse]
    total: int


# ---------------------------------------------------------------------------
# Exam
# ---------------------------------------------------------------------------
class ExamCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    duration_minutes: Optional[int] = Field(None, gt=0)
    allow_view_result_after: bool = False

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
    duration_minutes: Optional[int] = Field(None, gt=0)
    allow_view_result_after: Optional[bool] = None


class ExamCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")


class ExamResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    owner_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: str
    duration_minutes: Optional[int] = None
    allow_view_result_after: bool = False
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
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
    expired_at: Optional[datetime] = None
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
    # Only "STUDENT" (or omitted) is accepted from clients (docs/34 D5)
    termination_source: Optional[str] = None
    # Flush guard: highest sequence_number the client has sent (docs/34 D6)
    last_sequence_number: Optional[int] = Field(default=None, ge=0)


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
    first_code_at: Optional[datetime] = None   # REQ-TRACE-002 (DCR SPNC_FIRST_CODE_FACT)
    ended_at: Optional[datetime]
    final_loc: Optional[int] = None
    working_time_seconds: Optional[int] = None
    final_code_snapshot_id: Optional[uuid.UUID] = None
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
    exam_id: Optional[uuid.UUID] = None
    source: str = "STUDENT"
    status: str
    verdict: Optional[str]
    score: Optional[int]
    # Filtered per docs/36 D7 (hidden-case I/O never present) and D14 (visibility)
    judge_result: Optional[Dict[str, Any]] = None
    result_visible: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmitRequest(BaseModel):
    snapshot_id: uuid.UUID


class SubmissionListResponse(PaginatedResponse):
    items: List[SubmissionResponse]
