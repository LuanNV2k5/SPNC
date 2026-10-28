"""Phase 10A — Submit endpoint (docs/36 §4 10A). Thin router; the service owns the transaction."""
import uuid

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.db.session import get_db
from app.models.user import User
from app.schemas.academic import SubmissionResponse, SubmitRequest
from app.services import submission as svc

router = APIRouter()


@router.post("/my/coding-sessions/{session_id}/submissions", response_model=SubmissionResponse,
             status_code=status.HTTP_201_CREATED, tags=["submissions"],
             summary="[P10-S01] Submit a snapshot for judging; ends the session (Student owner)")
def submit(req: SubmitRequest, session_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
           current_user: User = Depends(require_student)):
    submission = svc.create_submission(db, current_user, session_id, req.snapshot_id)
    return svc.to_student_response(submission)
