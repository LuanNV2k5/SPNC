"""Phase 10B — Exam scheduler daemon (docs/36 D10). 30 s tick, idempotent, row-locked."""
import logging
import signal
import threading

from app.db.session import SessionLocal
from app.core.config import settings
from app.services.exam_lifecycle import run_tick
from app.services.session_lifecycle import abandon_stale_practice_sessions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

shutdown_event = threading.Event()

def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()

try:
    signal.signal(signal.SIGINT, handle_shutdown)
except (ValueError, AttributeError):
    pass

try:
    signal.signal(signal.SIGTERM, handle_shutdown)
except (ValueError, AttributeError):
    pass

def run_scheduler_loop():
    logger.info("Exam Scheduler started")

    while not shutdown_event.is_set():
        try:
            with SessionLocal() as db:
                result = run_tick(db)
                if result["started"] or result["ended"]:
                    logger.info(f"Exam tick: started={result['started']} ended={result['ended']} "
                                f"auto_submissions={len(result['auto_submissions'])}")
        except Exception as e:
            logger.error(f"Exam scheduler tick error: {e}")
        try:
            with SessionLocal() as db:
                abandoned = abandon_stale_practice_sessions(db)   # docs/41 R5
                if abandoned:
                    logger.info(f"Stale practice sessions abandoned: {len(abandoned)}")
        except Exception as e:
            logger.error(f"Stale session sweep error: {e}")

        # Interruptible sleep: wakes up immediately if shutdown_event is set
        shutdown_event.wait(timeout=settings.EXAM_SCHEDULER_INTERVAL_SECONDS)

    logger.info("Exam Scheduler shutdown complete.")

if __name__ == "__main__":
    run_scheduler_loop()
