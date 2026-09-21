import json
import uuid
import redis
from app.core.config import settings

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
            print(f"Failed to enqueue run {run_id}: {e}")
            return False

judge_queue = JudgeQueue()
