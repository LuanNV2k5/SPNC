import time
import logging
from datetime import datetime, timezone, timedelta

from app.db.session import SessionLocal
from app.core.config import settings
from app.services.judge.materializer import run_cycle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_scheduler_loop():
    logger.info("Signal Scheduler started")
    
    while True:
        try:
            with SessionLocal() as db:
                # We check a bit further back to safely overlap polling cycles
                since_dt = datetime.now(timezone.utc) - timedelta(seconds=settings.SIGNAL_SCHEDULER_INTERVAL_SECONDS * 2)
                run_cycle(db, since_dt)
        except Exception as e:
            logger.error(f"Scheduler cycle error: {e}")
            
        time.sleep(settings.SIGNAL_SCHEDULER_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_scheduler_loop()
