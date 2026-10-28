"""Phase 12A — Problem immutability while an exam uses it (REQ-PROB-004/005, docs/38 D4).

A problem attached to a SCHEDULED or ONGOING exam is frozen: statement, limits and test
cases cannot change, and it cannot be deleted. DRAFT/ENDED/CANCELLED exams do not freeze it.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.models.exam import Exam, ExamProblem, ExamStatus

FREEZING_STATUSES = (ExamStatus.SCHEDULED.value, ExamStatus.ONGOING.value)


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def problem_in_active_exam(db: Session, problem_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(exists(
        select(ExamProblem.id).join(Exam, Exam.id == ExamProblem.exam_id).where(and_(
            ExamProblem.problem_id == problem_id,
            Exam.status.in_(FREEZING_STATUSES),
        ))
    ))))


def assert_problem_mutable(db: Session, problem_id: uuid.UUID) -> None:
    if problem_in_active_exam(db, problem_id):
        raise HTTPException(status_code=409, detail=_error(
            "PROBLEM_IN_ACTIVE_EXAM", "The problem is used by a scheduled or ongoing exam and cannot change"))


def assert_not_deleted(problem) -> None:
    if problem.deleted_at is not None:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
