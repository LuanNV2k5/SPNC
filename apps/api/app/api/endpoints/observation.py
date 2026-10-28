"""Phase 09A — Teacher Observation endpoints (docs/35 §4). Thin router; logic lives in services."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.observation import (
    AttentionListResponse, ExamObservationResponse, ObservedSessionListResponse,
    SignalListResponse, SnapshotContentResponse, TeacherRunListResponse, TimelineResponse,
)
from app.services import observation as svc

router = APIRouter()

STUDENT_PATH = "/classes/{class_id}/students/{student_id}"
SESSION_PATH = STUDENT_PATH + "/sessions/{session_id}"


def _paginate(page: int, size: int):
    return page, size, (page - 1) * size


@router.get("/classes/{class_id}/attention", response_model=AttentionListResponse,
            summary="[P09-O01] Students needing attention (NEW signals) in own class")
def list_attention(
    class_id: uuid.UUID = Path(...),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_attention(db, current_user, class_id, skip, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(STUDENT_PATH + "/sessions", response_model=ObservedSessionListResponse,
            summary="[P09-O02] Sessions of a student visible in this class")
def list_student_sessions(
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_student_sessions(db, current_user, class_id, student_id, skip, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(SESSION_PATH + "/timeline", response_model=TimelineResponse,
            summary="[P09-O03] Session timeline: trace events, signals, snapshot references")
def get_timeline(
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...), session_id: uuid.UUID = Path(...),
    skip: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    return svc.get_timeline(db, current_user, class_id, student_id, session_id, skip, limit)


@router.get(SESSION_PATH + "/snapshots/{snapshot_id}", response_model=SnapshotContentResponse,
            summary="[P09-O04] Code snapshot content at a timeline point")
def get_snapshot(
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...), session_id: uuid.UUID = Path(...),
    snapshot_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    return svc.get_snapshot(db, current_user, class_id, student_id, session_id, snapshot_id)


@router.get(SESSION_PATH + "/runs", response_model=TeacherRunListResponse,
            summary="[P09-O05] Run history of a session (class-scoped)")
def list_session_runs(
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...), session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    items, total = svc.list_session_runs(db, current_user, class_id, student_id, session_id)
    return {"items": items, "total": total}


@router.get(STUDENT_PATH + "/signals", response_model=SignalListResponse,
            summary="[P09-O06] Attention signals of a student visible in this class")
def list_student_signals(
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...),
    status: Optional[str] = Query(None), session_id: Optional[uuid.UUID] = Query(None),
    signal_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    items, total = svc.list_student_signals(db, current_user, class_id, student_id, status, session_id, signal_type, skip, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/exams/{exam_id}/observation", response_model=ExamObservationResponse,
            summary="[P09-O07] Exam observation overview (exam owner)")
def get_exam_observation(
    exam_id: uuid.UUID = Path(...),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    page, size, skip = _paginate(page, size)
    exam, items, total = svc.get_exam_observation(db, current_user, exam_id, skip, size)
    return {"exam_id": exam.id, "exam_title": exam.title, "exam_status": getattr(exam.status, "value", exam.status),
            "items": items, "total": total, "page": page, "size": size}
