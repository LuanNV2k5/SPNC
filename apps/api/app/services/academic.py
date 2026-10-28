"""Phase 05 — Academic domain service layer.

Handles business logic and authorization for:
- Classes and memberships
- Problems and publications
- Exams and assignments
- Participations (concurrency-safe)
- Sessions and submissions
"""
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import academic as repo
from app.services.problem_guard import assert_not_deleted, assert_problem_mutable
from app.schemas.academic import (
    ClassCreateRequest, ClassUpdateRequest,
    EnrollRequest,
    ProblemCreateRequest, ProblemUpdateRequest,
    PublishToCLassRequest,
    ExamCreateRequest, ExamUpdateRequest,
    AttachProblemRequest, AssignClassRequest,
    StartPracticeSessionRequest, StartExamSessionRequest, EndSessionRequest
)

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


# ============================================================
# CLASS
# ============================================================

def create_class(db: Session, owner: User, req: ClassCreateRequest):
    return repo.create_class(db, owner_id=owner.id, name=req.name, academic_year=req.academic_year)

def get_class(db: Session, owner: User, class_id: uuid.UUID):
    cls = repo.get_class_by_id(db, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail=_error("CLASS_NOT_FOUND", "Class not found"))
    if cls.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("CLASS_FORBIDDEN", "Not your class"))
    return cls

def update_class(db: Session, owner: User, class_id: uuid.UUID, req: ClassUpdateRequest):
    cls = get_class(db, owner, class_id)
    update_data = req.model_dump(exclude_none=True)
    return repo.update_class(db, cls, **update_data)

def rotate_invite_code(db: Session, owner: User, class_id: uuid.UUID):
    """docs/38 D2: replaces the code; the old one stops working immediately."""
    from app.models.class_org import generate_invite_code
    cls = get_class(db, owner, class_id)
    code = generate_invite_code()
    while repo.invite_code_taken(db, code):
        code = generate_invite_code()
    return repo.update_class(db, cls, invite_code=code)

def list_classes(db: Session, owner: User, skip: int, limit: int):
    return repo.get_classes_by_owner(db, owner_id=owner.id, skip=skip, limit=limit)


# ============================================================
# MEMBERSHIP
# ============================================================

def enroll_student(db: Session, owner: User, class_id: uuid.UUID, req: EnrollRequest):
    cls = get_class(db, owner, class_id)
    
    from app.repositories.auth import get_user_by_id
    student = get_user_by_id(db, req.student_id)
    if not student:
        raise HTTPException(status_code=404, detail=_error("USER_NOT_FOUND", "Student not found"))
    student_role = student.role.value if hasattr(student.role, 'value') else student.role
    if student_role != "STUDENT":
        raise HTTPException(status_code=422, detail=_error("NOT_A_STUDENT", "Target user is not a student"))

    existing = repo.get_membership(db, class_id, req.student_id)
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=409, detail=_error("ALREADY_ENROLLED", "Student already enrolled"))
        existing.is_active = True
        db.flush()
        return existing

    try:
        # Use SAVEPOINT to avoid rolling back entire transaction on conflict
        with db.begin_nested():
            m = repo.enroll_student(db, class_id=class_id, student_id=req.student_id)
            return m
    except IntegrityError:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ENROLLED", "Student already enrolled"))

def join_class(db: Session, student: User, invite_code: str):
    """UC-B03 / REQ-CLASS-005. Enrollment is auto-approved (OQ-08 current assumption)."""
    cls = repo.get_class_by_invite_code(db, invite_code.strip().upper())
    if not cls:
        raise HTTPException(status_code=404, detail=_error("INVITE_CODE_INVALID", "Invite code not found"))
    if not cls.is_active:
        raise HTTPException(status_code=403, detail=_error("CLASS_NOT_ACTIVE", "This class is not accepting members"))
    existing = repo.get_membership(db, cls.id, student.id)
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=409, detail=_error("ALREADY_ENROLLED", "You are already in this class"))
        # docs/38 D3: a removed member re-joins on the same record
        existing.is_active = True
        db.flush()
        return existing
    try:
        with db.begin_nested():
            return repo.enroll_student(db, class_id=cls.id, student_id=student.id)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ENROLLED", "You are already in this class"))

def list_class_members(db: Session, owner: User, class_id: uuid.UUID, skip: int, limit: int):
    cls = get_class(db, owner, class_id)
    return repo.get_memberships_by_class(db, class_id, skip=skip, limit=limit)

