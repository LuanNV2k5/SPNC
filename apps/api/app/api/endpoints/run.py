import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.run import RunCreate, RunResponse
from app.services.run import run_service

router = APIRouter()

@router.post("/{session_id}/runs", response_model=RunResponse)
def create_run(
    session_id: uuid.UUID,
    run_in: RunCreate,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """
    Submit a Run for execution in the isolated Sandbox.
    """
    return run_service.create_run(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        snapshot_id=run_in.snapshot_id,
        input_data=run_in.input
    )

@router.get("/{session_id}/runs", response_model=List[RunResponse])
def list_runs(
    session_id: uuid.UUID,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """
    List runs for a coding session.
    """
    return run_service.list_runs(
        db=db,
        user_id=current_user.id,
        session_id=session_id
    )

@router.get("/{session_id}/runs/{run_id}", response_model=RunResponse)
def get_run(
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """
    Get a specific run.
    """
    return run_service.get_run(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        run_id=run_id
    )
