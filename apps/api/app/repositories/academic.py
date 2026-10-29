"""Phase 05 — Academic domain repository layer.

All database queries for classes, problems, exams, participations,
sessions, and submissions. No HTTP concerns here.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, text, and_, or_, exists
from sqlalchemy.orm import Session

from app.models.class_org import Class, ClassMembership
from app.models.problem import Problem, ProblemClassPublication, ProblemVisibility
from app.models.exam import (
    Exam, ExamStatus, ExamProblem, ExamAssignment, ExamParticipation, ParticipationStatus
)
from app.models.session import CodingSession, SessionStatus, PracticeAttempt
from app.models.run_submit import Submission
from app.models.user import User, RoleEnum


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

def create_class(db: Session, owner_id: uuid.UUID, name: str, academic_year: str) -> Class:
    cls = Class(owner_id=owner_id, name=name, academic_year=academic_year)
    db.add(cls)
    db.flush()
    return cls


def get_class_by_invite_code(db: Session, invite_code: str) -> Optional[Class]:
    return db.query(Class).filter(Class.invite_code == invite_code).first()


def invite_code_taken(db: Session, invite_code: str) -> bool:
    return db.query(Class.id).filter(Class.invite_code == invite_code).first() is not None


def get_class_by_id(db: Session, class_id: uuid.UUID) -> Optional[Class]:
    return db.query(Class).filter(Class.id == class_id).first()


def get_classes_by_owner(db: Session, owner_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[Class], int]:
    q = db.query(Class).filter(Class.owner_id == owner_id)
    total = q.count()
    items = q.order_by(Class.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_all_classes_paginated(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[Class], int]:
    q = db.query(Class)
    total = q.count()
    items = q.order_by(Class.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_class(db: Session, cls: Class, **fields) -> Class:
    for k, v in fields.items():
        if v is not None:
            setattr(cls, k, v)
    db.flush()
    return cls


# ---------------------------------------------------------------------------
# ClassMembership
# ---------------------------------------------------------------------------

def get_membership(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> Optional[ClassMembership]:
    return db.query(ClassMembership).filter(
        ClassMembership.class_id == class_id,
        ClassMembership.student_id == student_id
    ).first()


def get_memberships_by_class(db: Session, class_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[ClassMembership], int]:
    q = db.query(ClassMembership).filter(ClassMembership.class_id == class_id, ClassMembership.is_active == True)
    total = q.count()
    items = q.order_by(ClassMembership.created_at.asc()).offset(skip).limit(limit).all()
    return items, total


def get_memberships_by_student(db: Session, student_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[ClassMembership], int]:
    q = db.query(ClassMembership).filter(ClassMembership.student_id == student_id, ClassMembership.is_active == True)
    total = q.count()
    items = q.order_by(ClassMembership.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def enroll_student(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> ClassMembership:
    m = ClassMembership(class_id=class_id, student_id=student_id, is_active=True)
    db.add(m)
    db.flush()
    return m


def deactivate_membership(db: Session, membership: ClassMembership) -> ClassMembership:
    membership.is_active = False
    db.flush()
    return membership


def student_in_class(db: Session, class_id: uuid.UUID, student_id: uuid.UUID) -> bool:
    return db.query(
        exists().where(
            ClassMembership.class_id == class_id,
            ClassMembership.student_id == student_id,
            ClassMembership.is_active == True
        )
    ).scalar()


def student_in_any_class(db: Session, student_id: uuid.UUID) -> bool:
    return db.query(
        exists().where(
            ClassMembership.student_id == student_id,
            ClassMembership.is_active == True
        )
    ).scalar()


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------

def create_problem(db: Session, owner_id: uuid.UUID, **fields) -> Problem:
    fields.setdefault("supported_languages", ["CPP17", "PYTHON3"])
    p = Problem(owner_id=owner_id, **fields)
    db.add(p)
    db.flush()
    return p


def get_problem_by_id(db: Session, problem_id: uuid.UUID) -> Optional[Problem]:
    return db.query(Problem).filter(Problem.id == problem_id).first()


def get_problems_by_owner(
    db: Session, owner_id: uuid.UUID, skip: int = 0, limit: int = 50,
    difficulty: Optional[str] = None, language: Optional[str] = None, visibility: Optional[str] = None,
) -> Tuple[List[Problem], int]:
    """Owner's bank (REQ-PROB-006); soft-deleted problems are hidden (docs/38 D5)."""
    q = db.query(Problem).filter(Problem.owner_id == owner_id, Problem.deleted_at.is_(None))
    if difficulty:
        q = q.filter(Problem.difficulty == difficulty)
    if visibility:
        q = q.filter(Problem.visibility == visibility)
    if language:
        q = q.filter(Problem.supported_languages.contains([language]))
    total = q.count()
    items = q.order_by(Problem.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_public_problems(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[Problem], int]:
    q = db.query(Problem).filter(Problem.visibility == ProblemVisibility.PUBLIC.value, Problem.deleted_at.is_(None))
    total = q.count()
    items = q.order_by(Problem.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_practice_problems_for_student(
    db: Session, student_id: uuid.UUID, skip: int = 0, limit: int = 50,
    difficulty: Optional[str] = None, language: Optional[str] = None,
) -> Tuple[List[Problem], int]:
    """REQ-STU-001: PUBLIC problems plus CLASS problems published to the student's active classes."""
    class_ids = get_class_ids_for_student(db, student_id)
    if not class_ids:
        return [], 0   # REQ-PROB-003 / OQ-10: PUBLIC also needs an active class membership
    published = db.query(ProblemClassPublication.problem_id).filter(ProblemClassPublication.class_id.in_(class_ids))
    visible = (Problem.visibility == ProblemVisibility.PUBLIC.value) | (
        (Problem.visibility == ProblemVisibility.CLASS.value) & Problem.id.in_(published))
    q = db.query(Problem).filter(Problem.deleted_at.is_(None), visible)
    if difficulty:
        q = q.filter(Problem.difficulty == difficulty)
    if language:
        q = q.filter(Problem.supported_languages.contains([language]))
    total = q.count()
    items = q.order_by(Problem.created_at.desc(), Problem.id).offset(skip).limit(limit).all()
    return items, total


def update_problem(db: Session, problem: Problem, **fields) -> Problem:
    for k, v in fields.items():
        if v is not None:
            setattr(problem, k, v)
    db.flush()
    return problem


# ---------------------------------------------------------------------------
# ProblemClassPublication
# ---------------------------------------------------------------------------

def get_publication(db: Session, problem_id: uuid.UUID, class_id: uuid.UUID) -> Optional[ProblemClassPublication]:
    return db.query(ProblemClassPublication).filter(
        ProblemClassPublication.problem_id == problem_id,
        ProblemClassPublication.class_id == class_id,
    ).first()


def create_publication(db: Session, problem_id: uuid.UUID, class_id: uuid.UUID) -> ProblemClassPublication:
    pub = ProblemClassPublication(problem_id=problem_id, class_id=class_id)
    db.add(pub)
    db.flush()
    return pub


def delete_publication(db: Session, pub: ProblemClassPublication) -> None:
    db.delete(pub)
    db.flush()


def problem_published_to_class(db: Session, problem_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    return db.query(
        exists().where(
            ProblemClassPublication.problem_id == problem_id,
            ProblemClassPublication.class_id == class_id,
        )
    ).scalar()


def get_class_ids_for_student(db: Session, student_id: uuid.UUID) -> List[uuid.UUID]:
    rows = db.query(ClassMembership.class_id).filter(
        ClassMembership.student_id == student_id,
        ClassMembership.is_active == True
    ).all()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Exam
# ---------------------------------------------------------------------------

def create_exam(
    db: Session,
    owner_id: uuid.UUID,
    title: str,
    description: Optional[str],
    start_time: datetime,
    end_time: datetime,
    allow_view_result_after: bool = False,
    duration_minutes: Optional[int] = None,
) -> Exam:
    exam = Exam(
        owner_id=owner_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        status=ExamStatus.DRAFT.value,
        allow_view_result_after=allow_view_result_after,
        duration_minutes=duration_minutes,
    )
    db.add(exam)
    db.flush()
    return exam


def get_exam_by_id(db: Session, exam_id: uuid.UUID) -> Optional[Exam]:
    return db.query(Exam).filter(Exam.id == exam_id).first()


def get_exams_by_owner(db: Session, owner_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[Exam], int]:
    q = db.query(Exam).filter(Exam.owner_id == owner_id)
    total = q.count()
    items = q.order_by(Exam.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_exam(db: Session, exam: Exam, **fields) -> Exam:
    for k, v in fields.items():
        if v is not None:
            setattr(exam, k, v)
    db.flush()
    return exam


# ExamProblem
def attach_problem_to_exam(db: Session, exam_id: uuid.UUID, problem_id: uuid.UUID, order_index: int, max_score: int = 100) -> ExamProblem:
    ep = ExamProblem(exam_id=exam_id, problem_id=problem_id, order_index=order_index, max_score=max_score)
    db.add(ep)
    db.flush()
    return ep


def get_exam_problem(db: Session, exam_id: uuid.UUID, problem_id: uuid.UUID) -> Optional[ExamProblem]:
    return db.query(ExamProblem).filter(
        ExamProblem.exam_id == exam_id,
        ExamProblem.problem_id == problem_id,
    ).first()


def detach_problem_from_exam(db: Session, ep: ExamProblem) -> None:
    db.delete(ep)
    db.flush()


def get_exam_problems(db: Session, exam_id: uuid.UUID) -> List[ExamProblem]:
    return db.query(ExamProblem).filter(ExamProblem.exam_id == exam_id).order_by(ExamProblem.order_index).all()


# ExamAssignment
def assign_class_to_exam(db: Session, exam_id: uuid.UUID, class_id: uuid.UUID) -> ExamAssignment:
    ea = ExamAssignment(exam_id=exam_id, class_id=class_id)
    db.add(ea)
    db.flush()
    return ea


def get_exam_assignment(db: Session, exam_id: uuid.UUID, class_id: uuid.UUID) -> Optional[ExamAssignment]:
    return db.query(ExamAssignment).filter(
        ExamAssignment.exam_id == exam_id,
        ExamAssignment.class_id == class_id,
    ).first()


def unassign_class_from_exam(db: Session, ea: ExamAssignment) -> None:
    db.delete(ea)
    db.flush()


def get_exam_class_ids(db: Session, exam_id: uuid.UUID) -> List[uuid.UUID]:
    rows = db.query(ExamAssignment.class_id).filter(ExamAssignment.exam_id == exam_id).all()
    return [r[0] for r in rows]


def student_assigned_to_exam(db: Session, exam_id: uuid.UUID, student_id: uuid.UUID) -> bool:
    """Check if student is in any class assigned to this exam."""
    student_class_ids = get_class_ids_for_student(db, student_id)
    if not student_class_ids:
        return False
    exam_class_ids = get_exam_class_ids(db, exam_id)
    return bool(set(student_class_ids) & set(exam_class_ids))


def get_exams_for_student(db: Session, student_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[Exam], int]:
    """Return exams assigned to classes the student belongs to."""
    student_class_ids = get_class_ids_for_student(db, student_id)
    if not student_class_ids:
        return [], 0
    now = datetime.now(timezone.utc)
    exam_ids_q = db.query(ExamAssignment.exam_id).filter(
        ExamAssignment.class_id.in_(student_class_ids)
    ).distinct()
    q = db.query(Exam).filter(
        Exam.id.in_(exam_ids_q),
        # D11: drafts and cancelled exams are not offered to students
        Exam.status.notin_([ExamStatus.CANCELLED.value, ExamStatus.DRAFT.value]),
        Exam.start_time <= now,  # only show started or ongoing
    )
    total = q.count()
    items = q.order_by(Exam.start_time.desc()).offset(skip).limit(limit).all()
    return items, total


# ExamParticipation
def get_participation(db: Session, exam_id: uuid.UUID, student_id: uuid.UUID) -> Optional[ExamParticipation]:
    return db.query(ExamParticipation).filter(
        ExamParticipation.exam_id == exam_id,
        ExamParticipation.student_id == student_id,
    ).first()


def get_participation_by_id(db: Session, participation_id: uuid.UUID) -> Optional[ExamParticipation]:
    return db.query(ExamParticipation).filter(ExamParticipation.id == participation_id).first()


def create_participation(db: Session, exam_id: uuid.UUID, student_id: uuid.UUID) -> ExamParticipation:
    p = ExamParticipation(
        exam_id=exam_id,
        student_id=student_id,
        status=ParticipationStatus.IN_PROGRESS.value,
        started_at=datetime.now(timezone.utc),
    )
    db.add(p)
    db.flush()
    return p


def get_active_exam_participation_for_student(db: Session, student_id: uuid.UUID) -> Optional[ExamParticipation]:
    """Return in-progress exam participation where exam is currently active by server time."""
    now = datetime.now(timezone.utc)
    return (
        db.query(ExamParticipation)
        .join(Exam, Exam.id == ExamParticipation.exam_id)
        .filter(
            ExamParticipation.student_id == student_id,
            ExamParticipation.status == ParticipationStatus.IN_PROGRESS.value,
            Exam.start_time <= now,
            Exam.end_time > now,
            Exam.status != ExamStatus.CANCELLED.value,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# CodingSession / PracticeAttempt
# ---------------------------------------------------------------------------

def get_or_create_practice_attempt(
    db: Session, student_id: uuid.UUID, problem_id: uuid.UUID
) -> PracticeAttempt:
    attempt = db.query(PracticeAttempt).filter(
        PracticeAttempt.student_id == student_id,
        PracticeAttempt.problem_id == problem_id,
    ).first()
    if not attempt:
        attempt = PracticeAttempt(student_id=student_id, problem_id=problem_id)
        db.add(attempt)
        db.flush()
    return attempt


def create_practice_session(
    db: Session,
    student_id: uuid.UUID,
    problem_id: uuid.UUID,
    language: str,
    practice_attempt_id: uuid.UUID,
    idle_threshold_seconds: Optional[int] = None,
) -> CodingSession:
    s = CodingSession(
        student_id=student_id,
        problem_id=problem_id,
        language=language,
        is_exam_context=False,
        practice_attempt_id=practice_attempt_id,
        status=SessionStatus.ACTIVE.value,
        idle_threshold_seconds=idle_threshold_seconds,
    )
    db.add(s)
    db.flush()
    return s


def create_exam_session(
    db: Session,
    student_id: uuid.UUID,
    problem_id: uuid.UUID,
    language: str,
    exam_participation_id: uuid.UUID,
    idle_threshold_seconds: Optional[int] = None,
) -> CodingSession:
    s = CodingSession(
        student_id=student_id,
        problem_id=problem_id,
        language=language,
        is_exam_context=True,
        exam_participation_id=exam_participation_id,
        status=SessionStatus.ACTIVE.value,
        idle_threshold_seconds=idle_threshold_seconds,
    )
    db.add(s)
    db.flush()
    return s


def lock_participation(db: Session, participation_id: uuid.UUID) -> Optional[ExamParticipation]:
    return (db.query(ExamParticipation).filter(ExamParticipation.id == participation_id)
            .with_for_update().populate_existing().first())


def get_active_exam_session(db: Session, participation_id: uuid.UUID, problem_id: uuid.UUID) -> Optional[CodingSession]:
    return db.query(CodingSession).filter(
        CodingSession.exam_participation_id == participation_id,
        CodingSession.problem_id == problem_id,
        CodingSession.status == SessionStatus.ACTIVE.value,
    ).order_by(CodingSession.opened_at).first()


def get_session_by_id(db: Session, session_id: uuid.UUID) -> Optional[CodingSession]:
    return db.query(CodingSession).filter(CodingSession.id == session_id).first()


def get_sessions_by_student(db: Session, student_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[CodingSession], int]:
    q = db.query(CodingSession).filter(CodingSession.student_id == student_id)
    total = q.count()
    items = q.order_by(CodingSession.opened_at.desc()).offset(skip).limit(limit).all()
    return items, total


def lock_session_for_finalize(db: Session, session_id: uuid.UUID) -> Optional[CodingSession]:
    """SELECT ... FOR UPDATE: serializes finalization against trace ingest (FOR KEY SHARE)."""
    return (
        db.query(CodingSession)
        .filter(CodingSession.id == session_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def mark_session_terminated(
    db: Session,
    session: CodingSession,
    status: SessionStatus,
    termination_source: str,
    ended_at: datetime,
    final_loc: Optional[int],
    working_time_seconds: int,
    final_code_snapshot_id: Optional[uuid.UUID],
) -> CodingSession:
    session.status = status.value
    session.termination_source = termination_source
    session.ended_at = ended_at
    session.final_loc = final_loc
    session.working_time_seconds = working_time_seconds
    session.final_code_snapshot_id = final_code_snapshot_id
    db.flush()
    return session


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def get_submissions_by_student(db: Session, student_id: uuid.UUID, skip: int = 0, limit: int = 50) -> Tuple[List[Submission], int]:
    q = db.query(Submission).filter(Submission.student_id == student_id)
    total = q.count()
    items = q.order_by(Submission.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_submission_by_id(db: Session, submission_id: uuid.UUID) -> Optional[Submission]:
    return db.query(Submission).filter(Submission.id == submission_id).first()
