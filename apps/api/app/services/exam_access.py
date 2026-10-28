"""Phase 10B — Student exam access rule (docs/36 D11, REQ-EXAM-012).

Status must be SCHEDULED or ONGOING (a published exam) **and** the server clock must be inside
[start_time, end_time). The time check is authoritative, so scheduler lag never grants or
denies access on its own.
"""
from datetime import datetime

from fastapi import HTTPException

from app.models.exam import Exam, ExamStatus

OPEN_STATUSES = (ExamStatus.SCHEDULED.value, ExamStatus.ONGOING.value)


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def _value(v) -> str:
    return v if isinstance(v, str) else v.value


def assert_exam_open(exam: Exam, now: datetime) -> None:
    status = _value(exam.status)
    if status == ExamStatus.CANCELLED.value:
        raise HTTPException(status_code=403, detail=_error("EXAM_CANCELLED", "Exam is cancelled"))
    if status == ExamStatus.DRAFT.value:
        raise HTTPException(status_code=403, detail=_error("EXAM_NOT_PUBLISHED", "Exam is not published"))
    if now < exam.start_time:
        raise HTTPException(status_code=403, detail=_error("EXAM_NOT_STARTED", "Exam has not started yet"))
    if now >= exam.end_time or status not in OPEN_STATUSES:
        raise HTTPException(status_code=403, detail=_error("EXAM_ENDED", "Exam has ended"))
