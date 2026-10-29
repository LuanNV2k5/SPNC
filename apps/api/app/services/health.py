"""Phase 17 — Liveness and readiness (docs/43 §3.3, D4).

Readiness runs the dependency checks in parallel, each bounded by
READY_CHECK_TIMEOUT_SECONDS. Failure detail is logged, never returned.
"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable, Dict

import redis
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.storage import storage_adapter

logger = logging.getLogger(__name__)

_engines = {}


def check_database() -> None:
    url = settings.DATABASE_URL
    if url not in _engines:
        # Own one-connection pool: a probe must not wait for, or exhaust, the request pool,
        # and frequent probes reuse one connection instead of opening a new one each time
        t = settings.READY_CHECK_TIMEOUT_SECONDS
        _engines[url] = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=t, pool_pre_ping=True,
                                      connect_args={"connect_timeout": max(1, math.ceil(t))})
    with _engines[url].connect() as conn:
        conn.execute(text("SELECT 1"))


def check_redis() -> None:
    t = settings.READY_CHECK_TIMEOUT_SECONDS
    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=t, socket_timeout=t)
    try:
        client.ping()
    finally:
        client.close()


def check_storage() -> None:
    storage_adapter.ping()


CHECKS: Dict[str, Callable[[], None]] = {"database": check_database, "redis": check_redis, "storage": check_storage}


def readiness() -> Dict[str, str]:
    """Returns {check: "ok" | "fail"} for every dependency."""
    pool = ThreadPoolExecutor(max_workers=len(CHECKS))
    try:
        futures = {name: pool.submit(fn) for name, fn in CHECKS.items()}
        results = {}
        for name, future in futures.items():
            try:
                future.result(timeout=settings.READY_CHECK_TIMEOUT_SECONDS)
                results[name] = "ok"
            except FutureTimeout:
                logger.warning(f"Readiness check {name} timed out")
                results[name] = "fail"
            except Exception as e:
                logger.warning(f"Readiness check {name} failed: {type(e).__name__}: {e}")
                results[name] = "fail"
        return results
    finally:
        pool.shutdown(wait=False)
