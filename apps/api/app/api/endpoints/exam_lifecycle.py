"""Phase 10B — Exam lifecycle endpoints (docs/36 §4 10B). Thin router; the service flushes, the router commits."""
import uuid

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import require_student, require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.academic import ExamCancelRequest, ExamResponse, ParticipationResponse
from app.services import exam_lifecycle as svc

router = APIRouter()


@router.post("/exams/{exam_id}/publish", response_model=ExamResponse, tags=["exams"],
             summary="[P10-E01] Publish a DRAFT exam -> SCHEDULED (owner Teacher)")
def publish_exam(exam_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                 current_user: User = Depends(require_teacher)):
    exam = svc.publish_exam(db, current_user, exam_id)
    db.commit()
    db.refresh(exam)
    return exam


@router.post("/exams/{exam_id}/cancel", response_model=ExamResponse, tags=["exams"],
             summary="[P10-E02] Cancel a DRAFT/SCHEDULED exam (owner Teacher)")
def cancel_exam(req: ExamCancelRequest, exam_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                current_user: User = Depends(require_teacher)):
    exam = svc.cancel_exam(db, current_user, exam_id, req.reason)
    db.commit()
    db.refresh(exam)
    return exam


@router.post("/my/exams/{exam_id}/finalize", response_model=ParticipationResponse, tags=["participations"],
             summary="[P10-E03] Finish my exam: IN_PROGRESS -> COMPLETED (Student)")
def finalize_exam(exam_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                  current_user: User = Depends(require_student)):
    participation = svc.finalize_participation(db, current_user, exam_id)
    db.commit()
    db.refresh(participation)
    return participation
