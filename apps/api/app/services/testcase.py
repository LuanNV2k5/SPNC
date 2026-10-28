"""Phase 10A — Test case management (REQ-PROB-002, docs/36 §4 10A).

`is_sample` is the API name for NOT `ProblemTestCase.is_hidden`. Hidden cases are only
ever returned to the owning TEACHER.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.models.exam import ExamParticipation, ExamProblem, ParticipationStatus
from app.models.problem import Problem, ProblemTestCase
from app.models.user import User
from app.repositories import academic as academic_repo
from app.schemas.testcase import TestCaseCreate, TestCaseUpdate
from app.services import academic as academic_svc
from app.services.problem_guard import assert_not_deleted, assert_problem_mutable


def _error(code: str, msg: str) -> dict:
    return {"error_code": code, "message": msg}


def to_response(tc: ProblemTestCase) -> dict:
    return {
        "id": tc.id, "problem_id": tc.problem_id, "order_index": tc.order_index,
        "input_data": tc.input_data, "expected_output": tc.expected_output,
        "is_sample": not tc.is_hidden, "score_weight": tc.score_weight,
    }


def _owned_problem(db: Session, teacher: User, problem_id: uuid.UUID) -> Problem:
    p = academic_repo.get_problem_by_id(db, problem_id)
    if not p:
        raise HTTPException(status_code=404, detail=_error("PROBLEM_NOT_FOUND", "Problem not found"))
    if p.owner_id != teacher.id:
        raise HTTPException(status_code=403, detail=_error("PROBLEM_FORBIDDEN", "Not your problem"))
    return p


def _owned_live_problem(db: Session, teacher: User, problem_id: uuid.UUID) -> Problem:
    p = _owned_problem(db, teacher, problem_id)
    assert_not_deleted(p)
    return p


def _guard_not_running(db: Session, problem_id: uuid.UUID) -> None:
    # docs/38 D4: frozen while any SCHEDULED/ONGOING exam uses the problem
    assert_problem_mutable(db, problem_id)


def list_test_cases(db: Session, teacher: User, problem_id: uuid.UUID):
    _owned_problem(db, teacher, problem_id)
    items = db.scalars(select(ProblemTestCase).where(ProblemTestCase.problem_id == problem_id)
                       .order_by(ProblemTestCase.order_index)).all()
    return [to_response(tc) for tc in items]


def create_test_case(db: Session, teacher: User, problem_id: uuid.UUID, req: TestCaseCreate) -> dict:
    _owned_live_problem(db, teacher, problem_id)
    _guard_not_running(db, problem_id)
    order_index = req.order_index
    if order_index is None:
        order_index = (db.scalar(select(func.max(ProblemTestCase.order_index))
                                 .where(ProblemTestCase.problem_id == problem_id)) or 0) + 1
    elif db.scalar(select(exists(select(ProblemTestCase.id).where(and_(
            ProblemTestCase.problem_id == problem_id, ProblemTestCase.order_index == order_index))))):
        raise HTTPException(status_code=409, detail=_error("TEST_CASE_ORDER_TAKEN", "order_index already used"))
    tc = ProblemTestCase(
        problem_id=problem_id, order_index=order_index, input_data=req.input_data,
        expected_output=req.expected_output, is_hidden=not req.is_sample, score_weight=req.score_weight,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return to_response(tc)


def _owned_case(db: Session, teacher: User, problem_id: uuid.UUID, tc_id: uuid.UUID) -> ProblemTestCase:
    _owned_live_problem(db, teacher, problem_id)
    tc = db.get(ProblemTestCase, tc_id)
    if not tc or tc.problem_id != problem_id:
        raise HTTPException(status_code=404, detail=_error("TEST_CASE_NOT_FOUND", "Test case not found"))
    return tc


def update_test_case(db: Session, teacher: User, problem_id: uuid.UUID, tc_id: uuid.UUID, req: TestCaseUpdate) -> dict:
    tc = _owned_case(db, teacher, problem_id, tc_id)
    _guard_not_running(db, problem_id)
    data = req.model_dump(exclude_none=True)
    if "is_sample" in data:
        tc.is_hidden = not data.pop("is_sample")
    for field, value in data.items():
        setattr(tc, field, value)
    db.commit()
    db.refresh(tc)
    return to_response(tc)


def delete_test_case(db: Session, teacher: User, problem_id: uuid.UUID, tc_id: uuid.UUID) -> None:
    tc = _owned_case(db, teacher, problem_id, tc_id)
    _guard_not_running(db, problem_id)
    db.delete(tc)
    db.commit()


def _student_in_exam_with_problem(db: Session, student: User, problem_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(exists(
        select(ExamParticipation.id)
        .join(ExamProblem, ExamProblem.exam_id == ExamParticipation.exam_id)
        .where(and_(
            ExamParticipation.student_id == student.id,
            ExamParticipation.status == ParticipationStatus.IN_PROGRESS.value,
            ExamProblem.problem_id == problem_id,
        ))
    ))))


def list_samples(db: Session, user: User, problem_id: uuid.UUID):
    """Samples are visible to anyone who may view the problem, or a student taking an exam that contains it."""
    try:
        academic_svc.get_problem(db, user, problem_id)
    except HTTPException as e:
        role = getattr(user.role, "value", user.role)
        if not (e.status_code == 403 and role == "STUDENT" and _student_in_exam_with_problem(db, user, problem_id)):
            raise
    items = db.scalars(select(ProblemTestCase).where(and_(
        ProblemTestCase.problem_id == problem_id, ProblemTestCase.is_hidden == False,
    )).order_by(ProblemTestCase.order_index)).all()
    return [{"order_index": tc.order_index, "input_data": tc.input_data, "expected_output": tc.expected_output} for tc in items]