def remove_student(db: Session, owner: User, class_id: uuid.UUID, student_id: uuid.UUID):
    cls = get_class(db, owner, class_id)
    m = repo.get_membership(db, class_id, student_id)
    if not m or not m.is_active:
        raise HTTPException(status_code=404, detail=_error("MEMBER_NOT_FOUND", "Membership not found"))
    return repo.deactivate_membership(db, m)

def list_student_classes(db: Session, student: User, skip: int, limit: int):
    memberships, total = repo.get_memberships_by_student(db, student.id, skip=skip, limit=limit)
    class_ids = [m.class_id for m in memberships]
    items = []
    for cid in class_ids:
        c = repo.get_class_by_id(db, cid)
        if c:
            items.append(c)
    return items, total


# ============================================================
# PROBLEM
# ============================================================

def create_problem(db: Session, owner: User, req: ProblemCreateRequest):
    return repo.create_problem(db, owner_id=owner.id, **req.model_dump())

def get_problem(db: Session, user: User, problem_id: uuid.UUID):
    p = repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    # docs/38 D5: a deleted problem stays readable to its owner only (history)
    if p.deleted_at is not None and p.owner_id != user.id:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))

    user_role = user.role.value if hasattr(user.role, 'value') else user.role

    if user_role == "TEACHER":
        if p.owner_id == user.id:
            return p
        if p.visibility == "PUBLIC":
            return p
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not authorized to view this problem"))

    if user_role == "STUDENT":
        vis = p.visibility if isinstance(p.visibility, str) else p.visibility.value
        if vis == "PUBLIC":
            return p
        if vis == "CLASS":
            student_class_ids = repo.get_class_ids_for_student(db, user.id)
            from app.models.problem import ProblemClassPublication
            pub = db.query(ProblemClassPublication).filter(
                ProblemClassPublication.problem_id == problem_id,
                ProblemClassPublication.class_id.in_(student_class_ids)
            ).first() if student_class_ids else None
            if pub:
                return p
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not authorized to view this problem"))

    raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not authorized"))

def update_problem(db: Session, owner: User, problem_id: uuid.UUID, req: ProblemUpdateRequest):
    p = repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    assert_not_deleted(p)
    assert_problem_mutable(db, problem_id)   # REQ-PROB-004
    update_data = req.model_dump(exclude_none=True)
    return repo.update_problem(db, p, **update_data)

def delete_problem(db: Session, owner: User, problem_id: uuid.UUID):
    """REQ-PROB-005, docs/38 D5: soft delete; sessions, submissions and trace stay intact."""
    p = repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    assert_not_deleted(p)
    assert_problem_mutable(db, problem_id)
    return repo.update_problem(db, p, deleted_at=_now_utc())

def list_problems(db: Session, owner: User, skip: int, limit: int,
                  difficulty: Optional[str] = None, language: Optional[str] = None, visibility: Optional[str] = None):
    return repo.get_problems_by_owner(db, owner.id, skip=skip, limit=limit,
                                      difficulty=difficulty, language=language, visibility=visibility)

def list_public_problems(db: Session, skip: int, limit: int):
    return repo.get_public_problems(db, skip=skip, limit=limit)

def publish_to_class(db: Session, owner: User, problem_id: uuid.UUID, req: PublishToCLassRequest):
    p = repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    assert_not_deleted(p)

    cls = repo.get_class_by_id(db, req.class_id)
    if not cls:
        raise HTTPException(status_code=404, detail=_error("CLASS_NOT_FOUND", "Class not found"))
    if cls.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("CLASS_FORBIDDEN", "Not your class"))

    existing = repo.get_publication(db, problem_id, req.class_id)
    if existing:
        raise HTTPException(status_code=409, detail=_error("ALREADY_PUBLISHED", "Problem already published to this class"))

    vis = p.visibility if isinstance(p.visibility, str) else p.visibility.value
    if vis == "PRIVATE":
        raise HTTPException(
            status_code=422,
            detail=_error("PROBLEM_NOT_CLASS_VISIBLE", "Change problem visibility to CLASS before publishing"),
        )

    return repo.create_publication(db, problem_id=problem_id, class_id=req.class_id)

def unpublish_from_class(db: Session, owner: User, problem_id: uuid.UUID, class_id: uuid.UUID):
    p = repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    pub = repo.get_publication(db, problem_id, class_id)
    if not pub:
        raise HTTPException(status_code=404, detail=_error("PUBLICATION_NOT_FOUND", "Publication not found"))
    repo.delete_publication(db, pub)


