"""Phase 10A — Submission persistence with Phase 07-style CAS fencing."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from app.models.exam import ExamParticipation, ExamProblem
from app.models.problem import ProblemTestCase
from app.models.run_submit import RunStatus, Submission


def create(db: Session, submission: Submission) -> Submission:
    db.add(submission)
    db.flush()
    return submission


def get(db: Session, submission_id: uuid.UUID) -> Optional[Submission]:
    return db.get(Submission, submission_id)


def claim_for_judging(db: Session, submission_id: uuid.UUID) -> Optional[Submission]:
    """PENDING -> RUNNING with generation bump; None if not PENDING or another worker won."""
    sub = get(db, submission_id)
    if not sub or sub.status != RunStatus.PENDING.value:
        return None
    result = db.execute(
        update(Submission)
        .where(and_(Submission.id == submission_id,
                    Submission.status == RunStatus.PENDING.value,
                    Submission.execution_generation == sub.execution_generation))
        .values(status=RunStatus.RUNNING.value, execution_generation=Submission.execution_generation + 1)
    )
    if result.rowcount == 0:
        db.rollback()
        return None
    db.commit()
    db.refresh(sub)
    return sub


def write_result(db: Session, submission_id: uuid.UUID, generation: int, status: RunStatus,
                 verdict: Optional[str], score: Optional[int], judge_result: dict) -> bool:
    """Fenced write: only the current generation may persist a result."""
    result = db.execute(
        update(Submission)
        .where(and_(Submission.id == submission_id, Submission.execution_generation == generation,
                    Submission.status == RunStatus.RUNNING.value))
        .values(status=status.value, verdict=verdict, score=score, judge_result=judge_result)
    )
    return result.rowcount > 0


def get_stale(db: Session, threshold_seconds: int) -> List[Submission]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
    return list(db.scalars(select(Submission).where(and_(
        Submission.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]),
        Submission.updated_at < cutoff,
    ))).all())


def recover_stale(db: Session, submission_id: uuid.UUID, expected_generation: int) -> Optional[Submission]:
    result = db.execute(
        update(Submission)
        .where(and_(Submission.id == submission_id, Submission.execution_generation == expected_generation,
                    Submission.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value])))
        .values(status=RunStatus.PENDING.value, execution_generation=Submission.execution_generation + 1)
    )
    if result.rowcount == 0:
        db.rollback()
        return None
    db.commit()
    return get(db, submission_id)


def load_test_cases(db: Session, problem_id: uuid.UUID) -> List[ProblemTestCase]:
    return list(db.scalars(select(ProblemTestCase).where(ProblemTestCase.problem_id == problem_id)
                           .order_by(ProblemTestCase.order_index)).all())


def count_test_cases(db: Session, problem_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(ProblemTestCase.id)).where(ProblemTestCase.problem_id == problem_id)) or 0


def exam_max_score(db: Session, exam_id: uuid.UUID, problem_id: uuid.UUID) -> Optional[int]:
    return db.scalar(select(ExamProblem.max_score).where(and_(ExamProblem.exam_id == exam_id, ExamProblem.problem_id == problem_id)))


def recompute_exam_total(db: Session, exam_id: uuid.UUID, student_id: uuid.UUID) -> Optional[int]:
    """D5: total = sum over exam problems of the best judged score."""
    best = (
        select(Submission.problem_id, func.max(Submission.score).label("best"))
        .where(and_(Submission.exam_id == exam_id, Submission.student_id == student_id,
                    Submission.status == RunStatus.COMPLETED.value, Submission.score.isnot(None)))
        .group_by(Submission.problem_id)
        .subquery()
    )
    total = db.scalar(select(func.coalesce(func.sum(best.c.best), 0))) or 0
    participation = db.scalar(
        select(ExamParticipation).where(and_(ExamParticipation.exam_id == exam_id, ExamParticipation.student_id == student_id))
        .with_for_update()
    )
    if participation is None:
        return None
    participation.total_score = int(total)
    return int(total)
