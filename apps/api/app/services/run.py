import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.session import CodingSession, SessionStatus
from app.models.run_submit import Run
from app.models.trace import CodeSnapshot
from app.repositories.run import run_repository
from app.services.exam_access import assert_session_writable
from app.services.queue import judge_queue

class RunService:
    def create_run(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID, snapshot_id: uuid.UUID, input_data: Optional[str]) -> Run:
        # Check authorization and session state
        coding_session = db.get(CodingSession, session_id)
        if not coding_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if coding_session.student_id != user_id:
            raise HTTPException(status_code=403, detail="RUN_FORBIDDEN: Cannot create run for another student's session")
            
        if coding_session.status != SessionStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="RUN_SESSION_NOT_ACTIVE: Session is not ACTIVE")

        # docs/38 D8: no runs after the participant's exam deadline
        assert_session_writable(db, coding_session, datetime.now(timezone.utc))

        # Verify snapshot exists and belongs to this session
        snapshot = db.get(CodeSnapshot, snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="RUN_SNAPSHOT_INVALID: Snapshot not found")
            
        if snapshot.session_id != session_id:
            raise HTTPException(status_code=403, detail="RUN_SNAPSHOT_INVALID: Cross-session snapshot rejected")

        # Verify language is supported V1 (CPP17, PYTHON3)
        if snapshot.language not in ("CPP17", "PYTHON3"):
            raise HTTPException(status_code=400, detail="RUN_LANGUAGE_UNSUPPORTED: Only CPP17 and PYTHON3 are supported")

        # 1. Persist Run PENDING first in PostgreSQL
        run = run_repository.create(db, session_id=session_id, snapshot_id=snapshot_id, input_data=input_data)

        # 2. Enqueue Run id
        enqueued = judge_queue.enqueue_run(run.id)
        if not enqueued:
            # Documented recovery behavior: queue delivery failure is harmless because Reconciler will find PENDING runs.
            pass
            
        return run

    def get_run(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID, run_id: uuid.UUID) -> Run:
        coding_session = db.get(CodingSession, session_id)
        if not coding_session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        # Owning student only; teachers read runs through the class-scoped observation API (docs/35 F1)
        if coding_session.student_id != user_id:
            raise HTTPException(status_code=403, detail="RUN_FORBIDDEN: Unauthorized Run read denied")

        run = run_repository.get(db, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
            
        if run.session_id != session_id:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
            
        return run

    def list_runs(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> List[Run]:
        coding_session = db.get(CodingSession, session_id)
        if not coding_session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        # Owning student only; teachers read runs through the class-scoped observation API (docs/35 F1)
        if coding_session.student_id != user_id:
            raise HTTPException(status_code=403, detail="RUN_FORBIDDEN: Unauthorized Run read denied")

        return run_repository.get_by_session(db, session_id)

run_service = RunService()
