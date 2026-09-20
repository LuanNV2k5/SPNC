"""Phase 05 — Academic domain API endpoints.

Covers:
    - Teacher: Class CRUD + membership management
    - Teacher: Problem CRUD + class publication
    - Teacher: Exam CRUD + problem association + class assignment
    - Student: Exam access (via assignment + authoritative timing)
    - Student: ExamParticipation (start-exam)
    - Student: Practice CodingSession (with active-exam guard)
    - Student: Exam CodingSession
    - Session lifecycle (ACTIVE → ENDED | ABANDONED)
    - Submission foundation (list / get; judge deferred to Phase 07)
    - Full authorization matrix per PROJECT_RULES / RBAC_MATRIX
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_teacher, require_student, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import academic as svc
from app.schemas.academic import (
    # Class
    ClassCreateRequest, ClassUpdateRequest, ClassResponse, ClassListResponse,
    # ClassMembership
    EnrollRequest, MemberResponse, MemberListResponse,
    # Problem
    ProblemCreateRequest, ProblemUpdateRequest, ProblemResponse, ProblemListResponse,
    PublishToCLassRequest, PublicationResponse,
    # Exam
    ExamCreateRequest, ExamUpdateRequest, ExamResponse, ExamListResponse,
    AttachProblemRequest, ExamProblemResponse,
    AssignClassRequest, ExamAssignmentResponse,
    # Participation
    ParticipationResponse,
    # Session
    StartPracticeSessionRequest, StartExamSessionRequest, EndSessionRequest,
    SessionResponse, SessionListResponse,
    # Submission
    SubmissionResponse, SubmissionListResponse,
)

router = APIRouter()

def _paginate(page: int, size: int):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    return page, size, (page - 1) * size

# ============================================================
# CLASS endpoints  (Teacher only)
# ============================================================

@router.post(
    "/classes",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
    summary="[P05-C01] Create a new class (Teacher)",
)
def create_class(
    req: ClassCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    cls = svc.create_class(db, owner=current_user, req=req)
    db.commit()
    db.refresh(cls)
    return cls


@router.get(
    "/classes",
    response_model=ClassListResponse,
    tags=["classes"],
    summary="[P05-C02] List own classes (Teacher)",
)
def list_classes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_classes(db, owner=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/classes/{class_id}",
    response_model=ClassResponse,
    tags=["classes"],
    summary="[P05-C03] Get class detail (Teacher owner only)",
)
def get_class(
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    return svc.get_class(db, owner=current_user, class_id=class_id)


@router.patch(
    "/classes/{class_id}",
    response_model=ClassResponse,
    tags=["classes"],
    summary="[P05-C04] Update class (Teacher owner only)",
)
def update_class(
    class_id: uuid.UUID,
    req: ClassUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    cls = svc.update_class(db, owner=current_user, class_id=class_id, req=req)
    db.commit()
    db.refresh(cls)
    return cls


# ============================================================
# CLASS MEMBERSHIP endpoints  (Teacher only)
# ============================================================

@router.post(
    "/classes/{class_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["classes"],
    summary="[P05-C05] Enroll student into class (Teacher owner only)",
)
def enroll_student(
    class_id: uuid.UUID,
    req: EnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    m = svc.enroll_student(db, owner=current_user, class_id=class_id, req=req)
    db.commit()
    db.refresh(m)
    return m


@router.get(
    "/classes/{class_id}/members",
    response_model=MemberListResponse,
    tags=["classes"],
    summary="[P05-C06] List class members (Teacher owner only)",
)
def list_class_members(
    class_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_class_members(db, owner=current_user, class_id=class_id, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.delete(
    "/classes/{class_id}/members/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["classes"],
    summary="[P05-C07] Remove student from class (Teacher owner only)",
)
def remove_student(
    class_id: uuid.UUID,
    student_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    svc.remove_student(db, owner=current_user, class_id=class_id, student_id=student_id)
    db.commit()


@router.get(
    "/my/classes",
    response_model=ClassListResponse,
    tags=["classes"],
    summary="[P05-C08] List my enrolled classes (Student)",
)
def student_list_classes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_student_classes(db, student=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


# ============================================================
# PROBLEM endpoints  (Teacher)
# ============================================================

@router.post(
    "/problems",
    response_model=ProblemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["problems"],
    summary="[P05-P01] Create problem (Teacher)",
)
def create_problem(
    req: ProblemCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    p = svc.create_problem(db, owner=current_user, req=req)
    db.commit()
    db.refresh(p)
    return p


@router.get(
    "/problems",
    response_model=ProblemListResponse,
    tags=["problems"],
    summary="[P05-P02] List own problems (Teacher)",
)
def list_problems(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_problems(db, owner=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/problems/{problem_id}",
    response_model=ProblemResponse,
    tags=["problems"],
    summary="[P05-P03] Get problem (Teacher owner; or Student via access rules)",
)
def get_problem(
    problem_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_problem(db, user=current_user, problem_id=problem_id)


@router.patch(
    "/problems/{problem_id}",
    response_model=ProblemResponse,
    tags=["problems"],
    summary="[P05-P04] Update problem (Teacher owner only)",
)
def update_problem(
    problem_id: uuid.UUID,
    req: ProblemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    p = svc.update_problem(db, owner=current_user, problem_id=problem_id, req=req)
    db.commit()
    db.refresh(p)
    return p


@router.get(
    "/problems/public/bank",
    response_model=ProblemListResponse,
    tags=["problems"],
    summary="[P05-P05] Browse public problem bank (Student)",
)
def list_public_problems(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_public_problems(db, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/problems/{problem_id}/publish",
    response_model=PublicationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["problems"],
    summary="[P05-P06] Publish problem to class (Teacher owner only)",
)
def publish_to_class(
    problem_id: uuid.UUID,
    req: PublishToCLassRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    pub = svc.publish_to_class(db, owner=current_user, problem_id=problem_id, req=req)
    db.commit()
    db.refresh(pub)
    return pub


@router.delete(
    "/problems/{problem_id}/publish/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["problems"],
    summary="[P05-P07] Unpublish problem from class (Teacher owner only)",
)
def unpublish_from_class(
    problem_id: uuid.UUID,
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    svc.unpublish_from_class(db, owner=current_user, problem_id=problem_id, class_id=class_id)
    db.commit()


# ============================================================
# EXAM endpoints  (Teacher)
# ============================================================

@router.post(
    "/exams",
    response_model=ExamResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["exams"],
    summary="[P05-E01] Create exam (Teacher)",
)
def create_exam(
    req: ExamCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    e = svc.create_exam(db, owner=current_user, req=req)
    db.commit()
    db.refresh(e)
    return e


@router.get(
    "/exams",
    response_model=ExamListResponse,
    tags=["exams"],
    summary="[P05-E02] List own exams (Teacher)",
)
def list_exams(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_exams(db, owner=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/exams/{exam_id}",
    response_model=ExamResponse,
    tags=["exams"],
    summary="[P05-E03] Get exam detail (Teacher owner)",
)
def get_exam(
    exam_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    return svc.get_exam(db, owner=current_user, exam_id=exam_id)


@router.patch(
    "/exams/{exam_id}",
    response_model=ExamResponse,
    tags=["exams"],
    summary="[P05-E04] Update exam (Teacher owner only)",
)
def update_exam(
    exam_id: uuid.UUID,
    req: ExamUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    e = svc.update_exam(db, owner=current_user, exam_id=exam_id, req=req)
    db.commit()
    db.refresh(e)
    return e


@router.post(
    "/exams/{exam_id}/problems",
    response_model=ExamProblemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["exams"],
    summary="[P05-E05] Attach problem to exam (Teacher owner)",
)
def attach_problem(
    exam_id: uuid.UUID,
    req: AttachProblemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    ep = svc.attach_problem(db, owner=current_user, exam_id=exam_id, req=req)
    db.commit()
    db.refresh(ep)
    return ep


@router.get(
    "/exams/{exam_id}/problems",
    response_model=list,
    tags=["exams"],
    summary="[P05-E06] List exam problems (Teacher owner)",
)
def list_exam_problems(
    exam_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    eps = svc.list_exam_problems(db, owner=current_user, exam_id=exam_id)
    return [
        {"id": str(ep.id), "exam_id": str(ep.exam_id), "problem_id": str(ep.problem_id),
         "order_index": ep.order_index, "max_score": ep.max_score}
        for ep in eps
    ]


@router.delete(
    "/exams/{exam_id}/problems/{problem_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["exams"],
    summary="[P05-E07] Detach problem from exam (Teacher owner)",
)
def detach_problem(
    exam_id: uuid.UUID,
    problem_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    svc.detach_problem(db, owner=current_user, exam_id=exam_id, problem_id=problem_id)
    db.commit()


@router.post(
    "/exams/{exam_id}/classes",
    response_model=ExamAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["exams"],
    summary="[P05-E08] Assign class to exam (Teacher owner)",
)
def assign_class(
    exam_id: uuid.UUID,
    req: AssignClassRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    ea = svc.assign_class(db, owner=current_user, exam_id=exam_id, req=req)
    db.commit()
    db.refresh(ea)
    return ea


@router.get(
    "/exams/{exam_id}/classes",
    response_model=list,
    tags=["exams"],
    summary="[P05-E09] List assigned classes (Teacher owner)",
)
def list_exam_classes(
    exam_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    ea_list = svc.list_exam_classes(db, owner=current_user, exam_id=exam_id)
    return [
        {"id": str(ea.id), "exam_id": str(ea.exam_id), "class_id": str(ea.class_id), "created_at": ea.created_at.isoformat()}
        for ea in ea_list
    ]


@router.delete(
    "/exams/{exam_id}/classes/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["exams"],
    summary="[P05-E10] Unassign class from exam (Teacher owner)",
)
def unassign_class(
    exam_id: uuid.UUID,
    class_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    svc.unassign_class(db, owner=current_user, exam_id=exam_id, class_id=class_id)
    db.commit()


# ============================================================
# STUDENT: Exam access + participation
# ============================================================

@router.get(
    "/my/exams",
    response_model=ExamListResponse,
    tags=["exams"],
    summary="[P05-E11] List accessible exams (Student via class assignment)",
)
def student_list_exams(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.student_list_exams(db, student=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/my/exams/{exam_id}/start",
    response_model=ParticipationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["exams"],
    summary="[P05-E12] Start exam / create ExamParticipation (Student)",
)
def start_exam(
    exam_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    p = svc.start_exam_participation(db, student=current_user, exam_id=exam_id)
    db.commit()
    db.refresh(p)
    return p


@router.get(
    "/my/exams/{exam_id}/participation",
    response_model=ParticipationResponse,
    tags=["exams"],
    summary="[P05-E13] Get my participation for an exam (Student)",
)
def get_my_participation(
    exam_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return svc.get_my_participation(db, student=current_user, exam_id=exam_id)


# ============================================================
# PRACTICE SESSIONS  (Student)
# ============================================================

@router.post(
    "/my/practice/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["practice"],
    summary="[P05-S01] Start practice coding session (Student)",
)
def start_practice_session(
    req: StartPracticeSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    s = svc.start_practice_session(db, student=current_user, req=req)
    db.commit()
    db.refresh(s)
    return s


@router.get(
    "/my/practice/sessions",
    response_model=SessionListResponse,
    tags=["practice"],
    summary="[P05-S02] List my practice sessions (Student)",
)
def list_practice_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_practice_sessions(db, student=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/my/practice/sessions/{session_id}",
    response_model=SessionResponse,
    tags=["practice"],
    summary="[P05-S03] Get practice session detail (Student owner only)",
)
def get_practice_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return svc.get_practice_session(db, student=current_user, session_id=session_id)


@router.post(
    "/my/practice/sessions/{session_id}/end",
    response_model=SessionResponse,
    tags=["practice"],
    summary="[P05-S04] End practice session (Student)",
)
def end_practice_session(
    session_id: uuid.UUID,
    req: EndSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    s = svc.end_practice_session(db, student=current_user, session_id=session_id, req=req)
    db.commit()
    db.refresh(s)
    return s


# ============================================================
# EXAM SESSIONS  (Student)
# ============================================================

@router.post(
    "/my/exam-sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sessions"],
    summary="[P05-S05] Start exam coding session (Student with active participation)",
)
def start_exam_session(
    req: StartExamSessionRequest,
    participation_id: uuid.UUID = Query(..., description="ExamParticipation ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    s = svc.start_exam_session(db, student=current_user, participation_id=participation_id, req=req)
    db.commit()
    db.refresh(s)
    return s


@router.get(
    "/my/exam-sessions/{session_id}",
    response_model=SessionResponse,
    tags=["sessions"],
    summary="[P05-S06] Get exam session detail (Student owner only)",
)
def get_exam_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return svc.get_exam_session(db, student=current_user, session_id=session_id)


@router.post(
    "/my/exam-sessions/{session_id}/end",
    response_model=SessionResponse,
    tags=["sessions"],
    summary="[P05-S07] End exam session (Student)",
)
def end_exam_session(
    session_id: uuid.UUID,
    req: EndSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    s = svc.end_exam_session(db, student=current_user, session_id=session_id, req=req)
    db.commit()
    db.refresh(s)
    return s


# ============================================================
# SUBMISSIONS  (Student — foundation; Judge is Phase 07)
# ============================================================

@router.get(
    "/my/submissions",
    response_model=SubmissionListResponse,
    tags=["submissions"],
    summary="[P05-A01] List my submissions (Student)",
)
def list_submissions(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_submissions(db, student=current_user, skip=skip, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/my/submissions/{submission_id}",
    response_model=SubmissionResponse,
    tags=["submissions"],
    summary="[P05-A02] Get submission detail (Student owner only)",
)
def get_submission(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return svc.get_submission(db, student=current_user, submission_id=submission_id)
