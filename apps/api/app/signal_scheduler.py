import logging
import signal
import threading
from datetime import datetime, timezone, timedelta

from app.db.session import SessionLocal
from app.core.config import settings
from app.core import metrics
from app.core.logging import configure_logging
from app.services.judge.materializer import run_cycle, process_outbox_cycle

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
    logger.info("Signal Scheduler started")
    
    while not shutdown_event.is_set():
        try:
            with SessionLocal() as db:
                # 1. Process pending transactional outbox events
                process_outbox_cycle(db)
                # 2. Process active-tail and periodic signals
                since_dt = datetime.now(timezone.utc) - timedelta(
                    seconds=settings.SIGNAL_SCHEDULER_INTERVAL_SECONDS * 2
                )
                run_cycle(db, since_dt)
            metrics.record_cycle("signal_scheduler", ok=True)
        except Exception as e:
            logger.error(f"Scheduler cycle error: {e}")
            metrics.record_cycle("signal_scheduler", ok=False)
            
        # Interruptible sleep: wakes up immediately if shutdown_event is set
        shutdown_event.wait(timeout=settings.SIGNAL_SCHEDULER_INTERVAL_SECONDS)

    logger.info("Signal Scheduler shutdown complete.")

if __name__ == "__main__":
    configure_logging(daemon="signal_scheduler")
    metrics.start_metrics_server()
    run_scheduler_loop()
