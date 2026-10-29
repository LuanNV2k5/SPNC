from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import AnyHttpUrl

from typing import List, Optional, Union



class Settings(BaseSettings):

    PROJECT_NAME: str = "SPNC"

    API_V1_STR: str = "/api/v1"



    # DB

    DATABASE_URL: str

    TEST_DATABASE_URL: str = ""



    # Security

    SECRET_KEY: str = "unsafe-default-secret-key-change-in-production"

    ALGORITHM: str = "HS256"

from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import AnyHttpUrl

from typing import List, Union



class Settings(BaseSettings):

    PROJECT_NAME: str = "SPNC"

    API_V1_STR: str = "/api/v1"



    # DB

    DATABASE_URL: str

    TEST_DATABASE_URL: str = ""



    # Security

    SECRET_KEY: str = "unsafe-default-secret-key-change-in-production"

    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days



    # Judge Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    JUDGE_STALE_RUN_TIMEOUT_SECONDS: int = 300
    JUDGE_MEMORY_LIMIT_MB: int = 256
    JUDGE_CPU_QUOTA: int = 100000
    JUDGE_WALL_TIME_LIMIT_SECONDS: int = 5
    JUDGE_PIDS_LIMIT: int = 64
    JUDGE_OUTPUT_LIMIT_BYTES: int = 1048576  # 1MB
    JUDGE_TEMP_DIR: str = "/tmp/spnc_judge"
    # docs/40 Q4 (OQ-26): container runtime for sandboxes, e.g. "runsc" (gVisor) on judge hosts; empty = default
    JUDGE_CONTAINER_RUNTIME: str = ""
    # docs/36 D12: measured run time includes interpreter start inside the container
    JUDGE_STARTUP_ALLOWANCE_MS: int = 500
    # Submissions stuck in PENDING/RUNNING longer than this are re-queued by the reconciler
    JUDGE_STALE_SUBMISSION_TIMEOUT_SECONDS: int = 600

    # Judge Signals
    SIGNAL_RULE_VERSION: str = "1.1.0"  # 1.1.0: LOC_ANOMALY final_loc after finalization (docs/34 D7)
    SIGNAL_IDLE_THRESHOLD_SECONDS: int = 300
    SIGNAL_FAST_FIRST_CODE_THRESHOLD_SECONDS: int = 30
    SIGNAL_REPEATED_FAILURE_MIN_ATTEMPTS: int = 3
    SIGNAL_REPEATED_FAILURE_MAX_CODE_CHANGE_RATIO: float = 0.1
    SIGNAL_LOC_MIN_COHORT_SIZE: int = 3
    SIGNAL_LOC_DEVIATION_MULTIPLIER: float = 2.0

    # Signal Scheduler
    SIGNAL_SCHEDULER_INTERVAL_SECONDS: int = 60
    SIGNAL_SCHEDULER_BATCH_SIZE: int = 100
    # Phase 10B exam scheduler tick (docs/36 D10; REQ-EXAM-003 needs <= 60 s)
    EXAM_SCHEDULER_INTERVAL_SECONDS: int = 30

    # Snapshot storage (docs/37 D1/D2): "memory" (per process, tests/dev) or "s3" (MinIO/S3)
    STORAGE_BACKEND: str = "memory"
    S3_ENDPOINT: str = "localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "spnc-snapshots"
    S3_SECURE: bool = False
    S3_REGION: Optional[str] = None
    S3_CONNECT_TIMEOUT_SECONDS: float = 2.0
    S3_READ_TIMEOUT_SECONDS: float = 10.0
    S3_MAX_RETRIES: int = 2
    # Orphan-blob cleanup (ADR-007, docs/39 D2)
    SNAPSHOT_ORPHAN_GRACE_HOURS: int = 24
    SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS: int = 3600
    SNAPSHOT_ORPHAN_BATCH_SIZE: int = 500

    # REQ-TRACE-013, docs/39 D4: cadence clients should follow for CHECKPOINT snapshots
    TRACE_CHECKPOINT_INTERVAL_SECONDS: int = 60

    # Teacher notification WebSocket (docs/35 09C)
    WS_AUTH_TIMEOUT_SECONDS: float = 5.0

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")



settings = Settings()
