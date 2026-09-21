import time
import logging
from app.db.session import SessionLocal
from app.core.config import settings
from app.repositories.run import run_repository
from app.services.queue import judge_queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reconcile():
    logger.info("Reconciler started")
    with SessionLocal() as db:
        stale_runs = run_repository.get_stale_runs(db, settings.JUDGE_STALE_RUN_TIMEOUT_SECONDS)
        for run in stale_runs:
            logger.info(f"Attempting to recover stale run: {run.id} (Status: {run.status})")
            
            # Atomic CAS bump generation
            recovered_run = run_repository.recover_stale_run(db, run.id, run.execution_generation)
            if recovered_run:
                logger.info(f"Successfully claimed stale run {run.id}, re-enqueuing.")
                judge_queue.enqueue_run(recovered_run.id)
            else:
                logger.info(f"Failed to claim stale run {run.id} (already recovered by another process)")

if __name__ == "__main__":
    while True:
        try:
            reconcile()
        except Exception as e:
            logger.error(f"Reconciler error: {e}")
        time.sleep(60) # Run periodically
