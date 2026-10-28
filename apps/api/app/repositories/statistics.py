"""Phase 10C — Statistics queries (docs/36 §4 10C). Scope follows docs/35 §3."""
import uuid
from typing import Dict, List

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.class_org import Class, ClassMembership
from app.models.exam import ExamAssignment, ExamParticipation, ExamProblem
from app.models.run_submit import Run, Submission
from app.models.session import CodingSession
from app.models.user import User
from app.services.observation_auth import session_visible_in_class_clause


def class_students(db: Session, class_id: uuid.UUID) -> List[User]:
    return list(db.scalars(
        select(User).join(ClassMembership, ClassMembership.student_id == User.id)
        .where(and_(ClassMembership.class_id == class_id, ClassMembership.is_active == True))
        .order_by(User.username, User.id)
    ).all())


def exam_students(db: Session, exam_id: uuid.UUID, teacher_id: uuid.UUID) -> List[User]:
    """Active members of classes assigned to the exam AND owned by the teacher (docs/35 §3)."""
    ids = (
        select(ClassMembership.student_id)
        .join(ExamAssignment, ExamAssignment.class_id == ClassMembership.class_id)
        .join(Class, Class.id == ClassMembership.class_id)
        .where(and_(ExamAssignment.exam_id == exam_id, Class.owner_id == teacher_id, ClassMembership.is_active == True))
    )
    return list(db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username, User.id)).all())


def class_sessions(db: Session, class_id: uuid.UUID, teacher_id: uuid.UUID, student_ids: List[uuid.UUID]) -> List[CodingSession]:
    if not student_ids:
        return []
    return list(db.scalars(select(CodingSession).where(and_(
        CodingSession.student_id.in_(student_ids),
        session_visible_in_class_clause(class_id, teacher_id),
    ))).all())


def exam_sessions(db: Session, exam_id: uuid.UUID, student_ids: List[uuid.UUID]) -> List[CodingSession]:
    if not student_ids:
        return []
    return list(db.scalars(
        select(CodingSession).join(ExamParticipation, ExamParticipation.id == CodingSession.exam_participation_id)
        .where(and_(ExamParticipation.exam_id == exam_id, CodingSession.student_id.in_(student_ids)))
    ).all())


def run_counts(db: Session, session_ids: List[uuid.UUID]) -> Dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    rows = db.execute(select(Run.session_id, func.count(Run.id)).where(Run.session_id.in_(session_ids))
                      .group_by(Run.session_id)).all()
    return {sid: n for sid, n in rows}


def submissions(db: Session, session_ids: List[uuid.UUID]) -> List[Submission]:
    if not session_ids:
        return []
    return list(db.scalars(select(Submission).where(Submission.session_id.in_(session_ids))).all())


def exam_participations(db: Session, exam_id: uuid.UUID) -> Dict[uuid.UUID, ExamParticipation]:
    rows = db.scalars(select(ExamParticipation).where(ExamParticipation.exam_id == exam_id)).all()
    return {p.student_id: p for p in rows}


def exam_max_total(db: Session, exam_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(ExamProblem.max_score), 0)).where(ExamProblem.exam_id == exam_id)) or 0)
