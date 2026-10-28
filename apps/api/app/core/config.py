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

    # Teacher notification WebSocket (docs/35 09C)
    WS_AUTH_TIMEOUT_SECONDS: float = 5.0

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")



settings = Settings()
