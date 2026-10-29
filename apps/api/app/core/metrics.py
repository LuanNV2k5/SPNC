"""Phase 17 — Prometheus metrics (docs/43 §3.1, docs/07 §4).

Every metric is defined here; services import the object instead of creating their own.
Labels are bounded enumerations only (docs/43 §4.2): never ids, raw paths or free text.
Each process serves its own registry on an internal port (docs/43 D3/D5).
"""
import logging
import time

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from app.core.config import settings

logger = logging.getLogger(__name__)

# -- HTTP ----------------------------------------------------------------------
HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests by route template", ["method", "route", "status"])
HTTP_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "route"])

# -- Trace (docs/07 §4.1) --------------------------------------------------------
TRACE_BATCHES = Counter("trace_ingest_batch_total", "Trace batches by outcome (accepted/duplicate/rejected)", ["outcome"])
TRACE_BATCH_REJECTED = Counter("trace_ingest_batch_rejected_total", "Trace batches rejected")
TRACE_CONFLICTS = Counter("trace_conflicting_duplicate_total", "Sequence numbers re-sent with different content")
TRACE_RETRIES = Counter("trace_batch_retry_total", "Batches whose events were all stored already (client retry)")
TRACE_LATENCY = Histogram("trace_ingest_latency_seconds", "Trace batch processing time")

# -- Run / judge (docs/07 §4.2); kind = run | submission ---------------------------
JUDGE_QUEUE_DEPTH = Gauge("judge_queue_depth", "Jobs waiting in the Redis judge queue")
CLAIM_CONFLICTS = Counter("run_claim_conflict_total", "Job deliveries that lost the atomic claim", ["kind"])
FENCING_REJECTIONS = Counter("run_fencing_rejection_total", "Results rejected by execution_generation fencing", ["kind"])
REENQUEUES = Counter("run_reenqueue_total", "Stale jobs recovered and re-enqueued by the reconciler", ["kind"])
JUDGE_DURATION = Histogram("judge_execution_duration_seconds", "Sandbox execution / grading time", ["kind"],
                           buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120))
JUDGE_FAILURES = Counter("judge_worker_failure_total", "Jobs finished as FAILED_INTERNAL", ["kind"])
ENQUEUE_FAILURES = Counter("judge_enqueue_failure_total", "Jobs that could not be pushed to Redis", ["kind"])

# -- Snapshot storage (docs/07 §4.3) ---------------------------------------------
SNAPSHOT_UPLOAD_FAILURES = Counter("snapshot_upload_failure_total", "Snapshot uploads that failed on storage")
SNAPSHOT_BLOB_MISSING = Counter("snapshot_blob_missing_total", "Snapshot metadata whose blob is absent", ["reader"])
ORPHANS_DETECTED = Counter("snapshot_orphan_detected_total", "Unreferenced snapshot blobs past the grace period")
ORPHANS_CLEANED = Counter("snapshot_orphan_cleanup_total", "Orphan snapshot blobs deleted")
ORPHAN_CLEANUP_FAILURES = Counter("snapshot_orphan_cleanup_failure_total", "Orphan sweep or delete failures")

# -- Retention purge (docs/45 §3.7) ----------------------------------------------
RETENTION_ROWS = Counter("retention_purge_rows_total", "Rows deleted by the retention purge", ["data_class"])
RETENTION_SESSIONS = Counter("retention_purge_sessions_total", "Sessions handled by the retention purge", ["outcome"])
RETENTION_BLOB_DELETES = Counter("retention_purge_blob_delete_total", "Snapshot blob deletes after a purge", ["outcome"])
RETENTION_ELIGIBLE = Gauge("retention_purge_eligible_sessions", "Sessions eligible for purge at the last run")

# -- Realtime (docs/07 §4.4) -----------------------------------------------------
WS_ACTIVE = Gauge("websocket_active_connections", "Authenticated teacher WebSocket connections")
WS_AUTH_REJECTIONS = Counter("websocket_auth_rejection_total", "WebSocket connections closed during auth", ["reason"])

# -- Daemons ---------------------------------------------------------------------
DAEMON_CYCLES = Counter("spnc_daemon_cycles_total", "Daemon loop iterations by outcome", ["daemon", "outcome"])
DAEMON_LAST_SUCCESS = Gauge("spnc_daemon_last_success_timestamp_seconds", "Unix time of the last successful cycle", ["daemon"])


def record_cycle(daemon: str, ok: bool) -> None:
    DAEMON_CYCLES.labels(daemon=daemon, outcome="ok" if ok else "error").inc()
    if ok:
        DAEMON_LAST_SUCCESS.labels(daemon=daemon).set(time.time())


def start_metrics_server(port: int = None) -> bool:
    """Serves this process's registry on the internal metrics port; 0 disables (docs/43 §3.2).
    A port clash is logged, never fatal: metrics must not stop the process."""
    port = settings.METRICS_PORT if port is None else port
    if not port:
        return False
    try:
        start_http_server(port)
    except OSError as e:
        logger.warning(f"Metrics listener not started on port {port}: {e}")
        return False
    logger.info(f"Metrics listener on port {port}")
    return True
