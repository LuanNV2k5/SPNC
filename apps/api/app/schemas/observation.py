"""Phase 09 — Teacher Observation schemas (docs/35)."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.observation import SignalStatus
from app.schemas.academic import PaginatedResponse
from app.schemas.run import RunResponse
from app.schemas.trace import TraceEventResponse, TraceStateResponse


class AttentionStudentItem(BaseModel):
    student_id: uuid.UUID
    username: str
    full_name: str
    new_signal_count: int
    counts_by_type: Dict[str, int]
    latest_detected_at: datetime


class AttentionListResponse(PaginatedResponse):
    items: List[AttentionStudentItem]


class ObservedSessionItem(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    problem_title: str
    context: str  # "EXAM" | "PRACTICE"
    exam_id: Optional[uuid.UUID] = None
    exam_title: Optional[str] = None
    opened_at: datetime
    ended_at: Optional[datetime] = None
    status: str
    termination_source: Optional[str] = None
    latest_meaningful_event_at: Optional[datetime] = None
    latest_submission_verdict: Optional[str] = None
    signal_count: int
    final_loc: Optional[int] = None
    working_time_seconds: Optional[int] = None


class ObservedSessionListResponse(PaginatedResponse):
    items: List[ObservedSessionItem]


class SignalItem(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    student_id: uuid.UUID
    signal_type: str
    status: str
    detected_at: datetime
    rule_version: Optional[str] = None
    evidence: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SignalListResponse(PaginatedResponse):
    items: List[SignalItem]


class SnapshotRef(BaseModel):
    id: uuid.UUID
    reason: str
    language: str
    line_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SnapshotContentResponse(SnapshotRef):
    session_id: uuid.UUID
    source_code: Optional[str] = None
    content_available: bool


class TimelineResponse(BaseModel):
    session: ObservedSessionItem
    events: List[TraceEventResponse]
    total_events: int
    skip: int
    limit: int
    state: TraceStateResponse
    signals: List[SignalItem]
    snapshots: List[SnapshotRef]


class TeacherRunListResponse(BaseModel):
    items: List[RunResponse]
    total: int


class CurrentSessionInfo(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    opened_at: datetime
    latest_activity_at: Optional[datetime] = None
    run_count: int


class ExamObservationItem(BaseModel):
    student_id: uuid.UUID
    username: str
    full_name: str
    participation_status: str  # NOT_STARTED | IN_PROGRESS | COMPLETED | EXPIRED | CANCELLED (docs/36 D8)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    submitted_problem_count: int
    current_session: Optional[CurrentSessionInfo] = None
    signal_count: int


class ExamObservationResponse(PaginatedResponse):
    exam_id: uuid.UUID
    exam_title: str
    exam_status: str
    items: List[ExamObservationItem]


# ---------------------------------------------------------------------------
# Phase 09B — signal status & annotations
# ---------------------------------------------------------------------------
class SignalStatusUpdate(BaseModel):
    # Only the status can change; any other field (e.g. evidence) is rejected (DTI-08)
    model_config = ConfigDict(extra="forbid")
    status: SignalStatus


def _validate_content(v: str) -> str:
    # D8: plain text, 1-5000 characters, not blank
    if not v or not v.strip():
        raise ValueError("content must not be blank")
    if len(v) > 5000:
        raise ValueError("content must be at most 5000 characters")
    return v


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    signal_id: Optional[uuid.UUID] = None
    content: str

    @field_validator("content")
    @classmethod
    def _check_content(cls, v: str) -> str:
        return _validate_content(v)


class AnnotationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str

    @field_validator("content")
    @classmethod
    def _check_content(cls, v: str) -> str:
        return _validate_content(v)


class AnnotationResponse(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    student_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    signal_id: Optional[uuid.UUID] = None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnnotationListResponse(PaginatedResponse):
    items: List[AnnotationResponse]