# ============================================================
# EXAM
# ============================================================

def _check_duration(start_time, end_time, duration_minutes) -> None:
    """docs/38 D7: a per-student limit cannot exceed the exam window."""
    if duration_minutes is not None and duration_minutes * 60 > (end_time - start_time).total_seconds():
        raise HTTPException(status_code=422, detail=_error("EXAM_DURATION_TOO_LONG", "duration_minutes exceeds the exam window"))

def _assert_exam_editable(e) -> None:
    """REQ-EXAM-006, docs/38 D6: schedule, problems and classes change only while DRAFT."""
    status = e.status if isinstance(e.status, str) else e.status.value
    if status != "DRAFT":
        raise HTTPException(status_code=409, detail=_error("EXAM_NOT_EDITABLE", "Only a DRAFT exam can be edited"))

def create_exam(db: Session, owner: User, req: ExamCreateRequest):
    _check_duration(req.start_time, req.end_time, req.duration_minutes)
    return repo.create_exam(
        db,
        owner_id=owner.id,
        title=req.title,
        description=req.description,
        start_time=req.start_time,
        end_time=req.end_time,
        allow_view_result_after=req.allow_view_result_after,
        duration_minutes=req.duration_minutes,
    )

def list_exams(db: Session, owner: User, skip: int, limit: int):
    return repo.get_exams_by_owner(db, owner.id, skip=skip, limit=limit)

def get_exam(db: Session, owner: User, exam_id: uuid.UUID):
    e = repo.get_exam_by_id(db, exam_id)
    if not e:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    if e.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("EXAM_FORBIDDEN", "Not your exam"))
    return e

def update_exam(db: Session, owner: User, exam_id: uuid.UUID, req: ExamUpdateRequest):
    e = get_exam(db, owner, exam_id)
    update_data = req.model_dump(exclude_none=True)
    status = e.status if isinstance(e.status, str) else e.status.value
    if set(update_data) == {"allow_view_result_after"}:
        # D6 exception: result visibility may change after publication (D14), not once cancelled
        if status == "CANCELLED":
            raise HTTPException(status_code=409, detail=_error("EXAM_NOT_EDITABLE", "A cancelled exam cannot be edited"))
    elif update_data:
        _assert_exam_editable(e)
        _check_duration(update_data.get("start_time", e.start_time), update_data.get("end_time", e.end_time),
                        update_data.get("duration_minutes", e.duration_minutes))
    return repo.update_exam(db, e, **update_data)

