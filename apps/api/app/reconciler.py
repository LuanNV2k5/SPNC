import time
import logging
from app.db.session import SessionLocal
from app.core import metrics
from app.core.config import settings
from app.core.logging import configure_logging
from app.repositories.run import run_repository
from app.services.queue import judge_queue
from app.services.submission import recover_stale_submissions
from app.services.snapshot_cleanup import sweep_orphans
from app.services.retention import purge as retention_purge

logger = logging.getLogger(__name__)

_last_orphan_sweep = 0.0
_last_retention_purge = 0.0


def maybe_sweep_orphans(db, clock=time.monotonic):
    """At most once per SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS (docs/39 D2)."""
    global _last_orphan_sweep
    if clock() - _last_orphan_sweep < settings.SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS and _last_orphan_sweep:
        return None
    _last_orphan_sweep = clock()
    return sweep_orphans(db)


def maybe_purge_retention(db, clock=time.monotonic):
    """docs/45 D3: off unless RETENTION_PURGE_ENABLED; at most once per RETENTION_PURGE_INTERVAL_SECONDS."""
    global _last_retention_purge
    if not settings.RETENTION_PURGE_ENABLED:
        return None
    if clock() - _last_retention_purge < settings.RETENTION_PURGE_INTERVAL_SECONDS and _last_retention_purge:
        return None
    _last_retention_purge = clock()
    return retention_purge(db, apply=True)


def reconcile():
    logger.info("Reconciler started")
    with SessionLocal() as db:
        stale_runs = run_repository.get_stale_runs(db, settings.JUDGE_STALE_RUN_TIMEOUT_SECONDS)
        for run in stale_runs:
            logger.info(f"Attempting to recover stale run: {run.id} (Status: {run.status})", extra={"run_id": run.id})

            # Atomic CAS bump generation
            recovered_run = run_repository.recover_stale_run(db, run.id, run.execution_generation)
            if recovered_run:
                logger.info(f"Successfully claimed stale run {run.id}, re-enqueuing.", extra={"run_id": run.id})
                judge_queue.enqueue_run(recovered_run.id)
                metrics.REENQUEUES.labels(kind="run").inc()
            else:
                logger.info(f"Failed to claim stale run {run.id} (already recovered by another process)", extra={"run_id": run.id})

        # Phase 10A: same sweep for submission jobs
        recover_stale_submissions(db, settings.JUDGE_STALE_SUBMISSION_TIMEOUT_SECONDS)

        # Phase 13A: orphan snapshot blobs (ADR-007)
        maybe_sweep_orphans(db)

        # Phase 19: retention purge of raw trace (docs/45)
        maybe_purge_retention(db)

    # docs/43 §3.1: backlog gauge, refreshed every cycle
    depth = judge_queue.depth()
    if depth is not None:
        metrics.JUDGE_QUEUE_DEPTH.set(depth)

if __name__ == "__main__":
    configure_logging(daemon="reconciler")
    metrics.start_metrics_server()
    while True:
        try:
            reconcile()
            metrics.record_cycle("reconciler", ok=True)
        except Exception as e:
            logger.error(f"Reconciler error: {e}")
            metrics.record_cycle("reconciler", ok=False)
        time.sleep(60) # Run periodically
