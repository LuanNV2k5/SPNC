"""Phase 10C — Statistics schemas (docs/36 §4 10C). Descriptive numbers only."""
import uuid
from typing import List, Optional

from pydantic import BaseModel


class ScoreBucket(BaseModel):
    range_start: int   # percent, inclusive
    range_end: int     # percent, exclusive (the last bucket includes 100)
    count: int


class ScoreSummary(BaseModel):
    unit: str          # PERCENT (class) | POINTS (exam)
    max_possible: int
    scored_student_count: int
    average: Optional[float]
    distribution: List[ScoreBucket]


class SubmissionSummary(BaseModel):
    total: int
    judged: int
    accepted: int
    not_accepted: int
    accepted_ratio: Optional[float]


class StudentStatistics(BaseModel):
    student_id: uuid.UUID
    username: str
    full_name: Optional[str]
    score: Optional[float]
    run_count: int
    submission_count: int
    session_count: int


class _Statistics(BaseModel):
    student_count: int
    score: ScoreSummary
    submissions: SubmissionSummary
    average_working_time_seconds: Optional[float]
    students: List[StudentStatistics]


class ClassStatisticsResponse(_Statistics):
    class_id: uuid.UUID


class ExamStatisticsResponse(_Statistics):
    exam_id: uuid.UUID
