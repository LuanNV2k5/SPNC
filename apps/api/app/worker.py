import json
import time
import uuid
import logging
from app.db.session import SessionLocal
from app.core import metrics
from app.core.config import settings
from app.core.logging import configure_logging
from app.models.run_submit import RunStatus
from app.models.trace import CodeSnapshot
from app.repositories.run import run_repository
from app.services.judge.adapters import ADAPTERS
from app.services.storage import StorageUnavailable, storage_adapter
from app.services.submission import judge_submission
import redis

logger = logging.getLogger(__name__)


def _write(db, run_id, execution_generation, status, verdict, time_ms, memory_kb, testcase_results) -> bool:
    """Fenced result write; counts failures and stale-generation rejections (docs/43 §3.1)."""
    if status == RunStatus.FAILED_INTERNAL:
        metrics.JUDGE_FAILURES.labels(kind="run").inc()
    written = run_repository.write_result(db, run_id, execution_generation, status=status, verdict=verdict,
                                          time_ms=time_ms, memory_kb=memory_kb, testcase_results=testcase_results)
    if not written:
        metrics.FENCING_REJECTIONS.labels(kind="run").inc()
        logger.info(f"Stale result for run {run_id} generation {execution_generation} rejected",
                    extra={"run_id": run_id, "execution_generation": execution_generation})
    return written


def process_run(db, run_id: uuid.UUID):
    # 1. Atomic Claim (PENDING -> RUNNING)
    run = run_repository.claim_run_for_execution(db, run_id)
    if not run:
        logger.info(f"Worker skipped run {run_id}, either not PENDING or CAS failed.", extra={"run_id": run_id})
        metrics.CLAIM_CONFLICTS.labels(kind="run").inc()
        return

    execution_generation = run.execution_generation

    # 2. Fetch immutable snapshot
    snapshot = db.get(CodeSnapshot, run.snapshot_id)
    if not snapshot:
        logger.error(f"Run {run_id} missing snapshot {run.snapshot_id}", extra={"run_id": run_id})
        # Write failure
        _write(
            db, run_id, execution_generation,
            status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
            time_ms=0, memory_kb=0,
            testcase_results={"stderr": "Snapshot not found"}
        )
        return

    adapter = ADAPTERS.get(snapshot.language)
    if not adapter:
        _write(
            db, run_id, execution_generation,
            status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
            time_ms=0, memory_kb=0,
            testcase_results={"stderr": f"Unsupported language: {snapshot.language}"}
        )
        return

    # Snapshot content lives in storage, keyed by object_key (never fabricate empty source)
    try:
        available = storage_adapter.exists_code_snapshot(snapshot.object_key)
        source_code = storage_adapter.download_code_snapshot(snapshot.object_key) if available else None
        if not available:
            metrics.SNAPSHOT_BLOB_MISSING.labels(reader="worker_run").inc()
    except StorageUnavailable:
        source_code = None
    if source_code is None:
        _write(
            db, run_id, execution_generation,
            status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
            time_ms=0, memory_kb=0,
            testcase_results={"stderr": "Snapshot content unavailable"}
        )
        return

    input_data = run.testcase_results.get("input") if run.testcase_results else None

    # 3. Execute Sandbox
    try:
        with metrics.JUDGE_DURATION.labels(kind="run").time():
            result_dict = adapter.execute(source_code, input_data)

        # Update testcase_results preserving existing input
        tc_res = run.testcase_results or {}
        tc_res.update({
            "stdout": result_dict["stdout"],
            "stderr": result_dict["stderr"],
            "compile_error_message": result_dict["compile_error_message"],
            "runtime_error_message": result_dict["runtime_error_message"]
        })

        # 4. Save result via CAS
        _write(
            db, run_id, execution_generation,
            status=RunStatus.COMPLETED,
            verdict=result_dict["verdict"],
            time_ms=result_dict["time_ms"],
            memory_kb=result_dict["memory_kb"],
            testcase_results=tc_res
        )

    except Exception as e:
        logger.exception(f"Unhandled error processing run {run_id}", extra={"run_id": run_id})
        _write(
            db, run_id, execution_generation,
            status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
            time_ms=0, memory_kb=0,
            testcase_results={"stderr": str(e)}
        )


def handle_message(message: dict):
    """Dispatch by kind; messages without a kind are Phase 07 Runs ({"run_id": ...})."""
    if message.get("kind") == "submission":
        submission_id_str = message.get("submission_id")
        if not submission_id_str:
            return
        with SessionLocal() as db:
            judge_submission(db, uuid.UUID(submission_id_str))
        return

    run_id_str = message.get("run_id")
    if not run_id_str:
        return
    with SessionLocal() as db:
        process_run(db, uuid.UUID(run_id_str))


def process_queue():
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    logger.info("Worker started, waiting for jobs...")
    while True:
        try:
            # Blocking pop from the queue
            item = r.brpop("judge_queue", timeout=5)
            if item:
                queue_name, message_data = item
                handle_message(json.loads(message_data))
            # Every iteration, idle ones too, so last_success doubles as a heartbeat (docs/43 §3.3)
            metrics.record_cycle("worker", ok=True)

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            metrics.record_cycle("worker", ok=False)
            time.sleep(1)

if __name__ == "__main__":
    configure_logging(daemon="worker")
    metrics.start_metrics_server()
    process_queue()
