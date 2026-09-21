import json
import time
import uuid
import logging
from app.db.session import SessionLocal
from app.core.config import settings
from app.models.run_submit import RunStatus
from app.models.trace import CodeSnapshot
from app.repositories.run import run_repository
from app.services.judge.adapters import ADAPTERS
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            if not item:
                continue
            
            queue_name, message_data = item
            message = json.loads(message_data)
            run_id_str = message.get("run_id")
            
            if not run_id_str:
                continue
                
            run_id = uuid.UUID(run_id_str)
            
            # Database Session
            with SessionLocal() as db:
                # 1. Atomic Claim (PENDING -> RUNNING)
                run = run_repository.claim_run_for_execution(db, run_id)
                if not run:
                    logger.info(f"Worker skipped run {run_id}, either not PENDING or CAS failed.")
                    continue
                    
                execution_generation = run.execution_generation
                
                # 2. Fetch immutable snapshot
                snapshot = db.get(CodeSnapshot, run.snapshot_id)
                if not snapshot:
                    logger.error(f"Run {run_id} missing snapshot {run.snapshot_id}")
                    # Write failure
                    run_repository.write_result(
                        db, run_id, execution_generation,
                        status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
                        time_ms=0, memory_kb=0,
                        testcase_results={"stderr": "Snapshot not found"}
                    )
                    continue

                adapter = ADAPTERS.get(snapshot.language)
                if not adapter:
                    run_repository.write_result(
                        db, run_id, execution_generation,
                        status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
                        time_ms=0, memory_kb=0,
                        testcase_results={"stderr": f"Unsupported language: {snapshot.language}"}
                    )
                    continue

                input_data = run.testcase_results.get("input") if run.testcase_results else None
                
                # 3. Execute Sandbox
                try:
                    result_dict = adapter.execute(snapshot.source_code, input_data)
                    
                    # Update testcase_results preserving existing input
                    tc_res = run.testcase_results or {}
                    tc_res.update({
                        "stdout": result_dict["stdout"],
                        "stderr": result_dict["stderr"],
                        "compile_error_message": result_dict["compile_error_message"],
                        "runtime_error_message": result_dict["runtime_error_message"]
                    })
                    
                    # 4. Save result via CAS
                    run_repository.write_result(
                        db, run_id, execution_generation,
                        status=RunStatus.COMPLETED,
                        verdict=result_dict["verdict"],
                        time_ms=result_dict["time_ms"],
                        memory_kb=result_dict["memory_kb"],
                        testcase_results=tc_res
                    )
                    
                except Exception as e:
                    logger.exception(f"Unhandled error processing run {run_id}")
                    run_repository.write_result(
                        db, run_id, execution_generation,
                        status=RunStatus.FAILED_INTERNAL, verdict="INTERNAL_ERROR",
                        time_ms=0, memory_kb=0,
                        testcase_results={"stderr": str(e)}
                    )

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    process_queue()
