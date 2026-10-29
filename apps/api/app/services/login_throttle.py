"""Phase 15A — Login brute-force throttling (OQ-02 resolved by docs/41 R1).

Per username + client IP: LOGIN_MAX_FAILURES failed logins within LOGIN_WINDOW_SECONDS
block further attempts (429) for LOGIN_WINDOW_SECONDS from the last counted failure.
No account lockout (an attacker cannot lock real users out). A successful login resets it.

Backends: "memory" (per process; dev and tests) or "redis" (shared across API processes;
compose and production). If Redis is unreachable the check fails open and logs a warning,
so an outage never blocks every login.
"""
import logging
import threading
import time
from typing import Dict, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


def _key(username: str, ip: str) -> str:
    return f"login_fail:{(username or '').strip().lower()}|{ip or '-'}"


class _MemoryBackend:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Tuple[int, float]] = {}   # key -> (failures, expires_at)

    def _live(self, key: str, now: float) -> int:
        count, expires = self._data.get(key, (0, 0.0))
        if expires <= now:
            self._data.pop(key, None)
            return 0
        return count

    def failures(self, key: str) -> int:
        with self._lock:
            return self._live(key, time.monotonic())

    def add_failure(self, key: str, window: int) -> int:
        with self._lock:
            now = time.monotonic()
            count = self._live(key, now) + 1
            self._data[key] = (count, now + window)
            return count

    def reset(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class _RedisBackend:
    def __init__(self):
        import redis
        self._client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                            socket_connect_timeout=1, socket_timeout=1)

    def failures(self, key: str) -> int:
        return int(self._client.get(key) or 0)

    def add_failure(self, key: str, window: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = pipe.execute()
        return int(count)

    def reset(self, key: str) -> None:
        self._client.delete(key)


class LoginThrottle:
    def __init__(self):
        self._backend = None

    def backend(self):
        if self._backend is None:
            self._backend = _RedisBackend() if settings.LOGIN_THROTTLE_BACKEND == "redis" else _MemoryBackend()
        return self._backend

    def is_blocked(self, username: str, ip: str) -> bool:
        try:
            return self.backend().failures(_key(username, ip)) >= settings.LOGIN_MAX_FAILURES
        except Exception as e:
            logger.warning(f"Login throttle unavailable, failing open: {e}")
            return False

    def record_failure(self, username: str, ip: str) -> None:
        try:
            self.backend().add_failure(_key(username, ip), settings.LOGIN_WINDOW_SECONDS)
        except Exception as e:
            logger.warning(f"Login throttle unavailable, failure not counted: {e}")

    def reset(self, username: str, ip: str) -> None:
        try:
            self.backend().reset(_key(username, ip))
        except Exception as e:
            logger.warning(f"Login throttle unavailable, reset skipped: {e}")


login_throttle = LoginThrottle()
