"""Phase 10B — Student exam access rule (docs/36 D11, REQ-EXAM-012).

Status must be SCHEDULED or ONGOING (a published exam) **and** the server clock must be inside
[start_time, end_time). The time check is authoritative, so scheduler lag never grants or
denies access on its own.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException

from app.models.exam import Exam, ExamParticipation, ExamStatus

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


def participant_deadline(exam: Exam, participation: Optional[ExamParticipation]) -> datetime:
    """docs/38 D7 (OQ-27): min(started_at + duration_minutes, end_time); end_time without a duration."""
    if exam.duration_minutes and participation is not None and participation.started_at is not None:
        return min(participation.started_at + timedelta(minutes=exam.duration_minutes), exam.end_time)
    return exam.end_time


def assert_participant_open(exam: Exam, participation: ExamParticipation, now: datetime) -> None:
    """D11 exam rule plus the participant's own deadline."""
    assert_exam_open(exam, now)
    if now >= participant_deadline(exam, participation):
        raise HTTPException(status_code=403, detail=_error("EXAM_ENDED", "Your exam time is over"))


def assert_session_writable(db, session, now: datetime) -> None:
    """
    docs/38 D8: no client data is stored for an exam session after the participant's deadline
    (server clock, REQ-TRACE-006). Practice sessions are unaffected.
    """
    if not session.is_exam_context:
        return
    participation = db.get(ExamParticipation, session.exam_participation_id)
    exam = db.get(Exam, participation.exam_id)
    if _value(exam.status) in (ExamStatus.ENDED.value, ExamStatus.CANCELLED.value) or now >= participant_deadline(exam, participation):
        raise HTTPException(status_code=403, detail=_error("EXAM_ENDED", "Exam time is over; no further changes are accepted"))
