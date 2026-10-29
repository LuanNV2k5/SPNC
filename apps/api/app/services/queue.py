import json
import logging
import uuid
from typing import Optional

import redis
from app.core import metrics
from app.core.config import settings

logger = logging.getLogger(__name__)

class JudgeQueue:
    def __init__(self):
        self.redis_client = None

    def connect(self):
        if self.redis_client is None:
            self.redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def enqueue_run(self, run_id: uuid.UUID):
        self.connect()
        try:
            message = {"run_id": str(run_id)}
            self.redis_client.lpush("judge_queue", json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue run {run_id}: {e}", extra={"run_id": run_id})
            metrics.ENQUEUE_FAILURES.labels(kind="run").inc()
            return False

    def enqueue_submission(self, submission_id: uuid.UUID):
        self.connect()
        try:
            message = {"kind": "submission", "submission_id": str(submission_id)}
            self.redis_client.lpush("judge_queue", json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue submission {submission_id}: {e}", extra={"submission_id": submission_id})
            metrics.ENQUEUE_FAILURES.labels(kind="submission").inc()
            return False

    def depth(self) -> Optional[int]:
        """Jobs waiting (LLEN); None when Redis cannot answer."""
        self.connect()
        try:
            return int(self.redis_client.llen("judge_queue"))
        except Exception as e:
            logger.warning(f"Cannot read judge queue depth: {e}")
            return None

judge_queue = JudgeQueue()
