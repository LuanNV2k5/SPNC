import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.api.deps import get_current_user, require_student, require_teacher
from app.models.user import User, RoleEnum
from app.schemas.trace import (
    TraceBatchRequest, TraceBatchResponse, TraceStateResponse,
    TraceReplayResponse, SnapshotCreate, SnapshotResponse
)
from app.services import trace as svc

router = APIRouter()

@router.post(
    "/my/coding-sessions/{session_id}/trace-events/batch",
    response_model=TraceBatchResponse,
    dependencies=[Depends(require_student)],
    summary="[P06-T01] Ingest trace event batch (Student)"
)
def ingest_trace_batch(
    req: TraceBatchRequest,
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    accepted_count = svc.ingest_trace_batch(db, current_user, session_id, req)
    highest, next_exp = svc.get_trace_state(db, current_user, session_id)
    return TraceBatchResponse(
        accepted_count=accepted_count,
        state=TraceStateResponse(
            highest_contiguous_sequence=highest,
            next_expected_sequence=next_exp
        )
    )

@router.get(
    "/my/coding-sessions/{session_id}/trace-state",
    response_model=TraceStateResponse,
    dependencies=[Depends(require_student)],
    summary="[P06-T02] Get own session trace state (Student)"
)
def get_my_trace_state(
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    highest, next_exp = svc.get_trace_state(db, current_user, session_id)
    return TraceStateResponse(
        highest_contiguous_sequence=highest,
        next_expected_sequence=next_exp,
        checkpoint_interval_seconds=settings.TRACE_CHECKPOINT_INTERVAL_SECONDS,
    )

@router.post(
    "/my/coding-sessions/{session_id}/snapshots",
    response_model=SnapshotResponse,
    dependencies=[Depends(require_student)],
    summary="[P06-S01] Create code snapshot checkpoint (Student)"
)
def create_my_snapshot(
    req: SnapshotCreate,
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return svc.create_snapshot(db, current_user, session_id, req)


@router.get(
    "/classes/{class_id}/students/{student_id}/sessions/{session_id}/trace-events",
    response_model=TraceReplayResponse,
    dependencies=[Depends(require_teacher)],
    summary="[P06-R01] Replay trace history (Teacher)"
)
def get_trace_history(
    class_id: uuid.UUID = Path(...),
    student_id: uuid.UUID = Path(...),
    session_id: uuid.UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items, total = svc.get_teacher_trace_history(db, current_user, class_id, student_id, session_id, skip, limit)
    highest, next_exp = svc.get_teacher_trace_state(db, current_user, class_id, student_id, session_id)
    
    return TraceReplayResponse(
        items=items,
        state=TraceStateResponse(highest_contiguous_sequence=highest, next_expected_sequence=next_exp),
        total=total,
        skip=skip,
        limit=limit
    )

@router.get(
    "/classes/{class_id}/students/{student_id}/sessions/{session_id}/trace-state",
    response_model=TraceStateResponse,
    dependencies=[Depends(require_teacher)],
    summary="[P06-R02] Get trace replay state (Teacher)"
)
def get_teacher_trace_state(
    class_id: uuid.UUID = Path(...),
    student_id: uuid.UUID = Path(...),
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    highest, next_exp = svc.get_teacher_trace_state(db, current_user, class_id, student_id, session_id)
    return TraceStateResponse(
        highest_contiguous_sequence=highest,
        next_expected_sequence=next_exp
    )

from app.schemas.trace import ScratchpadRequest, ScratchpadRevisionResponse, ScratchpadHistoryResponse

@router.get(
    "/my/coding-sessions/{session_id}/scratchpad",
    response_model=ScratchpadRevisionResponse,
    dependencies=[Depends(require_student)],
    summary="[P06-N01] Get current scratchpad (Student)"
)
def get_my_scratchpad(
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rev = svc.get_student_scratchpad(db, current_user, session_id)
    if not rev:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "No scratchpad found"})
    return rev

@router.put(
    "/my/coding-sessions/{session_id}/scratchpad",
    response_model=ScratchpadRevisionResponse,
    dependencies=[Depends(require_student)],
    summary="[P06-N02] Update scratchpad / checkpoint (Student)"
)
def update_my_scratchpad(
    req: ScratchpadRequest,
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return svc.save_student_scratchpad(db, current_user, session_id, req)

@router.get(
    "/classes/{class_id}/students/{student_id}/sessions/{session_id}/scratchpad",
    response_model=ScratchpadRevisionResponse,
    dependencies=[Depends(require_teacher)],
    summary="[P06-N08] View current scratchpad (Teacher)"
)
def get_teacher_scratchpad(
    class_id: uuid.UUID = Path(...),
    student_id: uuid.UUID = Path(...),
    session_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rev = svc.get_teacher_scratchpad(db, current_user, class_id, student_id, session_id)
    if not rev:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "No scratchpad found"})
    return rev

@router.get(
    "/classes/{class_id}/students/{student_id}/sessions/{session_id}/scratchpad/history",
    response_model=ScratchpadHistoryResponse,
    dependencies=[Depends(require_teacher)],
    summary="[P06-N08-History] View scratchpad history (Teacher)"
)
def get_teacher_scratchpad_history(
    class_id: uuid.UUID = Path(...),
    student_id: uuid.UUID = Path(...),
    session_id: uuid.UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items, total = svc.get_teacher_scratchpad_history(db, current_user, class_id, student_id, session_id, skip, limit)
    return ScratchpadHistoryResponse(items=items, total=total)
