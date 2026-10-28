"""Phase 09 — Observation authorization (docs/35 §3, decision D2).

Single source of truth for "may TEACHER T observe session S of student U in class C".
Used by every teacher-facing observation endpoint, the Phase 06 teacher trace and
scratchpad endpoints, and teacher run reads.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models.class_org import Class, ClassMembership
from app.models.exam import Exam, ExamAssignment, ExamParticipation
from app.models.problem import Problem, ProblemClassPublication
from app.models.session import CodingSession
from app.models.user import User
from app.repositories import academic as academic_repo


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def authorize_class(db: Session, teacher: User, class_id: uuid.UUID) -> Class:
    cls = academic_repo.get_class_by_id(db, class_id)
    if not cls or cls.owner_id != teacher.id:
        raise HTTPException(status_code=403, detail=_error("FORBIDDEN_RESOURCE", "Not your class"))
    return cls


def authorize_student(db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID) -> Class:
    cls = authorize_class(db, teacher, class_id)
    membership = academic_repo.get_membership(db, class_id, student_id)
    if not membership or not membership.is_active:
        raise HTTPException(status_code=403, detail=_error("FORBIDDEN_RESOURCE", "Student not in your class"))
    return cls


def session_visible_in_class_clause(class_id: uuid.UUID, teacher_id: uuid.UUID):
    """
    SQL predicate on CodingSession: the session belongs to class C (docs/35 §3 rule 4).
    Exam session -> its exam is assigned to C. Practice session -> problem published to C or owned by T.
    """
    exam_in_class = exists(
        select(ExamAssignment.id)
        .join(ExamParticipation, ExamParticipation.exam_id == ExamAssignment.exam_id)
        .where(and_(
            ExamParticipation.id == CodingSession.exam_participation_id,
            ExamAssignment.class_id == class_id,
        ))
    )
    practice_in_class = or_(
        exists(select(ProblemClassPublication.id).where(and_(
            ProblemClassPublication.problem_id == CodingSession.problem_id,
            ProblemClassPublication.class_id == class_id,
        ))),
        exists(select(Problem.id).where(and_(
            Problem.id == CodingSession.problem_id,
            Problem.owner_id == teacher_id,
        ))),
    )
    return or_(
        and_(CodingSession.is_exam_context == True, exam_in_class),
        and_(CodingSession.is_exam_context == False, practice_in_class),
    )


def authorize_session(
    db: Session, teacher: User, class_id: uuid.UUID, student_id: uuid.UUID, session_id: uuid.UUID
) -> CodingSession:
    authorize_student(db, teacher, class_id, student_id)
    stmt = select(CodingSession).where(and_(
        CodingSession.id == session_id,
        CodingSession.student_id == student_id,
        session_visible_in_class_clause(class_id, teacher.id),
    ))
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found for student in this class"))
    return session


def authorize_exam(db: Session, teacher: User, exam_id: uuid.UUID) -> Exam:
    exam = academic_repo.get_exam_by_id(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    if exam.owner_id != teacher.id:
        raise HTTPException(status_code=403, detail=_error("FORBIDDEN_RESOURCE", "Not your exam"))
    return exam


def teacher_can_observe_student(db: Session, teacher: User, student_id: uuid.UUID) -> bool:
    """True if the student has an active membership in at least one class owned by the teacher."""
    stmt = select(exists(
        select(ClassMembership.id)
        .join(Class, Class.id == ClassMembership.class_id)
        .where(and_(
            ClassMembership.student_id == student_id,
            ClassMembership.is_active == True,
            Class.owner_id == teacher.id,
        ))
    ))
    return bool(db.scalar(stmt))


def teacher_can_observe_session(db: Session, teacher: User, session: CodingSession) -> bool:
    """True if the session is visible in at least one class owned by the teacher where the student is active."""
    class_ids = db.scalars(
        select(Class.id)
        .join(ClassMembership, ClassMembership.class_id == Class.id)
        .where(and_(
            Class.owner_id == teacher.id,
            ClassMembership.student_id == session.student_id,
            ClassMembership.is_active == True,
        ))
    ).all()
    for class_id in class_ids:
        visible = db.scalar(select(exists(
            select(CodingSession.id).where(and_(
                CodingSession.id == session.id,
                session_visible_in_class_clause(class_id, teacher.id),
            ))
        )))
        if visible:
            return True
    return False
