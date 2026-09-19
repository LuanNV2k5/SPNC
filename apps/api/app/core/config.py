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



    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")



settings = Settings()
