import time
import logging
from app.db.session import SessionLocal
from app.core.config import settings
from app.repositories.run import run_repository
from app.services.queue import judge_queue
from app.services.submission import recover_stale_submissions
from app.services.snapshot_cleanup import sweep_orphans

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_last_orphan_sweep = 0.0


def maybe_sweep_orphans(db, clock=time.monotonic):
    """At most once per SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS (docs/39 D2)."""
    global _last_orphan_sweep
    if clock() - _last_orphan_sweep < settings.SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS and _last_orphan_sweep:
        return None
    _last_orphan_sweep = clock()
    return sweep_orphans(db)


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

        # Phase 10A: same sweep for submission jobs
        recover_stale_submissions(db, settings.JUDGE_STALE_SUBMISSION_TIMEOUT_SECONDS)

        # Phase 13A: orphan snapshot blobs (ADR-007)
        maybe_sweep_orphans(db)

if __name__ == "__main__":
    while True:
        try:
            reconcile()
        except Exception as e:
            logger.error(f"Reconciler error: {e}")
        time.sleep(60) # Run periodically