def attach_problem(db: Session, owner: User, exam_id: uuid.UUID, req: AttachProblemRequest):
    e = get_exam(db, owner, exam_id)
    _assert_exam_editable(e)
    p = repo.get_problem_by_id(db, req.problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    assert_not_deleted(p)

    existing = repo.get_exam_problem(db, exam_id, req.problem_id)
    if existing:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ATTACHED", "Problem already attached to exam"))

    try:
        with db.begin_nested():
            return repo.attach_problem_to_exam(
                db, exam_id=exam_id, problem_id=req.problem_id,
                order_index=req.order_index, max_score=req.max_score
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ATTACHED", "Problem already attached to exam"))

def list_exam_problems(db: Session, owner: User, exam_id: uuid.UUID):
    e = get_exam(db, owner, exam_id)
    return repo.get_exam_problems(db, exam_id)

def detach_problem(db: Session, owner: User, exam_id: uuid.UUID, problem_id: uuid.UUID):
    e = get_exam(db, owner, exam_id)
    _assert_exam_editable(e)
    ep = repo.get_exam_problem(db, exam_id, problem_id)
    if not ep:
        raise HTTPException(status_code=404, detail=_error("EXAM_PROBLEM_NOT_FOUND", "Problem not attached"))
    repo.detach_problem_from_exam(db, ep)

def assign_class(db: Session, owner: User, exam_id: uuid.UUID, req: AssignClassRequest):
    e = get_exam(db, owner, exam_id)
    _assert_exam_editable(e)
    cls = repo.get_class_by_id(db, req.class_id)
    if not cls:
        raise HTTPException(status_code=404, detail=_error("CLASS_NOT_FOUND", "Class not found"))
    if cls.owner_id != owner.id:
        raise HTTPException(status_code=403, detail=_error("CLASS_FORBIDDEN", "Not your class"))

    existing = repo.get_exam_assignment(db, exam_id, req.class_id)
    if existing:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ASSIGNED", "Class already assigned to exam"))

    try:
        with db.begin_nested():
            return repo.assign_class_to_exam(db, exam_id=exam_id, class_id=req.class_id)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=_error("ALREADY_ASSIGNED", "Class already assigned to exam"))

def list_exam_classes(db: Session, owner: User, exam_id: uuid.UUID):
    e = get_exam(db, owner, exam_id)
    from app.models.exam import ExamAssignment
    return db.query(ExamAssignment).filter_by(exam_id=exam_id).all()

def unassign_class(db: Session, owner: User, exam_id: uuid.UUID, class_id: uuid.UUID):
    e = get_exam(db, owner, exam_id)
    _assert_exam_editable(e)
    ea = repo.get_exam_assignment(db, exam_id, class_id)
    if not ea:
        raise HTTPException(status_code=404, detail=_error("ASSIGNMENT_NOT_FOUND", "Assignment not found"))
    repo.unassign_class_from_exam(db, ea)


# ============================================================
# PARTICIPATION
# ============================================================

def student_list_exams(db: Session, student: User, skip: int, limit: int):
    return repo.get_exams_for_student(db, student.id, skip=skip, limit=limit)

def start_exam_participation(db: Session, student: User, exam_id: uuid.UUID):
    e = repo.get_exam_by_id(db, exam_id)
    if not e:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))

    # D11: published (SCHEDULED/ONGOING) and inside the authoritative time window
    from app.services.exam_access import assert_exam_open
    assert_exam_open(e, _now_utc())

    if not repo.student_assigned_to_exam(db, exam_id, student.id):
        raise HTTPException(status_code=403, detail=_error("EXAM_NOT_ASSIGNED", "You are not assigned to this exam"))

    existing = repo.get_participation(db, exam_id, student.id)
    if existing:
        return existing

    try:
        with db.begin_nested():
            return repo.create_participation(db, exam_id=exam_id, student_id=student.id)
    except IntegrityError:
        existing = repo.get_participation(db, exam_id, student.id)
        if existing:
            return existing
        raise HTTPException(status_code=500, detail=_error("INTERNAL_ERROR", "Concurrent participation conflict"))

def get_my_participation(db: Session, student: User, exam_id: uuid.UUID):
    e = repo.get_exam_by_id(db, exam_id)
    if not e:
        raise HTTPException(status_code=404, detail=_error("EXAM_NOT_FOUND", "Exam not found"))
    if not repo.student_assigned_to_exam(db, exam_id, student.id):
        raise HTTPException(status_code=403, detail=_error("EXAM_NOT_ASSIGNED", "Not assigned to this exam"))
    p = repo.get_participation(db, exam_id, student.id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PARTICIPATION_NOT_FOUND", "Participation not found"))
    return p


# ============================================================
# SESSIONS
# ============================================================

def start_practice_session(db: Session, student: User, req: StartPracticeSessionRequest):
    active_participation = repo.get_active_exam_participation_for_student(db, student.id)
    if active_participation:
        raise HTTPException(
            status_code=403,
            detail=_error("ACTIVE_EXAM_IN_PROGRESS", "Cannot start practice session during an active exam"),
        )

    p = repo.get_problem_by_id(db, req.problem_id)
    if not p or p.deleted_at is not None:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))

    vis = p.visibility if isinstance(p.visibility, str) else p.visibility.value
    if vis == "PRIVATE":
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Problem is not accessible"))
    if vis == "CLASS":
        student_class_ids = repo.get_class_ids_for_student(db, student.id)
        if not student_class_ids or not repo.problem_published_to_class(db, req.problem_id, student_class_ids[0]):
            from app.models.problem import ProblemClassPublication
            pub = db.query(ProblemClassPublication).filter(
                ProblemClassPublication.problem_id == req.problem_id,
                ProblemClassPublication.class_id.in_(student_class_ids)
            ).first() if student_class_ids else None
            if not pub:
                raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Problem not published to your class"))

    supported = p.supported_languages if isinstance(p.supported_languages, list) else []
    if req.language not in supported:
        raise HTTPException(
            status_code=422,
            detail=_error("LANGUAGE_NOT_SUPPORTED", f"Language {req.language} not supported by this problem"),
        )

    attempt = repo.get_or_create_practice_attempt(db, student.id, req.problem_id)
    return repo.create_practice_session(
        db,
        student_id=student.id,
        problem_id=req.problem_id,
        language=req.language,
        practice_attempt_id=attempt.id,
    )

