"""Phase 14A — Practice points (REQ-STU-004, UC-G02; OQ-16 resolved by docs/40 Q1-Q3).

Practice only; once per problem at the first ACCEPTED submission; points by difficulty;
cumulative, never reset; no leaderboard. Stored on the point_transactions ledger.
"""
import uuid
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.observation import PointTransaction
from app.models.problem import Problem
from app.models.run_submit import RunVerdict, Submission, SubmissionSource
from app.models.user import User
from app.services import observation_auth as auth

PRACTICE_REASON = "PRACTICE_ACCEPTED"
POINTS_BY_DIFFICULTY = {"EASY": 10, "MEDIUM": 20, "HARD": 30}
DEFAULT_POINTS = 10


def _value(v):
    return getattr(v, "value", v)


def points_for(problem: Problem) -> int:
    return POINTS_BY_DIFFICULTY.get(_value(problem.difficulty), DEFAULT_POINTS)


def award_for_submission(db: Session, submission: Submission, verdict: str) -> bool:
    """
    Called by the judge in the same transaction as the fenced result write. Returns True when
    points were added. Exams never award (D14 visibility); a repeat ACCEPTED on the same problem
    is a no-op through the partial unique index.
    """
    if (verdict != RunVerdict.ACCEPTED.value or submission.exam_id is not None
            or _value(submission.source) != SubmissionSource.STUDENT.value):
        return False
    problem = db.get(Problem, submission.problem_id)
    result = db.execute(
        insert(PointTransaction)
        .values(id=uuid.uuid4(), student_id=submission.student_id, amount=points_for(problem), reason=PRACTICE_REASON,
                source_reference=f"submission:{submission.id}", problem_id=submission.problem_id, submission_id=submission.id)
        .on_conflict_do_nothing(index_elements=["student_id", "problem_id"],
                                index_where=PointTransaction.reason == PRACTICE_REASON)
    )
    return result.rowcount > 0


def _summary(db: Session, student_id: uuid.UUID) -> Dict[str, Any]:
    rows = db.execute(
        select(PointTransaction, Problem.title)
        .outerjoin(Problem, Problem.id == PointTransaction.problem_id)
        .where(PointTransaction.student_id == student_id)
        .order_by(PointTransaction.created_at.desc(), PointTransaction.id)
    ).all()
    total = db.scalar(select(func.coalesce(func.sum(PointTransaction.amount), 0))
                      .where(PointTransaction.student_id == student_id)) or 0
    return {
        "student_id": student_id,
        "total": int(total),
        "transactions": [
            {"amount": t.amount, "reason": t.reason, "problem_id": t.problem_id, "problem_title": title,
             "submission_id": t.submission_id, "created_at": t.created_at}
            for t, title in rows
        ],
    }


def my_points(db: Session, student: User) -> Dict[str, Any]:
    return _summary(db, student.id)


def student_points_for_teacher(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID) -> Dict[str, Any]:
    """Teacher of a class the student actively belongs to (docs/40 Q1)."""
    auth.authorize_student(db, teacher, class_id, student_id)
    return _summary(db, student_id)
