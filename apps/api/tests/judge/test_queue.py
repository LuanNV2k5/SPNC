"""Phase 07 — Judge Queue & Reconciler Test Suite."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime
from app.services.queue import judge_queue
import redis
from app.core.config import settings

PHASE07_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase07_judge_test")
engine = create_engine(PHASE07_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.models.run_submit import Run, RunStatus
from app.repositories.run import run_repository

@pytest.fixture(autouse=True)
def clear_db():
    db = TestingSessionLocal()
    for table in reversed(Run.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    # db.close()
    
    r = redis.Redis.from_url(settings.REDIS_URL)
    r.delete("judge_queue")

def setup_run(status=RunStatus.PENDING):
    db = TestingSessionLocal()
    from tests.api.test_run import create_user, create_session, create_snapshot
    user = create_user(db)
    sess = create_session(db, user.id)
    snap = create_snapshot(db, sess.id)
    run = run_repository.create(db, session_id=sess.id, snapshot_id=snap.id)
    
    if status != RunStatus.PENDING:
        run.status = status
        db.commit()
        db.refresh(run)
        
    # db.close()
    return run.id

# Q01 enqueued job delivery
def test_Q01_enqueued_job_delivery():
    run_id = setup_run()
    judge_queue.enqueue_run(run_id)
    
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    item = r.rpop("judge_queue")
    assert item is not None
    assert str(run_id) in item

# Q02 Reconciler identifies stale RUNNING
def test_Q02_reconciler_stale_running():
    run_id = setup_run(RunStatus.RUNNING)
    db = TestingSessionLocal()
    
    # Manually make it stale
    from sqlalchemy import update
    stmt = update(Run).where(Run.id == run_id).values(updated_at=datetime.datetime(2000, 1, 1))
    db.execute(stmt)
    db.commit()
    
    stale = run_repository.get_stale_runs(db, 300)
    assert len(stale) == 1
    assert stale[0].id == run_id
    # db.close()

# Q03 Reconciler identifies stale PENDING (dropped queue msg)
def test_Q03_reconciler_stale_pending():
    run_id = setup_run(RunStatus.PENDING)
    db = TestingSessionLocal()
    
    from sqlalchemy import update
    stmt = update(Run).where(Run.id == run_id).values(updated_at=datetime.datetime(2000, 1, 1))
    db.execute(stmt)
    db.commit()
    
    stale = run_repository.get_stale_runs(db, 300)
    assert len(stale) == 1
    assert stale[0].id == run_id
    # db.close()

# Q04 Reconciler ignores fresh RUNNING
def test_Q04_reconciler_ignores_fresh_running():
    run_id = setup_run(RunStatus.RUNNING)
    db = TestingSessionLocal()
    
    stale = run_repository.get_stale_runs(db, 300)
    assert len(stale) == 0
    # db.close()

# Q05 Reconciler ignores COMPLETED
def test_Q05_reconciler_ignores_completed():
    run_id = setup_run(RunStatus.COMPLETED)
    db = TestingSessionLocal()
    
    from sqlalchemy import update
    stmt = update(Run).where(Run.id == run_id).values(updated_at=datetime.datetime(2000, 1, 1))
    db.execute(stmt)
    db.commit()
    
    stale = run_repository.get_stale_runs(db, 300)
    assert len(stale) == 0
    # db.close()

# Q06 Reconciler pushes to queue
def test_Q06_reconciler_pushes_to_queue():
    run_id = setup_run(RunStatus.RUNNING)
    db = TestingSessionLocal()
    
    from sqlalchemy import update
    stmt = update(Run).where(Run.id == run_id).values(updated_at=datetime.datetime(2000, 1, 1))
    db.execute(stmt)
    db.commit()
    
    # Run reconciler manually
    from app.reconciler import reconcile
    reconcile()
    
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    item = r.rpop("judge_queue")
    assert item is not None
    assert str(run_id) in item
    
    # Verify DB state
    run = run_repository.get(db, run_id)
    assert run.status == RunStatus.PENDING
    assert run.execution_generation == 1
    # db.close()