def list_practice_sessions(db: Session, student: User, skip: int, limit: int):
    from app.models.session import CodingSession
    q = db.query(CodingSession).filter(
        CodingSession.student_id == student.id,
        CodingSession.is_exam_context == False,
    )
    total = q.count()
    items = q.order_by(CodingSession.opened_at.desc()).offset(skip).limit(limit).all()
    return items, total

def get_practice_session(db: Session, student: User, session_id: uuid.UUID):
    s = repo.get_session_by_id(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))
    if s.student_id != student.id:
        raise HTTPException(status_code=403, detail=_error("SESSION_FORBIDDEN", "Not your session"))
    if s.is_exam_context:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))
    return s

def _finalize_student_end(db: Session, s, req: EndSessionRequest):
    # D5: a student can only end their own session as STUDENT; SYSTEM_* actors are internal-only
    if req.termination_source not in (None, "STUDENT"):
        raise HTTPException(
            status_code=422,
            detail=_error("TERMINATION_SOURCE_FORBIDDEN", "Students can only end a session with termination_source STUDENT"),
        )
    from app.models.session import SessionStatus, TerminationSource
    from app.services.session_lifecycle import finalize_session
    return finalize_session(
        db, s.id, SessionStatus.ENDED, TerminationSource.STUDENT,
        last_sequence_number=req.last_sequence_number,
    )

def end_practice_session(db: Session, student: User, session_id: uuid.UUID, req: EndSessionRequest):
    s = get_practice_session(db, student, session_id)
    return _finalize_student_end(db, s, req)

def start_exam_session(db: Session, student: User, participation_id: uuid.UUID, req: StartExamSessionRequest):
    participation = repo.get_participation_by_id(db, participation_id)
    if not participation:
        raise HTTPException(status_code=404, detail=_error("PARTICIPATION_NOT_FOUND", "Participation not found"))
    if participation.student_id != student.id:
        raise HTTPException(status_code=403, detail=_error("PARTICIPATION_FORBIDDEN", "Not your participation"))

    from app.models.exam import ParticipationStatus
    part_status = participation.status if isinstance(participation.status, str) else participation.status.value
    if part_status != ParticipationStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=403, detail=_error("PARTICIPATION_NOT_ACTIVE", "Participation is not in progress"))

    e = repo.get_exam_by_id(db, participation.exam_id)
    from app.services.exam_access import assert_participant_open
    assert_participant_open(e, participation, _now_utc())   # D11 + docs/38 D7 deadline

    ep = repo.get_exam_problem(db, e.id, req.problem_id)
    if not ep:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_NOT_IN_EXAM", "Problem is not part of this exam"))

    p = repo.get_problem_by_id(db, req.problem_id)
    supported = p.supported_languages if isinstance(p.supported_languages, list) else []
    if req.language not in supported:
        raise HTTPException(
            status_code=422,
            detail=_error("LANGUAGE_NOT_SUPPORTED", f"Language {req.language} not supported"),
        )

    return repo.create_exam_session(
        db,
        student_id=student.id,
        problem_id=req.problem_id,
        language=req.language,
        exam_participation_id=participation_id,
    )

def get_exam_session(db: Session, student: User, session_id: uuid.UUID):
    s = repo.get_session_by_id(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))
    if s.student_id != student.id:
        raise HTTPException(status_code=403, detail=_error("SESSION_FORBIDDEN", "Not your session"))
    if not s.is_exam_context:
        raise HTTPException(status_code=404, detail=_error("SESSION_NOT_FOUND", "Session not found"))
    return s

def end_exam_session(db: Session, student: User, session_id: uuid.UUID, req: EndSessionRequest):
    s = get_exam_session(db, student, session_id)
    return _finalize_student_end(db, s, req)


# ============================================================
# SUBMISSIONS
# ============================================================

def list_submissions(db: Session, student: User, skip: int, limit: int):
    from app.services.submission import to_student_response
    items, total = repo.get_submissions_by_student(db, student.id, skip=skip, limit=limit)
    return [to_student_response(db, s) for s in items], total

def get_submission(db: Session, student: User, submission_id: uuid.UUID):
    from app.services.submission import to_student_response
    s = repo.get_submission_by_id(db, submission_id)
    if not s:
        raise HTTPException(status_code=404, detail=_error("SUBMISSION_NOT_FOUND", "Submission not found"))
    if s.student_id != student.id:
        raise HTTPException(status_code=403, detail=_error("SUBMISSION_FORBIDDEN", "Not your submission"))
    return to_student_response(db, s)
