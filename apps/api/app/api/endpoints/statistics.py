"""Phase 10C — Statistics endpoints (REQ-OBS-007). Thin router, owner Teacher only."""
import uuid

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.statistics import ClassStatisticsResponse, ExamStatisticsResponse
from app.services import statistics as svc

router = APIRouter()


@router.get("/classes/{class_id}/statistics", response_model=ClassStatisticsResponse, tags=["statistics"],
            summary="[P10-ST01] Class statistics (owner Teacher)")
def class_statistics(class_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                     current_user: User = Depends(require_teacher)):
    return svc.class_statistics(db, current_user, class_id)


@router.get("/exams/{exam_id}/statistics", response_model=ExamStatisticsResponse, tags=["statistics"],
            summary="[P10-ST02] Exam statistics (owner Teacher)")
def exam_statistics(exam_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                    current_user: User = Depends(require_teacher)):
    return svc.exam_statistics(db, current_user, exam_id)
