"""Phase 09B — Signal status and TeacherAnnotation endpoints (docs/35 §4 09B). Thin router."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.observation import (
    AnnotationCreate, AnnotationListResponse, AnnotationResponse, AnnotationUpdate,
    SignalItem, SignalStatusUpdate,
)
from app.services import annotation as svc

router = APIRouter()


@router.patch("/classes/{class_id}/students/{student_id}/signals/{signal_id}", response_model=SignalItem,
              tags=["observation"], summary="[P09-B01] Change attention signal status (ACK / DISMISS / reopen)")
def change_signal_status(
    req: SignalStatusUpdate, request: Request,
    class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...), signal_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    return svc.change_signal_status(db, current_user, class_id, student_id, signal_id, req.status,
                                    getattr(request.state, "request_id", None))


@router.post("/annotations", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED,
             tags=["annotations"], summary="[P09-B02] Create annotation (Teacher)")
def create_annotation(req: AnnotationCreate, db: Session = Depends(get_db), current_user: User = Depends(require_teacher)):
    return svc.create_annotation(db, current_user, req.student_id, req.session_id, req.signal_id, req.content)


@router.get("/annotations", response_model=AnnotationListResponse,
            tags=["annotations"], summary="[P09-B03] List own annotations (Teacher)")
def list_annotations(
    student_id: Optional[uuid.UUID] = Query(None), session_id: Optional[uuid.UUID] = Query(None),
    signal_id: Optional[uuid.UUID] = Query(None),
    created_from: Optional[datetime] = Query(None), created_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    skip = (page - 1) * size
    items, total = svc.list_annotations(db, current_user, student_id, session_id, signal_id, created_from, created_to, skip, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse,
              tags=["annotations"], summary="[P09-B04] Update own annotation (Teacher)")
def update_annotation(
    req: AnnotationUpdate, annotation_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    return svc.update_annotation(db, current_user, annotation_id, req.content)


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["annotations"], summary="[P09-B05] Delete own annotation (soft delete, Teacher)")
def delete_annotation(
    annotation_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_teacher),
):
    svc.delete_annotation(db, current_user, annotation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
