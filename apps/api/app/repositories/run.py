import uuid
from typing import List, Optional
from sqlalchemy import update, select
from sqlalchemy.orm import Session
from app.models.run_submit import Run, RunStatus

class RunRepository:
    def create(self, db: Session, *, session_id: uuid.UUID, snapshot_id: uuid.UUID, input_data: Optional[str] = None) -> Run:
        testcase_results = {}
        if input_data is not None:
            testcase_results["input"] = input_data

        db_obj = Run(
            session_id=session_id,
            snapshot_id=snapshot_id,
            status=RunStatus.PENDING,
            testcase_results=testcase_results
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, run_id: uuid.UUID) -> Optional[Run]:
        return db.scalars(select(Run).where(Run.id == run_id)).first()

    def get_by_session(self, db: Session, session_id: uuid.UUID) -> List[Run]:
        return list(db.scalars(
            select(Run).where(Run.session_id == session_id).order_by(Run.created_at.desc())
        ).all())

    def claim_run_for_execution(self, db: Session, run_id: uuid.UUID) -> Optional[Run]:
        """
        Atomic claim of a PENDING run using CAS-like update of execution_generation.
        """
        run = self.get(db, run_id)
        if not run:
            return None
            
        if run.status != RunStatus.PENDING:
            return None

        # Attempt atomic update
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .where(Run.status == RunStatus.PENDING)
            .where(Run.execution_generation == run.execution_generation)
            .values(
                status=RunStatus.RUNNING,
                execution_generation=Run.execution_generation + 1
            )
        )
        result = db.execute(stmt)
        if result.rowcount == 0:
            return None # CAS failed

        db.commit()
        return self.get(db, run_id)

    def write_result(self, db: Session, run_id: uuid.UUID, execution_generation: int, status: RunStatus, verdict: str, time_ms: int, memory_kb: int, testcase_results: dict) -> bool:
        """
        Atomic write of the execution result using execution_generation fencing.
        """
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .where(Run.execution_generation == execution_generation)
            .values(
                status=status,
                verdict=verdict,
                execution_time_ms=time_ms,
                execution_memory_kb=memory_kb,
                testcase_results=testcase_results
            )
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount > 0

    def get_stale_runs(self, db: Session, threshold_seconds: int) -> List[Run]:
        """
        For the Reconciler: find runs that are RUNNING or PENDING but haven't been updated recently.
        Since we only have created_at/updated_at, we can use updated_at.
        """
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
        
        return list(db.scalars(
            select(Run)
            .where(Run.status.in_([RunStatus.PENDING, RunStatus.RUNNING]))
            .where(Run.updated_at < cutoff)
        ).all())

    def recover_stale_run(self, db: Session, run_id: uuid.UUID, expected_generation: int) -> Optional[Run]:
        """
        Reclaim a stale run for retry.
        """
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .where(Run.execution_generation == expected_generation)
            .values(
                status=RunStatus.PENDING,
                execution_generation=Run.execution_generation + 1
            )
        )
        result = db.execute(stmt)
        if result.rowcount == 0:
            return None
            
        db.commit()
        return self.get(db, run_id)

run_repository = RunRepository()
