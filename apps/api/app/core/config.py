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



    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")



settings = Settings()
