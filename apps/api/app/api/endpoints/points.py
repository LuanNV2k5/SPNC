"""Phase 14A — Points endpoints (REQ-STU-004). Thin router."""
import uuid

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import require_student, require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.points import PointsSummary
from app.services import points as svc

router = APIRouter()


@router.get("/my/points", response_model=PointsSummary, tags=["points"],
            summary="[P14-PT01] My practice points (Student)")
def my_points(db: Session = Depends(get_db), current_user: User = Depends(require_student)):
    return svc.my_points(db, current_user)


@router.get("/classes/{class_id}/students/{student_id}/points", response_model=PointsSummary, tags=["points"],
            summary="[P14-PT02] A class member's practice points (owner Teacher)")
def student_points(class_id: uuid.UUID = Path(...), student_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                   current_user: User = Depends(require_teacher)):
    return svc.student_points_for_teacher(db, current_user, class_id, student_id)
